"""DECLARAÇÃO + CORPO das tools de ITEM (spec 038, L2 — domínio-piloto).

Um `ToolSpec` por tool, co-localizado com o CORPO (`_take`/`_give`/…, o antigo
`tool_X` de `arbiter_tools/itens.py`, agora deletado). A FACE do turno e o despacho
DERIVAM daqui: o builder genérico (`arbiter_tools.build_face`) monta o manifest a
partir de `params`+`enum_sources`; o despacho genérico do Árbitro roda `apply`.

O CORPO opera sobre o `ctx` do turno (duck-typed: `ctx.apply_op_now`, `ctx.deny`,
`ctx.track_move`, `ctx.arb_deny`, …) — este módulo NÃO importa o Árbitro, então a
fronteira segue intacta (o Motor não conhece o Árbitro; o Árbitro é que injeta o
`ctx`). Byte-equivalente a v2.0.0 (golden + as 39 fases).
"""
from __future__ import annotations

import json
from .. import juizo

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# Saiu de `arbiter.py`, onde vivia colada num system prompt único que despejava
# TODAS as réguas em todo turno (12.507 de 15.164 caracteres — 82% do prompt —
# para no máximo uma ser usada). Migrou como TEXTO: string não cria dependência,
# e o Motor segue sem conhecer o Árbitro nem o llm.

REGUA_FURTO = """\
Régua da EXPOSIÇÃO do furto (quão arriscado é subtrair AQUELE item DAQUELE dono
AGORA, sem ser notado). Você a lê ANTES de tudo pela DESCRIÇÃO do item e pela cena.

Dimensione por três coisas: (a) a VISTOSIDADE do item na descrição — uma carne
fumegante no balcão está à mão; um anel "que ela mantém preso por dentro do punho
da manga" ou "a bolsa amarrada à cintura" é quase impossível; (b) a ATENÇÃO do
dono — o que ele faz agora (distraído no ensopado, absorto numa conversa, ou de
olho em quem age?), o quanto confia em quem age; (c) a CENA — salão cheio e
barulhento esconde a mão; um quarto a sós, a dois palmos, não perdoa.
  0  impossível às claras — o dono está de olho, o item colado ao corpo (sem teste)
  1  temerário — ele quase o encara, e a coisa está bem guardada
  2  muito arriscado — atento, e o item não está solto
  3  arriscado — meio atento, ou o item exige um gesto largo
  4  incerto — poderia dar, se a sorte ajudar
  5  parelho — tão provável passar quanto ser pego
  6  favorável — ele está distraído e a coisa está acessível
  7  fácil — absorto em outra coisa, o item à mão
  8  quase livre — nem olha para cá, o item solto ao alcance
  9  bandeja — ele deu as costas e esqueceu a coisa à vista
  10 trivial — dorme, desmaiou ou está totalmente alheio (sem teste)
Item DISCRETO/preso ao corpo puxa a nota PARA BAIXO mesmo com o dono distraído —
é a leitura da prosa que manda. A nota é segredo do mundo: nunca o número na
narrativa; 1–9 têm teste de furtividade na aplicação — não narre o desfecho como certo."""

_STR = {"type": "string"}


@inworld("equip_ops_applied")
def _iw_equip(op):
    item = name_of(op.get("item"))
    if op.get("op") == "unequip":
        destino = op.get("to")
        if destino and destino != op.get("character"):
            return f"tirou {item} do corpo e deixou em {name_of(destino)}"
        return f"tirou {item} do corpo"
    return f"vestiu {item}"


@inworld("item_transfers_applied")
def _iw_transfer(op):
    item = name_of(op.get("item"))
    destino = op.get("to") or op.get("destino")
    frase = (f"{item} passou para {name_of(destino)}" if destino
             else f"{item} mudou de lugar")
    # ITEM 44: o gesto de acomodar é do MUNDO, não do jogador — e o Princípio X
    # proíbe que ele aconteça calado. Vai na MESMA frase porque é um gesto só:
    # quem recebe muda a pega para poder receber.
    ac = op.get("acomodou")
    if isinstance(ac, dict):
        guardado, abrigo = name_of(ac.get("item")), name_of(ac.get("para"))
        if ac.get("modo") == "liberou_a_mao":
            frase += f", que guardou {guardado} em {abrigo} para abrir a mão"
        else:
            frase += f", que guardou em {abrigo} por não ter mão livre"
    return frase


@inworld("steal_ops_applied")
def _iw_steal(op):
    dono = name_of(op.get("de"))
    item = name_of(op.get("item"))
    if op.get("levou") and not op.get("flagrado"):
        return f"furtou {item} de {dono} sem ser notado"
    if op.get("levou"):
        return f"arrancou {item} de {dono}, mas foi FLAGRADO"
    return f"foi FLAGRADO tentando furtar {item} de {dono}"


def _item_setup(name, args, ctx):
    """Setup compartilhado das tools de item: valida o item e devolve (item, e, st)
    ou (erro, None, None)."""
    item = args.get("item")
    bad = ctx.check_item(item, name)
    if bad:
        return bad, None, None
    return item, ctx.items[item], ctx.loc[item]


def _take(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    if st["porter"] == ctx.actor and st["slot"] == ctx.hand:
        return ctx.err(f"'{item}' já está na mão"), False
    rej = ctx.apply_op_now("item_transfers", {"item": item, "to": ctx.actor})
    if rej:
        return ctx.deny(item, ctx.actor, rej), False
    ctx.track_move(item, "char", ctx.actor, ctx.hand)
    return {"ok": True, "aplicado": {"item": item, "to": ctx.actor}}, False


def _give(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    to = args.get("to")
    if to not in ctx.chars or to == ctx.actor:
        return ctx.err(f"destino '{to}' não é outro personagem presente", "to",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    # posse (item na mão) e slot (não vestido) são AUTORIDADE do executor agora
    # (item 31): a recusa volta corrigível, com os validos. Aqui só o SENTIDO de give.
    give_op = {"item": item, "to": to, "mode": "give"}
    if args.get("intention_id"):
        give_op["intention_id"] = args["intention_id"]
    if args.get("emprestimo"):
        give_op["emprestimo"] = True
    rej = ctx.apply_op_now("item_transfers", give_op)
    if rej:
        return ctx.deny(item, to, rej), False
    ctx.track_move(item, "char", to, ctx.hand)
    return {"ok": True, "aplicado": {"item": item, "to": to}}, False


def _stow(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    to = args.get("container")
    if to == item:
        return ctx.err(f"'{item}' não pode ser guardado dentro de si mesmo"), False
    # ITEM 44 — SEM DESTINO, o mundo resolve. Guardar é o gesto com que se libera a
    # mão, e exigir que A Mente escolha o contêiner é cobrar dela uma decisão que o
    # corpo toma sozinho. Medido: das 9 chamadas de `stow` do jogo, 3 morreram por
    # não nomear contêiner — duas omitindo o campo (este caso) e uma chamando-o de
    # `to`, o nome que `give` e `shove` usam para a mesma ideia.
    if to is None:
        abrigo = ctx.stow_spot_for(item)
        if abrigo is None:
            return ctx.err(f"não há onde guardar '{name_of(item)}' — "
                           "nenhuma bolsa aberta com espaço"), False
        to = abrigo
    if to in ctx.objects:
        dest_kind = "obj"
    elif to in ctx.items and ctx.items[to].get("container"):
        dest_kind = "cont"
    else:
        dests = {i: e2 for i, e2 in ctx.items.items() if e2.get("container")}
        dests.update({o: n for o, n in ctx.objects.items()})
        return ctx.err(f"'{to}' não guarda nada dentro", "container",
                       ctx.validos(dests)), False
    # slot (não vestido) é AUTORIDADE do executor agora (item 31): recusa corrigível.
    rej = ctx.apply_op_now("item_transfers", {"item": item, "to": to, "mode": "stow"})
    if rej:
        return ctx.deny(item, to, rej), False
    ctx.track_move(item, dest_kind, to, None)
    return {"ok": True, "aplicado": {"item": item, "to": to}}, False


def _drop(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    # posse (na mão) e slot (não vestido) são AUTORIDADE do executor agora (item 31).
    rej = ctx.apply_op_now("item_transfers", {"item": item, "to": ctx.place_id,
                                              "mode": "drop"})
    if rej:
        return ctx.deny(item, ctx.place_id, rej), False
    ctx.track_move(item, "place", ctx.place_id, None)
    return {"ok": True, "aplicado": {"item": item, "to": ctx.place_id}}, False


def _shove(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    to = args.get("to")
    dests = dict(ctx.objects)
    if ctx.place_id:
        dests[ctx.place_id] = f"{ctx.idx['place_name']} (o chão daqui)"
    if to not in dests:
        return ctx.err(f"destino '{to}' não reconhecido", "to", ctx.validos(dests)), False
    # "empurra-se só o que ninguém carrega" é AUTORIDADE do executor agora (item 31):
    # a recusa (item_carregado) volta corrigível, com os itens soltos como validos.
    dest_kind = "obj" if to in ctx.objects else "place"
    rej = ctx.apply_op_now("item_transfers", {"item": item, "to": to, "mode": "shove"})
    if rej:
        return ctx.deny(item, to, rej), False
    ctx.track_move(item, dest_kind, to, None)
    return {"ok": True, "aplicado": {"item": item, "to": to}}, False


def _equip(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    # vestibilidade (item_nao_vestivel), posse-alheia (item_alheio) e "já vestido"
    # (no-op idempotente) são AUTORIDADE do executor agora (item 31): a recusa volta
    # estruturada/corrigível. `veste_em` fica só como slot de destino do track.
    veste = e.get("veste_em")
    rej = ctx.apply_op_now("equip_ops", {"op": "equip", "item": item})
    if rej:
        return ctx.deny(item, ctx.actor, rej), False
    ctx.track_move(item, "char", ctx.actor, veste)
    return {"ok": True, "aplicado": {"item": item, "veste_em": veste}}, False


def _unequip(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    # "está vestido em quem age?" é AUTORIDADE do executor agora (item 31): a recusa
    # (nao_vestido_em_voce) volta corrigível, com os vestidos como validos.
    to = args.get("to") or ctx.actor
    if to == ctx.actor:
        rej = ctx.apply_op_now("equip_ops", {"op": "unequip", "item": item, "to": ctx.actor})
        if rej:
            return ctx.deny(item, ctx.actor, rej), False
        ctx.track_move(item, "char", ctx.actor, ctx.hand)
        return {"ok": True, "aplicado": {"item": item, "to": "mão"}}, False
    if to == ctx.place_id:
        rej = ctx.apply_op_now("equip_ops", {"op": "unequip", "item": item, "to": ctx.place_id})
        if rej:
            return ctx.deny(item, ctx.place_id, rej), False
        ctx.track_move(item, "place", ctx.place_id, None)
        return {"ok": True, "aplicado": {"item": item, "to": ctx.place_id}}, False
    if to in ctx.items and ctx.items[to].get("container"):
        rej = ctx.apply_op_now("equip_ops", {"op": "unequip", "item": item, "to": to})
        if rej:
            return ctx.deny(item, to, rej), False
        ctx.track_move(item, "cont", to, None)
        return {"ok": True, "aplicado": {"item": item, "to": to}}, False
    dests = {i: e2 for i, e2 in ctx.items.items() if e2.get("container")}
    if ctx.place_id:
        dests[ctx.place_id] = f"{ctx.idx['place_name']} (o chão daqui)"
    return ctx.err(f"destino '{to}' não reconhecido", "to",
                   ctx.validos(dests, {ctx.actor: ctx.chars.get(ctx.actor, "")})), False


def _steal(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    item = args.get("item")
    if alvo == ctx.actor:
        return ctx.err("não se rouba de si mesmo"), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "alvo",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    if item not in ctx.items:
        return ctx.err(f"item '{item}' não está na cena", "item", ctx.validos(ctx.items)), False
    if ctx.items[item].get("porter") != alvo:
        return ctx.err(f"'{item}' não é de '{alvo}' para furtar", "item"), False
    if (alvo, item) in ctx.stole_asked:
        return ctx.err(f"furtar '{item}' de '{alvo}' já foi tentado neste turno — "
                       "o desfecho sai na aplicação; NÃO repita"), False
    # spec 043 — O CONTRATO DE ANÁLISE do furto. A nota NÃO vem de fora (o que chegar
    # em `args["exposicao"]` é ignorado, FR-005): é a capacidade que pergunta ao
    # mundo, com a régua que mora aqui do lado e exatamente o que ela manda ler.
    exposicao = juizo.nota(
        ctx.ask(REGUA_FURTO + juizo.NOTA_0_10,
                json.dumps({
                    "item": ctx.describe(item),      # vistosidade, pela descrição
                    "dono": ctx.describe(alvo),      # atenção: o que ele faz agora
                    "cena": ctx.describe(ctx.place_id),   # cheia ou vazia
                    "prosa": ctx.prosa,              # COMO se tentou
                }, ensure_ascii=False, indent=2)),
        default=5)   # parelho: tão provável passar quanto ser pego
    # VEREDITO é do executor agora (item 31 §2): extremo da régua (exposicao 0 =
    # furto_impossivel) e a ROLAGEM (limpo/flagrado) decidem lá. A tentativa
    # ACONTECEU — trava o veredito único mesmo negada — e a recusa do mundo narra.
    ctx.stole_asked.add((alvo, item))
    rej, rolled = ctx.apply_arbitrated(
        "steal_ops", {"alvo": alvo, "item": item, "exposicao": exposicao})
    if rej:
        return ctx.arb_deny(rolled, ("steal", alvo, item),
                            {"alvo": alvo, "item": item}, rej)
    return {"ok": True, "aplicado": {"alvo": alvo, "item": item,
                                     "nota": "o desfecho sai na aplicação"}}, False


TAKE = tool_spec(ToolSpec(
    names=("take",),
    description="Pega um item para a mão do personagem que age.",
    params={"item": _STR},
    required=("item",),
    enum_sources={"item": "take"},
    apply=_take,
))


GIVE = tool_spec(ToolSpec(
    names=("give",),
    description=(
        "Entrega um item seu na mão de outro personagem presente. Se esta "
        "entrega CUMPRE algo que você mesmo pretendia (devolver, pagar, "
        "completar um compromisso seu), informe intention_id com o id dela — "
        "a intenção fecha automaticamente. Omitir não muda nada: a entrega "
        "funciona normalmente, sem tocar em nenhuma intenção. Se emprestimo "
        "for true, a posse muda mas o DONO não — você continua sendo "
        "reconhecido como dono de fato (ninguém mais consegue vender/"
        "oferecer o item enquanto isso for lembrado), sem precisar de "
        "nenhuma promessa: é garantia mecânica, não social. Para reforçar "
        "com uma expectativa de devolução ('prometo devolver em três "
        "dias'), use promise (sem item) OU faça quem recebeu prometer "
        "verbalmente — os dois se somam, não se substituem."
    ),
    params={"item": _STR, "to": _STR, "intention_id": _STR,
            "emprestimo": {"type": "boolean"}},
    required=("item", "to"),
    enum_sources={"item": "give", "to": "give_to",
                  "intention_id": lambda s: s.active_intention_ids},
    apply=_give,
))


STOW = tool_spec(ToolSpec(
    names=("stow",),
    description=("Guarda um item dentro de um contêiner (bolso, mochila, "
                 "bolsa) ou de um objeto da cena (baú). Se você não disser "
                 "ONDE, ele mesmo acha a primeira bolsa aberta com espaço — "
                 "é assim que se libera uma mão sem ter de escolher."),
    params={"item": _STR, "container": _STR},
    required=("item",),
    enum_sources={"item": "stow", "container": "stow_in"},
    apply=_stow,
))


DROP = tool_spec(ToolSpec(
    names=("drop",),
    description=lambda s: f"Larga um item no chão daqui ('{s.place_id}').",
    params={"item": _STR},
    required=("item",),
    enum_sources={"item": "drop"},
    apply=_drop,
))


SHOVE = tool_spec(ToolSpec(
    names=("shove",),
    description=("Empurra/arrasta um item que ninguém carried_item_ids até um objeto "
                 "ou o chão da cena — para o que é pesado demais de erguer."),
    params={"item": _STR, "to": _STR},
    required=("item", "to"),
    enum_sources={"item": "shove", "to": "shove_to"},
    apply=_shove,
))


EQUIP = tool_spec(ToolSpec(
    names=("equip",),
    description=("Veste um item na parte do corpo que ELE declara. Para "
                 "trocar, chame unequip antes, no mesmo turno."),
    params={"item": _STR},
    required=("item",),
    enum_sources={"item": "equip"},
    apply=_equip,
))


def _unequip_to(s):
    return ([s.actor_id] if s.actor_id else []) \
        + s.cand["stow_in"] + ([s.place_id] if s.place_id else [])


UNEQUIP = tool_spec(ToolSpec(
    names=("unequip",),
    description=lambda s: ("Tira um item vestido. 'to': o próprio personagem (fica na "
                           "mão), um contêiner com vaga, ou "
                           f"'{s.place_id}' (o chão daqui)."),
    params={"item": _STR, "to": _STR},
    required=("item",),
    enum_sources={"item": "unequip", "to": _unequip_to},
    apply=_unequip,
))


STEAL = tool_spec(ToolSpec(
    names=("steal",),
    juizo=("exposicao", REGUA_FURTO),
    description=("FURTA um item de outro presente, SEM consentimento — o item é do "
     "ALVO. O que é vistoso e o que está preso ao corpo não se tiram do "
     "mesmo jeito, e um dono atento não é um dono distraído: o mundo lê a "
     "cena e decide. Se FLAGRADO, o dono guarda rancor GRAVE, como se "
     "agredido."),
    params={"alvo": _STR, "item": _STR,
            "exposicao": {"type": "integer", "minimum": 0, "maximum": 10}},
    required=("alvo", "item", "exposicao"),
    enum_sources={"alvo": "persuade_give_alvo", "item": "persuade_give_item"},
    apply=_steal,
))
