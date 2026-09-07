"""O Motor / combate — EXECUTORES (item 31 §3: DDD por domínio).

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

from .. import estado, fisica, io, memoria, registro, rolagem, trabalho
from ..estado import (
    _set_condition,
)
from ..fisica import (
    DEAD,
    INCAPACITATED,
    PUSH_TRIVIAL_RATIO,
    _conditions_of,
    ensure_hp,
    is_dead,
    is_down,
    protection_of,
    push_capacity,
    weapon_of,
)
from ..io import (
    _fail,
    _rejection,
    find_entity,
    read_doc,
    write_doc,
)
from ..rolagem import (
    NEUTRAL_ADVANTAGE,
    _roll_d20,
    attack_tendencia,
    attr_modifier,
    defense_of,
    push_dc,
    resist_dc,
)



from .primitivas import (  # noqa: F401
    roll_attack_check,
    roll_push_check,
    roll_resist_check,
)

def _apply_attack_ops(character_id: str, actor_folder: Path, resolution: dict,
                      rolls: list | None = None) -> tuple[list, list, list]:
    """Golpear outro personagem presente (`attack_ops`, spec 008 + 069).

    Ponto autoritativo do teste oposto: a guarda do Árbitro valida só o
    determinístico — e nem poderia fazer mais, porque o contexto não expõe os
    atributos crus de terceiros. Rolagem ÚNICA, aqui. Zonas deterministas
    (espelho de trivial/impossível do empurrar): alvo já caído não tem defesa e o
    golpe deliberado o MATA sem dado; alvo morto nega sem dado. A vantagem
    (0–10, do Árbitro pela régua canônica) é efêmera e secreta: clampada, usada e
    descartada. Assume o WRITE_LOCK já em mãos.

    Spec 069: cada golpe pode provocar um REVIDE do alvo — ver `_talvez_revidar`. O
    terceiro elemento do retorno são as memórias que o contra-golpe criou (as do ator
    deste golpe seguem vindo do barramento, `react_actor_memory`).
    """
    applied, rejected, criadas = [], [], []
    if not resolution.get("attack_ops"):
        return applied, rejected, criadas

    def _talvez_revidar(op: dict, alvo: str, alvo_folder: Path,
                        caiu: bool = False) -> None:
        """O REVIDE (spec 069): o corpo de quem apanhou responde, sem ninguém decidir.

        Reentra pela PORTA ÚNICA (`turno.apply_op`) em nome do REVIDANTE — e é isso
        que faz a atribuição sair certa. `_publish_facts` monta todo fato com
        `actor=character_id`, o dono do turno; um contra-golpe empilhado no `applied`
        daqui gravaria "Golpeei o dragão" na conta de quem APANHOU, e o leque de
        testemunha veria o agressor errado. Reentrando, `fato.actor` é o revidante, e
        memória, testemunha, fadiga e interrupção-de-viagem saem corretas sem uma
        linha nova.

        `revide: True` na op faz DOIS trabalhos: é a TRAVA da recursão (sem ela o
        contra-golpe dispara o contra-golpe do agressor, e como o WRITE_LOCK é RLock
        ele NÃO protegeria — recursionaria até estourar a pilha, dentro do lock, com
        o mundo meio escrito em disco), e é o sinal de que este golpe é DEFESA, que
        `_record_attack`/`_witness_facts` leem para não condenar quem se defendeu.

        Dispara também quando o golpe original ERRA ou é ABSORVIDO: a lâmina passou
        perto, e isso é provocação consumada — sem isso o agressor teria tentativas
        de graça, o mesmo buraco que a spec 043 fechou cobrando fadiga do erro.
        """
        if op.get("revide"):
            return                       # A TRAVA: profundidade máxima 1
        try:
            nota = int(op.get("revide_nota") or 0)
        except (TypeError, ValueError):
            return
        if nota <= 0 or caiu:            # nota 0, ou quem apanhou já caiu
            return
        alvo_fm_agora, _ = read_doc(alvo_folder / "character.md")
        if is_dead(alvo_fm_agora) or is_down(alvo_fm_agora):
            return
        if fisica.is_resting(alvo_fm_agora) or trabalho.is_busy(alvo_folder):
            return
        # import LOCAL de propósito: `turno` importa `combate` no topo (motor/turno.py
        # linha 18), então importá-lo aqui em cima seria ciclo.
        from .. import turno
        eco = turno.apply_op(alvo, "attack_ops", {
            "alvo": character_id, "arma": None,
            "vantagem": max(0, min(10, nota)), "revide": True,
        }, rolls=rolls)
        # O contra-golpe precisa SUBIR — revide que não chega ao chamador é dano
        # invisível, e o Princípio X proíbe efeito que não se relata. Mas ele JÁ FOI
        # publicado pela reentrada, com o ator certo: subir a entrada crua fazia o
        # `_publish_facts` do turno EXTERNO publicá-la de novo, agora com o ator
        # errado. Medido antes da marca: "Golpeei Torvin, o Ferreiro" gravado na pasta
        # do próprio Torvin, e "Vi Torvin golpear Torvin" na plateia. `ja_publicado`
        # é o que faz o barramento ignorá-las na segunda passagem.
        applied.extend({**a, "ja_publicado": True}
                       for a in (eco.get("applied") or []) if isinstance(a, dict))
        rejected.extend({**r, "ja_publicado": True}
                        for r in (eco.get("rejected") or []) if isinstance(r, dict))
        criadas.extend(eco.get("created") or [])
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected, criadas
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    for op in resolution.get("attack_ops") or []:
        alvo = op.get("alvo") or op.get("personagem")
        arma_id = op.get("arma")
        base = {"atacar": alvo, "arma": arma_id}
        if alvo == character_id:
            rejected.append({**base, "why": "é ele quem golpeia"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        alvo_folder = present_chars[alvo]
        alvo_fm, alvo_body = read_doc(alvo_folder / "character.md")

        if is_dead(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_ja_morto", alvo=alvo)))
            continue

        # Já caído: sem defesa, sem dado. Chamar o golpe contra quem não pode se
        # defender É o ato deliberado — a morte nunca sai da sorte (FR-009).
        if is_down(alvo_fm):
            _set_condition(alvo_folder, DEAD)
            golpe = fisica.pick_natural_weapon(
                read_doc(actor_folder / "character.md")[0]) if not arma_id else None
            applied.append({"alvo": alvo, "arma": arma_id,
                            "parte": golpe[0] if golpe else None, "dano": 0,
                            "derrota": DEAD, "deliberado": True,
                            "revide": bool(op.get("revide"))})
            fisica.spend_fatigue(character_id, "alto")  # spec 030: golpear cansa
            continue

        actor_fm, _ = read_doc(actor_folder / "character.md")
        arma_fm = None
        if arma_id:
            found = find_entity(arma_id)
            if found is not None:
                _, arma_fm, _ = found
        # spec 068: a FONTE da arma. Item na mão quando a Mente escolheu um; uma
        # PARTE ARMADA do corpo quando não — a garra do dragão, que antes valia 1 de
        # dano como um soco. A escolha EXPLÍCITA sempre vence: um item sem bloco
        # `weapon` (uma pedra) segue valendo improvisado, nunca a garra — ela escolheu
        # a pedra. Sem parte armada e sem item, o improvisado de sempre.
        #
        # A parte é SORTEADA porque golpear com o corpo é instintivo, não deliberado
        # (ver `pick_natural_weapon`) — e por isso ela precisa ser RELATADA: sem saber
        # se foram as garras ou os dentes, A Mente não tem como narrar o golpe que o
        # mundo resolveu.
        parte = None
        if arma_id:
            damage, attribute = weapon_of(arma_fm)
        else:
            natural = fisica.pick_natural_weapon(actor_fm)
            if natural is None:
                damage, attribute = weapon_of(None)      # improvisado
            else:
                parte, damage, attribute = natural

        try:
            vantagem = int(op.get("vantagem"))
        except (TypeError, ValueError):
            vantagem = NEUTRAL_ADVANTAGE  # sem nota legível: combate limpo
        vantagem = max(0, min(10, vantagem))

        rej, info = roll_attack_check(actor_fm, alvo_fm, character_id, alvo,
                                      arma_id, damage, attribute, vantagem)
        if info is not None:
            if parte:
                info["parte"] = parte     # com que PARTE do corpo se golpeou
            if rolls is not None:
                rolls.append(info)
        if rej:
            rejected.append(_rejection(base, rej))
            # spec 043: o golpe que ERRA também cansa — menos que o que acerta.
            # Sem isto, repetir o ataque na mesma cena era de graça.
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
            _talvez_revidar(op, alvo, alvo_folder)   # errar também provoca
            continue

        mod = attr_modifier((actor_fm.get("attributes") or {}).get(attribute, 10))
        protecao = protection_of(alvo_folder)
        dano = max(0, damage + mod - protecao)
        if info is not None:
            info["dano"] = dano
        if dano == 0:
            # o golpe conectou e o aço segurou: não é o mesmo que errar
            rejected.append(_rejection(base, _fail(
                "golpe_absorvido", alvo=alvo, personagem=character_id,
                arma=arma_id, parte=parte, protecao=protecao,
                rolagem=info["rolagem"])))
            # spec 043: conectar na armadura cansa o braço igual — o esforço houve.
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
            _talvez_revidar(op, alvo, alvo_folder)   # absorvido também provoca
            continue

        novo_hp, derrota = fisica.apply_damage(alvo_folder, dano)  # spec 038: estado vira primitiva
        applied.append({"alvo": alvo, "arma": arma_id, "parte": parte, "dano": dano,
                        "hp_restante": novo_hp, "derrota": derrota,
                        # spec 069: a marca viaja no APLICADO, não só na op de entrada
                        # — é o applied que a memória e o leque leem para saber que
                        # este golpe foi DEFESA e não condenar quem se defendeu.
                        "revide": bool(op.get("revide"))})
        fisica.spend_fatigue(character_id, "alto")  # spec 030: golpear cansa
        _talvez_revidar(op, alvo, alvo_folder, caiu=bool(derrota))
    return applied, rejected, criadas


@registro.handler("attack_ops")
def _h_attack(cid, af, res, rolls):
    # `criadas` são as memórias do REVIDE (spec 069), que nasceram na reentrada por
    # `apply_op` em nome do revidante. A memória do ATOR deste golpe continua vindo do
    # barramento (`react_actor_memory`, spec 038) — não é gravada aqui.
    applied, rejected, criadas = _apply_attack_ops(cid, af, res, rolls)
    return applied, rejected, criadas
