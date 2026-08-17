"""O Motor / intencoes — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, registro
from ..io import (
    _fail,
    new_id,
    read_doc,
    write_doc,
)

# Duplicado de `validator.INTENTION_STATES` de propósito — mesmo padrão que
# `memoria._MEMORY_INTENSITIES` já usa: o Motor valida a PRÓPRIA regra de
# negócio (rejeitar graciosamente) antes de `write_doc` validar o SCHEMA
# (que levantaria exceção, não uma rejeição estruturada).
_INTENTION_STATUSES = {"ativa", "concluida", "abandonada"}

# Teto de exposição no contexto (Decisão 5, research.md da spec 026) — mesmo
# espírito de `memoria._MEMORY_CONTEXT_CAP`, mas aqui não há relógio de
# expiração: sem teto, um personagem mal-comportado acumularia intenções
# ativas sem limite. As mais RECENTES ficam; as mais antigas cedem lugar.
_INTENTION_CONTEXT_CAP = 20




from .primitivas import (  # noqa: F401
    close_intention,
    create_intention,
    get_active_intentions,
    update_intention,
)

@registro.handler("intentions")
def _h_intentions(character_id, actor_folder, res, rolls):
    """Handler AUTO-CONTIDO (spec 025): lê a própria pasta fresca, valida a
    PRÓPRIA regra de negócio (não confia no que `execute()` já validou —
    o fallback de texto/replay chega aqui sem ter passado por lá), aplica e
    devolve (applied, rejected, created). `created` fica vazio: intenção NÃO
    passa por `record_event` (Constitution Check do plan.md da 026 — ela
    mesma é o registro persistente, paralela a memória, não um eco dentro
    dela)."""
    applied, rejected = [], []
    if not res.get("intentions"):
        return applied, rejected, []
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected, []
    for op in res.get("intentions") or []:
        content = (op.get("content") or "").strip()
        status = op.get("status") or "ativa"
        intention_id = op.get("intention_id")
        if not content:
            rejected.append({**op, "why": "'content' vazio"})
            continue
        if status not in _INTENTION_STATUSES:
            rejected.append({**op, "why": f"'status' inválido: {status}"})
            continue
        if intention_id:
            if not update_intention(actor_folder, intention_id, content, status):
                rejected.append({**op, "why": "intention_id inexistente ou já "
                                              "não está ativa"})
                continue
            applied.append({**op, "intention_id": intention_id})
        else:
            new_iid = create_intention(actor_folder, content, status)
            applied.append({**op, "intention_id": new_iid})
    return applied, rejected, []
