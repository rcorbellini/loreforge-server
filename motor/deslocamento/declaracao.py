"""DECLARAÇÃO + CORPO das tools de DESLOCAMENTO (spec 038, L3).

enter_route, persuade, travel_to, carry — migradas de `arbiter_tools/deslocamento.py`
(deletado). O TERMINAL (encerra o turno) mora no corpo (`return …, True`), não numa
flag: enter_route e travel_to devolvem done=True. Corpos operam sobre o `ctx`
duck-typed; sem importar o Árbitro. `s.routes` é a fonte-de-enum de rota (callable).
Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

import json

import motor

from .. import juizo

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec
from ..rolagem import NEUTRAL_ADVANTAGE


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# Saiu de `arbiter.py`, onde vivia colada num system prompt único que despejava
# TODAS as réguas em todo turno (12.507 de 15.164 caracteres — 82% do prompt —
# para no máximo uma ser usada). Migrou como TEXTO: string não cria dependência,
# e o Motor segue sem conhecer o Árbitro nem o llm.

REGUA_VONTADE = """\
Régua da vontade (dimensione SEMPRE por ela, lendo o ALVO — personalidade, memórias,
humor/ação atuais, relação com quem pede e com o destino — nunca o interesse de quem
persuade; reavalie a cada tentativa, a insistência pode subir ou baixar a nota).
O mundo já mediu o afeto do alvo pelos destinos e o entrega em "afeto_por_lugar"
(quando pesa): "nutre estima" por um lugar inclina a ir; "guarda mágoa" dele, a
ficar. Use como insumo, sem recalcular de cabeça:
  0  recusa absoluta — ir contraria algo essencial dele; nada NESTA conversa o move (não vai, sem teste)
  1  fortemente contrário — motivo concreto e atual para ficar; só algo extraordinário moveria
  2  muito relutante — aversão clara ao destino, ao caminho ou ao pedido
  3  relutante — prefere ficar; o que faz agora importa mais que o pedido
  4  levemente contrário — sem interesse próprio; iria só por consideração a quem pede
  5  indiferente — nada o prende, nada o chama; a conversa decide sozinha
  6  levemente inclinado — alguma curiosidade ou simpatia pelo pedido
  7  inclinado — o pedido combina com os interesses ou a rotina dele
  8  muito inclinado — tem motivo próprio para ir; a conversa é só o empurrão
  9  quase decidido — já queria ir; qualquer palavra razoável basta
  10 vontade própria — quer/precisa ir AGORA por motivo dele (vai sem teste)
A nota é segredo do mundo: NUNCA mencione o número na narrativa. Entre 1 e 9 há um
teste de persuasão resolvido na aplicação — não narre o desfecho como certo; o mundo
devolve o que de fato aconteceu (inclusive recusas e reviravoltas)."""

_STR = {"type": "string"}
_VANTAGEM = {"type": "integer", "minimum": 0, "maximum": 10}


@inworld("carry_ops_applied")
def _iw_carry(op):
    return f"levou {name_of(op.get('alvo') or op.get('target'))} consigo"


@inworld("expel_ops_applied")
def _iw_expel(op):
    return f"pôs {name_of(op.get('alvo') or op.get('target'))} para fora"


def _expel(name: str, args: dict, ctx) -> tuple[dict, bool]:
    """Pôr OUTRO para fora à força (spec 041). Guarda: alvo≠ator, presente, rota
    parte daqui, dedup por alvo. Move só o alvo — o desfecho (força/peso) sai na
    aplicação. Irmã do `_carry`, mas o ator FICA."""
    alvo = args.get("alvo")
    rota = args.get("rota")
    outros = ctx.validos({c: n for c, n in ctx.chars.items() if c != ctx.actor})
    if alvo == ctx.actor:
        # aponta o destino em vez de só negar — é o padrão do projeto (`persuade` já
        # dizia "para ir, basta partir"). Recusa que não diz o que fazer no lugar
        # gasta o turno duas vezes.
        return ctx.err("é ele quem sairia — para partir, use enter_route; expulsar "
                       "é para pôr OUTRO para fora", "alvo", outros), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "alvo", outros), False
    if alvo in ctx.expulsos:
        return ctx.err(f"'{alvo}' já foi posto para fora neste turno — o desfecho "
                       "sai na aplicação; NÃO repita: siga para outra ação ou narrate"), False
    if rota not in ctx.routes:
        return ctx.err(f"rota '{rota}' não parte daqui", "rota",
                       ctx.validos(ctx.routes)), False
    ctx.expulsos.add(alvo)
    ctx.queue["expel_ops"].append({"alvo": alvo, "rota": rota})
    return {"ok": True, "aplicado": {"alvo": alvo, "rota": rota,
                                     "nota": "o desfecho sai na aplicação"}}, False


EXPEL = tool_spec(ToolSpec(
    names=("expulsar",),
    description=("Põe OUTRO personagem presente para FORA daqui, à força. SE É "
     "QUEM AGE QUE VAI SAIR, esta NÃO é a ferramenta — use enter_route. "
     "'alvo' é QUEM É POSTO PARA FORA, e tem de ser outra pessoa da cena; "
     "quem age FICA onde está. Diferente de carry, que leva os dois. A "
     "força dele resiste à sua, e o desfecho é do mundo."),
    params={"alvo": _STR, "rota": _STR},
    required=("alvo", "rota"),
    enum_sources={"alvo": "carry", "rota": lambda s: s.routes},
    apply=_expel,
))


@inworld("persuade_ops_applied")
def _iw_persuade(op):
    return f"convenceu {name_of(op.get('alvo') or op.get('personagem'))} a partir"


@inworld("travel_ops_applied")
def _iw_travel(op):
    return f"partiu rumo a {name_of(op.get('destino_final'))}"


def _enter_route(name: str, args: dict, ctx) -> tuple[dict, bool]:
    route = args.get("route")
    if route not in ctx.routes:
        return ctx.err(f"rota '{route}' não parte daqui", "route",
                       ctx.validos(ctx.routes)), False
    ctx.queue["movement"] = {"enter_route": route}
    ctx.queue["mutations"] = []  # regra atual: movimento exclui mutations
    return {"ok": True, "aplicado": {"enter_route": route}}, True


def _persuade(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("personagem")
    rota = args.get("rota")
    # CORRIGÍVEL fica na tool (a guarda PROPÕE com validos): alvo é OUTRO presente,
    # rota parte daqui, e a conversa não se repete no turno (veredito único, §1).
    if alvo == ctx.actor:
        return ctx.err("é ele quem fala — para ir, basta partir (use enter_route)"), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "personagem",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    if rota not in ctx.routes:
        return ctx.err(f"rota '{rota}' não parte daqui", "rota", ctx.validos(ctx.routes)), False
    if alvo in ctx.persuaded:
        return ctx.err(f"a conversa com '{alvo}' já aconteceu neste turno — a primeira "
                       "nota vale e o desfecho sai na aplicação; NÃO repita: siga para "
                       "outra ação ou narrate"), False
    # VEREDITO é AUTORIDADE do executor agora (item 31 §2): estado do alvo
    # (alvo_desacordado), extremo da régua (vontade 0 = recusa_absoluta) e a ROLAGEM
    # decidem lá, contra os arquivos. A conversa ACONTECEU — trava o veredito único
    # mesmo negada — e a recusa do mundo narra (registrada em rejections).
    # spec 043 — CONTRATO DE ANÁLISE: a régua da vontade lê o ALVO (quem é, o que faz)
    # e o que ele guarda de quem pede. Nota vinda de fora é ignorada (FR-005).
    vontade = juizo.nota(
        ctx.ask(REGUA_VONTADE + juizo.NOTA_0_10,
                json.dumps({"alvo": ctx.describe(alvo),
                            "rota": ctx.describe(rota),
                            "saldo_afeto": motor.sentiment_label(motor.sentiment_toward(alvo, ctx.actor)),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=NEUTRAL_ADVANTAGE)
    ctx.persuaded.add(alvo)
    rej, rolled = ctx.apply_arbitrated(
        "persuade_ops", {"personagem": alvo, "rota": rota, "vontade": vontade})
    if rej:
        return ctx.arb_deny(rolled, ("persuade", alvo),
                            {"persuadir": alvo, "rota": rota}, rej)
    return {"ok": True, "aplicado": {"personagem": alvo, "rota": rota,
                                     "nota": "o desfecho sai na aplicação"}}, False


def _travel_to(name: str, args: dict, ctx) -> tuple[dict, bool]:
    destino = args.get("destino")
    if destino not in ctx.cand["viajar_para"]:
        return ctx.err(f"'{destino}' não é lugar a que ele saiba chegar", "destino",
                       [{"id": d, "nome": d} for d in ctx.cand["viajar_para"]]), False
    if destino in ctx.viajado:
        return ctx.err(f"a viagem para '{destino}' já foi decidida neste turno — o "
                       "mundo resolve o percurso; NÃO repita: siga para outra ação ou "
                       "narrate"), False
    ctx.viajado.add(destino)
    ctx.queue["travel_ops"].append({"destino": destino})
    return {"ok": True, "aplicado": {"destino": destino,
                                     "nota": "o percurso é resolvido pelo mundo"}}, True


def _carry(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    rota = args.get("rota")
    outros_c = ctx.validos({c: n for c, n in ctx.chars.items() if c != ctx.actor})
    if alvo == ctx.actor:
        return ctx.err("'alvo' é QUEM É LEVADO, não quem age — escolha outro "
                       "personagem presente", "alvo", outros_c), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "alvo", outros_c), False
    if alvo in ctx.carried:
        return ctx.err(f"'{alvo}' já foi levantado neste turno — o desfecho sai na "
                       "aplicação; NÃO repita: siga para outra ação ou narrate"), False
    if rota not in ctx.routes:
        return ctx.err(f"rota '{rota}' não parte daqui", "rota", ctx.validos(ctx.routes)), False
    ctx.carried.add(alvo)
    ctx.queue["carry_ops"].append({"alvo": alvo, "rota": rota})
    return {"ok": True, "aplicado": {"alvo": alvo, "rota": rota,
                                     "nota": "o desfecho sai na aplicação"}}, False


ENTER_ROUTE = tool_spec(ToolSpec(
    names=("enter_route",),
    description=("QUEM AGE se desloca por um caminho — é a tool de "
                 "andar. Use SEMPRE que quem age vai partir, mesmo que "
                 "haja outras pessoas na cena: 'sozinho' aqui significa "
                 "SEM LEVAR NINGUÉM JUNTO, não 'sem ninguém por perto'. "
                 "Encerra o turno: quem resolve viagem e chegada é o "
                 "mundo. Para LEVAR outro consigo (carregado ou "
                 "arrastado) use carry; para mandar OUTRO ir sem que "
                 "quem age saia do lugar, use persuade."),
    params={"route": _STR},
    required=("route",),
    enum_sources={"route": lambda s: s.routes},
    apply=_enter_route,
))


PERSUADE = tool_spec(ToolSpec(
    names=("persuade",),
    juizo=(("vontade", REGUA_VONTADE),),
    description=("Convence OUTRO personagem a partir por um caminho, enquanto QUEM AGE "
     "FICA. Nunca use para deslocar quem age — se é ele que vai andar, use "
     "enter_route. Se a pessoa se deixa convencer é ela quem decide, pelo "
     "que sente e pelo que guarda de quem pede. Não adianta falar com quem "
     "está CAÍDO — para tirá-lo do lugar, use carry."),
    params={"personagem": _STR, "rota": _STR, "vontade": _VANTAGEM},
    required=("personagem", "rota", "vontade"),
    enum_sources={"personagem": "persuade", "rota": lambda s: s.routes},
    apply=_persuade,
))


TRAVEL_TO = tool_spec(ToolSpec(
    names=("travel_to",),
    description=("O personagem viaja até um LUGAR conhecido, por todas "
                 "as pernas do caminho — use quando o destino não é "
                 "vizinho. Ele percorre cada trecho e passa por cada "
                 "lugar; não é teleporte, e leva o tempo somado. Para "
                 "ir a um lugar VIZINHO por um caminho específico, use "
                 "enter_route. Para LEVAR outro junto, use carry."),
    params={"destino": _STR},
    required=("destino",),
    enum_sources={"destino": "viajar_para"},
    apply=_travel_to,
))


CARRY = tool_spec(ToolSpec(
    names=("carry",),
    description=("Leva OUTRO personagem presente por um caminho, à força ou por estar "
     "ele caído. 'alvo' é QUEM É LEVADO — nunca quem age. Se ele vai nos "
     "braços ou arrastado pelo chão, e se a tentativa dá certo, decidem o "
     "peso dele e a força de quem carrega. Para convencer alguém a ir por "
     "vontade própria, use persuade."),
    params={"alvo": _STR, "rota": _STR},
    required=("alvo", "rota"),
    enum_sources={"alvo": "carry", "rota": lambda s: s.routes},
    apply=_carry,
))
