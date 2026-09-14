"""DECLARAÇÃO + CORPO das tools de COMÉRCIO (spec 038, L3).

ask_wares (consultiva), persuade_give (arbitrada), buy/trade (arbitradas, MESMO
corpo, DUAS declarações — a variante `modo` é o próprio `name`). Migradas de
`arbiter_tools/comercio.py` (deletado). Corpos operam sobre o `ctx` duck-typed;
`import motor` é usado só em RUNTIME (offered_by), nunca no import — sem ciclo.
Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

import json
from .. import juizo

import motor

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# Saiu de `arbiter.py`, onde vivia colada num system prompt único que despejava
# TODAS as réguas em todo turno (12.507 de 15.164 caracteres — 82% do prompt —
# para no máximo uma ser usada). Migrou como TEXTO: string não cria dependência,
# e o Motor segue sem conhecer o Árbitro nem o llm.

REGUA_DISPOSICAO_CEDER = """\
Régua da DISPOSIÇÃO A CEDER um item (quando pedem que o DONO entregue algo dele a
alguém — a si mesmo ou a outro presente).

PASSO 1 — o portão do trauma. Se o DONO guarda lembrança de violência, roubo ou
traição às mãos de QUEM PEDE, a nota É 0, sem ponderar. Quem foi golpeado ou
roubado não faz favor ao agressor. (O Motor também impõe isso; não o contrarie.)

PASSO 2 — ceder um bem NÃO é trivial (ao contrário de indicar um caminho): o normal
é HESITAR, e o padrão de um desconhecido pedindo algo de valor é BAIXO. Dimensione
lendo (a) o que a coisa VALE e o que a DESCRIÇÃO dela sugere (comida farta que
sobra é fácil; um anel de família, quase impossível), (b) a RELAÇÃO PERCEPTÍVEL
entre o dono e QUEM VAI RECEBER (dar a um amigo/protegido é mais fácil que a um
estranho — leia o "saldo_afeto" e a cena, sem inventar número), e (c) a
razoabilidade do pedido:
  0  não cede de jeito nenhum — trauma de quem pede, ou é um bem que ele jamais larga (sem teste)
  1  agarra o que é seu — hostil ou o item lhe é precioso demais
  2  muito relutante — desconfia, ou o valor pesa muito
  3  resiste — não vê por que se desfazer disso
  4  hesitante — daria, mas o item ou o momento o seguram
  5  em dúvida — poderia ceder, se houver um bom motivo/relação
  6  disposto — não lhe custa caro e a pessoa não lhe é indiferente
  7  generoso — dá de bom grado a quem trata bem, coisa de pouca monta
  8  solícito — gosta de agradar, ou o bem é banal para ele
  9  pródigo — afeto, gratidão ou fartura o fazem oferecer quase sem pedir
  10 já ia dando — estende a mão antes de terminarem o pedido (sem teste)
Coisa de valor + estranho = nota BAIXA por padrão (não é hostilidade, é prudência).
Comida/bagatela + qualquer um razoável = nota média-alta. A relação com QUEM RECEBE
move a nota mais que a simpatia por quem pede. A nota é segredo do mundo: nunca o
número na narrativa; 1–9 têm teste na aplicação — não narre o desfecho como certo."""

REGUA_NECESSIDADE = """\
Régua da NECESSIDADE (dimensione SEMPRE por ela, lendo o PARCEIRO — o que ele faz da
vida, o que suas memórias e sua condição dizem que lhe falta, e o quanto o que ele
ENTREGA lhe faz falta; nunca o desejo de quem propõe, nunca o fato de o player ter
pedido; reavalie a cada tentativa):
  0  não precisa de nada disso, e o que se pede lhe faz falta real (não troca, sem teste)
  1  o que recebe é inútil para ele e o que dá faz falta
  2  não vê serventia no que recebe
  3  prefere ficar com o que tem
  4  trocaria só por consideração a quem pede
  5  indiferente — nem ganha nem perde com isso
  6  o que recebe tem alguma serventia
  7  o que recebe serve ao que ele faz ou quer
  8  precisava justamente disso
  9  é o que ele procurava, e o que dá já lhe pesa
  10 precisa desesperadamente do que recebe e o que entrega já lhe sobra (troca sem teste)
O PADRÃO É 2-4, NÃO 5: ninguém entrega o que é seu sem motivo, e nota alta precisa de
justificativa no que o mundo registra sobre ele. A nota é sobre NECESSIDADE, não sobre
preço — o mundo compara os valores sozinho, e uma oferta generosa ajuda mesmo com
necessidade baixa.
O AFETO do parceiro por quem propõe o mundo JÁ PESA sozinho no desfecho (em
"afeto_por_voce", quando pesa): quem detesta cobra mais caro, quem estima cobra menos.
NÃO rebaixe a necessidade por causa disso — a régua é só sobre precisar do que recebe;
o afeto entra por fora. Use "afeto_por_voce" para NARRAR a reação (a má vontade, a
cordialidade), não para mexer na nota.
A nota é segredo do mundo: NUNCA a mencione na narrativa, e ela NÃO
decide sozinha — entre 1 e 9 há um teste resolvido na aplicação. Não narre o negócio
como certo."""

_STR = {"type": "string"}
_NOTA = {"type": "integer", "minimum": 0, "maximum": 10}


@inworld("persuade_give_ops_applied")
def _iw_persuade_give(op):
    doador = name_of(op.get("alvo"))
    item = name_of(op.get("item"))
    para = name_of(op.get("para"))
    return f"convenceu {doador} a entregar {item} a {para}"


@inworld("trade_ops_applied")
def _iw_trade(op):
    return f"fechou negócio com {name_of(op.get('parceiro'))}"


def _ask_wares(name: str, args: dict, ctx) -> tuple[dict, bool]:
    parceiro = args.get("parceiro")
    if parceiro not in ctx.chars or parceiro == ctx.actor:
        return ctx.err(f"'{parceiro}' não é um personagem presente", "parceiro",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    try:
        oferta = motor.offered_by(parceiro)
    except motor.MotorError:
        return ctx.err(f"'{parceiro}' não está ao alcance"), False
    ctx.queue["wares"].append(oferta)
    return {"ok": True, "oferta": oferta}, False


def _persuade_give(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    item = args.get("item")
    para = args.get("para")
    if alvo == ctx.actor:
        return ctx.err("para dar o que é SEU, use give — persuade_give é o item de OUTRO"), False
    if alvo not in ctx.chars:
        return ctx.err(f"'{alvo}' não é um personagem presente", "alvo",
                       ctx.validos({c: n for c, n in ctx.chars.items()
                                    if c != ctx.actor})), False
    if para == alvo:
        return ctx.err("não faz sentido pedir que ele dê a si mesmo", "para"), False
    if para not in ctx.chars:
        return ctx.err(f"'{para}' não é um presente que possa receber", "para",
                       ctx.validos(ctx.chars)), False
    if item not in ctx.items:
        return ctx.err(f"item '{item}' não está na cena", "item", ctx.validos(ctx.items)), False
    if ctx.items[item].get("porter") != alvo:
        return ctx.err(f"'{item}' não é de '{alvo}' para ceder", "item"), False
    if (alvo, item) in ctx.gave_asked:
        return ctx.err(f"pedir a '{alvo}' que ceda '{item}' já foi feito neste turno — "
                       "o desfecho sai na aplicação; NÃO repita"), False
    # spec 043 — CONTRATO DE ANÁLISE: a régua de CEDER lê o que a coisa vale, a
    # relação do dono com QUEM VAI RECEBER, e o que ele guarda de quem pede.
    disposicao = juizo.nota(
        ctx.ask(REGUA_DISPOSICAO_CEDER + juizo.NOTA_0_10,
                json.dumps({"dono": ctx.describe(alvo),
                            "item": ctx.describe(item),
                            "quem_recebe": ctx.describe(para),
                            "saldo_afeto": motor.sentiment_label(motor.sentiment_toward(alvo, ctx.actor)),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=5)
    # VEREDITO é do executor agora (item 31 §2): estado do alvo (alvo_desacordado),
    # extremo da régua (nada_a_ceder), portão de trauma e ROLAGEM decidem lá. O pedido
    # ACONTECEU — trava o veredito único mesmo negado — e a recusa do mundo narra.
    ctx.gave_asked.add((alvo, item))
    rej, rolled = ctx.apply_arbitrated(
        "persuade_give_ops",
        {"alvo": alvo, "item": item, "para": para, "disposicao": disposicao})
    if rej:
        return ctx.arb_deny(rolled, ("persuade_give", alvo, item),
                            {"alvo": alvo, "item": item}, rej)
    return {"ok": True, "aplicado": {"alvo": alvo, "item": item, "para": para,
                                     "nota": "o desfecho sai na aplicação"}}, False


REGUA_COBRANCA = """\
Régua do CUMPRIMENTO (dimensione SEMPRE por ela, lendo o que o MUNDO lembra da
promessa e do que veio depois dela — nunca o desejo de quem cobra, nunca o fato de o
player ter pedido; reavalie a cada cena):
  0  não cumpriu nada do que foi prometido (não paga, sem teste)
  1  fez o contrário do combinado
  2  começou e largou
  3  cumpriu mal, ou cobra na frente de gente, constrangendo
  4  cumpriu em parte, e faz tempo
  5  cumpriu faz tempo, ou cumpriu em parte — o caso comum
  6  cumpriu o essencial, com sobras pendentes
  7  cumpriu, mas ele não presenciou — precisa acreditar na sua palavra
  8  cumpriu e há quem tenha visto
  9  cumpriu à vista dele, e ainda é assunto recente
  10 cumpriu exatamente o combinado, ele viu, e foi há pouco (paga sem teste)
PUXAM PARA BAIXO: cobrar antes da hora combinada, cobrar com agressividade, cobrar o
que não se cumpriu. O PADRÃO É 4-5, NÃO 7: quem cobra sempre acha que cumpriu mais do
que o outro viu, e nota alta precisa de um fato na cena ou na memória que a sustente."""


def _buy_trade(name: str, args: dict, ctx) -> tuple[dict, bool]:
    parceiro = args.get("parceiro")
    outros_n = ctx.validos({c: n for c, n in ctx.chars.items() if c != ctx.actor})
    if parceiro == ctx.actor:
        return ctx.err("ninguém negocia consigo mesmo — escolha outro personagem "
                       "presente", "parceiro", outros_n), False
    if parceiro not in ctx.chars:
        return ctx.err(f"'{parceiro}' não é um personagem presente", "parceiro", outros_n), False
    if parceiro in ctx.negociados:
        return ctx.err(f"a negociação com '{parceiro}' já aconteceu neste turno — o "
                       "desfecho sai na aplicação; NÃO repita"), False
    if name == "buy":
        dou, recebo = args.get("pagamento") or [], args.get("mercadoria") or []
    else:
        dou, recebo = args.get("ofereco") or [], args.get("quero") or []
    if not isinstance(dou, list) or not isinstance(recebo, list) or not dou or not recebo:
        return ctx.err("negociação precisa de duas pontas: algo sai de cada lado"), False
    # posse é CORRIGÍVEL (a guarda propõe com validos). O estado do parceiro
    # (parceiro_incapaz), o PORTÃO de item (moeda/à venda/negociável) e a DECISÃO
    # (valor/necessidade/dado) são AUTORIDADE do executor agora (item 31 §2).
    for iid in dou:
        e = ctx.items.get(iid)
        if e is None or e["porter"] != ctx.actor:
            return ctx.err(f"'{iid}' não está com quem oferece", "item",
                           ctx.validos({i: v["name"] for i, v in ctx.items.items()
                                        if v["porter"] == ctx.actor})), False
    for iid in recebo:
        e = ctx.items.get(iid)
        if e is None or e["porter"] in (None, ctx.actor):
            return ctx.err(f"'{iid}' não está com '{parceiro}'", "item"), False
    op = {"modo": "buy" if name == "buy" else "trade",
          "parceiro": parceiro, "dou": list(dou), "recebo": list(recebo)}
    if name == "trade":
        # spec 043 — CONTRATO DE ANÁLISE: a régua da necessidade lê o PARCEIRO e o
        # que ele recebe contra o que entrega. O valor das coisas o mundo calcula à
        # parte — a nota é só sobre PRECISAR.
        op["necessidade"] = juizo.nota(
            ctx.ask(REGUA_NECESSIDADE + juizo.NOTA_0_10,
                    json.dumps({"parceiro": ctx.describe(parceiro),
                                "ele_recebe": [ctx.describe(i) for i in dou],
                                "ele_entrega": [ctx.describe(i) for i in recebo],
                                "afeto_por_voce": motor.sentiment_label(motor.sentiment_toward(parceiro, ctx.actor)),
                                "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
            default=3)   # o padrão é NÃO negociar
    ctx.negociados.add(parceiro)
    rej, rolled = ctx.apply_arbitrated("trade_ops", op)
    if rej:
        return ctx.arb_deny(rolled, ("trade", parceiro),
                            {"negociar": parceiro, "modo": op["modo"]}, rej)
    return {"ok": True, "aplicado": {"parceiro": parceiro,
                                     "nota": "o desfecho sai na aplicação"}}, False


ASK_WARES = tool_spec(ToolSpec(
    names=("ask_wares",),
    description=("Pergunta a OUTRO personagem presente o que ele tem à "
                 "venda ou para trocar. Use quando o personagem quiser "
                 "saber o que alguém oferece — a mercadoria pode estar "
                 "guardada, e ninguém adivinha o que não viu. Não muda "
                 "nada no mundo: só traz a resposta para narrar."),
    params={"parceiro": _STR},
    required=("parceiro",),
    enum_sources={"parceiro": "negociar_com"},
    apply=_ask_wares,
))


PERSUADE_GIVE = tool_spec(ToolSpec(
    names=("persuade_give",),
    juizo=(("disposicao", REGUA_DISPOSICAO_CEDER),),
    description=("Convence o DONO (outro presente) a ENTREGAR um item DELE a alguém — "
     "a QUEM AGE ou a outro presente ('para'). O item é do ALVO, não seu; "
     "para dar o que é SEU use give. Ceder um bem não é favor pequeno, e "
     "quem cede pesa o que a coisa vale e quem vai recebê-la. Dando certo, "
     "quem RECEBE ganha afeto pelo DONO — foi ele quem deu."),
    params={"alvo": _STR, "item": _STR, "para": _STR, "disposicao": _NOTA},
    required=("alvo", "item", "para", "disposicao"),
    enum_sources={"alvo": "persuade_give_alvo", "item": "persuade_give_item",
                  "para": "persuade_give_para"},
    apply=_persuade_give,
))


BUY = tool_spec(ToolSpec(
    names=("buy",),
    description=("Compra itens de OUTRO personagem presente pagando com "
                 "DINHEIRO. Só aparecem aqui as moedas de quem age e o "
                 "que o dono marcou à venda. Você NÃO decide se o "
                 "negócio fecha: o mundo compara o que se paga com o "
                 "que a mercadoria vale. Para pagar com bens em vez de "
                 "moedas, use trade. UMA vez por parceiro no turno."),
    params={"parceiro": _STR,
            "pagamento": {"type": "array", "items": {"type": "string"}},
            "mercadoria": {"type": "array", "items": {"type": "string"}}},
    required=("parceiro", "pagamento", "mercadoria"),
    enum_sources={"parceiro": "negociar_com", "pagamento": "pagar_com",
                  "mercadoria": "comprar"},
    apply=_buy_trade,
))


TRADE = tool_spec(ToolSpec(
    names=("trade",),
    juizo=(("necessidade", REGUA_NECESSIDADE),),
    description=("Troca bens por bens com OUTRO personagem presente, sem dinheiro. Só "
     "aparecem aqui os itens que o mundo marca como negociáveis. Ninguém "
     "entrega o que é seu sem precisar do que recebe: o parceiro pesa o "
     "que ganha contra o que perde, e o valor das coisas também conta."),
    params={"parceiro": _STR,
            "ofereco": {"type": "array", "items": {"type": "string"}},
            "quero": {"type": "array", "items": {"type": "string"}},
            "necessidade": _NOTA},
    required=("parceiro", "ofereco", "quero", "necessidade"),
    # FR-014 (spec 073): sem `intention_id` — ver a nota em `itens/declaracao.py`.
    enum_sources={"parceiro": "negociar_com", "ofereco": "ofertar",
                  "quero": "pedir"},
    apply=_buy_trade,
))


def _cobrar(name: str, args: dict, ctx) -> tuple[dict, bool]:
    """COBRAR o que foi prometido (spec 073, US6).

    A guarda PROPÕE (resolve referências, barra o que é erro corrigível); o Motor
    DECIDE (a promessa existe? o dado passou?). A régua é lida UMA VEZ por turno por
    alvo — ver `ctx.cobrados`.
    """
    de_quem = args.get("de_quem")
    item = args.get("item")
    outros_n = ctx.validos({c: n for c, n in ctx.chars.items() if c != ctx.actor})
    if de_quem == ctx.actor:
        return ctx.err("ninguém cobra de si mesmo — escolha outro personagem "
                       "presente", "de_quem", outros_n), False
    if de_quem not in ctx.chars:
        return ctx.err(f"'{de_quem}' não é um personagem presente", "de_quem",
                       outros_n), False
    # O VEREDITO É ÚNICO NO TURNO. A cena se lê uma vez; recusado o desfecho, re-ler a
    # régua com nota maior seria contornar o Árbitro por reescrita de régua.
    if de_quem in ctx.cobrados:
        return ctx.err(f"a cobrança a '{de_quem}' já aconteceu neste turno — o "
                       "desfecho sai na aplicação; NÃO repita"), False
    op = {"de_quem": de_quem}
    if item:
        op["item"] = item
    # CONTRATO DE ANÁLISE: a régua lê o que o MUNDO lembra, não o que quem cobra acha.
    # O afeto desce em RÓTULO (o mundo é que soma as memórias — pedir ao Árbitro que
    # as some de cabeça foi medido ruim na spec 016).
    # A DÍVIDA DESCE COMO DADO, e o NOME DA CHAVE CARREGA O SUJEITO.
    #
    # Medido em três variantes (`tests/exploracao/sondagem_cobranca.py`, e o
    # registro em `medicoes.md` §14):
    #
    #   V0  sem o fato                        média 2.31, 2 contrastes frouxos
    #   V1  `o_que_ele_prometeu`              média 1.06, 2 contrastes INVERTIDOS
    #   V2  `a_divida_dele_com_voce`          média 3.88, todos os contrastes OK
    #
    # A V1 foi um erro meu, e ele ensina: a régua julga se VOCÊ cumpriu a sua parte,
    # e uma chave chamada "o que ele prometeu" trocou o sujeito do juízo — o modelo
    # passou a perguntar se ELE cumpriu, e como ele ainda não pagou (é por isso que
    # se cobra), a nota desabou para 0. O nome da chave não é rótulo: é parte do
    # contrato de análise.
    promessa = motor.memoria.promessa_em_texto(
        motor.memoria.promessa_viva_de(ctx.actor, de_quem))
    op["cumprimento"] = juizo.nota(
        ctx.ask(REGUA_COBRANCA + juizo.NOTA_0_10,
                json.dumps({"de_quem": ctx.describe(de_quem),
                            "a_divida_dele_com_voce": promessa,
                            "afeto_por_voce": motor.sentiment_label(
                                motor.sentiment_toward(de_quem, ctx.actor)),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=4)   # o padrão é a dúvida, não o pagamento
    ctx.cobrados.add(de_quem)
    rej, rolled = ctx.apply_arbitrated("cobranca_ops", op)
    if rej:
        return ctx.arb_deny(rolled, ("cobrar", de_quem), {"cobrar": de_quem}, rej)
    return {"ok": True, "aplicado": {"de_quem": de_quem,
                                     "nota": "o desfecho sai na aplicação"}}, False


COBRAR = tool_spec(ToolSpec(
    names=("cobrar",),
    juizo=(("cumprimento", REGUA_COBRANCA),),
    description=(
        "Reivindica de OUTRO personagem presente aquilo que ele prometeu a você. "
        "Use quando o personagem decide COBRAR — não para perguntar se o outro "
        "pretende pagar (isso é ask_about, e não obriga ninguém). Aqui duas "
        "vontades se opõem: você exige, ele decide. Só cabe cobrar de quem você "
        "LEMBRA ter prometido algo; sem essa lembrança, não há o que reivindicar. "
        "Você NÃO decide o desfecho: o mundo pesa o quanto você cumpriu a sua "
        "parte, o que ele guarda de você, e o acaso. Ele pode pagar, regatear "
        "(pagar menos, ou em outra coisa) ou negar — e negar deixa marca nos dois. "
        "Informe item se há algo dele que você aceita como pagamento. UMA vez por "
        "pessoa no turno."
    ),
    params={"de_quem": _STR, "item": _STR},
    required=("de_quem",),
    enum_sources={"de_quem": "negociar_com", "item": "cobrar_item"},
    apply=_cobrar,
))


@inworld("cobranca_ops_applied")
def _iw_cobranca(op):
    """O desfecho da cobrança, sem NENHUM número (Princípio V).

    Os três desfechos são coisas diferentes na cena, e por isso três frases: pagar
    encerra, regatear deixa um resto, negar deixa uma dívida de pé. A última é a que
    o jogo precisa que se leia — é dela que nasce a memória que endurece os dois.
    """
    de_quem = name_of(op.get("de_quem"))
    item = op.get("item")
    desfecho = op.get("desfecho")
    if desfecho == "nega":
        return f"cobrou {de_quem}, e não recebeu nada"
    if desfecho == "regateia":
        return f"cobrou {de_quem}, e saiu com menos do que era devido"
    if item:
        return f"cobrou {de_quem}, e recebeu {name_of(item)}"
    return f"cobrou {de_quem}, e ele acertou o que devia"
