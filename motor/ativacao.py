"""O Motor / ativacao (spec 038, US2) — o Manifesto de Ativação de tools por-mundo.

Um mundo escolhe QUAIS tools a engine oferece, sem tocar em código. É config
BOOLEANA DE IDENTIDADE (Princípio XI: `id` é o caso-exceção do campo fixo) — não
descreve nem define tool, só liga/desliga por id. Mora num `.md` de topo do mundo
(`WORLD_DIR/world.md`), no frontmatter:

    tools_ativas: [take, give, narrate, ...]     # liga SÓ estas
    # — ou —
    tools_desativadas: [attack, steal]           # desliga estas sobre "todas"

Ausência dos dois (ou do arquivo) ⇒ TODAS as tools registradas ativas (default
explícito). Id que não casa nenhuma declaração vira AVISO (World Validator /
/api/world/health), é IGNORADO e NUNCA derruba o boot.

NÍVEL 1: lê o mundo (io) e o registro de declarações (registro). Não roda LLM.
"""
from __future__ import annotations

from . import io, registro

_MANIFEST_FILE = "world.md"


def _manifest() -> dict:
    path = io.WORLD_DIR / _MANIFEST_FILE
    if not path.exists():
        return {}
    try:
        fm, _ = io.read_doc(path)
    except Exception:
        return {}
    return fm if isinstance(fm, dict) else {}


def _ids(fm: dict, campo: str) -> list[str]:
    return [x for x in (fm.get(campo) or []) if isinstance(x, str)]


def active_tool_ids() -> set | None:
    """Conjunto de ids de tools ATIVAS neste mundo, ou None = TODAS (default).

    `tools_ativas` vence `tools_desativadas` se ambas existirem (o explícito manda).
    Filtra ao que está REGISTRADO — id órfão não vira tool (ver `orphan_tool_ids`)."""
    fm = _manifest()
    todas = set(registro.specs())
    if fm.get("tools_ativas") is not None:
        return set(_ids(fm, "tools_ativas")) & todas
    if fm.get("tools_desativadas") is not None:
        return todas - set(_ids(fm, "tools_desativadas"))
    return None


def is_active(name: str) -> bool:
    """A tool `name` é oferecida/resolvível neste mundo? (None = todas ⇒ True.)"""
    ativas = active_tool_ids()
    return ativas is None or name in ativas


def orphan_tool_ids() -> list[str]:
    """Ids citados no manifesto que não casam nenhuma declaração registrada — AVISO
    (ignorado, nunca derruba). Um refactor de tools ou um typo no manifesto aparece
    aqui, no mesmo canal do World Validator."""
    fm = _manifest()
    if not fm:
        return []
    todas = set(registro.specs())
    orfaos = {x for campo in ("tools_ativas", "tools_desativadas")
              for x in _ids(fm, campo) if x not in todas}
    return sorted(orfaos)
