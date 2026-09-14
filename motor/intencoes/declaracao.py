"""DECLARAÇÃO + CORPO da tool de INTENÇÕES (spec 038, L3).

set_intention — migrada de `arbiter_tools/intencoes.py` (deletado). Sem gate: nenhum
param obrigatório tem fonte-de-enum. Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

from ..io import _WHY_BY_REGRA as _FRASE
from ..registro import ToolSpec, tool_spec

# Os critérios que o mundo sabe conferir NESTA FATIA — leitura de campo, só.
# As outras três famílias (posse, lugar, fato lembrado) estão desenhadas em
# `specs/073-intention-cycle/research.md` §R2.
# UMA LISTA SÓ, e ela mora na PRIMITIVA que confere o critério.
#
# Isto nasceu duplicado — a tupla aqui e o `_CRITERIO_POR_CAMPO` em `primitivas.py`
# — e as duas ficaram iguais por um commit. É exatamente a segunda via do Princípio
# I: quem acrescentasse a quarta família editaria uma e esqueceria a outra, e o
# sintoma seria um critério que a tool oferece e o mundo não sabe conferir (ou o
# contrário) — em silêncio, com a suíte verde.
#
# US4 acrescentou `peca`: a carência do MUNDO entra pelo mesmo enum que a do corpo,
# porque é a mesma família — leitura de campo, só que num arquivo que não é o do
# corpo. As outras três (posse, lugar, fato lembrado) seguem desenhadas em
# `specs/073-intention-cycle/research.md` §R2, sem leitor.
from .primitivas import _CRITERIO_POR_CAMPO as _CRITERIOS


def _verbos_do_mundo() -> set:
    """Os verbos que EXISTEM e estão ativos neste mundo (FR-007).

    Sai do mesmo registro que monta a face, e respeita o manifesto de ativação
    (spec 038, US2) — um mundo que desligou `forge_weapon` não aceita um plano que
    o cite. Import tardio de propósito: `registro` já está carregado quando a tool
    roda, e amarrá-lo no topo faria ciclo.
    """
    from .. import ativacao, registro
    ativos = ativacao.active_tool_ids()
    nomes = {n for sp in registro.specs().values() for n in sp.names}
    return nomes if ativos is None else (nomes & set(ativos))


def _set_intention(name: str, args: dict, ctx) -> tuple[dict, bool]:
    content = (args.get("content") or "").strip()
    status = args.get("status") or "ativa"
    intention_id = args.get("intention_id")
    pronto_quando = (args.get("pronto_quando") or "").strip() or None
    if not content:
        return ctx.err("informe 'content' (o compromisso, em prosa)"), False
    if status not in ctx.INTENTION_STATUSES:
        return ctx.err(f"status '{status}' inválido", "status",
                       [{"id": s, "nome": s} for s in ctx.INTENTION_STATUSES]), False
    if intention_id:
        active_ids = {i["id"] for i in (ctx.context["self"].get("intentions") or [])
                      if i.get("id")}
        if intention_id not in active_ids:
            return ctx.err(f"intention_id '{intention_id}' não é uma intenção ativa "
                           "deste personagem", "intention_id",
                           [{"id": i, "nome": i} for i in sorted(active_ids)]), False
    # AS TRAVAS DO NASCIMENTO (spec 073, FR-003) — só ao CRIAR.
    #
    # Atualizar ou encerrar um compromisso que já existe não passa por elas: o que se
    # barra é um compromisso NASCER torto, não alguém mexer num que já vive. (E as
    # quatro intenções podres que já estão gravadas no mundo continuam intocadas —
    # o validador as aceita, e `fechar_por_criterio` simplesmente as ignora.)
    if not intention_id:
        from ..intencoes.primitivas import travas_do_nascimento
        eu = (ctx.context.get("self") or {}).get("name")
        trava = travas_do_nascimento(content, pronto_quando, eu)
        if trava:
            regra, valores = trava
            # ERRO CORRIGÍVEL x RECUSA DE MÉRITO — e a diferença custou uma corrida
            # de duas horas (medicoes.md §15).
            #
            # Medido em jogo: a Nerissa montou um plano BOM de oito passos (pedir o
            # caminho, viajar, colher a raiz, preparar) e mandou
            # `pronto_quando: "odila-aguadeira"` — o id de uma PESSOA, porque o
            # runtime não impõe o enum (spec 060: um id fora dele saiu 4/5) e o nome
            # do campo convida a responder "com quem". O mundo recusou com uma frase
            # solta, apontando o campo ERRADO (`content`) e ENGOLINDO a lista de
            # critérios válidos que a própria trava devolvia. A Mente não tinha como
            # corrigir, e não tentou de novo: UM `set_intention` em duas horas.
            #
            # As duas travas de VOCABULÁRIO são erro corrigível — ela quis dizer algo
            # real e nomeou errado —, então voltam com o CAMPO certo e os `validos`,
            # que é o que convida o retry. As outras são recusa de mérito (o
            # compromisso não devia nascer), e essas seguem sem lista: não há o que
            # corrigir num "isso já é verdade agora".
            campo = "pronto_quando" if regra in (
                "intencao_sem_criterio", "intencao_criterio_desconhecido") else "content"
            validos = [{"id": v, "nome": v} for v in (valores or {}).get("validos") or []]
            if not validos and campo == "pronto_quando":
                validos = [{"id": v, "nome": v} for v in sorted(_CRITERIOS)]
            return ctx.err(_FRASE[regra], campo, validos or None), False
        # E A GUARDA DO FR-013b: se o critério JÁ é verdade, a intenção nasceria
        # cumprida. Um saciado não firma compromisso de matar a fome — recusar é o
        # que evita criar lixo que fecha no mesmo instante.
        from ..intencoes.primitivas import criterio_cumprido
        if criterio_cumprido((ctx.context.get("self") or {}).get("needs"),
                             pronto_quando):
            return ctx.err(_FRASE["intencao_ja_cumprida"], "pronto_quando"), False
        # E A TRAVA DO PASSO SEM VERBO (FR-007). O caso do Tobias: "fazer um
        # inventário completo dos frascos de vidro" não nomeia ato nenhum que o
        # mundo saiba executar — nasce impossível, e nada percebia.
        #
        # A régua é o VOCABULÁRIO DO MUNDO, não a face da cena (ver a nota em
        # `primitivas.passos_sem_verbo`): um plano que atravessa cenas — "ir à
        # forja", depois "forjar" — é bom, e a face de quem está na praça não tem
        # `forge_weapon`. Validar contra a face rejeitaria os melhores planos.
        from ..intencoes.primitivas import passos_sem_verbo
        ruins = passos_sem_verbo(content, _verbos_do_mundo())
        if ruins:
            return ctx.err(_FRASE["intencao_passo_sem_verbo"], "content"), False

    ctx.queue["intentions"].append({"intention_id": intention_id,
                                    "content": content, "status": status,
                                    "pronto_quando": pronto_quando})
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
            "status": {"type": "string"},
            "pronto_quando": {"type": "string"}},
    required=("content",),
    enum_sources={"intention_id": lambda s: s.active_intention_ids,
                  "status": lambda s: sorted(s.INTENTION_STATUSES),
                  # VOCABULARIO FECHADO, nao lista de cena — por isso SOBREVIVE ao
                  # corte de `face._ENUM_QUE_FICA`, como `status` ja sobrevivia.
                  "pronto_quando": lambda s: sorted(_CRITERIOS)},
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
