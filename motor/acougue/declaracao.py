"""DECLARAÇÃO + CORPO da tool de ESQUARTEJAR (spec 050).

`butcher` extrai carne de um corpo QUE JÁ ESTÁ MORTO, julgado numa ÚNICA chamada ao
Árbitro (`REGUA_ESQUARTEJAR`, molde reduzido de `REGUA_COZINHAR`) — DUAS notas em vez
de quatro, e UMA description em vez de três candidatas: a banda aqui decide
QUANTIDADE/peso das porções (física do Motor, `porcoes_de_carne`), nunca o texto —
diferente de `cook`, onde a banda muda a textura sensorial do prato. O corpo ENFILEIRA
via `ctx.apply_arbitrated` (mesmo padrão de `cook`/`eat`/`drink`), sem importar o
Árbitro. Nunca causa a morte de ninguém — a pré-condição dura (`alvo` já MORTO) é
checada pelo `enum_source` `butcher_alvo` (`arbiter.py::_verb_candidates`), zero LLM se
violada.
"""
from __future__ import annotations

import json
from .. import juizo

from ..registro import ToolSpec, inworld, tool_spec


# --- As duas réguas de `butcher` (spec 050) ---------------------------------- #
# Uma categórica (ESQUARTEJABILIDADE — gate: este corpo é feito de carne?) antes
# de uma graduada (RENDIMENTO — só perguntada se a primeira é > 0: quanto daquela
# carne está aproveitável agora?). Separadas por motivo análogo ao de `cook`
# (fonte_de_calor/cozinhabilidade): um erro de calibração ambíguo (2 em vez de 0
# num golem) nunca pode deixar a rolagem prosseguir — research R1.

REGUA_ESQUARTEJABILIDADE = """\
Régua da ESQUARTEJABILIDADE (o quanto, PELA DESCRIÇÃO, este corpo é feito de
matéria que vira carne de verdade — carne, gordura, sangue — não o quanto seria
bom açougueiro, e não se É um animal em tese):
  0  categoricamente não é carne — pedra, metal, osso puro, energia, construto,
     morto-vivo ósseo (sem teste)
  1  quase certamente não — quase nada na descrição sugere carne
  2  muito improvável — indícios fracos demais
  3  duvidoso — a descrição não convence
  4  incerto — poderia ser, poderia não ser
  5  ambíguo — a descrição não decide
  6  provável — indícios razoáveis de matéria orgânica
  7  bastante provável — claramente algo com carne/sangue
  8  carne evidente — corpo orgânico comum, sem dúvida
  9  carne muito evidente — descrição rica em detalhes de carne/sangue
  10 claramente carne — qualquer criatura orgânica comum, sem ambiguidade nenhuma
     (sem teste)
Um corpo CLARAMENTE de pedra, metal ou osso puro (um golem, um esqueleto, um
construto) é 0, não 1 ou 2 — não hesite no extremo quando a descrição já diz que
não há carne nenhuma ali. A nota é segredo do mundo: nunca o número na
narrativa; nota 0 faz a tentativa ser recusada, SEM perguntar rendimento."""

REGUA_RENDIMENTO = """\
Régua do RENDIMENTO (só importa se esquartejabilidade > 0 — o quanto, PELO PORTE
e ESTADO DE CONSERVAÇÃO deste corpo específico, há carne aproveitável AGORA — não
o quanto ele É carne):
  0  nada sobrou — carbonizado, mutilado além do reconhecível, podre a ponto de
     não sobrar nada (sem teste)
  1  quase nada — só resquícios
  2  muito pouco — a maior parte se perdeu
  3  escasso — porte pequeno ou estado ruim
  4  abaixo do comum — porte modesto
  5  comum — porte médio, estado razoável
  6  acima do comum — porte bom, bem conservado
  7  farto — porte grande, boa conservação
  8  muito farto — porte grande, saudável antes de morrer
  9  quase perfeito — porte excelente, conservação ótima
  10 fartura máxima — porte enorme, saudável antes de morrer, conservação
     perfeita (sem teste)
A nota é segredo do mundo: nunca o número na narrativa. Entre 1 e 9 há um teste
resolvido na aplicação — não narre o resultado como certo."""

# spec 050 — UMA chamada combinada (mesmo custo/latência que `cook` já fixou, com
# metade das chaves): as duas notas + nome + UMA description saem da MESMA
# resposta. Diferente de `cook`, não há três candidatas — a banda decide
# quantidade/peso (física do Motor), não o texto (research R1/Eixo 2 da spec).
REGUA_ESQUARTEJAR = f"""\
Você vai julgar UMA tentativa de esquartejar um corpo que já está morto. Leia a
descrição REAL fornecida com cuidado antes de responder — nunca invente detalhes
que não estejam nela.

{REGUA_ESQUARTEJABILIDADE}

{REGUA_RENDIMENTO}

A rolagem que decide a banda final (fraco/médio/farto) só acontece DEPOIS desta
resposta, no Motor — você não sabe qual banda vai sair, e não precisa saber: a
description que você escrever serve às três bandas igualmente (só a quantidade de
carne muda, decidida pelo Motor, nunca por você).

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas quatro chaves (todas OBRIGATÓRIAS, mesmo que
esquartejabilidade ou rendimento sejam 0):

{{"esquartejabilidade": <inteiro 0-10>, "rendimento": <inteiro 0-10>, "nome": "<nome curto do corte de carne>", "descricao": "<texto factual da carne resultante, nunca sabor ou apetite>"}}"""

_STR = {"type": "string"}


@inworld("esquartejar_ops_applied")
def _iw_butcher(op):
    return "esquartejou o corpo, com cuidado de açougueiro"


def _butcher(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    if not alvo:
        return ctx.err("informe 'alvo'"), False
    disponiveis = ctx.cand["butcher_alvo"]
    if alvo not in disponiveis:
        return ctx.err(f"'{alvo}' não está disponível para esquartejar", "alvo",
                       ctx.validos({c: ctx.chars[c] for c in disponiveis})), False
    if alvo in ctx.butchered_asked:
        return ctx.err("esquartejar esse corpo já foi tentado neste turno — o "
                       "desfecho sai na aplicação; NÃO repita: siga para outra "
                       "ação ou narrate"), False
    # spec 050 — CONTRATO DE ANÁLISE: a régua combinada lê só o corpo-alvo.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_ESQUARTEJAR, json.dumps({
            "alvo": ctx.describe(alvo),
        }, ensure_ascii=False, indent=2)),
        campos={"esquartejabilidade": 5, "rendimento": 5},
        texto_campos={"nome": "", "descricao": ""})
    ctx.butchered_asked.add(alvo)
    base = {"alvo": alvo}
    esquartejabilidade = julgado["esquartejabilidade"]
    if esquartejabilidade == 0:
        rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
            **base, "esquartejabilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rendimento = julgado["rendimento"]
    if rendimento == 0:
        rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
            **base, "esquartejabilidade": esquartejabilidade, "rendimento": 0})
        if rej:
            return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
        **base, "esquartejabilidade": esquartejabilidade, "rendimento": rendimento,
        "nome": julgado["nome"], "descricao": julgado["descricao"]})
    if rej:
        return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


BUTCHER = tool_spec(ToolSpec(
    names=("butcher",),
    juizo=(
        ("esquartejabilidade", REGUA_ESQUARTEJAR),
        ("rendimento", REGUA_ESQUARTEJAR),
        ("nome", REGUA_ESQUARTEJAR),
        ("descricao", REGUA_ESQUARTEJAR),
    ),
    description=("Esquarteja um corpo que já está morto, extraindo carne crua. O "
     "mundo decide, lendo a descrição, se aquele corpo é feito de carne e o quanto "
     "dela está aproveitável. Um corpo sem matéria orgânica (pedra, osso, "
     "construto) não rende nada, e um corpo já esquartejado não pode ser "
     "esquartejado de novo. Nunca causa a morte de ninguém — só age sobre quem já "
     "está morto."),
    params={"alvo": _STR,
            "esquartejabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "rendimento": {"type": "integer", "minimum": 0, "maximum": 10},
            "nome": _STR, "descricao": _STR},
    required=("alvo", "esquartejabilidade", "rendimento", "nome", "descricao"),
    enum_sources={"alvo": "butcher_alvo"},
    apply=_butcher,
))
