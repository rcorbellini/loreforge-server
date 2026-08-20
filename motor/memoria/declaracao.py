"""DECLARAÇÃO + CORPO das tools de MEMÓRIA (spec 038, L3).

create_memory + sleep (sem gate) + accuse (gate no alvo). Migradas de
`arbiter_tools/memoria.py` (deletado). O enum de `create_memory`/`accuse.memoria_id`
entra por SCHEMA-CALLABLE (não `enum_sources`) para NÃO gatear — casando o manifest
que sempre aparecia. `import motor` só em RUNTIME. Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

import motor

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec
from .primitivas import DOMAINS

_STR = {"type": "string"}


def _create_memory(name: str, args: dict, ctx) -> tuple[dict, bool]:
    target = args.get("target")
    content = (args.get("content") or "").strip()
    intensity = args.get("intensity")
    domain = args.get("domain")
    if target not in ctx.chars:
        return ctx.err(f"alvo '{target}' não é um personagem presente", "target",
                       ctx.validos(ctx.chars)), False
    if not content:
        return ctx.err("informe 'content' (a lembrança em 1ª pessoa)"), False
    if intensity not in ctx.MEMORY_INTENSITIES:
        return ctx.err(f"intensity '{intensity}' inválida", "intensity",
                       [{"id": i, "nome": i} for i in ctx.MEMORY_INTENSITIES]), False
    if domain not in DOMAINS:
        return ctx.err(f"domain '{domain}' inválido — decida a que prática pertence, "
                       "ou 'nenhuma'", "domain",
                       [{"id": d, "nome": d} for d in sorted(DOMAINS)]), False
    try:
        ttl = int(args.get("ttl_seconds"))
    except (TypeError, ValueError):
        return ctx.err("'ttl_seconds' deve ser um inteiro (segundos)"), False
    # `evento` VEM DE QUEM CHAMA (decisão do mantenedor, 2026-08-13): esta tool é
    # INTERNA — a caneta do mundo —, então nunca é a Mente escrevendo direto; há
    # sempre uma tool/origem por trás, e é ela que sabe que tipo de fato é aquele.
    #
    # Sem isto, 743 memórias nascidas em runtime (28% de TODO o acervo do mundo)
    # ficaram sem etiqueta nenhuma — texto bom, invisíveis ao casamento por TEMA do
    # `recall` e a qualquer régua que leia `evento`. O default nomeia a origem em vez
    # de deixar vazio: "registrado pelo mundo" é mais honesto que nada, e distingue
    # essas do resto sem fingir que são um evento de jogo.
    ctx.queue["memories"].append({"target": target, "content": content,
                                  "summary": args.get("summary"),
                                  "intensity": intensity, "ttl_seconds": ttl,
                                  "domain": domain,
                                  "evento": (args.get("evento") or "").strip() or "registro"})
    return {"ok": True, "aplicado": {"target": target}}, False


def _rest(op: str, falha: str):
    """O corpo de `sleep` e o de `wake_up` — DOIS corpos, um molde.

    Item 50 (decisão do mantenedor): deitar e despertar não são a mesma ação vista de
    dois lados. Pré-condição oposta (acordado × dormindo), efeito oposto (entra em
    repouso × sai dele), e só uma tem desfecho graduado (a fadiga recuperada depende
    da duração; deitar não recupera nada). Eram uma tool alternadora que decidia qual
    das duas era pelo ESTADO DO ARQUIVO, em silêncio.

    O que se ganha não é elegância: é a ESCOLHA DA MENTE. Medido no item 30 — com a
    face oferecendo `sleep` a quem dorme e o jogador pedindo "acorda", a Mente acerta
    6 de 10; com o MESMO corpo exposto como `wake_up`, 10 de 10. Nome de capacidade é
    interface, não etiqueta.

    O que fica compartilhado é só o encanamento (uma op, um canal), e é por isso que
    isto é uma fábrica de dois corpos em vez de um corpo com `if`: a intenção viaja
    no `op` e o executor VALIDA a pré-condição, em vez de adivinhá-la.
    """
    def corpo(name: str, args: dict, ctx) -> tuple[dict, bool]:
        rej = ctx.apply_op_now("rest_ops", {"op": op})
        if rej:
            if "regra" in rej:
                return ctx.err(motor._WHY_BY_REGRA.get(rej["regra"], rej["regra"]),
                               rej=rej), False
            return ctx.err(rej.get("why") or falha), False
        return {"ok": True, "aplicado": {"ator": ctx.actor}}, False
    return corpo


def _accuse(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo_ac = args.get("alvo")
    if alvo_ac not in ctx.cand["acusar_alvo"]:
        return ctx.err(f"'{alvo_ac}' não é alguém sobre quem você tem memória", "alvo",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c in ctx.cand["acusar_alvo"]})), False
    memoria_id = args.get("memoria_id")
    if memoria_id not in ctx.cand["acusar_memorias"]:
        return ctx.err(f"'{memoria_id}' não é uma memória sua válida", "memoria_id",
                       list(ctx.cand["acusar_memorias"])), False
    rej = ctx.apply_op_now("accuse_ops", {"alvo": alvo_ac, "memoria_id": memoria_id})
    if rej:
        return ctx.err(rej.get("why") or "não foi possível acusar"), False
    return {"ok": True, "aplicado": {"alvo": alvo_ac}}, False


def _accuse_desc(s):
    # a lista de evidências entra na DESCRIÇÃO (não só no enum): um id sem contexto
    # não dá ao Árbitro como escolher com critério.
    evid = s.cand["acusar_memorias"]
    listagem = "; ".join(
        f"{mid} (sobre {motor.name_of(info['sobre'])}: {info['resumo']})"
        for mid, info in sorted(evid.items()))
    return (
        "Confronta outro personagem presente com algo que você "
        "REALMENTE se lembra sobre ele — viveu ou testemunhou. "
        "Referencie a memória (memoria_id) e diga quem é o alvo "
        "(precisam bater: o alvo tem de estar envolvido na memória "
        "escolhida). Isso registra, na hora, que você o acusou e que "
        "ele foi acusado — quem mais estiver por perto pode perceber "
        "a cena. NÃO decide como ele reage (isso é outra ação, se "
        "acontecer) e NÃO move nenhum item. Memórias disponíveis: "
        f"{listagem}.")


CREATE_MEMORY = tool_spec(ToolSpec(
    names=("create_memory",),
    interna=True,
    description=(
        "Registra uma lembrança em UM personagem presente, escrita na perspectiva dele "
        "(1ª pessoa). Chame uma vez por pessoa marcada. 'domain' é obrigatório: a que "
        "prática esta lembrança pertence (combate, crime, comercio, social, "
        "deslocamento) — ou 'nenhuma' se for puramente social/afetiva, sem prática "
        "nenhuma associada. Você SEMPRE decide, mesmo que a resposta seja 'nenhuma'. "
        "'evento' é QUE TIPO DE FATO é este (attack, transfer, promise, hearsay…) — "
        "quem chama sabe, e é o que deixa a lembrança achável POR TEMA depois."
    ),
    params={
        "target": lambda s: {"type": "string", "enum": s.chars},
        "content": _STR,
        "summary": _STR,
        "intensity": lambda s: {"type": "string", "enum": s.MEMORY_INTENSITIES},
        "ttl_seconds": {"type": "integer"},
        "domain": {"type": "string", "enum": sorted(DOMAINS)},
        "evento": _STR,
    },
    required=("target", "content", "intensity", "ttl_seconds", "domain"),
    apply=_create_memory,
))


SLEEP = tool_spec(ToolSpec(
    names=("sleep",),
    description=(
        "O personagem se deita para descansar e adormece. Nada é recuperado AGORA: "
        "o que a fadiga devolve depende de quanto tempo ele ficar dormindo, e isso "
        "só se sabe ao acordar. Enquanto dorme, ele não faz mais nada — nem percebe "
        "quem chega."
    ),
    params={},
    required=(),
    apply=_rest("sleep", "não foi possível descansar"),
))


WAKE_UP = tool_spec(ToolSpec(
    names=("wake_up",),
    description=(
        # A descrição ABRE dizendo o estado, e isso não é enfeite: ela é o texto
        # player-facing (fonte única, item 036), e é dela que sai a explicação quando
        # a cena só oferece esta capacidade. Sem o "está dormindo" aqui, o jogador lia
        # que o personagem "hesitou" e nunca descobria que ele dormia — o defeito que
        # a spec 041 consertou, e que uma descrição só sobre o DESPERTAR reabriria.
        "O personagem está dormindo, e esta é a ação de despertar e se levantar. "
        "Uma noite completa devolve toda a fadiga; acordar cedo devolve só uma "
        "fração — e só um descanso de qualidade (metade ou mais da fadiga "
        "recuperada) pesa em compromissos seus ainda não cumpridos, na memória de "
        "quem prometeu."
    ),
    params={},
    required=(),
    # SÓ existe dormindo — e, enquanto ele dorme, é a ÚNICA que existe. O gate de
    # descanso lê esta marca em vez de escrever a face à mão (ver `registro.ToolSpec`).
    only_while_resting=True,
    apply=_rest("wake_up", "não foi possível acordar"),
))


ACCUSE = tool_spec(ToolSpec(
    names=("accuse",),
    description=_accuse_desc,
    params={
        "alvo": _STR,
        "memoria_id": lambda s: {"type": "string", "enum": sorted(s.cand["acusar_memorias"])},
    },
    required=("alvo", "memoria_id"),
    enum_sources={"alvo": "acusar_alvo"},
    apply=_accuse,
))


# --------------------------------------------------------------------------- #
# FRASES IN-WORLD (spec 038) — o que VOLTA para A Mente em `aconteceu`.
#
# Sem construtor registrado aqui o canal é MUDO: `aconteceu` sai vazio e o único
# retorno é o `narrative_hint`, que é a prosa que A PRÓPRIA Mente escreveu. Ela
# então age contra o eco de si mesma. Foi assim que a Elga dormiu e acordou 61
# vezes em 12h recuperando ZERO fadiga (2026-08-20): o dado estava no outcome
# (`fadiga_recuperada: 0`), e ninguém o traduzia.
# --------------------------------------------------------------------------- #

@inworld("rest_ops_applied")
def _iw_rest(op):
    if op.get("iniciou_descanso"):
        return "deitou e pegou no sono"
    if not op.get("acordou"):
        return None
    # a frase do sono RUIM é a razão de este construtor existir: ela é o único
    # jeito de A Mente saber que deitar de novo não vai adiantar.
    return {"inteiro": "acordou inteiro, o corpo descansado",
            "pouco": "acordou cedo demais: o corpo aproveitou pouco e o cansaço "
                     "ainda pesa",
            "nenhum": "acordou sem ter descansado NADA — mal fechou os olhos, e "
                      "o cansaço está inteiro onde estava"}.get(
        op.get("qualidade"), "acordou")


@inworld("accuse_ops_applied")
def _iw_accuse(op):
    return f"acusou {name_of(op.get('alvo'))} na cara, com a lembrança inteira"
