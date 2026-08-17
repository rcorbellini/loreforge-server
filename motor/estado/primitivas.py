"""O Motor / estado — PRIMITIVAS (item 31 §3: DDD por domínio).

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

from .. import fisica, io, memoria, registro
from ..fisica import (
    _conditions_of,
)
from ..io import (
    read_doc,
    write_doc,
)


def _set_condition(char_folder: Path, condition: str) -> None:
    """Acrescenta uma condição ao status sem duplicar. Nada é removido do mundo:
    a derrota é estado gravado, nunca arquivo apagado."""
    fm, body = read_doc(char_folder / "character.md")
    status = dict(fm.get("status") or {})
    conds = _conditions_of(fm)
    if condition not in conds:
        conds.append(condition)
    status["conditions"] = conds
    fm["status"] = status
    write_doc(char_folder / "character.md", fm, body)


def _clear_condition(char_folder: Path, condition: str) -> None:
    """Par exato de `_set_condition` (spec 032): remove uma condição da
    lista, sem erro se ela já estiver ausente. O ARQUIVO nunca é tocado
    além do campo — é a mesma disciplina de "nada se apaga", só que
    aplicada ao que já era gravável desde a spec 008."""
    fm, body = read_doc(char_folder / "character.md")
    status = dict(fm.get("status") or {})
    conds = [c for c in _conditions_of(fm) if c != condition]
    status["conditions"] = conds
    fm["status"] = status
    write_doc(char_folder / "character.md", fm, body)


def _set_field(entity_folder: Path, path: str, value, filename: str = "character.md") -> None:
    """Aplica uma mutação `<raiz>.<campo>` a um character.md/object.md e grava atômico."""
    fm, body = read_doc(entity_folder / filename)
    parts = path.split(".")
    node = fm
    for key in parts[:-1]:
        nxt = node.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            node[key] = nxt
        node = nxt
    node[parts[-1]] = value
    write_doc(entity_folder / filename, fm, body)


