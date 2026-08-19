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

from .. import estado, fisica, io, memoria, registro, rolagem
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
                      rolls: list | None = None) -> tuple[list, list]:
    """Golpear outro personagem presente (`attack_ops`, spec 008).

    Ponto autoritativo do teste oposto: a guarda do Árbitro valida só o
    determinístico — e nem poderia fazer mais, porque o contexto não expõe os
    atributos crus de terceiros. Rolagem ÚNICA, aqui. Zonas deterministas
    (espelho de trivial/impossível do empurrar): alvo já caído não tem defesa e o
    golpe deliberado o MATA sem dado; alvo morto nega sem dado. A vantagem
    (0–10, do Árbitro pela régua canônica) é efêmera e secreta: clampada, usada e
    descartada. Assume o WRITE_LOCK já em mãos.
    """
    applied, rejected = [], []
    if not resolution.get("attack_ops"):
        return applied, rejected
    actor_fm_sono, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm_sono) or fisica.is_cooking(actor_fm_sono):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
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
            applied.append({"alvo": alvo, "arma": arma_id, "dano": 0,
                            "derrota": DEAD, "deliberado": True})
            fisica.spend_fatigue(character_id, "alto")  # spec 030: golpear cansa
            continue

        actor_fm, _ = read_doc(actor_folder / "character.md")
        arma_fm = None
        if arma_id:
            found = find_entity(arma_id)
            if found is not None:
                _, arma_fm, _ = found
        damage, attribute = weapon_of(arma_fm)

        try:
            vantagem = int(op.get("vantagem"))
        except (TypeError, ValueError):
            vantagem = NEUTRAL_ADVANTAGE  # sem nota legível: combate limpo
        vantagem = max(0, min(10, vantagem))

        rej, info = roll_attack_check(actor_fm, alvo_fm, character_id, alvo,
                                      arma_id, damage, attribute, vantagem)
        if info is not None and rolls is not None:
            rolls.append(info)
        if rej:
            rejected.append(_rejection(base, rej))
            # spec 043: o golpe que ERRA também cansa — menos que o que acerta.
            # Sem isto, repetir o ataque na mesma cena era de graça.
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
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
                arma=arma_id, protecao=protecao, rolagem=info["rolagem"])))
            # spec 043: conectar na armadura cansa o braço igual — o esforço houve.
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
            continue

        novo_hp, derrota = fisica.apply_damage(alvo_folder, dano)  # spec 038: estado vira primitiva
        applied.append({"alvo": alvo, "arma": arma_id, "dano": dano,
                        "hp_restante": novo_hp, "derrota": derrota})
        fisica.spend_fatigue(character_id, "alto")  # spec 030: golpear cansa
    return applied, rejected


@registro.handler("attack_ops")
def _h_attack(cid, af, res, rolls):
    applied, rejected = _apply_attack_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator (e arma que errou) via react_actor_memory (spec 038)
