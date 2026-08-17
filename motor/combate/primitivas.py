"""O Motor / combate — PRIMITIVAS (item 31 §3: DDD por domínio).

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


def roll_push_check(actor_fm: dict, char_id: str, item_id: str,
                    peso_item: float) -> tuple[dict | None, dict | None]:
    """Teste de força da zona de rolagem (spec 006). Retorna (rejeicao, roll_info).

    roll_info descreve a tentativa (para o devlog e para as VIRADAS narrativas);
    é None quando a zona é trivial (sem dado). `virada` = resultado invertido do
    natural (peso ≤ capacidade)."""
    capacidade = push_capacity(actor_fm)
    if peso_item <= capacidade * PUSH_TRIVIAL_RATIO:
        return None, None  # trivial: sem rolagem (SC-002)
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("STR", 10))
    dc = push_dc(peso_item, capacidade)
    total = d20 + mod
    passou = total >= dc
    natural = peso_item <= capacidade
    info = {
        "personagem": char_id, "item": item_id,
        "peso_item": round(peso_item, 3), "capacidade_empurrar": capacidade,
        "natural_conseguiria": natural,
        "resultado": "sucesso" if passou else "falha",
        "virada": passou != natural,
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if passou:
        return None, info
    rej = _fail("teste_de_forca_falhou", item=item_id,
                peso_item=round(peso_item, 3), capacidade_empurrar=capacidade,
                personagem=char_id, rolagem=info["rolagem"],
                natural_conseguiria=natural, virada=info["virada"])
    return rej, info


def roll_resist_check(actor_fm: dict, alvo_fm: dict, char_id: str,
                      alvo_id: str) -> tuple[dict | None, dict | None]:
    """Disputa de força para levar alguém DE PÉ (spec 010, regime disputa).

    Rolagem ÚNICA: `d20 + mod(STR do ator)` contra a resistência do alvo. O peso
    NÃO entra aqui — o que impede é ele se firmar, não ele ser pesado. `virada` é
    o resultado contrário ao que os corpos naturalmente fariam (mais forte leva
    mais fraco).
    """
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get("STR", 10))
    dc = resist_dc(alvo_fm)
    total = d20 + mod
    passou = total >= dc
    natural = mod >= dc - 10  # a força do ator alcança a do alvo sem sorte
    critico = ("sucesso" if (d20 == 20 and passou)
               else "falha" if (d20 == 1 and not passou) else None)
    info = {
        "tipo": "transporte", "regime": "disputa",
        "personagem": char_id, "alvo": alvo_id,
        "resultado": "sucesso" if passou else "falha",
        "natural_conseguiria": natural,
        "virada": passou != natural, "critico": critico,
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if passou:
        return None, info
    rej = _fail("alvo_resistiu", alvo=alvo_id, personagem=char_id,
                rolagem=info["rolagem"], natural_conseguiria=natural,
                virada=info["virada"], critico=critico)
    return rej, info


def roll_attack_check(actor_fm: dict, alvo_fm: dict, char_id: str, alvo_id: str,
                      arma_id: str | None, damage: int, attribute: str,
                      vantagem: int) -> tuple[dict | None, dict | None]:
    """Teste oposto do golpe (spec 008). Retorna (rejeicao, roll_info).

    Rolagem ÚNICA: `d20 + mod(atributo da arma) + (vantagem − 5)` contra a defesa
    do alvo. A vantagem CRUA nunca entra no roll_info (segredo do mundo, FR-010) —
    sobem a tendência qualitativa e o modificador já aplicado. `critico` só quando
    o extremo do dado ALINHOU com o desfecho (20 e acertou / 1 e errou).
    """
    d20 = rolagem._roll_d20()
    mod = attr_modifier((actor_fm.get("attributes") or {}).get(attribute, 10))
    vantagem_mod = int(vantagem) - NEUTRAL_ADVANTAGE
    dc = defense_of(alvo_fm)
    total = d20 + mod + vantagem_mod
    passou = total >= dc
    tendencia = attack_tendencia(vantagem)
    virada = (tendencia == "acertar" and not passou) or \
             (tendencia == "errar" and passou)
    critico = ("sucesso" if (d20 == 20 and passou)
               else "falha" if (d20 == 1 and not passou) else None)
    info = {
        "tipo": "combate",
        "personagem": char_id, "alvo": alvo_id, "arma": arma_id,
        "tendencia": tendencia,
        "resultado": "sucesso" if passou else "falha",
        "virada": virada, "critico": critico,
        "rolagem": {"d20": d20, "mod": mod, "vantagem_mod": vantagem_mod,
                    "total": total, "dc": dc},
    }
    if passou:
        return None, info
    rej = _fail("ataque_errou", alvo=alvo_id, personagem=char_id, arma=arma_id,
                tendencia=tendencia, virada=virada, critico=critico,
                rolagem=info["rolagem"])
    return rej, info


