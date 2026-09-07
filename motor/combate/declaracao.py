"""DECLARAÇÃO + CORPO da tool de COMBATE (spec 038, L3).

`attack` migrada de `arbiter_tools/combate.py` (deletado). O corpo opera sobre o
`ctx` do turno (duck-typed) — este módulo NÃO importa o Árbitro. Byte-equivalente
a v2.0.0 (golden + as 39 fases).
"""
from __future__ import annotations

import json
from .. import juizo

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec
from ..rolagem import NEUTRAL_ADVANTAGE


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# Saiu de `arbiter.py`, onde vivia colada num system prompt único que despejava
# TODAS as réguas em todo turno (12.507 de 15.164 caracteres — 82% do prompt —
# para no máximo uma ser usada). Migrou como TEXTO: string não cria dependência,
# e o Motor segue sem conhecer o Árbitro nem o llm.

REGUA_VANTAGEM = """\
Régua da vantagem do golpe (dimensione SEMPRE por ela, lendo o que a CENA dá ou tira
— posição, ação e humor do alvo, terreno, luz, condições — nunca o desejo de quem
ataca; reavalie a cada golpe):
  0  golpe quase inviável — atacante preso, desequilibrado, sem ângulo
  1  circunstância muito contra — terreno traiçoeiro, escuridão quase total, alvo protegido por obstáculo
  2  claramente desfavorável — espaço apertado para a arma, chão instável, atacante ferido e lento
  3  desfavorável — alvo alerta e em guarda, atento a quem se aproxima
  4  levemente contra — alvo já esperava algo; algo atrapalha o movimento
  5  combate limpo — nada na cena favorece ou atrapalha; o corpo e a arma decidem
  6  levemente a favor — alvo meio distraído, atacante melhor posicionado
  7  favorável — alvo ocupado com outra coisa, ou terreno claramente melhor
  8  muito favorável — alvo de costas, atrapalhado, ou sem espaço para recuar
  9  quase certo — alvo desprevenido e exposto, golpe preparado
  10 surpresa total — o alvo não faz ideia; nada nele reage a tempo
A nota é segredo do mundo: NUNCA mencione o número na narrativa. Você NÃO decide se o
golpe acertou nem quanto feriu — o teste é resolvido na aplicação; narre só o que a
resposta confirmar, nunca um ferimento que o mundo não registrou."""


# --- A SEGUNDA RÉGUA (spec 069) — a PRONTIDÃO de quem apanha ----------------- #
# Mora aqui, ao lado da vantagem, pelo mesmo motivo (a régua mora COM a capacidade que
# a lê, como TEXTO). Lê DUAS coisas, nesta ordem: o que a cena diz sobre o corpo do
# alvo, e o que a PROSA dele diz sobre quem ele é. A segunda é o que separa um monge
# alerta de um dragão alerta — os dois percebem o golpe, e só um devolve.
#
# Por que não é um campo `temperamento`: seria só o revide. A fera que FOGE quando
# ferida, o lobo que HESITA diante do fogo, o guarda que GRITA antes de bater — cada
# um pediria outro enum. A prosa serve a todos, inclusive ao que ninguém previu.

REGUA_REVIDE = """\
Régua da PRONTIDÃO do alvo para devolver o golpe (dimensione SEMPRE por ela; leia
PRIMEIRO o que a cena diz do corpo dele — percebeu? está inteiro? está livre? — e
DEPOIS o que a prosa dele diz de quem ele é: um ser que não tolera intrusos devolve
golpe, um curandeiro avesso a violência não devolve nem estando alerta):
  0  não reage — não viu o golpe chegar, não pôde, ou não é de revidar
  1  reage tarde demais — o corpo entende quando já acabou
  2  reage muito mal — assustado, desequilibrado, contra a própria natureza
  3  reage mal — hesita, e a hesitação custa
  4  reage abaixo do seu — percebeu em cima da hora
  5  reage — o corpo responde, sem vantagem nem desvantagem
  6  reage bem — estava atento ao que vinha
  7  reage rápido — em guarda, ou é de sua natureza devolver
  8  reage muito bem — esperava exatamente isto
  9  reage quase junto — predador acuado, guarda de ronda em serviço
  10 reage antes de pensar — a fera em sua toca, o corpo mais rápido que o susto
DUAS regras acima das faixas, nesta ordem:
- Quem NÃO VIU o agressor chegar é 0, por mais perigoso que seja: não se devolve o que
  não se viu. Golpe pelas costas, contra quem dorme ou contra quem está absorto e de
  costas cai aqui.
- Mas quem PERCEBEU a aproximação — olhou, virou a cabeça, está de frente — já não é
  surpresa: aí vale a natureza dele, e uma fera em sua toca ou um guarda em serviço
  vão para o alto da régua.
A nota 0 é ABSOLUTA: não há contra-golpe nenhum. A nota NÃO decide se o revide acerta
nem quanto fere — o teste é resolvido na aplicação. É segredo do mundo: NUNCA mencione
o número, e NUNCA narre um revide como certo."""


# A régua-mãe: UMA chamada, DUAS notas. Molde de `REGUA_ESQUARTEJAR` (`butcher`).
# Por que não uma chamada por eixo: `motor/juizo.py` registra a decisão da spec 046 —
# "o custo é a prioridade sobre isolar cada régua na própria chamada". E as duas notas
# leem a MESMA cena: a faixa 10 da vantagem já diz "nada nele reage a tempo", que é
# literalmente revide 0.

# A FORMA desta composição foi MEDIDA, não intuída (`tests/exploracao/lab_regua_golpe.py`,
# llama3.1:8b, n=30 por variante). A primeira tentativa — as duas réguas simplesmente
# coladas, vantagem primeiro — falhou nas DUAS pontas: revide SEMPRE 0 (inclusive para
# guarda alerta e fera em sua toca) e vantagem INFLADA (+1.87 sobre a régua isolada,
# cuja variação própria é 0.07). Diagnóstico: a régua da vantagem é escrita da ótica de
# QUEM ATACA, e colada a ela a do revide era lida na mesma moldura — o modelo julgava os
# dois eixos a favor do agressor.
#
# O que consertou, medido: (1) INVERTER a ordem, pondo o eixo do alvo primeiro; (2)
# MARCAR de quem é cada eixo; (3) uma PERGUNTA explícita só no eixo do revide — a mesma
# pergunta acrescentada ao eixo da vantagem piorava a deriva (+1.60), então ela fica com
# a régua crua. Resultado: revide 4/5 com os casos decisivos determinísticos
# (curandeira alerta e pacífica 0/0/0/0/0/0; fera 10 seis vezes), e deriva da vantagem
# +0.53.

REGUA_GOLPE = f"""\
Você vai julgar UMA cena de golpe em DOIS eixos SEPARADOS. Eles olham para lados
OPOSTOS: um é do corpo de quem APANHA, o outro é da mão de quem GOLPEIA. Julgue cada
um por si, e NÃO deixe a nota de um puxar a do outro.

########  EIXO 1 — "revide": O ALVO DEVOLVE O GOLPE?  ########
A pergunta é sobre O ALVO, e só sobre ele: o corpo dele está desperto, livre e
disposto a responder AGORA? Um alvo alerta, em guarda, ou cuja natureza é devolver,
tem nota ALTA aqui — mesmo que o golpe contra ele seja fácil.

{REGUA_REVIDE}

########  EIXO 2 — "vantagem": O QUE A CENA DÁ OU TIRA DO GOLPE  ########

{REGUA_VANTAGEM}

Responda APENAS um objeto JSON, sem texto antes ou depois, com exatamente estas duas
chaves e nada mais:
{{"vantagem": <inteiro 0-10>, "revide": <inteiro 0-10>}}"""


@inworld("attack_ops_applied")
def _iw_attack(op):
    alvo = name_of(op.get("alvo") or op.get("target"))
    caiu = bool(op.get("derrota"))
    return f"acertou {alvo}" + (f", e {alvo} caiu" if caiu else "")


def _attack(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    arma = args.get("arma")
    outros = ctx.validos({c: n for c, n in ctx.chars.items() if c != ctx.actor})
    if alvo == ctx.actor:
        return ctx.err("'alvo' é QUEM APANHA, não quem golpeia — escolha outro "
                       "personagem presente", "alvo", outros), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "alvo", outros), False
    if alvo in ctx.attacked:
        return ctx.err(f"o golpe contra '{alvo}' já foi desferido neste turno — o "
                       "desfecho sai na aplicação; NÃO repita: siga para outra ação ou "
                       "narrate"), False
    mao_do_ator = [i for i, s in ctx.loc.items()
                   if s["porter"] == ctx.actor and s["slot"] == ctx.hand]
    if arma is not None and arma not in mao_do_ator:
        return ctx.err(f"'{arma}' não está na mão de quem golpeia", "arma",
                       ctx.validos({i: ctx.items[i]["name"] for i in mao_do_ator
                                    if i in ctx.items})), False
    # spec 043 — CONTRATO DE ANÁLISE do golpe: o que a régua da vantagem manda ler é
    # o que a CENA dá ou tira. Nota vinda de fora é ignorada (FR-005).
    #
    # spec 069 — DUAS notas, UMA chamada. O revide é um eixo A MAIS na pergunta que o
    # mundo já fazia, nunca uma ida nova ao modelo: `juizo.julgamento` existe desde a
    # spec 046 exatamente para isto, com o formato JSON já medido em 9/9. Defaults POR
    # CAMPO — vantagem cai em combate limpo, revide cai em 0, porque juízo indisponível
    # jamais deve INVENTAR violência que ninguém julgou.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_GOLPE,
                json.dumps({"alvo": ctx.describe(alvo),
                            "arma": ctx.describe(arma) if arma else "desarmado",
                            "cena": ctx.describe(ctx.place_id),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        {"vantagem": NEUTRAL_ADVANTAGE, "revide": 0})
    vantagem, revide = julgado["vantagem"], julgado["revide"]
    # VEREDITO (alvo morto) e a ROLAGEM (acertou/quanto feriu) são AUTORIDADE do
    # executor agora (item 31 §2): o golpe ACONTECEU — trava o veredito único — e a
    # recusa narra pelo client; o desfecho do dado é SEGREDO do modelo (Princípio IX).
    ctx.attacked.add(alvo)
    rej, rolled = ctx.apply_arbitrated(
        "attack_ops", {"alvo": alvo, "arma": arma, "vantagem": vantagem,
                       "revide_nota": revide})
    if rej:
        return ctx.arb_deny(rolled, ("attack", alvo),
                            {"atacar": alvo, "arma": arma}, rej)
    return {"ok": True, "aplicado": {"alvo": alvo, "arma": arma,
                                     "nota": "o desfecho sai na aplicação"}}, False


ATTACK = tool_spec(ToolSpec(
    names=("attack",),
    # spec 069: DOIS eixos de juízo, uma régua-mãe só. O par novo é o que faz
    # `app.py` descartar também a nota de revide vinda de fora (o laço
    # `for p, _ in spec.juizo` já é genérico) — e aqui isso é mais grave que na
    # vantagem: o revide como parâmetro seria o AGRESSOR decidindo se a vítima reage.
    juizo=(("vantagem", REGUA_GOLPE), ("revide", REGUA_GOLPE)),
    description=("Golpeia OUTRO personagem presente. 'alvo' é QUEM APANHA — nunca quem "
     "age. 'arma' é um item na mão de quem age (omita para golpe "
     "desarmado; sem nada na mão, golpeia-se com o corpo — a garra, os "
     "dentes —, e item que não é arma serve como improvisado). Nunca dê o "
     "desfecho por certo: descreva a tentativa. Contra alguém já caído o "
     "golpe é deliberado e fatal. E saiba o risco: quem está desperto e "
     "disposto pode devolver o golpe na hora, sem pensar — atacar alguém "
     "assim custa sangue dos dois lados."),
    params={"alvo": {"type": "string"},
            "vantagem": {"type": "integer", "minimum": 0, "maximum": 10},
            "arma": {"type": "string"}},
    required=("alvo", "vantagem"),
    enum_sources={"alvo": "attack", "arma": "attack_with"},
    omit_if_empty=("arma",),
    apply=_attack,
))
