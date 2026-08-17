"""Camada TOOLS — INFRA compartilhada do lado-Árbitro (spec 038, pós-L3).

Só resta a BASE: o builder de FACE genérico (`build_face`), a recusa arbitrada
(`_arb_deny`, via `ctx.arb_deny`) e os registros `HANDLERS`/`MANIFESTS` (vazios).
TODAS as tools migraram para declarações co-localizadas no Motor
(`motor/<dom>/declaracao.py`, via `@tool_spec`): a FACE deriva de `build_face` e o
despacho roda `ToolSpec.apply`. Os antigos `arbiter_tools/<dom>.py` (um por família)
foram deletados ao longo do L2/L3.
"""
from .base import HANDLERS, MANIFESTS, build_face, manifest, tool  # noqa: F401
