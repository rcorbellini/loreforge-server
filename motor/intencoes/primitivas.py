"""O Motor / intencoes — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
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



def create_intention(folder: Path, content: str, status: str = "ativa",
                     memoria_id: str | None = None) -> str:
    """Cria uma intenção nova na pasta de quem a possui. Devolve o id novo.

    `memoria_id` (spec 030, opcional): quando a intenção nasce de um
    compromisso (`prometer`, spec 027), referencia a memória ORIGINAL desse
    compromisso, na mesma pasta — é o que permite à Frente D (dormir com
    pendência) achar qual memória intensificar, sem inferir por conteúdo.
    Mesma identidade-por-id de `intention_id`/`memoria_id` em outras tools
    (`give`/`acusar`), nunca interpretação."""
    now = int(time.time())
    iid = new_id("int")
    fm = {
        "type": "intention", "id": iid, "status": status,
        "created_ts": now, "updated_ts": now,
    }
    if memoria_id:
        fm["memoria_id"] = memoria_id
    write_doc(folder / "intentions" / f"{iid}.md", fm, content)
    return iid


def update_intention(folder: Path, intention_id: str, content: str,
                     status: str = "ativa") -> bool:
    """Reescreve uma intenção EXISTENTE no lugar (mesmo arquivo, mesmo id).

    Só opera sobre intenção ATIVA — não reabre concluída/abandonada (uma
    continuação nasce como intenção nova, com o próprio id: research.md,
    Decisão 4). Devolve False se o id não existir nesta pasta ou não estiver
    ativa; quem chama decide como relatar isso (rejeição estruturada)."""
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return False
    fm, _ = read_doc(path)
    if fm.get("status") != "ativa":
        return False
    fm["status"] = status
    fm["updated_ts"] = int(time.time())
    write_doc(path, fm, content)
    return True


def close_intention(folder: Path, intention_id: str,
                    status: str = "concluida") -> bool:
    """Fecha uma intenção ATIVA da PRÓPRIA pasta SEM reescrever o conteúdo
    (spec 027) — usado quando quem fecha é um efeito colateral de `give`/
    `trade` cumprindo um compromisso, não o Árbitro autorando texto novo
    (`set_intention`, que sempre reescreve o corpo inteiro). Mesmas regras de
    `update_intention` (só ATIVA, só da própria pasta); devolve False sem
    tocar o arquivo se não existir ou já não estiver ativa."""
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return False
    fm, body = read_doc(path)
    if fm.get("status") != "ativa":
        return False
    return update_intention(folder, intention_id, body, status=status)


def get_active_intentions(folder: Path) -> list[dict]:
    """Intenções ATIVAS de quem possui `folder`, para o contexto (consultivo de
    client, Princípio IX nível 2) — mesmo shape enxuto de `data-model.md`:
    {id, status, content}. Encerradas somem daqui, mas continuam no disco."""
    dir_ = folder / "intentions"
    if not dir_.exists():
        return []
    out = []
    for path in sorted(dir_.glob("*.md")):
        fm, body = read_doc(path)
        if fm.get("status") != "ativa":
            continue
        out.append({"id": fm.get("id"), "status": fm.get("status"),
                    "content": body.strip()})
    if len(out) > _INTENTION_CONTEXT_CAP:
        out = out[-_INTENTION_CONTEXT_CAP:]  # as mais RECENTES ficam
    return out


