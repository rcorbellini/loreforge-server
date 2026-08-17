"""O Motor / conteiner — PRIMITIVAS (item 31 §3: DDD por domínio).

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

from .. import estado, fisica, io, itens, memoria, registro
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


def check_trava_item(actor_folder: Path, actor_id: str, cont_id: str, acao: str,
                     lock: dict, exclude_folder: Path) -> dict | None:
    """Trava tipo `item` (guichê único): passa se o ator tem o item exigido."""
    required = lock.get("required")
    if has_accessible_item(actor_folder, required, exclude_folder):
        return None
    valores = {"container": cont_id, "acao": acao, "tipo": "item",
               "item_requerido": required, "personagem": actor_id}
    if lock.get("deny_reason"):
        valores["motivo"] = lock["deny_reason"]
    return _fail("trava_nao_satisfeita", **valores)


def _find_lockable(target_id: str, location_folder: Path, present_chars: dict,
                   present_objects: dict, actor_folder: Path):
    """Localiza um contêiner-alvo de open/close: object presente ou item-contêiner
    acessível. Retorna (pasta, frontmatter, filename) ou None."""
    if target_id in present_objects:
        folder = present_objects[target_id]
        fm, _ = read_doc(folder / "object.md")
        return folder, fm, "object.md"
    folder = _find_item_folder_in_scene(target_id, actor_folder)
    if folder is not None:
        fm, _ = read_doc(folder / "item.md")
        return folder, fm, "item.md"
    return None


