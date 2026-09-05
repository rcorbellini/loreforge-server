"""DECLARAÇÃO + CORPO da tool de INTENÇÕES (spec 038, L3).

set_intention — migrada de `arbiter_tools/intencoes.py` (deletado). Sem gate: nenhum
param obrigatório tem fonte-de-enum. Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

from ..registro import ToolSpec, tool_spec


def _set_intention(name: str, args: dict, ctx) -> tuple[dict, bool]:
    content = (args.get("content") or "").strip()
    status = args.get("status") or "ativa"
    intention_id = args.get("intention_id")
    if not content:
        return ctx.err("informe 'content' (o compromisso, em prosa)"), False
    if status not in ctx.INTENTION_STATUSES:
        return ctx.err(f"status '{status}' inválido", "status",
                       [{"id": s, "nome": s} for s in ctx.INTENTION_STATUSES]), False
    if intention_id:
        active_ids = {i["id"] for i in (ctx.context.get("intentions") or [])
                      if i.get("id")}
        if intention_id not in active_ids:
            return ctx.err(f"intention_id '{intention_id}' não é uma intenção ativa "
                           "deste personagem", "intention_id",
                           [{"id": i, "nome": i} for i in sorted(active_ids)]), False
    ctx.queue["intentions"].append({"intention_id": intention_id,
                                    "content": content, "status": status})
    return {"ok": True, "aplicado": {"intention_id": intention_id or "(nova)"}}, False


SET_INTENTION = tool_spec(ToolSpec(
    names=("set_intention",),
    description=(
        "Use para registrar ou atualizar um COMPROMISSO de médio/longo prazo do "
        "PRÓPRIO personagem — algo concreto que sobrevive a esta cena, nomeando "
        "com quem ou com o quê. Chame quando ele DECIDE algo que passa a valer "
        "dali pra frente, sozinho ou com outra pessoa — não para um mandado "
        "comum que se esgota neste turno. Sem intention_id, cria um compromisso "
        "novo. Com intention_id (um dos ativos, vem no contexto), atualiza ou "
        "encerra (status: concluida/abandonada) — reescreva content por "
        "inteiro, nunca um trecho."
    ),
    params={"intention_id": {"type": "string"}, "content": {"type": "string"},
            "status": {"type": "string"}},
    required=("content",),
    enum_sources={"intention_id": lambda s: s.active_intention_ids,
                  "status": lambda s: sorted(s.INTENTION_STATUSES)},
    apply=_set_intention,
))


# NÃO existe `@inworld("intentions_applied")`, e é decisão, não esquecimento.
#
# `aconteceu` carrega O QUE O MUNDO SABE E A MENTE NÃO — é por isso que ele
# existe: acordar sem ter descansado é fato do corpo que só o Motor mediu. Uma
# DECISÃO é o inverso exato: a Mente acabou de tomá-la, foi ela que chamou a
# tool, e o mundo não viu nada (decidir não tem plateia). Devolver "assentou uma
# decisão: X" seria o Motor contando ao personagem o que ele mesmo pensou — a
# fronteira que `loreforge-arbiter-boundary` protege, e o mesmo motivo pelo qual
# `create_memory` também não tem frase. O relato mora no `narrative_hint`.
#
# Guardado por `selftest_phase28.py` ("nenhuma linha nova em inworld_effects").
