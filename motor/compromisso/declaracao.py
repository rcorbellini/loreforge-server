"""DECLARAÇÃO + CORPO da tool de COMPROMISSO (spec 038, L3).

promise — migrada de `arbiter_tools/compromisso.py` (deletado). Gate no `para`
(outro presente). `import motor` só em RUNTIME (_WHY_BY_REGRA). Byte-equivalente.
"""
from __future__ import annotations

import motor

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


def _promise(name: str, args: dict, ctx) -> tuple[dict, bool]:
    para = args.get("para")
    if para not in ctx.chars or para == ctx.actor:
        return ctx.err(f"destino '{para}' não é outro personagem presente", "para",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    expectativa = (args.get("expectativa") or "").strip()
    if not expectativa:
        return ctx.err("informe 'expectativa'"), False
    rej = ctx.apply_op_now("promise_ops", {"para": para, "expectativa": expectativa})
    if rej:
        if "regra" in rej:
            return ctx.err(motor._WHY_BY_REGRA.get(rej["regra"], rej["regra"]), rej=rej), False
        return ctx.err(rej.get("why") or "não foi possível prometer isso"), False
    return {"ok": True, "aplicado": {"para": para}}, False


PROMISE = tool_spec(ToolSpec(
    names=("promise",),
    description=(
        "Registra um COMPROMISSO VERBAL com outro personagem presente — "
        "uma promessa, um juramento. Nunca move item (para isso, use give "
        "— com emprestimo=true se a posse deve continuar sua). Numa "
        "chamada só, isso FICA GRAVADO como algo que aconteceu (memória, "
        "nos dois lados) E como algo que você mesmo pretende cobrar ou "
        "lembrar depois (sua própria intenção). Use expectativa para "
        "escrever o que se espera — 'que ele devolva na próxima vez que "
        "nos virmos', 'que ela nunca conte o que viu'. Reforça (não "
        "substitui) um empréstimo mecânico: dá pra prometer devolver algo "
        "que acabou de ser emprestado via give."
    ),
    params={"para": {"type": "string"}, "expectativa": {"type": "string"}},
    required=("para", "expectativa"),
    enum_sources={"para": "give_to"},
    apply=_promise,
))


@inworld("promise_ops_applied")
def _iw_promise(op):
    alvo = name_of(op.get("para"))
    expectativa = (op.get("expectativa") or "").strip()
    if not expectativa:
        return f"fez uma promessa a {alvo}"
    return f"prometeu a {alvo}: {expectativa}"
