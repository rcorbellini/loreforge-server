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
        "Registra ou atualiza um COMPROMISSO de médio/longo prazo do PRÓPRIO "
        "personagem — uma promessa, um plano, um objetivo que sobrevive a esta "
        "cena. Chame quando a ação que você está resolvendo ESTABELECE, "
        "ATUALIZA ou ENCERRA algo assim (prometeu ajudar alguém, descobriu que "
        "o plano não faz mais sentido) — INCLUSIVE quando o personagem resolve "
        "algo SOZINHO, sem prometer a ninguém: não precisa de outra pessoa "
        "envolvida. O sinal é a fala se ler como uma DECISÃO que passa a valer "
        "dali pra frente ('resolvo que...', 'decido que, a partir de agora...'), "
        "não apenas 'ele foi fazer algo' (um mandado comum que se esgota neste "
        "turno). NÃO é para toda ação — a maioria dos turnos não precisa desta "
        "tool, e um mandado do tipo 'vá buscar isto'/'converse com aquele' NÃO "
        "vira intenção sozinho. Para atualizar o progresso ou encerrar (status: "
        "concluida/abandonada) uma intenção já existente, informe intention_id "
        "(ids ativos do personagem vêm no contexto) e reescreva content por "
        "inteiro — nunca um trecho. Sem intention_id, cria uma intenção nova."
    ),
    params={"intention_id": {"type": "string"}, "content": {"type": "string"},
            "status": {"type": "string"}},
    required=("content",),
    enum_sources={"intention_id": lambda s: s.active_intention_ids,
                  "status": lambda s: sorted(s.INTENTION_STATUSES)},
    apply=_set_intention,
))
