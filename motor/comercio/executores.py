"""O Motor / comercio — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import (fisica, intencoes, io, itens, memoria, percepcao, registro, rolagem, trabalho)
from ..fisica import (
    HAND_SLOT,
    _direct_items,
    _walk_open_items,
    carried_weight,
    carry_capacity,
    check_carga_livre,
    check_encaixe,
    check_mao,
    check_vaga,
    effective_weight,
    grasp_slot_of,
    is_closed,
    is_currency,
    is_down,
    is_for_sale,
    is_negotiable,
    item_size,
    slot_capacity,
    slots_in_use,
    total_value,
    value_of,
)
from ..io import (
    _char_fm,
    _fail,
    _is_valid,
    _rejection,
    find_character_folder,
    read_doc,
    write_doc,
)
from ..itens import (
    _find_item_under,
)
from ..memoria import (
    familiarity_with,
    sentiment_toward,
)
from ..rolagem import (
    _roll_d20,
    attr_modifier,
    persuade_tendencia,
    trade_dc,
)



_CUSTO_ENTREGA = "baixo"



from .primitivas import (  # noqa: F401
    _open_container_for,
    _validate_negotiation,
    check_availability,
    check_purchase_affordable,
    offered_by,
    roll_cobranca_check,
    roll_persuade_give_check,
    roll_trade_check,
    trade_terms,
)

def _apply_trade_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Comprar e trocar (`trade_ops`, spec 011) — um pipeline, dois julgamentos.

    Três fases, nesta ordem: PORTÃO + validação física (nada escreve), DECISÃO
    (aritmética na compra; necessidade + valor + dado na troca) e só então COMMIT.
    Ou a negociação inteira acontece, ou nada acontece.

    Assume o WRITE_LOCK já em mãos.
    """
    applied, rejected = [], []
    if not resolution.get("trade_ops"):
        return applied, rejected
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    for op in resolution.get("trade_ops") or []:
        modo = "buy" if op.get("modo") == "buy" else "trade"
        parceiro = op.get("parceiro")
        dou = list(op.get("dou") or [])
        recebo = list(op.get("recebo") or [])
        base = {"negociar": parceiro, "modo": modo}

        if parceiro == character_id:
            rejected.append({**base, "why": "ninguém negocia consigo mesmo"})
            continue
        if parceiro not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel",
                                                 alvo=parceiro)))
            continue
        parceiro_folder = present_chars[parceiro]
        parceiro_fm, _ = read_doc(parceiro_folder / "character.md")
        if is_down(parceiro_fm):
            rejected.append(_rejection(base, _fail("parceiro_incapaz",
                                                  parceiro=parceiro)))
            continue
        if not dou or not recebo:
            rejected.append({**base, "why": "negociação precisa de duas pontas"})
            continue

        # posse: cada item precisa estar DISPONÍVEL pra quem se propõe a
        # entregá-lo (spec 036) — não só na própria estrutura: também conta o
        # que está na location atual/`object` aberto ali, contanto que
        # `dono(item, vendedor) == vendedor`. `dono_folder` continua sendo a
        # pasta do PERSONAGEM (não a do item) — é o que sustenta a
        # contabilidade de mão/carga em `_validate_negotiation`, que só faz
        # sentido pro corpo dele, esteja o item fisicamente com ele ou não.
        pernas, fms_dou, fms_recebo, falhou = [], [], [], False
        for ids, vendedor_id, dono_folder, destino_folder, acc in (
                (dou, character_id, actor_folder, parceiro_folder, fms_dou),
                (recebo, parceiro, parceiro_folder, actor_folder, fms_recebo)):
            disponivel_vendedor = percepcao.offerable_entities(vendedor_id)
            for iid in ids:
                no = disponivel_vendedor.get(iid)
                if no is None or no["tipo"] != "item":
                    rejected.append(_rejection(base, _fail("item_nao_e_seu",
                                                          item=iid)))
                    falhou = True
                    break
                folder, fm = no["folder"], no["fm"]
                acc.append((iid, fm))
                pernas.append((iid, folder, fm, dono_folder, destino_folder))
            if falhou:
                break
        if falhou:
            continue

        # PORTÃO — o que o mundo não põe à mesa não entra em negócio
        rej = check_availability(modo, fms_dou, fms_recebo)
        if rej:
            rejected.append(_rejection(base, rej))
            continue

        # física de TODAS as pernas, antes de mover qualquer coisa
        rej, destinos = _validate_negotiation(pernas)
        if rej:
            rejected.append(_rejection(base, _fail(
                "sem_espaco_para_receber", parceiro=parceiro,
                **{k: v for k, v in rej["valores"].items() if k != "personagem"})))
            continue

        # DECISÃO — a regra de mérito mora em primitivas (spec 037); o executor só as encadeia
        info = None
        if modo == "buy":
            rej = check_purchase_affordable(fms_dou, fms_recebo, parceiro)
            if rej:
                rejected.append(_rejection(base, rej))
                continue
        else:
            necessidade, razao = trade_terms(op, fms_dou, fms_recebo)
            if necessidade == 0:
                rejected.append(_rejection(base, _fail(
                    "necessidade_insuficiente", parceiro=parceiro)))
                # spec 043: propor negócio e ser recusado cobra de quem propôs.
                fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
                continue
            if necessidade < 10:
                actor_fm, _ = read_doc(actor_folder / "character.md")
                # apego do PARCEIRO ao que ELE entrega (spec 016): é a
                # necessidade dele que o teste mede, então é o apego dele que
                # dificulta abrir mão. `fms_recebo` = o que o ator recebe = o
                # que o parceiro perde.
                apego = sum(familiarity_with(parceiro, iid)
                            for iid, _ in fms_recebo)
                # afeto do PARCEIRO por quem propõe (spec 016): detesta = cobra
                # mais, estima = cobra menos. O "não vendo pra você".
                afeto_parc = sentiment_toward(parceiro, character_id)
                rej, info = roll_trade_check(actor_fm, character_id, parceiro,
                                             necessidade, razao, apego, afeto_parc)
                if info is not None and rolls is not None:
                    rolls.append(info)
                if rej:
                    rejected.append(_rejection(base, rej))
                    # spec 043: o negócio que não fecha cobra de quem propôs.
                    fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
                    continue

        # COMMIT — só agora o mundo muda, e exatamente nos destinos aprovados
        for (item_id, item_folder, _fm, _doador, recebedor), destino in zip(
                pernas, destinos):
            # spec 038: o estado do item (slot) vira primitiva; o executor só roteia.
            slot = (grasp_slot_of(_char_fm(recebedor)) or HAND_SLOT) if destino is None else None
            itens._set_item_slot(item_folder, slot)
            io.move_entity(item_folder, (destino or recebedor) / item_folder.name)
        applied.append({"parceiro": parceiro, "modo": modo,
                        "dou": dou, "recebo": recebo})
        fisica.spend_fatigue(character_id, _CUSTO_ENTREGA)  # spec 030
    return applied, rejected


# --------------------------------------------------------------------------- #
# Persuadir a DAR um item (spec 023) — o gêmeo do roll_disposicao, mas o desfecho
# é a física de doação, com o ALVO como doador (o afeto positivo recai sobre ele).
# --------------------------------------------------------------------------- #

# spec 030: categoria de esforço de ENTREGAR um item (negociar ou ceder por
# persuasão) — mora aqui, parte da física de comércio. Mesma constante usada por
# _apply_trade_ops (acima) e _apply_persuade_give_ops/roll_persuade_give_check
# (abaixo), nunca uma tabela externa (research.md §4).
def _apply_persuade_give_ops(character_id: str, actor_folder: Path, resolution: dict,
                             rolls: list | None = None) -> tuple[list, list]:
    """Convencer o DONO (alvo) a ENTREGAR um item ao ATOR ou a outro presente.

    No SUCESSO a transferência corre pela PRIMITIVA `itens.transfer_item` (spec 037,
    nunca a tool give) COM O ALVO como origem — e é gravada na perspectiva do ALVO (o
    doador), então o afeto positivo recai sobre ele em quem recebe (ver
    _record_persuade_give). Assume o WRITE_LOCK já em mãos.
    """
    applied, rejected = [], []
    if not resolution.get("persuade_give_ops"):
        return applied, rejected
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    for op in resolution.get("persuade_give_ops") or []:
        alvo = op.get("alvo")
        item_id = op.get("item")
        para = op.get("para")
        disposicao = op.get("disposicao")
        base = {"persuadir_a_dar": alvo, "item": item_id, "para": para}
        if alvo == character_id:
            rejected.append({**base, "why": "é ele quem age — para dar o que é seu, use give"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        if para == alvo:
            rejected.append(_rejection(base, _fail("destino_e_o_dono", alvo=alvo)))
            continue
        alvo_folder = present_chars[alvo]
        alvo_fm, _ = read_doc(alvo_folder / "character.md")
        if is_down(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_desacordado", alvo=alvo)))
            continue
        if _find_item_under(alvo_folder, item_id) is None:
            rejected.append(_rejection(base, _fail("item_nao_e_do_alvo", item=item_id, alvo=alvo)))
            continue
        # present map da perspectiva do ALVO: o ator entra, o alvo sai.
        present_from_alvo = dict(present_chars)
        present_from_alvo[character_id] = actor_folder
        if para not in present_from_alvo:
            rejected.append(_rejection(base, _fail("destino_inacessivel", destino=para)))
            continue
        # extremo da régua: nota 0 = recusa ABSOLUTA, sem dado (item 31 §2: o
        # veredito determinístico que era pré-voo da tool mora aqui). Distinto do
        # nao_cedeu (o dono ouviu e declinou, ou o trauma forçou 0 — segredo do mundo).
        if int(disposicao or 0) <= 0:
            rejected.append(_rejection(base, _fail("nada_a_ceder", alvo=alvo)))
            continue
        passou, info = roll_persuade_give_check(
            actor_fm, character_id, alvo, para, item_id, disposicao, rolls,
            alvo_fm=alvo_fm)
        if not passou:
            rejected.append(_rejection(base, _fail("nao_cedeu", alvo=alvo, item=item_id)))
            # spec 043: pedir e ouvir não cobra de QUEM PEDIU (supera a spec 030
            # FR-003). No SUCESSO segue como a 030 desenhou: quem entrega é que gasta.
            fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
            continue
        # o ALVO entrega: spec 037 reusa a PRIMITIVA de transferência (origem = alvo),
        # nunca a tool give. O SENTIDO (afeto ao DOADOR na perspectiva do alvo) mora em
        # _record_persuade_give; a primitiva não grava nada.
        scene = {"chars": present_chars, "objects": present_objects,
                 "items": present_items, "location_folder": actor_folder.parent,
                 "place_id": None}
        t_ap, t_rej = itens.transfer_item(item_id, alvo_folder, para, scene, rolls)
        if t_ap is None:
            rej = t_rej or {"why": "não coube em quem receberia"}
            entry = {**base, "why": rej.get("why", "não coube")}
            if rej.get("regra"):
                entry["regra"], entry["valores"] = rej["regra"], rej.get("valores")
            rejected.append(entry)
            continue
        applied.append({"alvo": alvo, "item": item_id, "para": para,
                        "virada": bool(info.get("virada"))})
        # spec 030 (FR-003): quem ENTREGA gasta a fadiga — o ALVO persuadido,
        # nunca quem persuadiu.
        fisica.spend_fatigue(alvo, _CUSTO_ENTREGA)
    return applied, rejected


@registro.handler("trade_ops")
def _h_trade(cid, af, res, rolls):
    # FR-014 (spec 073): aqui havia o fechamento da própria intenção pelo
    # `intention_id` que a Mente mandava junto da troca. Foi APOSENTADO — declarar
    # que a troca cumpriu o compromisso é pontuar o próprio desfecho (Princípio IX).
    # Quem fecha é `turno._fechar_compromissos`, conferindo o `pronto_quando`.
    applied, rejected = _apply_trade_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


@registro.handler("persuade_give_ops")
def _h_persuade_give(cid, af, res, rolls):
    applied, rejected = _apply_persuade_give_ops(cid, af, res, rolls)
    # memória gravada na perspectiva do ALVO via react_actor_memory (spec 038):
    # a reação recompõe a cena com o MESMO `io._scene_entities(af.parent)`.
    return applied, rejected, []


# A MEMÓRIA DA COBRANÇA, nos DOIS lados (spec 073, US6).
#
# O que faz esta tool valer é o CALOTE: negar deixa memória `large` NEGATIVA nos dois,
# e `large` é justamente o que `sofreu_trauma_de` procura — daí em diante eles não
# cooperam. Punição por reputação, num mundo sem Estado.
#
# Pagar aproxima (positiva, `medium`). Regatear deixa um resto: leve negativa em quem
# cobrou, e nada de positivo em quem pagou menos do que devia.
_COBRANCA = {
    # desfecho: (intensidade, valência de quem COBROU para com o outro,
    #            valência do OUTRO para com quem cobrou)
    "paga":     ("medium", memoria.POSITIVA, memoria.POSITIVA),
    "regateia": ("small",  memoria.NEGATIVA, None),
    "nega":     ("large",  memoria.NEGATIVA, memoria.NEGATIVA),
}


def _memoria_da_cobranca(quem_cobrou: str, alvo: str, desfecho: str,
                         item_id: str | None = None) -> list:
    """As DUAS lembranças do mesmo ato, cada uma na sua perspectiva.

    Duas entradas, não uma repetida: quem cobra lembra de ter cobrado, quem foi
    cobrado lembra de ter sido — e a frase de cada um diz o que ELE viveu. A lição é
    a do `_rec_unico` (spec 040): sem isso, os dois lados recebem a MESMA frase e a
    memória mente sobre quem fez o quê.
    """
    intensidade, val_ator, val_alvo = _COBRANCA[desfecho]
    eu = memoria._char_name(quem_cobrou)
    ele = memoria._char_name(alvo)
    o_que = f" ({io.name_of(item_id)})" if item_id else ""
    if desfecho == "paga":
        texto_ator = f"Cobrei {ele} o que me devia, e ele pagou{o_que}"
        texto_alvo = f"{eu} me cobrou o que eu devia, e eu paguei{o_que}"
    elif desfecho == "regateia":
        texto_ator = f"Cobrei {ele}, e ele me pagou menos do que devia"
        texto_alvo = f"{eu} me cobrou, e eu paguei menos do que devia"
    else:
        texto_ator = f"Cobrei {ele} o que me devia, e ele NÃO pagou"
        texto_alvo = f"{eu} me cobrou o que eu devia, e eu não paguei"
    envolvidos = [quem_cobrou, alvo]
    saida = [{"quem": quem_cobrou, "content": texto_ator, "event": "cobranca",
              "intensity": intensidade, "involved": envolvidos,
              "valence": {alvo: val_ator}}]
    entrada_alvo = {"quem": alvo, "content": texto_alvo, "event": "cobranca",
                    "intensity": intensidade, "involved": envolvidos}
    if val_alvo is not None:
        entrada_alvo["valence"] = {quem_cobrou: val_alvo}
    saida.append(entrada_alvo)
    return saida


def _apply_cobranca_ops(character_id: str, actor_folder: Path, resolution: dict,
                        rolls: list | None = None) -> tuple[list, list]:
    """COBRAR o que foi prometido (spec 073, US6 / FR-017, FR-018).

    Reivindicar, não perguntar: perguntar é `ask_about` e não obriga ninguém. Aqui
    duas vontades se opõem, e por isso há régua e dado.

    O QUARTO PORTÃO mora aqui, e é o que torna a tool barata: **sem promessa na
    memória de quem cobra, recusa SEM ROLAR**. É FATO, não juízo — a memória existe
    dos dois lados desde a spec 027, e só se consulta.

    FR-018: o pagamento NÃO se move por conta própria. Quando o desfecho é `paga`, a
    transferência corre pela PRIMITIVA `itens.transfer_item` (a mesma do `give`),
    com o ALVO como origem — nunca chamando a tool `give`. Princípio XII: a tool
    orquestra, a primitiva opera.

    Assume o WRITE_LOCK já em mãos.
    """
    applied, rejected = [], []
    if not resolution.get("cobranca_ops"):
        return applied, rejected
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):
        rejected.append(_fail("descansando"))
        return applied, rejected
    for op in resolution.get("cobranca_ops") or []:
        alvo = op.get("de_quem")
        item_id = op.get("item")          # opcional: o que se aceita como pagamento
        nota = op.get("cumprimento")
        base = {"cobrar_de": alvo, **({"item": item_id} if item_id else {})}
        if alvo == character_id:
            rejected.append({**base, "why": "não se cobra de si mesmo"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        alvo_folder = present_chars[alvo]
        alvo_fm, _ = read_doc(alvo_folder / "character.md")
        if is_down(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_desacordado", alvo=alvo)))
            continue
        # PORTÃO 1 — A PROMESSA. Sem ela não há o que cobrar, e o dado nem entra.
        # A frase convida a VERIFICAR, não a insistir: "não se lembra" é ignorância,
        # não proibição do sistema.
        if memoria.promessa_viva_de(character_id, alvo) is None:
            rejected.append(_rejection(base, _fail("sem_promessa", alvo=alvo)))
            continue
        # O item, quando nomeado, tem de ser DELE — cobrar apontando o que é seu, ou
        # o que é de terceiro, é erro de referência, não recusa de mérito.
        if item_id and _find_item_under(alvo_folder, item_id) is None:
            rejected.append(_rejection(base, _fail("item_nao_e_do_alvo",
                                                   item=item_id, alvo=alvo)))
            continue
        desfecho, info = roll_cobranca_check(actor_fm, character_id, alvo,
                                             int(nota or 0), rolls, alvo_fm=alvo_fm)
        if desfecho == "nega":
            # A FALHA NUNCA É SILENCIOSA (Princípio X): volta com regra e frase de
            # mundo, e A Mente narra a tentativa frustrada. O calote é o ponto da
            # tool — quem lembra dele é `_record_cobranca`.
            rejected.append(_rejection(base, _fail("nao_pagou", alvo=alvo)))
            fisica.spend_fatigue(character_id, fisica.CUSTO_TENTATIVA_SOCIAL)
            # O CALOTE É O PONTO DESTA TOOL, e por isso ele é um fato APLICADO —
            # ainda que nada se mova. `large` negativa dos DOIS lados é o que dispara
            # o portão de trauma (`sofreu_trauma_de`) nas próximas interações entre
            # eles: a asfixia social por memória, num mundo sem Estado. Valência e
            # intensidade viajam COM o ato, nunca numa tabela central — as
            # `_VALENCE_BY_EVENT`/`_RELEVANCE_BY_EVENT` morreram na spec 038.
            applied.append({
                "de_quem": alvo, "desfecho": "nega",
                "virada": bool(info.get("virada")),
                "memory": _memoria_da_cobranca(character_id, alvo, "nega"),
            })
            continue
        ap = {"de_quem": alvo, "desfecho": desfecho,
              "virada": bool(info.get("virada"))}
        if desfecho == "paga" and item_id:
            # FR-018: a PRIMITIVA de doação, com o alvo como origem. Nunca a tool.
            scene = {"chars": present_chars, "objects": present_objects,
                     "items": present_items, "location_folder": actor_folder.parent,
                     "place_id": None}
            t_ap, t_rej = itens.transfer_item(item_id, alvo_folder, character_id,
                                              scene, rolls)
            if t_ap is None:
                rej = t_rej or {"why": "não coube em quem receberia"}
                entry = {**base, "why": rej.get("why", "não coube")}
                if rej.get("regra"):
                    entry["regra"], entry["valores"] = rej["regra"], rej.get("valores")
                rejected.append(entry)
                continue
            ap["item"] = item_id
        ap["memory"] = _memoria_da_cobranca(character_id, alvo, desfecho,
                                            item_id if desfecho == "paga" else None)
        applied.append(ap)
        fisica.spend_fatigue(alvo, fisica.CUSTO_TENTATIVA_SOCIAL)
    return applied, rejected


@registro.handler("cobranca_ops")
def _h_cobranca(cid, af, res, rolls):
    applied, rejected = _apply_cobranca_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória dos dois via react_actor_memory (spec 038)
