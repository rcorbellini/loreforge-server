"""DECLARAÇÃO + CORPO da tool NARRATE (spec 038, L3).

narrate — controle de TURNO (não é de domínio): encerra o loop com o resumo
in-world. Migrada de `arbiter_tools/core.py` (deletado). TERMINAL (o corpo devolve
done=True). Sem gate — aparece sempre. Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

from .registro import ToolSpec, tool_spec


def _narrate(name: str, args: dict, ctx) -> tuple[dict, bool]:
    hint = (args.get("narrative_hint") or "").strip()
    if not hint:
        return ctx.err("informe 'narrative_hint' (resumo curto, in-world)"), False
    ctx.queue["narrative_hint"] = hint
    return {"ok": True}, True


NARRATE = tool_spec(ToolSpec(
    names=("narrate",),
    interna=True,
    description=("Encerra o turno com o resumo factual, curto e in-world do que "
                 "aconteceu. Nunca use termos de sistema. Chame por último, sempre."),
    params={"narrative_hint": {"type": "string"}},
    required=("narrative_hint",),
    apply=_narrate,
))
