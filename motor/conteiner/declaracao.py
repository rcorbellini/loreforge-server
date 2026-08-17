"""DECLARAÇÃO + CORPO das tools de CONTÊINER (spec 038, L3).

open/close — MESMO corpo, DUAS declarações (a variante é o `name`), cada uma com sua
fonte-de-enum (open→cand["open"], close→cand["close"]). Migradas de
`arbiter_tools/conteiner.py` (deletado). Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


@inworld("lock_ops_applied")
def _iw_lock(op):
    if op.get("noop"):
        return None
    alvo = name_of(op.get("target") or op.get("alvo"))
    return f"{'fechou' if op.get('op') == 'close' else 'abriu'} {alvo}"


def _open_close(name: str, args: dict, ctx) -> tuple[dict, bool]:
    target = args.get("target")
    lockables = {i: e for i, e in ctx.items.items() if e.get("container")}
    lockables.update({o: ctx.idx["objects"][o] for o in ctx.idx["objects_info"]})
    if target not in lockables:
        return ctx.err(f"'{target}' não abre nem fecha", "target",
                       ctx.validos(lockables)), False
    want_closed = name == "close"
    if ctx.fechado_state.get(target, False) == want_closed:
        est = "fechado" if want_closed else "aberto"
        return {"ok": True, "nota": f"'{target}' já está {est}"}, False
    # travas são segredo do mundo: o Motor valida na aplicação (D4); aqui só o estado.
    ctx.fechado_state[target] = want_closed
    ctx.queue["lock_ops"].append({"op": name, "target": target})
    return {"ok": True, "aplicado": {"op": name, "target": target}}, False


OPEN = tool_spec(ToolSpec(
    names=("open",),
    description=("Abre um contêiner fechado (baú, caixa, mochila). Pode "
                 "exigir chaves — o mundo valida e nega sem elas."),
    params={"target": {"type": "string"}},
    required=("target",),
    enum_sources={"target": "open"},
    apply=_open_close,
))


CLOSE = tool_spec(ToolSpec(
    names=("close",),
    description="Fecha um contêiner aberto. Pode exigir condições próprias.",
    params={"target": {"type": "string"}},
    required=("target",),
    enum_sources={"target": "close"},
    apply=_open_close,
))
