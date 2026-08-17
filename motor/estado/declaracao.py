"""DECLARAÇÃO + CORPO da tool de ESTADO (spec 038, L3).

mutate — migrada de `arbiter_tools/estado.py` (deletado). SEM gate (a tool aparece
sempre): o enum de `target` entra por SCHEMA-CALLABLE (não `enum_sources`), então
não some quando a cena está vazia — byte-equivalente ao manifest sem `return None`.
"""
from __future__ import annotations

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


@inworld("applied")
def _iw_mutate(mut):
    # mutação sintética da FR-014 (tocada QUANDO NADA ACONTECEU) sai fora; o resto
    # (humor que virou, tocha que acendeu, item que quebrou) É coisa que aconteceu.
    if not isinstance(mut, dict) or "FR-014" in (mut.get("reason") or ""):
        return None
    alvo = mut.get("target")
    campo = (mut.get("path") or "").split(".")[-1]
    valor = mut.get("value")
    if not campo:
        return None
    return (f"{name_of(alvo)} agora está {valor}" if campo == "mood"
            else f"{campo} de {name_of(alvo)} passou a {valor}")


def _mutate(name: str, args: dict, ctx) -> tuple[dict, bool]:
    target, path = args.get("target"), args.get("path") or ""
    if not target or not path or "value" not in args:
        return ctx.err("informe 'target', 'path' e 'value'"), False
    if path == "state.fechado":  # sem bypass das travas (spec 005)
        return ctx.err("o fecho só muda pelas ferramentas open/close"), False
    root = path.split(".")[0]
    if target in ctx.chars:
        want = "status"
    elif target in ctx.objects or target in ctx.items:
        want = "state"
    else:
        ctx.rejections[("mutate", target, path)] = {
            "target": target, "path": path, "why": "alvo não presente na cena"}
        return ctx.err(f"alvo '{target}' não reconhecido", "target",
                       ctx.validos(ctx.chars, ctx.objects, ctx.items)), False
    if root != want:
        # tolerância: o modelo confunde status.*/state.*; auto-corrige o prefixo.
        if root in ("status", "state"):
            path = want + path[len(root):]
            root = want
        else:
            kind = "personagem" if want == "status" else "objeto/item"
            return ctx.err(f"alvo '{target}' é um {kind}: use '{want}.<campo>', "
                           f"não '{root}.'"), False
    ctx.queue["mutations"].append({"target": target, "path": path,
                                   "value": args.get("value"),
                                   "reason": args.get("reason") or ""})
    ctx.rejections.pop(("mutate", target, path), None)
    return {"ok": True, "aplicado": {"target": target, "path": path}}, False


MUTATE = tool_spec(ToolSpec(
    names=("mutate",),
    interna=True,
    description=(
        "Altera um campo de estado: status.<campo> para personagem (action, mood, hp, "
        "hunger, fatigue, conditions); state.<campo> para objeto ou item (trancado, "
        "quebrado, aceso...). Identidade nunca muda."
    ),
    params={
        "target": lambda s: {"type": "string", "enum": s.mut_targets},
        "path": {"type": "string", "description": "status.<campo> ou state.<campo>"},
        "value": {"description": "novo valor"},
        "reason": {"type": "string"},
    },
    required=("target", "path", "value"),
    apply=_mutate,
))
