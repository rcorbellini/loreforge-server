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
    vantagem = juizo.nota(
        ctx.ask(REGUA_VANTAGEM + juizo.NOTA_0_10,
                json.dumps({"alvo": ctx.describe(alvo),
                            "arma": ctx.describe(arma) if arma else "desarmado",
                            "cena": ctx.describe(ctx.place_id),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=NEUTRAL_ADVANTAGE)   # combate limpo
    # VEREDITO (alvo morto) e a ROLAGEM (acertou/quanto feriu) são AUTORIDADE do
    # executor agora (item 31 §2): o golpe ACONTECEU — trava o veredito único — e a
    # recusa narra pelo client; o desfecho do dado é SEGREDO do modelo (Princípio IX).
    ctx.attacked.add(alvo)
    rej, rolled = ctx.apply_arbitrated(
        "attack_ops", {"alvo": alvo, "arma": arma, "vantagem": vantagem})
    if rej:
        return ctx.arb_deny(rolled, ("attack", alvo),
                            {"atacar": alvo, "arma": arma}, rej)
    return {"ok": True, "aplicado": {"alvo": alvo, "arma": arma,
                                     "nota": "o desfecho sai na aplicação"}}, False


ATTACK = tool_spec(ToolSpec(
    names=("attack",),
    juizo=(("vantagem", REGUA_VANTAGEM),),
    description=("Golpeia OUTRO personagem presente. 'alvo' é QUEM APANHA — nunca quem "
     "age. 'arma' é um item na mão de quem age (omita para golpe "
     "desarmado; item que não é arma serve como improvisado). Se acertou, "
     "e o quanto feriu, quem decide é o mundo — nunca dê o desfecho por "
     "certo. Contra alguém já caído o golpe é deliberado e fatal."),
    params={"alvo": {"type": "string"},
            "vantagem": {"type": "integer", "minimum": 0, "maximum": 10},
            "arma": {"type": "string"}},
    required=("alvo", "vantagem"),
    enum_sources={"alvo": "attack", "arma": "attack_with"},
    omit_if_empty=("arma",),
    apply=_attack,
))
