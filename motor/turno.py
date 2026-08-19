"""O Motor / turno (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
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

from . import acougue, combate, comercio, conhecimento, conteiner, cozinha, cura, deslocamento, estado, fatos, intencoes, io, itens, memoria, narrate, percepcao, registro
# os executores não são mais importados AQUI: cada tool registra o próprio handler no
# seu módulo (spec 025). O despachante (apply_op) só consulta `registro`; importar os
# módulos acima já popula a tabela. O turno só usa os helpers de FINALIZAÇÃO abaixo.
from .estado import (
    _set_field,
)
from .io import (
    WRITE_LOCK,
    find_character_folder,
)
from .itens import (
    _apply_movement,
)
from .memoria import (
    _create_memories,
    _short_summary,
)
from .percepcao import (
    _scene_entities,
)


# Canais de CONTEXTO (não-op) que alguns executores precisam ler junto da op: o
# `learn` confere a citação contra o que o ator LEU (`lido`) e OUVIU (`falas`) no
# turno. A porta os repassa; sem eles, aprender recusaria por citação-não-confere.
_CONTEXT_CHANNELS = ("lido", "falas")


def apply_op(character_id: str, canal: str, op: dict, rolls=None,
             actor_folder=None, context=None) -> dict:
    """A PORTA ÚNICA de UMA ação (spec 025, 021 Fase C): aplica-e-registra uma op.
    TODA origem entra por aqui — a tool do Árbitro E o fallback de texto —, não há
    segundo caminho (coesão: é o que impede o funil de renascer, e o que garante um
    comportamento só). A ORDEM é de quem chama (as chamadas do Árbitro, ou a lista
    ordenada do fallback), nunca uma sequência fixa embutida. `context` traz os canais
    consultivos (lido/falas) que o executor precise. Assume/toma o WRITE_LOCK (RLock,
    reentrante). Devolve {applied, rejected, created}."""
    with WRITE_LOCK:
        if actor_folder is None:
            actor_folder = find_character_folder(character_id)
        if rolls is None:
            rolls = []
        res = {canal: [op]}
        if context:
            res.update(context)
        h = registro.get(canal)
        if h is None:
            return {"applied": [], "rejected": [], "created": [],
                    "viagens_interrompidas": []}
        applied, rejected, created = h(character_id, actor_folder, res, rolls)
        created, viagens = _publish_facts(
            character_id, canal, actor_folder, applied, rejected, list(created))
        return {"applied": applied, "rejected": rejected, "created": created,
                "viagens_interrompidas": viagens}


def _publish_facts(character_id: str, canal: str, actor_folder: Path,
                   applied: list, rejected: list, created: list) -> tuple[list, list]:
    """O 5º ancoradouro (spec 038, L1): embrulha CADA op aplicada/rejeitada num
    `Fato` e o PUBLICA no barramento (`fatos.publish`), no instante em que acontece
    — a cena daquele instante. As reações devolvem as consequências transversais
    que antes moravam no executor (memória do ator) e no `_finalize_turn` (leque de
    testemunha, interrupção-de-viagem). Separa o que é MEMÓRIA (`created`) do que é
    viagem interrompida (`{"personagem": ...}`, sem `id`)."""
    if not applied and not rejected:
        return created, []
    present, _o, _i = _scene_entities(actor_folder.parent)
    viagens: list = []

    def _spread(status: str, ops: list) -> None:
        for op in ops or []:
            if not isinstance(op, dict):
                continue
            fato = fatos.Fato(kind=canal, actor=character_id, canal=canal,
                              status=status, payload=op)
            for efeito in fatos.publish(fato, actor_folder, present):
                if isinstance(efeito, dict) and "personagem" in efeito \
                        and "id" not in efeito:
                    viagens.append(efeito)
                else:
                    created.append(efeito)

    _spread("applied", applied)
    _spread("rejected", rejected)
    return created, viagens


def _ensure_actor_touched(character_id: str, resolution: dict, outcome: dict) -> None:
    """FR-014 (spec 020): a ação do ator é tocada UMA vez no turno se NADA já a tocou.
    É pós-condição de FRONTEIRA — sobre a AUSÊNCIA de fato, não sobre um fato —, o
    resíduo honesto do finado `_finalize_turn` (spec 038, L4). Resolve a pasta ATUAL
    (o ator pode ter se movido no turno: carry/travel)."""
    if any(isinstance(a, dict) and a.get("target") == character_id
           for a in outcome.get("applied") or []):
        return
    hint = " ".join((resolution.get("narrative_hint") or "").split())
    new_action = _short_summary(hint, limit=120) if hint else "reagiu à situação"
    af_now = find_character_folder(character_id)
    _set_field(af_now, "status.action", new_action)
    outcome["applied"].append({
        "target": character_id, "path": "status.action", "value": new_action,
        "reason": "garantia de consequência (FR-014)"})


def apply_resolution(character_id: str, resolution: dict,
                     ensure_action: bool = True) -> dict:
    """REPLAY em lote (spec 025/038): quebra a resolução em ações e empurra CADA UMA
    pela porta única `apply_op`. Usado pelo fallback de texto e pelos testes; o
    tool-calling chama `apply_op` por-op direto.

    Spec 038 (L4): `_TURN_STEPS` MORREU — o replay aplica os canais na ORDEM DA
    RESOLUÇÃO (insertion order, R6); no caminho autoritativo a ordem já é a do
    Árbitro. Os canais MUTADORES não são mais uma lista à mão: são os que têm handler
    no registro (`registro.get(canal)`), + `memories` (criado à parte). O fim-de-turno
    (`_finalize_turn`) dissolveu-se: sobra a garantia-de-consequência (FR-014) como
    pós-condição e a partida por rota por último."""
    if resolution.get("_applied_in_loop"):
        return resolution
    with WRITE_LOCK:
        movement = resolution.get("movement")
        # canal mutador = tem handler no registro; `memories` é criado à parte. A
        # pertença DERIVA do registro (spec 038, L4) — sem lista à mão a manter.
        _outras = any(resolution.get(c) for c in resolution
                      if registro.get(c) is not None or c == "memories")
        if isinstance(movement, dict) and movement.get("enter_route") and not _outras:
            return _apply_movement(character_id, movement["enter_route"])

        actor_folder = find_character_folder(character_id)
        present_chars, _po, _pi = _scene_entities(actor_folder.parent)
        rolls: list[dict] = []
        context = {k: resolution[k] for k in _CONTEXT_CHANNELS if resolution.get(k)}
        outcome = {
            "applied": [], "rejected": [], "rolls": rolls,
            "memories_created": _create_memories(present_chars, resolution),
            "viagens_interrompidas": [],
        }
        # o espelho `<canal>_applied` também DERIVA do registro (mutations → 'applied').
        for canal in registro._HANDLERS:
            if canal != "mutations":
                outcome.setdefault(canal + "_applied", [])
        def _run(canal: str, ops: list) -> None:
            for op in ops or []:
                frag = apply_op(character_id, canal, op, rolls, actor_folder, context)
                outcome["rejected"] += frag["rejected"]
                outcome["memories_created"] += frag["created"]
                outcome["viagens_interrompidas"] += frag.get("viagens_interrompidas", [])
                if canal == "mutations":
                    outcome["applied"] += frag["applied"]
                else:
                    outcome[canal + "_applied"] += frag["applied"]

        # ORDEM (spec 038 L4 / R6): os canais aplicam na ORDEM DA RESOLUÇÃO — MENOS a
        # única causalidade que sobrevive ao fim do _TURN_STEPS: um contêiner ABRE
        # antes de receber/ceder conteúdo e FECHA depois. Então lock 'open' primeiro,
        # lock 'close' por último, e o resto no meio, na ordem escrita. (Derivado do
        # próprio campo `op`, não de uma lista de fases à mão.) No tool-calling a
        # ordem já é a do Árbitro (uma op por apply_op); isto só rege o replay em lote.
        _locks = resolution.get("lock_ops") or []
        _run("lock_ops", [o for o in _locks if isinstance(o, dict) and o.get("op") == "open"])
        for canal in resolution:
            if canal == "lock_ops" or registro.get(canal) is None:
                continue
            _run(canal, resolution.get(canal))
        _run("lock_ops", [o for o in _locks if isinstance(o, dict) and o.get("op") == "close"])
        # fim de turno (ex-`_finalize_turn`, dissolvido — spec 038 L4)
        if ensure_action:
            _ensure_actor_touched(character_id, resolution, outcome)
        if isinstance(movement, dict) and movement.get("enter_route") \
                and not (resolution.get("carry_ops") or []):
            mov = _apply_movement(character_id, movement["enter_route"])
            outcome["applied"] = outcome.get("applied", []) + mov.get("applied", [])
            outcome["rejected"] = outcome.get("rejected", []) + mov.get("rejected", [])
            if mov.get("movement"):
                outcome["movement"] = mov["movement"]
            if mov.get("narrative_hint") and not outcome.get("narrative_hint"):
                outcome["narrative_hint"] = mov["narrative_hint"]
        return outcome
