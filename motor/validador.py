"""O Motor / validador (spec 021 — extraído de __init__).

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

from . import fisica, io
from .fisica import (
    _direct_items,
    is_closed,
    item_slot,
)
from .io import (
    WORLD_DIR,
    _is_valid,
    read_doc,
)


def duplicate_ids() -> list[dict]:
    """Ids que aparecem em mais de um arquivo — integridade, não estilo.

    O mundo é arquivo e a topologia é a pasta, então id repetido não dá erro:
    quem escrever por último ganha, e o resto some sem avisar. Já mordeu duas
    vezes (moedas na spec 011, memórias na 013). Varrer é barato; descobrir
    depois que um item evaporou, não.
    """
    por_id: dict[str, list[str]] = {}
    for path in sorted(WORLD_DIR.rglob("*.md")):
        try:
            fm, _ = read_doc(path)
        except OSError:
            continue
        if not fm or "type" not in fm:
            continue  # não é entidade
        ident = fm.get("id")
        if ident:
            por_id.setdefault(ident, []).append(str(path.relative_to(WORLD_DIR)))
    return [{"id": ident, "paths": paths}
            for ident, paths in sorted(por_id.items()) if len(paths) > 1]


def validate_world() -> list[dict]:
    """Varre o mundo e retorna os arquivos de entidade com schema inválido.

    Cada problema: {path, id, type, errors:[...]}. Lista vazia = mundo íntegro.
    Arquivos sem frontmatter/`type` (ex.: READMEs) são ignorados — não são entidades.
    Não altera nada: é só um relatório para o autor (startup log e /api/world/health).
    """
    problems = []
    for path in sorted(WORLD_DIR.rglob("*.md")):
        try:
            fm, _ = read_doc(path)
        except OSError as exc:
            problems.append({"path": str(path.relative_to(WORLD_DIR)), "id": None,
                             "type": None, "errors": [f"não foi possível ler: {exc}"]})
            continue
        if not fm or "type" not in fm:
            continue  # não é um arquivo de entidade
        errors = validator.validate(fm)
        if errors:
            problems.append({
                "path": str(path.relative_to(WORLD_DIR)),
                "id": fm.get("id"),
                "type": fm.get("type"),
                "errors": errors,
            })
    # id repetido é problema de MUNDO, não de arquivo: só aparece cruzando a
    # varredura inteira, e por isso nenhuma validação por arquivo o pegaria.
    for dup in duplicate_ids():
        outros = [p for p in dup["paths"]]
        for path_rel in dup["paths"]:
            problems.append({
                "path": path_rel, "id": dup["id"], "type": None,
                "errors": ["id duplicado: o mesmo id em "
                           + ", ".join(o for o in outros if o != path_rel)
                           + " — quem gravar por último apaga o outro"],
            })
    return problems


def migration_warnings() -> list[dict]:
    """Avisos (não erros) de migração para o modelo físico (spec 004, US4).

    Item filho direto de personagem SEM `state.slot` é mundo pré-004: o jogo o
    tolera como "segurado de cortesia" (não conta slot nem carga), mas o autor
    deve declarar o acoplamento ou movê-lo para um contêiner. Nada é expulso.
    """
    warns = []
    for path in sorted(WORLD_DIR.rglob("character.md")):
        for child, fm in _direct_items(path.parent):
            if _is_valid(fm) and item_slot(fm) is None:
                warns.append({
                    "path": str((child / "item.md").relative_to(WORLD_DIR)),
                    "id": fm.get("id"),
                    "aviso": ("item junto ao personagem sem acoplamento declarado "
                              "(pré-004): tratado como segurado de cortesia — "
                              "declare 'state.slot' ou mova para um contêiner"),
                })
    return warns


def deadlock_warnings() -> list[dict]:
    """Aviso AUTORAL (spec 005): contêiner fechado cuja trava de abertura exige um
    item que está DENTRO dele — sem arrombamento no MVP, é um deadlock escrito."""
    warns = []
    for fname, etype in (("object.md", "object"), ("item.md", "item")):
        for path in sorted(WORLD_DIR.rglob(fname)):
            fm, _ = read_doc(path)
            if not is_closed(fm):
                continue
            locks = fm.get("locks") if isinstance(fm.get("locks"), dict) else {}
            for lock in locks.get("open") or []:
                if not isinstance(lock, dict) or lock.get("type") != "item":
                    continue
                req = lock.get("required")
                for sub in path.parent.rglob("item.md"):
                    sub_fm, _ = read_doc(sub)
                    if sub_fm.get("id") == req:
                        warns.append({
                            "path": str(path.relative_to(WORLD_DIR)),
                            "id": fm.get("id"),
                            "aviso": (f"deadlock autoral: a chave '{req}' está "
                                      "dentro do próprio contêiner fechado que "
                                      "ela abre — mova a chave para fora"),
                        })
    return warns


def tool_activation_warnings() -> list[dict]:
    """Ids do manifesto de ativação (spec 038, US2) que não casam nenhuma tool
    registrada — typo ou refactor. AVISO, nunca fatal: o id órfão é ignorado."""
    from . import ativacao
    return [{"kind": "tool_ativacao_orfa", "id": tid,
             "detail": f"'{tid}' no manifesto de ativação não é uma tool conhecida — "
                       "ignorada"}
            for tid in ativacao.orphan_tool_ids()]


def world_warnings() -> list[dict]:
    """Todos os avisos não-fatais do mundo: migração (spec 004) + deadlock
    autoral (spec 005) + ativação de tools órfã (spec 038). Erros de schema
    continuam em validate_world()."""
    return migration_warnings() + deadlock_warnings() + tool_activation_warnings()
