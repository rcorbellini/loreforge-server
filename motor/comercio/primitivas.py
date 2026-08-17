"""O Motor / comercio — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
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

from .. import fisica, intencoes, io, itens, memoria, percepcao, registro, rolagem
from ..fisica import (
    HAND_SLOT,
    _direct_items,
    _walk_open_items,
    carried_weight,
    carry_capacity,
    check_carga_livre,
    check_encaixe,
    check_mao,
    open_container_for,
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


def offered_by(character_id: str) -> dict:
    """O que este personagem OFERECE — consulta de SERVER, não de client.

    Estar à venda não é estar à vista: a mercadoria pode morar no fundo da caixa
    do mascate, e `_visible_item_refs` (o que terceiros enxergam) continua sem
    mostrá-la. Quem sabe disto é o Árbitro, que lê o mundo — Princípio IX, nível
    "consultivo de server". O player só descobre perguntando, e a resposta chega
    a ele como fala do mercador.

    Fonte (spec 036): `percepcao.offerable_entities(character_id)`, NUNCA `visible_entities`/
    `reachable_entities` diretamente (FR-007) — inclui o que ele carrega E o que está
    na location atual/`object` aberto ali para o qual ele tem `dono`
    reconhecido (a banca do mascate, item 1 do backlog), mas EXCLUI de
    propósito o que está emprestado ou roubado por ele mas reivindicado por
    outro (o walk de `offerable_entities` para no personagem que não é ele mesmo
    antes de chegar em qualquer coisa que esteja com um terceiro). Contêiner
    FECHADO segue escondendo tudo (spec 005): o que está trancado não é
    `is_blocked`-livre, então nem entra em `offerable_entities`.
    """
    a_venda, trocaveis = [], []
    for eid, no in percepcao.offerable_entities(character_id).items():
        fm = no["fm"]
        if not _is_valid(fm):
            continue
        ref = {"id": fm.get("id"), "name": fm.get("name"),
               "value": value_of(fm)}
        if is_for_sale(fm) and value_of(fm) is not None:
            a_venda.append(ref)
        if is_negotiable(fm):
            trocaveis.append(ref)
    return {"personagem": character_id, "a_venda": a_venda,
            "trocaveis": trocaveis}


def check_availability(modo: str, sai_do_ator: list, sai_do_parceiro: list
                          ) -> dict | None:
    """O PORTÃO (spec 011): o que o mundo não põe à mesa não entra em negócio.

    Roda ANTES de qualquer avaliação — não toca preço total, não rola dado. É a
    defesa que não depende do modelo: um Árbitro complacente não transforma o
    relicário de família em moeda de troca, porque o item não está marcado.

    Cada lista é de pares (id, frontmatter).
    """
    if modo == "buy":
        for iid, fm in sai_do_ator:          # pagamento
            if not is_currency(fm):
                return _fail("pagamento_nao_e_dinheiro", item=iid)
            if value_of(fm) is None:
                return _fail("pagamento_nao_e_dinheiro", item=iid, motivo="sem preço")
        for iid, fm in sai_do_parceiro:      # mercadoria
            if not is_for_sale(fm) or value_of(fm) is None:
                return _fail("nao_esta_a_venda", item=iid)
        return None
    for iid, fm in list(sai_do_ator) + list(sai_do_parceiro):
        if not is_negotiable(fm):
            return _fail("nao_e_negociavel", item=iid)
    return None


def roll_trade_check(actor_fm: dict, char_id: str, parceiro_id: str,
                     necessidade: int, razao_valor: float, apego: float = 0.0,
                     afeto_parceiro: float = 0.0
                     ) -> tuple[dict | None, dict | None]:
    """Teste da troca (spec 011). Rolagem ÚNICA na faixa 1–9 da necessidade.

    Os extremos não chegam aqui: 0 recusa e 10 aceita sem dado (decididos por
    quem chama). A nota e a razão NÃO entram no roll_info — segredo do mundo,
    como a vontade do persuade.
    """
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    dc = trade_dc(necessidade, razao_valor, apego, afeto_parceiro)
    total = d20 + mod
    passou = total >= dc
    tendencia = persuade_tendencia(necessidade)  # mesma leitura qualitativa
    virada = (tendencia == "ir" and not passou) or (tendencia == "ficar" and passou)
    critico = ("sucesso" if (d20 == 20 and passou)
               else "falha" if (d20 == 1 and not passou) else None)
    info = {
        "tipo": "negociacao",
        "personagem": char_id, "parceiro": parceiro_id,
        "tendencia": tendencia,
        "resultado": "sucesso" if passou else "falha",
        "virada": virada, "critico": critico,
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if passou:
        return None, info
    rej = _fail("necessidade_insuficiente", parceiro=parceiro_id,
                personagem=char_id, tendencia=tendencia, virada=virada,
                critico=critico, rolagem=info["rolagem"])
    return rej, info


def _validate_negotiation(pernas: list) -> dict | None:
    """Fase 1 da negociação (spec 011): valida TODAS as pernas sem escrever nada.

    `pernas` = [(item_id, item_folder, item_fm, doador_folder, recebedor_folder)].

    Por que simulado e não perna a perna: `get_context` não pega o WRITE_LOCK, então
    mover e desfazer deixaria uma janela em que uma consulta veria meia negociação —
    o Princípio III proíbe. Aqui nada se move até tudo passar.

    Usa os MESMOS `check_*` do pipeline físico (guichê único): o snapshot vem dos
    arquivos e os deltas se acumulam — quem entrega libera mão e carga, quem recebe
    ocupa. Devolve `(rejeicao, destinos)`; `destinos[i]` é a pasta do contêiner que
    recebe a perna i, ou None para a mão.
    """
    maos: dict[Path, list] = {}
    livre: dict[Path, float] = {}
    vagas: dict[Path, int] = {}      # contêiner -> quantos itens já tem
    pega_de: dict[Path, str | None] = {}   # spec 019: slot de pega por personagem

    def _estado(folder: Path):
        if folder not in maos:
            fm, _ = read_doc(folder / "character.md")
            pega_de[folder] = grasp_slot_of(fm)
            maos[folder] = list(slots_in_use(folder).get(pega_de[folder]) or []) \
                if pega_de[folder] else []
            livre[folder] = carry_capacity(fm) - carried_weight(folder)
        return maos[folder], livre[folder]

    destinos = []
    for item_id, item_folder, item_fm, doador, recebedor in pernas:
        peso = effective_weight(item_folder)
        # o doador solta: libera a mão (se estava nela) e a carga
        d_maos, d_livre = _estado(doador)
        if item_id in d_maos:
            d_maos.remove(item_id)
        livre[doador] = d_livre + peso

        r_maos, r_livre = _estado(recebedor)
        r_fm, _ = read_doc(recebedor / "character.md")
        rej = check_carga_livre(r_fm.get("id"), item_id, peso, r_livre)
        if rej:
            return rej, None

        # Onde a coisa recebida vai parar: primeiro uma bolsa com espaço, e só
        # depois a mão. Sem isto, comprar com três moedas seria fisicamente
        # impossível — ninguém tem três mãos —, e o N↔N da spec não existiria.
        destino = _open_container_for(recebedor, item_fm, item_folder, vagas)
        if destino is None:
            _estado(recebedor)  # garante pega_de preenchido
            r_pega = pega_de[recebedor]
            rej = check_mao(r_fm.get("id"), r_maos,
                            slot_capacity(r_fm, r_pega) if r_pega else 0)
            if rej:
                return rej, None
            r_maos.append(item_id)
        # Colisão de nome de pasta no destino: acontece quando o mundo tem dois
        # itens com o mesmo id. O rename falharia NO MEIO do commit e deixaria
        # meia negociação aplicada — justo o que a atomicidade promete impedir.
        # Barrar aqui mantém a promessa mesmo com mundo mal escrito.
        if ((destino or recebedor) / item_folder.name).exists():
            return _fail("destino_ocupado", item=item_id,
                         motivo="já existe algo com esse nome no destino"), None
        livre[recebedor] = r_livre - peso
        destinos.append(destino)   # None = mão do recebedor
    return None, destinos


# `_open_container_for` SUBIU para `fisica.open_container_for` (item 44): a mesma
# pergunta — "onde isto cabe, sem eu ter de escolher?" — passou a ser feita pela
# entrega, pelo furto e pelo `stow` sem destino. Aqui fica só o apelido, para não
# reescrever as chamadas da negociação.
_open_container_for = open_container_for


def check_purchase_affordable(fms_dou: list, fms_recebo: list, parceiro: str) -> dict | None:
    """Regra de mérito da COMPRA (spec 037): o pagamento cobre o pedido? Aritmética
    pura sobre o `value` do mundo, sem opinião. Devolve a recusa `valor_insuficiente`
    (com oferecido/pedido) ou None. Extraída de `_apply_trade_ops` para a regra não
    morar no executor (Princípio XII). O mesmo mérito vive HOJE duplicado na guarda do
    Árbitro (`arbiter._execute`) — dedup é o item 31 do backlog, não esta fatia.
    """
    pago = total_value([fm for _, fm in fms_dou])
    pedido = total_value([fm for _, fm in fms_recebo])
    if pago is None or pedido is None or pago < pedido:
        return _fail("valor_insuficiente", parceiro=parceiro,
                     oferecido=pago, pedido=pedido)
    return None


def trade_terms(op: dict, fms_dou: list, fms_recebo: list) -> tuple[int, float]:
    """Termos da TROCA (spec 037): normaliza a nota de necessidade (padrão 3, faixa
    0-10) e a razão de valor (oferecido/pedido, 1.0 se indefinido) que alimentam
    `roll_trade_check`. A montagem da regra sai do executor. Devolve (necessidade, razao).
    """
    try:
        necessidade = int(op.get("necessidade"))
    except (TypeError, ValueError):
        necessidade = 3  # sem nota legível: o padrão é não negociar
    necessidade = max(0, min(10, necessidade))
    oferecido = total_value([fm for _, fm in fms_dou])
    pedido = total_value([fm for _, fm in fms_recebo])
    razao = 1.0
    if oferecido is not None and pedido:
        razao = oferecido / pedido
    return necessidade, razao


def roll_persuade_give_check(actor_fm: dict, char_id: str, alvo_id: str,
                             destino_id: str, item_id: str, disposicao: int,
                             rolls: list | None = None,
                             alvo_fm: dict | None = None) -> tuple[bool, dict]:
    """O dono cedeu? d20 + mod(CHA do ator) vs persuade_dc(disposição) — UMA vez.

    Curva da persuasão (mesma aritmética de "vencer relutância grau N"; a régua é
    outra, REGUA_DISPOSICAO_CEDER, ancorada BAIXO — ceder um bem não é trivial).
    Portão de trauma: se o dono sofreu violência/roubo de quem pede, disposição = 0,
    imposto pelo Motor sobre o estado ATUAL (fase única 020). Nota/DC são segredo.
    """
    disposicao = int(disposicao)
    if memoria.has_trauma_from(alvo_id, actor_fm.get("id")):
        disposicao = 0
    if disposicao <= 0 or disposicao >= 10:
        passou = disposicao >= 10
        info = {"tipo": "persuade_give", "personagem": char_id, "alvo": alvo_id,
                "item": item_id, "para": destino_id,
                "resultado": "sucesso" if passou else "falha",
                "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return passou, info
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("CHA", 10))
    dc = rolagem.persuade_dc(disposicao)
    # spec 030 (Frente B): mesmo tratamento de roll_persuasion_check —
    # entregar um item tem custo de fadiga (_CUSTO_ENTREGA), então quem já
    # está exausto resiste mais a ceder.
    if alvo_fm is not None and fisica._CUSTOS_FADIGA.get(_CUSTO_ENTREGA, 0) > 0:
        fadiga, teto = fisica.ensure_fatigue(alvo_fm)
        dc += memoria.fatigue_penalty(fadiga, teto)
    total = d20 + mod
    passou = total >= dc
    natural = persuade_tendencia(disposicao)
    info = {
        "tipo": "persuade_give", "personagem": char_id, "alvo": alvo_id,
        "item": item_id, "para": destino_id,
        "resultado": "sucesso" if passou else "falha",
        "virada": (natural == "ir" and not passou) or (natural == "ficar" and passou),
        "critico": ("sucesso" if (d20 == 20 and passou)
                    else "falha" if (d20 == 1 and not passou) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return passou, info


