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

# --- As quatro réguas de `eat` (spec 046) ----------------------------------- #
# `eat` é a primeira capacidade com MAIS de uma régua — cada uma cobre um eixo
# que o Motor não consegue validar sozinho (ele sabe presença/alcance; não sabe
# o que a descrição SIGNIFICA). Comestibilidade é perguntada PRIMEIRO e SEMPRE;
# as outras três só quando ela não for 0 (curto-circuito, research R1).

REGUA_COMESTIBILIDADE = """\
Régua da COMESTIBILIDADE (o quanto, PELA DESCRIÇÃO do item, ele é algo que se
poderia comer — não o quanto é gostoso, só se É comida):
  0  claramente NÃO é comida — objeto, material bruto, ou algo fabricado que só
     IMITA o formato (uma fruta de cera, um sabão em forma de maçã) (sem teste)
  1  quase certamente não — nada na descrição sugere nutrição, só a forma engana
  2  muito improvável — um material bruto (couro, madeira, pedra, metal)
  3  duvidoso — comestível só em teoria, sem preparo nenhum (casca crua, folha)
  4  incerto — serviria em desespero, mas a descrição não confirma nutrição
  5  ambíguo — a descrição não decide; tanto pode ser alimento quanto não
  6  provável — tem cara de comida, mas falta um detalhe que confirme
  7  bastante provável — claramente algo que se come, mesmo cru ou sem preparo
  8  comida reconhecível — fruta, carne, pão, claramente identificável como tal
  9  comida óbvia e fresca
  10 comida perfeita e evidente — não há dúvida nenhuma (sem teste)
Objeto decorativo ou fabricado que IMITA comida puxa a nota para 0, mesmo que a
aparência engane — a descrição costuma denunciar (frio demais, sem cheiro, cor
parada demais). A nota é segredo do mundo: nunca o número na narrativa; nota 0
faz a tentativa ser recusada, mesmo que as outras três notas venham preenchidas."""

REGUA_SACIEDADE = """\
Régua da SACIEDADE (o quanto o ato satisfaz a fome, pelo tamanho e tipo do
alimento DESCRITO — nunca a vontade de quem come):
  0  zero valor nutricional — a ação não alimenta em nada
  1  belisco ínfimo — uma amora, uma migalha
  2  quase nada — um gole, um pedaço minúsculo
  3  lanche leve — uma fruta pequena
  4  lanche — uma fruta média, um punhado
  5  refeição módica — um pedaço de pão, uma porção pequena
  6  refeição média — um prato de sopa, uma fatia farta
  7  refeição boa — uma refeição completa comum
  8  refeição farta — uma perna de carneiro, um prato fartíssimo
  9  banquete — muito mais que uma pessoa precisa numa refeição
  10 saciedade extrema/mágica — fartura fora do comum
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a nota
num RÓTULO de fome (nunca grava o número na ficha)."""

REGUA_TOXICIDADE = """\
Régua da TOXICIDADE (o quanto o item, PELA DESCRIÇÃO, é arriscado — cru,
estragado, contaminado ou venenoso pesam diferente de fresco e eram próprio):
  0  inofensivo — nada na descrição sugere risco (sem teste)
  1  risco mínimo — levemente cru ou não ideal, mal chega a incomodar
  2  risco baixo — desconfortável no máximo
  3  risco leve — pode embrulhar o estômago de quem for sensível
  4  risco moderado-baixo — cru ou mal conservado, mas não flagrante
  5  risco moderado — claramente não é o ideal, mas não é óbvio o perigo
  6  risco moderado-alto — sinais de deterioração ou contaminação visíveis
  7  risco alto — cheiro/aparência que qualquer um reconheceria como ruim
  8  risco muito alto — claramente estragado ou com sinais de veneno
  9  quase certo — a descrição deixa pouca dúvida do perigo
  10 mortal — veneno declarado ou deterioração extrema (sem teste)
A nota é segredo do mundo: nunca o número na narrativa; 1–9 têm UM teste de
resistência na aplicação — não narre o adoecimento como certo nem como evitado."""

REGUA_CONSUMO = """\
Régua do CONSUMO (o quanto do item RESTA depois do ato — não se foi gostoso):
  0  nada resta — devorado por completo
  1  quase nada — uma migalha, um resto irrisório
  2  muito pouco resta
  3  pouco resta
  4  perto da metade resta
  5  metade resta
  6  um pouco mais da metade resta
  7  a maior parte resta
  8  quase tudo resta — só uma mordida
  9  quase intacto — um traço mínimo de uso
  10 praticamente intacto
Junto da nota, escreva um texto CURTO e FACTUAL descrevendo o novo estado físico
do item (o que qualquer um veria olhando para ele — nunca o sabor, o nojo ou a
satisfação de quem comeu), preservando as qualidades da descrição original (ex.:
"maçã vermelha grande" -> "maçã vermelha, com a metade comida"). A nota é
segredo do mundo; o TEXTO da nova descrição é o único elemento desta régua que
vira estado do mundo."""

# spec 046 — CORRIGIDO em campo (custo/latência, decisão do mantenedor): os
# quatro eixos são julgados numa ÚNICA chamada ao modelo, não uma por régua —
# quatro chamadas por mordida deixava a ação lenta e cara. Pedir o JSON com o
# schema EXPLÍCITO (em vez de um formato livre tipo "duas linhas") é o que
# funciona: o modelo já quer responder em JSON por conta própria (medido em
# toda sondagem real deste projeto); brigar com esse hábito é que quebrava.
REGUA_COMER = f"""\
Você vai julgar UMA tentativa de comer um item, em QUATRO eixos independentes.
Leia a descrição do item com cuidado antes de responder.

{REGUA_COMESTIBILIDADE}

{REGUA_SACIEDADE}

{REGUA_TOXICIDADE}

{REGUA_CONSUMO}

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas cinco chaves (os quatro números são OBRIGATÓRIOS, mesmo
que comestibilidade seja 0):

{{"comestibilidade": <inteiro 0-10>, "saciedade": <inteiro 0-10>, "toxicidade": <inteiro 0-10>, "consumo": <inteiro 0-10>, "descricao": "<texto curto e factual do novo estado físico do item>"}}"""

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


@inworld("eat_ops_applied")
def _iw_eat(op):
    """O ATO e o DESFECHO — antes só dizia o ato.

    "comeu Moeda de Prata" é verdade e é inútil: não diz se matou a fome. A Elga
    comeu a MESMA moeda 17 vezes em 12h (2026-08-20) porque cada vez recebia de
    volta "comeu Moeda de Prata" e continuava com fome, sem nunca ligar as duas
    coisas. A nota é segredo do mundo (Princípio V) — desce o rótulo, nunca o
    número, no mesmo molde do rótulo de fome que o executor grava na ficha.
    """
    item = name_of(op.get("item"))
    if op.get("adoeceu"):
        return f"comeu {item} e passou mal"
    saciedade = int(op.get("saciedade") or 0)
    if saciedade >= 7:
        return f"comeu {item} e ficou saciado"
    if saciedade >= 3:
        return f"comeu {item} e tirou a pior da fome"
    return f"comeu {item}, e a fome continuou exatamente onde estava"


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


def _eat(name: str, args: dict, ctx) -> tuple[dict, bool]:
    item, e, st = _item_setup(name, args, ctx)
    if st is None:
        return item, False
    if item in ctx.eaten_asked:
        return ctx.err(f"comer '{item}' já foi tentado neste turno — o desfecho "
                       "sai na aplicação; NÃO repita: siga para outra ação ou narrate"), False
    # spec 046 — UMA chamada só (custo, decisão do mantenedor): os quatro eixos
    # (comestibilidade/saciedade/toxicidade/consumo) + o texto da nova descrição
    # saem da MESMA resposta, via REGUA_COMER (JSON com schema explícito).
    julgado = juizo.julgamento(
        ctx.ask(REGUA_COMER, json.dumps({"item": ctx.describe(item)},
                                        ensure_ascii=False, indent=2)),
        campos={"comestibilidade": 5, "saciedade": 5, "toxicidade": 0, "consumo": 0},
        texto_campos={"descricao": ""})
    ctx.eaten_asked.add(item)
    comestibilidade = julgado["comestibilidade"]
    if comestibilidade == 0:
        rej, rolled = ctx.apply_arbitrated("eat_ops", {"item": item, "comestibilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("eat", item), {"item": item}, rej)
        return {"ok": True, "aplicado": {"item": item,
                                         "nota": "o desfecho sai na aplicação"}}, False
    consumo, nova_descricao = julgado["consumo"], julgado["descricao"]
    # texto sem número correspondente não pode virar "nada resta" calado — ver
    # a régua de consumo (o mesmo achado da sondagem real segue valendo aqui).
    if consumo == 0 and nova_descricao:
        consumo = 5
    rej, rolled = ctx.apply_arbitrated("eat_ops", {
        "item": item, "comestibilidade": comestibilidade, "saciedade": julgado["saciedade"],
        "toxicidade": julgado["toxicidade"], "consumo": consumo, "nova_descricao": nova_descricao})
    if rej:
        return ctx.arb_deny(rolled, ("eat", item), {"item": item}, rej)
    return {"ok": True, "aplicado": {"item": item,
                                     "nota": "o desfecho sai na aplicação"}}, False


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
    juizo=(("exposicao", REGUA_FURTO),),
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


EAT = tool_spec(ToolSpec(
    names=("eat",),
    # spec 046 — os cinco (quatro notas + o texto) saem da MESMA chamada
    # (`REGUA_COMER`, uma resposta JSON só — custo, decisão do mantenedor).
    juizo=(
        ("comestibilidade", REGUA_COMER),
        ("saciedade", REGUA_COMER),
        ("toxicidade", REGUA_COMER),
        ("consumo", REGUA_COMER),
        ("nova_descricao", REGUA_COMER),
    ),
    description=("Come um item comestível presente ou na sua mão — o mundo decide "
     "se é comida, quanto sacia e quanto arrisca. Recusado se não for algo que "
     "se coma."),
    params={"item": _STR,
            "comestibilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "saciedade": {"type": "integer", "minimum": 0, "maximum": 10},
            "toxicidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "consumo": {"type": "integer", "minimum": 0, "maximum": 10},
            "nova_descricao": _STR},
    required=("item", "comestibilidade", "saciedade", "toxicidade", "consumo",
             "nova_descricao"),
    enum_sources={"item": "eat"},
    apply=_eat,
))


# --- As réguas de `drink` (spec 047) ----------------------------------------- #
# Espelham as de `eat`, com DUAS diferenças: um eixo a mais (embriaguez, com
# condição PRÓPRIA `bêbado`, separada de `doente`) e um alvo a mais (fonte
# ambiental — `object` não-portável, inesgotável). A régua de BEBIBILIDADE
# funciona para os dois tipos de alvo: a MESMA leitura decide se um item é
# líquido ou se um object é fonte de água — nenhum campo novo em nenhum schema.

REGUA_BEBIBILIDADE = """\
Régua da BEBIBILIDADE (o quanto, PELA DESCRIÇÃO do alvo — um item OU uma fonte
ambiental como um rio/poço —, ele é algo que se poderia beber — não o quanto é
saboroso, só se É líquido bebível):
  0  claramente NÃO é bebível — objeto sólido, material bruto, ou algo
     fabricado que só IMITA a forma (uma garrafa de decoração vazia, uma
     estátua de fonte sem água de verdade) (sem teste)
  1  quase certamente não — nada na descrição sugere líquido, só a forma engana
  2  muito improvável — algo pastoso ou sólido demais para se beber
  3  duvidoso — bebível só em desespero, sem confirmação de líquido de verdade
  4  incerto — serviria em desespero, mas a descrição não confirma
  5  ambíguo — a descrição não decide; tanto pode ter líquido quanto não (ex.:
     um cantil ou copo cuja descrição não diz se está cheio)
  6  provável — tem cara de bebida, mas falta um detalhe que confirme
  7  bastante provável — claramente algo que se bebe, mesmo cru ou impróprio
  8  bebida reconhecível — água, vinho, cerveja, claramente identificável
  9  bebida óbvia e fresca/farta
  10 bebida perfeita e evidente — não há dúvida nenhuma (sem teste)
Um cantil/copo/garrafa cuja descrição NÃO diz se tem líquido não é 0 automático
— é ambíguo (em torno de 5): a régua resolve como CLASSIFICAÇÃO, não travando a
ação. Objeto decorativo que IMITA bebida puxa a nota para 0. A nota é segredo do
mundo: nunca o número na narrativa; nota 0 recusa a tentativa, mesmo que as
outras notas venham preenchidas."""

REGUA_HIDRATACAO = """\
Régua da HIDRATAÇÃO (o quanto o ato satisfaz a sede, pela quantidade e tipo do
líquido DESCRITO — nunca a vontade de quem bebe):
  0  zero valor hidratante — a ação não mata a sede em nada
  1  gole ínfimo — uma gota, um resquício
  2  quase nada — um gole minúsculo
  3  pouco — um gole comum
  4  um pouco — alguns goles
  5  quantidade módica — meio copo, um cantil pela metade
  6  quantidade média — um copo cheio, um cantil razoável
  7  quantidade boa — uma bebida completa comum
  8  fartura — um cantil cheio, uma jarra
  9  banquete líquido — muito mais que uma pessoa precisa de uma vez
  10 hidratação extrema/mágica — fartura fora do comum, ou uma fonte inesgotável
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a nota
num RÓTULO de sede (nunca grava o número na ficha)."""

REGUA_EMBRIAGUEZ = """\
Régua da EMBRIAGUEZ (o quanto, PELA DESCRIÇÃO, o líquido é ALCOÓLICO/forte —
não o risco de contaminação, isso é outra régua):
  0  sem álcool nenhum — água, suco, chá (sem teste)
  1  traço mínimo — quase nada, mal se sente
  2  muito fraco — uma cerveja leve, bem aguada
  3  fraco — uma cerveja ou sidra comum
  4  moderado-baixo — uma cerveja forte, um vinho leve
  5  moderado — um vinho comum
  6  moderado-alto — um vinho forte, uma cerveja bem forte
  7  forte — destilado leve, ou vinho de alta graduação
  8  muito forte — aguardente, destilado comum
  9  quase certo de embriagar — destilado forte, feito para derrubar
  10 extremo — puro/reforçado a ponto de embriagar qualquer um (sem teste)
A nota é segredo do mundo: nunca o número na narrativa; 1–9 têm UM teste de
resistência na aplicação — não narre a bebedeira como certa nem como evitada."""

REGUA_TOXICIDADE_BEBIDA = """\
Régua da TOXICIDADE (o quanto o líquido, PELA DESCRIÇÃO, é arriscado por
contaminação/veneno — parado, turvo, contaminado pesam diferente de límpido e
fresco; INDEPENDENTE da força alcoólica):
  0  inofensivo — nada na descrição sugere risco (sem teste)
  1  risco mínimo — levemente parado, mal chega a incomodar
  2  risco baixo — desconfortável no máximo
  3  risco leve — pode embrulhar o estômago de quem for sensível
  4  risco moderado-baixo — parado ou mal conservado, mas não flagrante
  5  risco moderado — claramente não é o ideal, mas não é óbvio o perigo
  6  risco moderado-alto — sinais de contaminação/estagnação visíveis
  7  risco alto — cheiro/aparência que qualquer um reconheceria como ruim
  8  risco muito alto — claramente estragado ou com sinais de veneno
  9  quase certo — a descrição deixa pouca dúvida do perigo
  10 mortal — veneno declarado ou contaminação extrema (sem teste)
A nota é segredo do mundo: nunca o número na narrativa; 1–9 têm UM teste de
resistência na aplicação, INDEPENDENTE do teste de embriaguez — os dois podem
falhar juntos no mesmo gole."""

REGUA_CONSUMO_BEBIDA = """\
Régua do CONSUMO (o quanto do LÍQUIDO resta depois do ato — nunca o recipiente
em si, que NUNCA desaparece: um copo/cantil/garrafa esvaziado continua existindo,
só muda de "cheio" para "vazio"):
  0  nada resta — bebeu tudo, o recipiente fica vazio
  1  quase nada — um resíduo irrisório no fundo
  2  muito pouco resta
  3  pouco resta
  4  perto da metade resta
  5  metade resta
  6  um pouco mais da metade resta
  7  a maior parte resta
  8  quase tudo resta — só um gole a menos
  9  quase intacto — um traço mínimo de uso
  10 praticamente intacto
Junto da nota, escreva um texto CURTO e FACTUAL descrevendo o novo estado físico
do RECIPIENTE (o que qualquer um veria olhando para ele — nunca o sabor, a
ardência ou o alívio de quem bebeu), preservando as qualidades da descrição
original (ex.: "cantil de couro cheio" -> "cantil de couro, quase vazio").
O TEXTO precisa ser COERENTE com a PRÓPRIA nota de consumo que você acabou de
dar nesta resposta, palavra por palavra: nota 4 ou mais NUNCA pode conter
"vazio"/"seco"/"nada resta"/"acabou" — nota 2 ou menos NUNCA pode conter
"cheio"/"intacto"/"corrente". Antes de escrever o texto, releia o NÚMERO que
você mesmo escolheu para "consumo" nesta mesma resposta e confira se o texto
contradiz esse número — se contradizer, reescreva o texto. A nota é segredo
do mundo; o TEXTO da nova descrição é o único elemento desta régua que vira
estado do mundo — e só existe para ITEM, nunca para uma fonte ambiental (que
não muda por ter sido usada)."""

# spec 047 — mesma correção de custo/latência que `eat` (spec 046) já fechou:
# UMA chamada combinada, JSON com schema explícito. DOIS prompts — um alvo
# ITEM pede também consumo+descrição; uma FONTE AMBIENTAL nunca pede isso (ela
# é inesgotável e nunca muda de estado — pedir a nota seria perguntar algo sem
# sentido, e arriscaria uma resposta estranha à toa).
REGUA_BEBER_ITEM = f"""\
Você vai julgar UMA tentativa de beber de um ITEM (algo portátil — cantil,
copo, garrafa), em CINCO eixos independentes. Leia a descrição do item com
cuidado antes de responder.

{REGUA_BEBIBILIDADE}

{REGUA_HIDRATACAO}

{REGUA_EMBRIAGUEZ}

{REGUA_TOXICIDADE_BEBIDA}

{REGUA_CONSUMO_BEBIDA}

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas seis chaves (os quatro números são OBRIGATÓRIOS, mesmo que
bebibilidade seja 0):

{{"bebibilidade": <inteiro 0-10>, "hidratacao": <inteiro 0-10>, "embriaguez": <inteiro 0-10>, "toxicidade": <inteiro 0-10>, "consumo": <inteiro 0-10>, "descricao": "<texto curto e factual do novo estado físico do recipiente>"}}"""

REGUA_BEBER_FONTE = f"""\
Você vai julgar UMA tentativa de beber direto de uma FONTE AMBIENTAL (um
`object` não-portável presente na cena — rio, poço, riacho —, NUNCA um item que
se carregue), em QUATRO eixos independentes. Esta fonte é INESGOTÁVEL por
definição — NÃO existe régua de "quanto resta"; ela nunca muda de estado por
ter sido usada. Leia a descrição da fonte com cuidado antes de responder.

{REGUA_BEBIBILIDADE}

{REGUA_HIDRATACAO}

{REGUA_EMBRIAGUEZ}

{REGUA_TOXICIDADE_BEBIDA}

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas quatro chaves (todas OBRIGATÓRIAS, mesmo que bebibilidade
seja 0):

{{"bebibilidade": <inteiro 0-10>, "hidratacao": <inteiro 0-10>, "embriaguez": <inteiro 0-10>, "toxicidade": <inteiro 0-10>}}"""

_CAMPOS_BEBER_COMUM = {"bebibilidade": 5, "hidratacao": 5, "embriaguez": 0, "toxicidade": 0}
_CAMPOS_BEBER_ITEM = {**_CAMPOS_BEBER_COMUM, "consumo": 0}


@inworld("drink_ops_applied")
def _iw_drink(op):
    alvo = name_of(op.get("alvo"))
    if op.get("embebedou") and op.get("adoeceu"):
        return f"bebeu de {alvo}, ficou bêbado e passou mal"
    if op.get("embebedou"):
        return f"bebeu de {alvo} e ficou bêbado"
    if op.get("adoeceu"):
        return f"bebeu de {alvo} e passou mal"
    return f"bebeu de {alvo}"


def _drink(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    if not alvo:
        return ctx.err("informe 'alvo'"), False
    e_item = alvo in ctx.items
    if not e_item and alvo not in ctx.objects:
        return ctx.err(f"'{alvo}' não reconhecido", "alvo",
                       ctx.validos(ctx.items, ctx.objects)), False
    if alvo in ctx.drunk_asked:
        return ctx.err(f"beber de '{alvo}' já foi tentado neste turno — "
                       "o desfecho sai na aplicação; NÃO repita: siga para outra ação ou narrate"), False
    # spec 047 — o TIPO do alvo escolhe o prompt: só um ITEM pede consumo (uma
    # fonte ambiental nunca se esgota, R1/R4 do research).
    regua = REGUA_BEBER_ITEM if e_item else REGUA_BEBER_FONTE
    campos = _CAMPOS_BEBER_ITEM if e_item else _CAMPOS_BEBER_COMUM
    julgado = juizo.julgamento(
        ctx.ask(regua, json.dumps({"alvo": ctx.describe(alvo)},
                                  ensure_ascii=False, indent=2)),
        campos=campos, texto_campos=({"descricao": ""} if e_item else None))
    ctx.drunk_asked.add(alvo)
    bebibilidade = julgado["bebibilidade"]
    if bebibilidade == 0:
        rej, rolled = ctx.apply_arbitrated("drink_ops", {"alvo": alvo, "bebibilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("drink", alvo), {"alvo": alvo}, rej)
        return {"ok": True, "aplicado": {"alvo": alvo,
                                         "nota": "o desfecho sai na aplicação"}}, False
    payload = {"alvo": alvo, "bebibilidade": bebibilidade,
               "hidratacao": julgado["hidratacao"], "embriaguez": julgado["embriaguez"],
               "toxicidade": julgado["toxicidade"]}
    if e_item:
        consumo, nova_descricao = julgado["consumo"], julgado["descricao"]
        # texto sem número correspondente não pode virar "nada resta" calado —
        # mesmo achado que `eat` já registrou para a régua de consumo.
        if consumo == 0 and nova_descricao:
            consumo = 5
        payload["consumo"] = consumo
        payload["nova_descricao"] = nova_descricao
    rej, rolled = ctx.apply_arbitrated("drink_ops", payload)
    if rej:
        return ctx.arb_deny(rolled, ("drink", alvo), {"alvo": alvo}, rej)
    return {"ok": True, "aplicado": {"alvo": alvo,
                                     "nota": "o desfecho sai na aplicação"}}, False


DRINK = tool_spec(ToolSpec(
    names=("drink",),
    # spec 047 — os seis pares possíveis (mesmo quando o alvo é fonte ambiental
    # e só quatro são de fato perguntados, R4 do research: o `juizo` só serve
    # para esconder os params da FACE, nunca obriga o corpo a perguntar todos).
    juizo=(
        ("bebibilidade", REGUA_BEBER_ITEM),
        ("hidratacao", REGUA_BEBER_ITEM),
        ("embriaguez", REGUA_BEBER_ITEM),
        ("toxicidade", REGUA_BEBER_ITEM),
        ("consumo", REGUA_BEBER_ITEM),
        ("nova_descricao", REGUA_BEBER_ITEM),
    ),
    description=("Bebe de um item (cantil, copo, garrafa) presente/na sua mão, "
     "OU direto de uma fonte ambiental presente (rio, poço) — o mundo decide, "
     "lendo a descrição, se é bebível, o quanto hidrata, o quanto embriaga e o "
     "quanto arrisca. Um alvo claramente não-bebível é recusado. Uma fonte "
     "ambiental nunca se esgota."),
    params={"alvo": _STR,
            "bebibilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "hidratacao": {"type": "integer", "minimum": 0, "maximum": 10},
            "embriaguez": {"type": "integer", "minimum": 0, "maximum": 10},
            "toxicidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "consumo": {"type": "integer", "minimum": 0, "maximum": 10},
            "nova_descricao": _STR},
    required=("alvo", "bebibilidade", "hidratacao", "embriaguez", "toxicidade",
             "consumo", "nova_descricao"),
    enum_sources={"alvo": "drink"},
    apply=_drink,
))
