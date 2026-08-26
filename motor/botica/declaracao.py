"""DECLARAÇÃO + CORPO da tool de PREPARAR (spec 055).

`brew` combina N ingredientes sobre um recipiente, julgado numa ÚNICA chamada
ao Árbitro (`REGUA_PREPARAR`, cópia estrutural de `REGUA_COZINHAR`) — mesma
divergência de formato que `cook` já usa: como a BANDA do resultado só existe
DEPOIS da rolagem, a mesma chamada pede TRÊS descriptions candidatas (uma por
banda). O corpo ENFILEIRA via `ctx.apply_arbitrated` (mesmo padrão de `cook`),
sem importar o Árbitro. O recipiente NUNCA é escrito — divergência deliberada
de `forage`, molde EXATO de `cook` (o fogão de uma cozinha não trava, um
alambique também não).
"""
from __future__ import annotations

import json
from .. import juizo

from ..registro import ToolSpec, inworld, tool_spec


# --- As quatro réguas de `brew` (spec 055) — cópia estrutural de `REGUA_COZINHAR` --- #
# Duas de ADMISSÃO (gates) e duas que só importam quando as de admissão são > 0:
# FAVORABILIDADE (rolada, decide a banda) e DURAÇÃO (classificação pura).

REGUA_RECIPIENTE = """\
Régua do RECIPIENTE (o quanto, PELA DESCRIÇÃO, ele é equipamento capaz de
servir para PREPARAR algo — não se É bonito, valioso, ou se seria bom
recipiente em tese):
  0  categoricamente não serve — uma bota, uma pedra qualquer, um objeto
     decorativo sem cavidade nem função de preparo (sem teste)
  1  quase certamente não — quase nada na descrição sugere função de preparo
  2  muito improvável — indícios fracos demais
  3  duvidoso — a descrição não convence
  4  incerto — poderia ser, poderia não ser
  5  ambíguo — a descrição não decide
  6  provável — indícios razoáveis de função de preparo
  7  bastante provável — claramente algo com cavidade/função de misturar ou
     decoctar
  8  recipiente evidente — almofariz, caldeirão, vasilha de preparo comum
  9  recipiente muito evidente — descrição rica em detalhes de equipamento
     de botica
  10 claramente feito para isto — alambique, almofariz, caldeirão de
     boticário (sem teste)
Um objeto CLARAMENTE sem função de preparo (uma bota, uma pedra lisa) é 0,
não 1 ou 2 — não hesite no extremo quando a descrição já diz que não serve.
A nota é segredo do mundo: nunca o número na narrativa; nota 0 faz a
tentativa ser recusada, SEM perguntar preparabilidade."""

REGUA_PREPARABILIDADE = """\
Régua da PREPARABILIDADE (só importa se recipiente > 0 — o quanto os
ingredientes ESCOLHIDOS, PELA DESCRIÇÃO COMBINADA de todos eles, formam algo
que faz sentido preparar juntos — não o quanto ficaria eficaz):
  0  categoricamente não combinam — não sugerem preparo nenhum juntos (sem
     teste)
  5  ambíguo — a descrição não decide
  10 claramente um preparo — a combinação sustenta um remédio coerente
     (sem teste)
A nota é segredo do mundo. Entre 1 e 9 há um teste resolvido na aplicação."""

_STR = {"type": "string"}


@inworld("botica_ops_applied")
def _iw_brew(op):
    return "começou a preparar, atento à combinação"


def _brew(name: str, args: dict, ctx) -> tuple[dict, bool]:
    ingredientes = args.get("ingredientes")
    recipiente = args.get("recipiente")
    if not isinstance(ingredientes, list) or not ingredientes:
        return ctx.err("informe ao menos um ingrediente presente/na posse"), False
    ingredientes = list(dict.fromkeys(ingredientes))  # sem duplicata, mantém ordem
    disponiveis = ctx.cand["brew_ingredientes"]
    for iid in ingredientes:
        if iid not in disponiveis:
            return ctx.err(f"'{iid}' não está ao alcance para preparar", "ingredientes",
                           ctx.validos({i: ctx.items[i] for i in disponiveis})), False
    recipientes = ctx.cand["brew_recipiente"]
    if recipiente not in recipientes:
        # spec 055 (molde de cook_fonte): a lista mistura objects e o LUGAR — montar
        # o mapa por `ctx.objects[o]` levantaria KeyError no id do lugar.
        return ctx.err(f"'{recipiente}' não é um recipiente presente", "recipiente",
                       ctx.validos({o: ctx.objects.get(o)
                                    or {"name": (ctx.context.get("location") or {}).get("name") or o}
                                    for o in recipientes})), False
    chave = (tuple(sorted(ingredientes)), recipiente)
    if chave in ctx.brewed_asked:
        return ctx.err("preparar esses ingredientes nesse recipiente já foi tentado "
                       "neste turno — o desfecho sai na aplicação; NÃO repita: siga "
                       "para outra ação ou narrate"), False
    # spec 055 — CONTRATO DE ANÁLISE: a régua combinada lê o recipiente E todos os
    # ingredientes juntos, numa chamada só.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_PREPARAR, json.dumps({
            "recipiente": ctx.describe(recipiente),
            "ingredientes": [ctx.describe(i) for i in ingredientes],
        }, ensure_ascii=False, indent=2)),
        campos={"recipiente_adequado": 5, "preparabilidade": 5, "favorabilidade": 5,
                "duracao": 5},
        texto_campos={"nome": "", "descricao_ruim": "", "descricao_media": "",
                      "descricao_otima": ""})
    ctx.brewed_asked.add(chave)
    base = {"ingredientes": ingredientes, "recipiente": recipiente}
    recipiente_adequado = julgado["recipiente_adequado"]
    if recipiente_adequado == 0:
        rej, rolled = ctx.apply_arbitrated("botica_ops", {
            **base, "recipiente_adequado": 0})
        if rej:
            return ctx.arb_deny(rolled, ("brew", tuple(ingredientes), recipiente), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    preparabilidade = julgado["preparabilidade"]
    if preparabilidade == 0:
        rej, rolled = ctx.apply_arbitrated("botica_ops", {
            **base, "recipiente_adequado": recipiente_adequado, "preparabilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("brew", tuple(ingredientes), recipiente), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("botica_ops", {
        **base, "recipiente_adequado": recipiente_adequado,
        "preparabilidade": preparabilidade,
        "favorabilidade": julgado["favorabilidade"], "duracao": julgado["duracao"],
        "nome": julgado["nome"], "descricao_ruim": julgado["descricao_ruim"],
        "descricao_media": julgado["descricao_media"],
        "descricao_otima": julgado["descricao_otima"]})
    if rej:
        return ctx.arb_deny(rolled, ("brew", tuple(ingredientes), recipiente), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


# spec 055 — UMA chamada combinada (mesmo custo/latência que `cook` já fixou, mesmo
# schema de oito chaves).
REGUA_PREPARAR = f"""\
Você vai julgar UMA tentativa de preparar algo, combinando ingredientes sobre
um recipiente. Leia a descrição REAL fornecida com cuidado antes de responder
— nunca invente detalhes que não estejam nela.

{REGUA_RECIPIENTE}

{REGUA_PREPARABILIDADE}

A rolagem que decide a banda final (ruim/média/ótima) só acontece DEPOIS
desta resposta, no Motor — você não sabe qual banda vai sair, e não precisa
saber: a description que você escrever para cada banda serve independente do
que o Motor decidir depois.

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de
explicação, EXATAMENTE com estas oito chaves (todas OBRIGATÓRIAS, mesmo que
recipiente_adequado ou preparabilidade sejam 0):

{{"recipiente_adequado": <inteiro 0-10>, "preparabilidade": <inteiro 0-10>, \
"favorabilidade": <inteiro 0-10>, "duracao": <inteiro 0-10>, \
"nome": "<nome curto do preparo>", \
"descricao_ruim": "<texto factual, resultado malfeito>", \
"descricao_media": "<texto factual, resultado comum>", \
"descricao_otima": "<texto factual, resultado excelente>"}}"""


BREW = tool_spec(ToolSpec(
    names=("brew",),
    juizo=(
        ("recipiente_adequado", REGUA_PREPARAR),
        ("preparabilidade", REGUA_PREPARAR),
        ("favorabilidade", REGUA_PREPARAR),
        ("duracao", REGUA_PREPARAR),
        ("nome", REGUA_PREPARAR),
        ("descricao_ruim", REGUA_PREPARAR),
        ("descricao_media", REGUA_PREPARAR),
        ("descricao_otima", REGUA_PREPARAR),
    ),
    # A DESCRIPTION É PARA A LLM QUE ESCOLHE, não para o jogador ler (mesma
    # disciplina medida em `forage`, 2026-08-26, `sondagem_forage.py`): a frase
    # "o mundo julga, pela descrição, se X" mediu EMPATE EXATO contra removê-la
    # por completo — não carrega peso pra decisão de chamar. Não entra aqui.
    # Descreve EFEITO e CONTRATO DO PARÂMETRO; não enumera caso de uso (o que
    # o remédio serve pra curar) nem alardeia custo (os ingredientes somem).
    description=("Combina os ingredientes informados sobre um recipiente, criando um "
     "preparo novo ali — não pronto na hora, leva tempo real. Em `ingredientes` vão as "
     "coisas a combinar; em `recipiente`, o lugar atual ou uma coisa presente e "
     "alcançável capaz de servir para preparar — um objeto sem essa função é recusado, "
     "sem consumir nada."),
    params={"ingredientes": {"type": "array", "items": {"type": "string"}},
            "recipiente": _STR,
            "recipiente_adequado": {"type": "integer", "minimum": 0, "maximum": 10},
            "preparabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "favorabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "duracao": {"type": "integer", "minimum": 0, "maximum": 10},
            "nome": _STR, "descricao_ruim": _STR, "descricao_media": _STR,
            "descricao_otima": _STR},
    required=("ingredientes", "recipiente", "recipiente_adequado", "preparabilidade",
              "favorabilidade", "duracao", "nome", "descricao_ruim", "descricao_media",
              "descricao_otima"),
    enum_sources={"ingredientes": "brew_ingredientes", "recipiente": "brew_recipiente"},
    apply=_brew,
))
