"""Helper compartilhado dos selftests (spec 045) — substitui
`resolve_with_tools`/`scripted_loop`, que saíram do código de produção.

`resolve_with_tools` nunca teve lógica própria de validação/aplicação: era um
prompt (`TOOLS_SYSTEM_PROMPT`) e um `loop_fn` injetável em volta da MESMA
primitiva que `resolver_proposta` (o guichê único de produção, `app.py`) já
usa — `build_ctx` → `ctx.execute(nome, args)` (uma ou mais vezes) →
`finalize_turn`. `scripted_loop` (repetido em ~15 arquivos) só fazia
`for name, args in script: execute(name, args)` — nenhum teste real dependia
do prosa-degradation nem do prompt do loop antigo.

Este helper roda a MESMA cadeia direto, sem o `loop_fn` no meio — o teste
migrado exercita literalmente o mesmo caminho que o jogo real usa hoje.

Uso:
    from selftest_helpers import resolve_scripted
    out = resolve_scripted(intent, context, [("attack", {"alvo": "x"})])
"""
from __future__ import annotations

import arbiter


def resolve_scripted(intent: dict, context: dict, script: list[tuple[str, dict]],
                     *, ask=None, emit=None, captured: list | None = None) -> dict:
    """Substitui `resolve_with_tools(intent, context, scripted_loop(script, ...))`.

    `intent` é o mesmo dict de antes (`{"action": ..., "utterance": ...}`) — só
    `action`/`utterance` são lidos, pra montar a `prosa` que as réguas leem
    (idêntico ao que `resolve_with_tools` fazia internamente). `script` é a
    lista de `(nome, args)` NA ORDEM — o que `scripted_loop` executava, um a
    um, contra `execute`. Devolve o MESMO shape de `resolve_with_tools`
    (o dict de `finalize_turn`).

    `captured`, se passado, recebe o `result` de CADA `execute()`, na ordem —
    equivalente ao segundo argumento de `scripted_loop(script, captured)` (só
    `selftest_phase6.py` inspeciona resultado por chamada; a maioria só usa o
    outcome final).

    NÃO reproduz a degradação por prosa-em-texto (o modelo descrevendo a tool
    em vez de chamar): nenhum teste migrado dependia disso — todos scriptavam
    chamadas diretas. Se algum comportamento de teste depender de fato disso,
    ele precisa de tratamento à parte, não deste helper.
    """
    prosa = {k: v for k, v in {
        "acao": (intent or {}).get("action"),
        "fala": (intent or {}).get("utterance"),
    }.items() if v} if isinstance(intent, dict) else {}
    ctx = arbiter.build_ctx(context, emit=emit, ask=ask, prosa=prosa)
    for nome, args in script:
        result, _done = ctx.execute(nome, args)
        if captured is not None:
            captured.append(result)
    acao = (intent.get("action") if isinstance(intent, dict) else "") or ""
    return arbiter.finalize_turn(ctx, acao=acao)
