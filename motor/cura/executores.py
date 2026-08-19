"""O Motor / cura — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

from pathlib import Path

from .. import estado, fisica, io, memoria, registro, rolagem
from ..io import _fail, _rejection, read_doc, write_doc



from .primitivas import (  # noqa: F401
    _recovery_fraction,
    roll_cura_check,
)

def _apply_cura_ops(character_id: str, actor_folder: Path, resolution: dict,
                    rolls: list | None = None) -> tuple[list, list]:
    """Executor AUTO-SUFICIENTE (spec 025): lê a própria cena fresca e
    valida o alvo contra os arquivos reais — nunca confia que a guarda de
    `arbiter.py` já checou (o fallback de texto/replay chega aqui sem ter
    passado por lá; um teste que chame esta função DIRETO também precisa
    ser recusado corretamente, spec 032 tasks.md T011)."""
    applied, rejected = [], []
    if not resolution.get("cura_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    present_chars, _, _ = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    for op in resolution.get("cura_ops") or []:
        alvo = op.get("alvo")
        nota = op.get("vantagem")
        base = {"curar": alvo}
        if alvo == character_id:
            rejected.append({**base, "why": "é ele quem socorre"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        alvo_folder = present_chars[alvo]
        alvo_fm, alvo_body = read_doc(alvo_folder / "character.md")
        if fisica.is_dead(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_ja_morto", alvo=alvo)))
            continue
        if not fisica.is_down(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_nao_caido", alvo=alvo)))
            continue

        try:
            nota = int(nota)
        except (TypeError, ValueError):
            nota = 5  # sem nota legível: cena neutra
        nota = max(0, min(10, nota))

        banda, info = roll_cura_check(actor_fm, alvo_fm, nota, rolls)
        if info is not None:
            info["alvo"] = alvo
            info["personagem"] = character_id

        if banda == "baixa":
            applied.append({"alvo": alvo, "banda": banda, "curou": False})
            # spec 030: socorrer cansa. spec 043: o socorro que NÃO pegou já cansava o
            # cheio — agora um degrau abaixo (o esforço houve, o resultado não).
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("alto"))
            continue

        nivel_cura = memoria.proficiencies_for(character_id).get("cura", 0)
        hp, hp_max = fisica.ensure_hp(alvo_fm)
        recuperado = round(_recovery_fraction(banda, nivel_cura) * (hp_max - hp))
        hp_novo = fisica.apply_healing(alvo_folder, recuperado)  # spec 038: estado vira primitiva
        estado._clear_condition(alvo_folder, fisica.INCAPACITATED)

        wis_curador = (actor_fm.get("attributes") or {}).get("WIS", 10)
        con_curado = (alvo_fm.get("attributes") or {}).get("CON", 10)
        percentual = memoria._forgotten_percent(banda, nivel_cura, wis_curador, con_curado)
        esquecidas = memoria._forget_memories(alvo_folder, percentual)

        applied.append({"alvo": alvo, "banda": banda, "curou": True,
                        "hp_recuperado": recuperado, "hp_novo": hp_novo,
                        "memorias_esquecidas": esquecidas})
        fisica.spend_fatigue(character_id, "alto")  # spec 030: socorrer cansa
    return applied, rejected


@registro.handler("cura_ops")
def _h_cura(character_id, actor_folder, res, rolls):
    applied, rejected = _apply_cura_ops(character_id, actor_folder, res, rolls)
    return applied, rejected, []  # memória (dos dois lados) via react_actor_memory (spec 038)
