"""O Motor / estado — EXECUTORES (item 31 §3: DDD por domínio).

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

from .. import fisica, io, memoria, registro
from ..fisica import (
    _conditions_of,
)
from ..io import (
    read_doc,
    write_doc,
)



from .primitivas import (  # noqa: F401
    _clear_condition,
    _set_condition,
    _set_field,
)

def _apply_mutations(character_id: str, actor_folder: Path,
                     resolution: dict) -> tuple[list, list, bool]:
    """Aplica as `mutations` (status.* de personagem, state.* de object/item da cena).

    Executor AUTO-SUFICIENTE (spec 025): lê a PRÓPRIA cena fresca e valida alvo/raiz
    contra os arquivos reais. Devolve (applied, rejected, touched_actor) — o
    `touched_actor` alimenta a garantia de consequência (FR-014) do laço."""
    applied, rejected, touched_actor = [], [], False
    if not resolution.get("mutations"):
        return applied, rejected, touched_actor
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):  # spec 031/048: auto-suficiência, nível 0
        rejected.append(io._fail("descansando"))
        return applied, rejected, touched_actor
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)
    for mut in resolution.get("mutations", []):
        target = mut.get("target")
        path = mut.get("path", "")
        root = path.split(".")[0] if path else ""
        if path == "state.fechado":  # sem bypass das travas (spec 005)
            rejected.append({**mut, "why": "só abrir/fechar mudam o fecho"})
            continue
        if target in present_chars:
            kind, folder = "character", present_chars[target]
        elif target in present_objects:
            kind, folder = "object", present_objects[target]
        elif target in present_items:
            kind, folder = "item", present_items[target]
        else:
            rejected.append({**mut, "why": "alvo não presente na cena"})
            continue
        if root in io._IMMUTABLE_ROOTS_BY_KIND[kind]:
            rejected.append({**mut, "why": "identidade é imutável por ação"})
            continue
        mutable_root = io._MUTABLE_ROOT_BY_KIND[kind]
        if root != mutable_root:
            rejected.append({**mut, "why": f"só '{mutable_root}.*' é mutável"})
            continue
        _set_field(folder, path, mut.get("value"), filename=io._ENTITY_FILE_BY_KIND[kind])
        applied.append(mut)
        if target == character_id:
            touched_actor = True
    return applied, rejected, touched_actor


@registro.handler("mutations")
def _h_mutations(cid, af, res, rolls):
    applied, rejected, _touched = _apply_mutations(cid, af, res)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)
