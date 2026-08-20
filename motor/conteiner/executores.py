"""O Motor / conteiner — EXECUTORES (item 31 §3: DDD por domínio).

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

from .. import estado, fisica, io, itens, memoria, registro, trabalho
from ..fisica import (
    is_closed,
)
from ..io import (
    _fail,
    _rejection,
    read_doc,
    write_doc,
)
from ..itens import (
    _find_item_folder_in_scene,
    has_accessible_item,
)



from .primitivas import (  # noqa: F401
    _find_lockable,
    check_trava_item,
)

def _apply_lock_ops(character_id: str, actor_folder: Path, resolution: dict,
                    phase: str) -> tuple[list[dict], list[dict]]:
    """Aplica open/close (`lock_ops`) da fase pedida ("open" roda antes das
    transferências; "close" depois — contrato lock-tools.md), validando as travas
    de forma autoritativa. No-op quando o estado já é o desejado (nunca erro)."""
    applied, rejected = [], []
    if not resolution.get("lock_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    location_folder = actor_folder.parent
    present_chars, present_objects, _ = io._scene_entities(location_folder)  # cena fresca (025)
    for op in resolution.get("lock_ops") or []:
        if not isinstance(op, dict) or op.get("op") != phase:
            continue
        target = op.get("target")
        found = _find_lockable(target, location_folder, present_chars,
                               present_objects, actor_folder) if target else None
        if found is None:
            rejected.append(_rejection(op, _fail("destino_inacessivel",
                                                destino=target)))
            continue
        folder, fm, filename = found
        is_container = filename == "object.md" or isinstance(fm.get("container"), dict)
        if not is_container:
            rejected.append(_rejection(op, _fail("nao_tranca", target=target)))
            continue
        want_closed = phase == "close"
        if is_closed(fm) == want_closed:
            applied.append({"op": phase, "target": target, "noop": True})
            continue
        locks = fm.get("locks") if isinstance(fm.get("locks"), dict) else {}
        camadas = locks.get(phase) or []
        denied = None
        for lock in camadas:
            if not isinstance(lock, dict):
                continue
            if lock.get("type") == "item":
                denied = check_trava_item(actor_folder, character_id, target,
                                          phase, lock, folder)
            if denied:
                break
        if denied:
            rejected.append(_rejection(op, denied))
            continue
        estado._set_field(folder, "state.fechado", want_closed, filename=filename)  # spec 038: roteia
        applied.append({"op": phase, "target": target})
    return applied, rejected


@registro.handler("lock_ops")
def _h_lock(cid, af, res, rolls):
    ops = res.get("lock_ops") or []
    phase = ops[0].get("op") if ops and isinstance(ops[0], dict) else None
    applied, rejected = _apply_lock_ops(cid, af, res, phase)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)
