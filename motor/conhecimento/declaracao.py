"""DECLARAÇÃO + CORPO das tools de CONHECIMENTO (spec 038, L3).

recognize/examine/ask_directions/ask_about (consultivas — não mutam o mundo, só
trazem material para A Mente / gravam via primitiva) + learn_routes (param ARRAY de
objetos, enum FUNDO em `items.properties.rota` → schema por callable). Migradas de
`arbiter_tools/conhecimento.py` (deletado). Descrições que citam a régua são
callables (s.REGUA_*). Corpos sobre o `ctx` duck-typed; `import motor` só em RUNTIME.
Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

import json
import re

from .. import juizo

import motor

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# Saiu de `arbiter.py`, onde vivia colada num system prompt único que despejava
# TODAS as réguas em todo turno (12.507 de 15.164 caracteres — 82% do prompt —
# para no máximo uma ser usada). Migrou como TEXTO: string não cria dependência,
# e o Motor segue sem conhecer o Árbitro nem o llm.

REGUA_DISPOSICAO = """\
Régua da DISPOSIÇÃO A INFORMAR.

PASSO 1 — ANTES de qualquer outra coisa, olhe "lembra_de_voce" (o que o informante
guarda a respeito de QUEM PERGUNTA). Se houver ali QUALQUER lembrança de violência
ou humilhação sofrida às mãos de quem pergunta, a nota É 0. Ponto final.
NÃO pondere, NÃO compense com a simpatia dele, NÃO alegue que o pedido é pequeno
ou trivial, NÃO conclua que ele é prestativo "apesar disso". Nada disso importa:
quem apanhou não indica caminho.
São sinais de violência, e basta UM:
  - o texto contém "me golpeou", "Caí", "me espancou", "me bateu", "me feriu",
    "me ameaçou", "me roubou", "me traiu" — ou qualquer descrição equivalente em
    outras palavras (um punho, uma lâmina, sangue, o chão vindo ao rosto)
  - a lembrança tem intensity "large" ou "giant" e o que ela narra é algo que
    quem pergunta FEZ CONTRA o informante
Se você reconhecer o episódio a ponto de mencioná-lo na "atitude", então ele
CONTA: escrever "a lembrança do golpe ainda pesa" e mesmo assim dar nota alta é
contradição, e é erro. A atitude descreve a nota; não a substitui.

PASSO 1b — o mundo já mediu o afeto do informante por quem pergunta e te entrega
em "saldo_afeto" (ex.: "guarda mágoa", "nutre simpatia", "sem história que pese").
NÃO o recalcule de cabeça — some a ele o que a personalidade e a cena dele indicam.
Um saldo negativo puxa a nota para baixo; um positivo, para cima. Ele COLORE; o
gatilho do passo 1 (agressão viva → 0) manda mais que ele.

PASSO 2 — se o passo 1 não deu 0, dimensione pela régua abaixo, lendo o saldo, o
INFORMANTE (quem ele é pela própria descrição e o que está fazendo agora); nunca o
interesse de quem pergunta, nunca o fato de o jogador ter pedido:
  0  não diz uma palavra — há violência, traição ou humilhação de quem pergunta na
     lembrança dele (não informa, sem teste)
  1  hostil — guarda mágoa concreta e atual de quem pergunta
  2  desconfia fundo — algo naquela pessoa o alarma, ou já foi enganado por ela
  3  arisco — índole fechada, não fala de bom grado com ninguém
  4  ocupado demais — o que faz agora importa mais do que atender
  5  reticente — responderia, mas alguma coisa o faz hesitar
  6  cordato — não custa nada, e ele não vê motivo para negar
  7  prestativo — o desconhecido comum, que aponta o caminho na rua
  8  solícito — gosta de ser útil, ou de mostrar que conhece a região
  9  caloroso — há simpatia, gratidão ou interesse próprio em ajudar
  10 já ia dizendo — conta antes mesmo de ser bem perguntado (informa, sem teste)
ONDE SE VAI É INFORMAÇÃO TRIVIAL: o normal é ATENDER, e 7 é o desconhecido qualquer.
Notas de 1 a 4 exigem CAUSA — na descrição dele ou na lembrança que ele tem de quem
pergunta. Não baixe a nota por o pedido ser um pedido, nem por não haver intimidade:
ausência de história é o caso comum, e o caso fácil.
Mas o inverso também vale, e é o erro mais fácil de cometer: a trivialidade do
pedido NÃO anula o passo 1. "É só uma direção de rua" não faz ninguém esquecer
um soco.
A nota é segredo do mundo: NUNCA mencione o número na narrativa. Entre 1 e 9 há um
teste resolvido na aplicação — não narre o desfecho como certo."""

REGUA_CONFIDENCIA = """\
Régua da CONFIDÊNCIA (o quanto o narrador se abre para contar o que sabe de outro;
dimensione lendo-O — quem ele é pela descrição, o que guarda de QUEM PERGUNTA (em
"saldo_afeto"), e o que ganha em falar; nunca o interesse de quem pergunta):
  0  não conta nada — mágoa, medo ou traição de quem pergunta o cala (sem teste)
  1  guarda a sete chaves — desconfia fundo de quem pergunta
  2  reservado — não fala da vida alheia com estranhos
  3  cauteloso — o desconhecido comum, que não abre o que sabe de graça
  4  mede — contaria por algum motivo (interesse, simpatia mínima)
  5  disposto se houver troca — fofoca é moeda; o que ganho em contar?
  6  solto — gosta de uma boa história e de contá-la
  7  faladeiro — espalha o que sabe sem muito pudor
  8  cúmplice — confia em quem pergunta, abre-se
  9  quer contar — a história já lhe pesava na língua
  10 já ia dizendo — conta antes de ser bem perguntado (sem teste)
O QUE SE SABE DE ALGUÉM É MOEDA E ESCUDO: o padrão é GUARDAR — 3 é o desconhecido
comum, o OPOSTO de indicar uma rua (que é trivial e se dá de graça). A nota SOBE com
afinidade (saldo_afeto positivo), interesse próprio ou motivo de espalhar; DESCE com
desconfiança e mágoa. Saldo fortemente negativo de quem pergunta fecha a boca. A nota
é segredo do mundo: NUNCA a mencione. Entre 1 e 9 há um teste resolvido na aplicação —
não narre como certo."""

_STR = {"type": "string"}
_NOTA = {"type": "integer", "minimum": 0, "maximum": 10}


@inworld("learn_ops_applied")
def _iw_learn(op):
    nome = op.get("nome") or name_of(op.get("rota"))
    fonte = op.get("fonte")
    if op.get("renovou"):
        return f"reconheceu de novo o caminho {nome}"
    if fonte:
        # "decifrou" é a fala de quem leu rabiscos, e soa errado quando alguém lhe
        # explicou de viva voz (spec 015).
        return f"aprendeu com {name_of(fonte)} o caminho {nome}"
    return f"decifrou o caminho {nome}"


REGUA_RECONTO = (
    "Voce e um personagem a quem alguem acabou de perguntar sobre um ASSUNTO. "
    "Recebe as suas LEMBRANCAS e responde na PRIMEIRA PESSOA, como GENTE responde, "
    "nao como um relatorio. "
    "CONTE COMO SE CONTA: com as suas palavras, do jeito que ficou na sua cabeca. "
    "Voce pode se confundir na ordem, juntar duas coisas numa, dar mais peso ao que "
    "te marcou e passar rapido pelo resto. Isso e lembrar, nao e erro. "
    "O UNICO LIMITE: nao traga PESSOA, LUGAR ou OBJETO que nao apareca nas suas "
    "lembrancas. Sem numeros e sem datas. "
    "Curto: o que voce diria de pe, numa conversa. "
    'Responda SOMENTE JSON: {"conta": "<o que voce diz>"}'
)


def _conta_o_que_lembra(ctx, quem: str, sobre: str, fontes: list) -> str:
    """O Z — o que o informante DIZ, em uma peça só (item 52).

    Não-determinístico de propósito, e essa é a decisão de desenho mais importante
    aqui. Medi o caminho determinístico e ele funciona: junta as frases, cobertura
    100%, zero invenção, 0,00s. Foi recusado, com razão — *"nem sempre quando você
    pede informação a alguém, ele conta exatamente o que aconteceu"*. Trocar a ordem,
    dizer que o outro "veio pedir ajuda" quando na verdade foi socorrido, achar que
    "sempre" acontece o que aconteceu duas vezes: isso não é defeito do relato, é o
    relato. Num jogo cujo eixo é a memória, um informante que recita arquivo não é um
    informante.

    Medido (llama3.1:8b local, 6 pares reais): 4,9 a 12,5s, 228 a 393 caracteres,
    0% de cópia literal — e cada informante saiu com voz própria: a Mira indignada se
    defendendo, a Odila seca ("mulher perigosa"), o Coppo se enrolando e desistindo no
    meio. Uma tentativa anterior, endurecida contra invenção, fez a LLM parar de contar
    e passar a TRANSCREVER (93-100% literal, até 28s) — fidelidade perfeita e valor
    zero. O prompt aqui é o que devolveu a voz.

    Devolve "" quando o mundo não conseguiu formar o relato (juízo indisponível): o
    chamador recusa em linguagem de mundo em vez de inventar um Z.
    """
    if not fontes:
        return ""
    corpo = "\n".join("- " + t for t in fontes)
    raw = ctx.ask(REGUA_RECONTO,
                  "LEMBRANCAS de " + motor.name_of(quem) + ":\n" + corpo
                  + "\n\nASSUNTO: " + motor.name_of(sobre))
    try:
        z = (json.loads(raw or "{}").get("conta") or "").strip()
    except Exception:
        m = re.search(r'"conta"\s*:\s*"(.*?)"\s*}', raw or "", re.S)
        z = (m.group(1) if m else "").strip()
    if z.upper() == "NADA":
        return ""
    return " ".join(z.split())


def _assunto_legivel(sobre) -> str:
    """O ASSUNTO como gente lê — item 52.2, decisão do mantenedor: "o mais legível
    possível, e não um texto genérico, pra ambos poderem consultar de forma eficiente".

    Duas naturezas chegam neste parâmetro, e as duas têm de sair legíveis:
      - um ID de entidade (`verro-o-calado`) -> vira o NOME ("Verro, o Calado"), pela
        mesma razão de `name_of`: ninguém lembra de um id;
      - uma PERGUNTA em texto livre ("nome do deus do santuário") -> sai entre aspas,
        porque é a fala dele, não uma coisa do mundo. Sem as aspas a memória lia
        "perguntou sobre nome do deus do santuário", que confunde assunto com coisa.

    O que NÃO se faz aqui é resumir: o texto que a Mente escreveu é o que ela vai
    procurar depois (`recall` casa por palavra), e resumir é decidir por quem lê.
    """
    s = (str(sobre or "")).strip()
    if not s:
        return "algo que nem ele soube dizer o que era"
    if motor.find_entity(s) is not None:
        return name_of(s)
    return f'"{s}"'


@inworld("hearsay_ops_applied")
def _iw_hearsay(op):
    # o que o ouvinte tira da conversa: uma fofoca. A Mente narra a fala.
    return (f"ouviu de {name_of(op.get('fonte'))} sobre "
            f"{name_of(op.get('sobre'))}")


@inworld("unanswered_ops_applied")
def _iw_unanswered(op):
    """A pergunta que não rendeu — item 52.2.

    É FATO, não recusa: alguém perguntou, o outro não soube. Por isso vira frase
    in-world e memória nos DOIS lados, em vez de morrer como erro do turno. Sem
    isto a Nerissa repetiu a MESMA pergunta 23 vezes, porque nada guardava que ela
    já havia perguntado."""
    return (f"perguntou a {name_of(op.get('informante'))} sobre "
            f"{_assunto_legivel(op.get('sobre'))} — e ele não soube dizer")


def _recognize(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    if alvo not in ctx.cand["examinar"]:
        return ctx.err(f"'{alvo}' não é algo que ele perceba agora", "alvo",
                       [{"id": a, "nome": a} for a in ctx.cand["examinar"]]), False
    try:
        pacote = motor.recognition_of(ctx.actor, alvo)
    except motor.MotorError:
        return ctx.err(f"'{alvo}' não está ao alcance do olhar"), False
    # a FRONTEIRA (loreforge-arbiter-boundary): o pacote desce para A MENTE tecer;
    # NÃO volta ao raciocínio do Árbitro — ao modelo, só um aviso factual.
    ctx.queue["reconhecimentos"].append(pacote)
    return {"ok": True, "observou": alvo,
            "nota": ("a impressão desce para a narração do personagem — "
                     "não a descreva")}, False


def _examine(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    if alvo not in ctx.cand["examinar"]:
        return ctx.err(f"'{alvo}' não é algo que ele perceba agora", "alvo",
                       [{"id": a, "nome": a} for a in ctx.cand["examinar"]]), False
    texto = motor.prose_of(ctx.actor, alvo)
    if not texto:
        return ctx.err(motor._WHY_BY_REGRA["nada_a_examinar"]), False
    # o texto lido FICA no turno: é contra ele que a citação de learn_routes confere.
    if texto not in ctx.queue["lido"]:
        ctx.queue["lido"].append(texto)
    return {"ok": True, "texto": texto}, False


def _ask_directions(name: str, args: dict, ctx) -> tuple[dict, bool]:
    quem = args.get("quem")
    disposicao = None   # spec 043: pedida ao mundo abaixo, depois de validar `quem`
    if quem not in ctx.cand["perguntar_a"]:
        return ctx.err(f"'{quem}' não é alguém a quem ele possa perguntar agora",
                       "quem", [{"id": c, "nome": ctx.chars.get(c, c)}
                                for c in ctx.cand["perguntar_a"]]), False
    if quem in ctx.perguntados:
        return ctx.err("isso já foi perguntado a ele neste turno — o mundo já "
                       "decidiu; NÃO repita: siga para outra ação ou narrate"), False
    ctx.perguntados.add(quem)
    try:
        resposta = motor.directions_from(quem)
    except motor.MotorError:
        return ctx.err(f"'{quem}' não está ao alcance"), False
    # ELE SE DÁ CONTA DE QUE JÁ SABE (item 53.5) — e por isso nem pergunta.
    #
    # Não é o mundo barrando: é o personagem lembrando. Se TODO caminho que este
    # informante poderia ensinar já está vivo na memória de quem ia perguntar, a
    # pergunta não tem o que render, e alguém que sabe o caminho não pede
    # informação sobre ele.
    #
    # GRATUITA, de propósito, e é o que a torna diferente de toda outra recusa
    # daqui: não gasta fadiga (ninguém se cansa de NÃO perguntar) e não chega a
    # pedir juízo ao Árbitro — a decisão é anterior à conversa. De quebra, poupa
    # a chamada de modelo mais cara do turno.
    #
    # O CASO: o Irmão Tobias passou três horas pedindo à Nerissa o caminho do Beco
    # das Sombras. A memória dele dizia, com todas as letras, "Sei o caminho: Beco
    # das Sombras. Já o percorri, e os pés lembram por onde vai" — e o beco estava
    # aberto na cena. Ele nunca tentou entrar. Trinta e cinco lembranças de fracasso
    # gritando mais alto que uma de sucesso.
    if resposta["caminhos"] and all(motor.knows_route(ctx.actor, c["rota"])
                                    for c in resposta["caminhos"]):
        return ctx.err("ele se dá conta de que já sabe todos os caminhos que esse "
                       "aí teria a ensinar — e não chega a perguntar"), False

    lembra = motor.remembered_about(quem, ctx.actor)
    saldo = motor.sentiment_label(motor.sentiment_toward(quem, ctx.actor))
    # spec 043 — CONTRATO DE ANÁLISE: o PASSO 1 desta régua é `lembra_de_voce` (uma
    # lembrança de violência às mãos de quem pergunta zera a nota, sem ponderar), e é
    # por isso que ele vai no payload antes de qualquer outra coisa.
    disposicao = juizo.nota(
        ctx.ask(REGUA_DISPOSICAO + juizo.NOTA_0_10,
                json.dumps({"lembra_de_voce": lembra,
                            "saldo_afeto": saldo,
                            "informante": ctx.describe(quem),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=7)   # o desconhecido comum, que aponta o caminho na rua
    caminhos = resposta["caminhos"]
    ctx.queue["informes"].append({
        "informante": quem, "nome": resposta["nome"],
        "caminhos": [{"rota": c["rota"], "nome": c["nome"]} for c in caminhos]})
    if not caminhos:
        return {"ok": True, "quem": quem, "nome": resposta["nome"], "caminhos": [],
                "nada_a_ensinar": True, "lembra_de_voce": lembra,
                "saldo_afeto": saldo}, False
    for c in caminhos:
        if c["prosa"] not in ctx.queue["lido"]:
            ctx.queue["lido"].append(c["prosa"])
    pares = [{"rota": c["rota"], "trecho": c["prosa"]} for c in caminhos]
    op = {"rotas": [p["rota"] for p in pares], "citacoes": pares,
          "fonte": quem, "disposicao": disposicao, "atitude": ""}
    rej = ctx.apply_op_now("learn_ops", op)
    if rej:
        erro = ctx.err(rej.get("why") or f"'{quem}' não quis ensinar", rej=rej)
        erro.update({"lembra_de_voce": lembra, "saldo_afeto": saldo})
        return erro, False
    return {"ok": True, "quem": quem, "nome": resposta["nome"], "caminhos": caminhos,
            "lembra_de_voce": lembra, "saldo_afeto": saldo}, False


def _ask_about(name: str, args: dict, ctx) -> tuple[dict, bool]:
    quem = args.get("quem")
    sobre = (args.get("sobre") or "").strip()
    disposicao = None   # spec 043: pedida ao mundo abaixo, depois de validar `quem`
    if quem not in ctx.cand["perguntar_a"]:
        return ctx.err(f"'{quem}' não é alguém a quem ele possa perguntar agora",
                       "quem", [{"id": c, "nome": ctx.chars.get(c, c)}
                                for c in ctx.cand["perguntar_a"]]), False
    if not sobre:
        return ctx.err("informe SOBRE quem ou que lugar se pergunta", "sobre"), False
    achado = motor.find_entity(sobre)
    if achado and achado[1].get("type") == "location" \
            and sobre not in ctx.cand["perguntar_sobre_lugar"]:
        return ctx.err(f"'{sobre}' não é um lugar que ele conheça ou onde esteja agora",
                       "sobre", [{"id": l, "nome": l}
                                 for l in ctx.cand["perguntar_sobre_lugar"]]), False
    chave = (quem, sobre)
    if chave in ctx.perguntados_sobre:
        return ctx.err("isso já foi perguntado a ele neste turno — o mundo já "
                       "decidiu; NÃO repita: siga para outra ação ou narrate"), False
    ctx.perguntados_sobre.add(chave)
    episodios = motor.remembered_about(quem, sobre)
    saldo = motor.sentiment_label(motor.sentiment_toward(quem, ctx.actor))
    # spec 043 — CONTRATO DE ANÁLISE: a régua da confidência lê QUEM CONTA (índole,
    # o que ganha em falar) e o que ele guarda de quem pergunta.
    disposicao = juizo.nota(
        ctx.ask(REGUA_CONFIDENCIA + juizo.NOTA_0_10,
                json.dumps({"narrador": ctx.describe(quem),
                            "sobre": ctx.describe(sobre) or sobre,
                            "saldo_afeto": saldo,
                            "lembra_de_voce": motor.remembered_about(quem, ctx.actor),
                            "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=3)   # o desconhecido comum: o padrão é GUARDAR
    ctx.queue["informes"].append({"informante": quem, "nome": ctx.chars.get(quem, quem),
                                  "sobre": sobre, "episodios": len(episodios)})
    if not episodios:
        # ITEM 52.5 — DUAS AUSÊNCIAS QUE PARECIAM UMA. Medido na Nerissa: de 152
        # `ask_about`, só 4 tinham `sobre` apontando para entidade REAL. As outras 148
        # perguntavam por "nome-do-deus", "raiz-de-ferro", "devoção" — porque `sobre`
        # é texto livre e A Mente escreve a PERGUNTA ali, que é o que uma mente faria.
        # Todas voltavam `ok: True` e silêncio, sem memória e sem rastro, e o tick
        # seguinte repetia: 23 vezes a mesma.
        #
        # Mas as duas ausências NÃO são a mesma coisa, e a primeira versão desta
        # correção tratou como se fossem — a Fase 35 reprovou e estava certa:
        #
        #   `sobre` É uma entidade real, e o informante não a conhece
        #       -> resposta HONESTA ("não sei desse lugar"). Sucesso, é a US2 da
        #          spec 034, e some daqui.
        #   `sobre` não é entidade nenhuma
        #       -> a pergunta não tem o que responder. RECUSA com motivo, senão o
        #          vazio se repete para sempre.
        # ITEM 52.2 (decisão do mantenedor, 2026-08-13): a pergunta que não rendeu
        # deixa memória NOS DOIS, `small`, com texto legível. Vai pelo canal
        # `unanswered_ops` — e por isso deixou de ser RECUSA: gravar é escrever no
        # mundo, e escrita só acontece por op. Como FATO ela também ganha frase
        # in-world, então A Mente recebe "perguntou e ele não soube" em vez de um
        # erro seco — e, no tick seguinte, o personagem LEMBRA que já perguntou.
        rej_u = ctx.apply_op_now("unanswered_ops",
                                 {"informante": quem, "sobre": sobre})
        if rej_u:
            return ctx.err(rej_u.get("why") or motor._WHY_BY_REGRA["nada_a_contar"],
                           rej=rej_u), False
        return {"ok": True, "quem": quem, "sobre": sobre, "episodios": [],
                "nada_a_contar": True,
                "lembra_de_voce": motor.remembered_about(quem, ctx.actor),
                "saldo_afeto": saldo}, False
    # SANITIZAÇÃO antes de qualquer coisa (item 52): só as VIVAS — `remembered_about`
    # já garante —, só o TEXTO (nada de id, intensidade, valência ou `ouvido_de`: são
    # medidas de sistema, Princípios V/IX, e a proveniência é segredo) e SEM REPETIÇÃO,
    # que no corpus real corta pela metade (40 lembranças da Mira sobre a Hulda viram
    # 15 frases distintas) e evita que a repetição literal enviese o relato.
    vistos, fontes_txt, fontes_fm = set(), [], []
    for e in episodios:
        t = " ".join((e.get("content") or "").split())
        if not t or t in vistos:
            continue
        vistos.add(t)
        fontes_txt.append(t)
        fontes_fm.append(e)
        if t not in ctx.queue["lido"]:
            ctx.queue["lido"].append(t)
    # NOTA 0 NÃO GASTA O RELATO. A régua diz que 0 é "não diz uma palavra, sem teste":
    # pedir o Z antes de saber isso queimaria uma chamada de modelo (5 a 12s, medido)
    # para um relato que ninguém vai ouvir. A ordem aqui é economia, não regra nova.
    z = "" if disposicao <= 0 else _conta_o_que_lembra(ctx, quem, sobre, fontes_txt)
    if not z:
        # sem relato não há reconto. Duas causas caem aqui: ele não abriu a boca
        # (nota 0), ou o mundo não conseguiu formar o Z (juízo indisponível — e nesse
        # caso o `juizo_indisponivel` do item 52.1 já sobe alto por outro canal).
        # Não se inventa um Z nem se cai num literal de emergência: é UM caminho só.
        #
        # E a recusa LEVA O CONTEXTO (spec 043): `lembra_de_voce` e `saldo_afeto` são o
        # material com que A Mente narra o PORQUÊ do silêncio. Sem isso o jogador lê
        # uma recusa sem causa — o defeito que a 017 consertou e que uma recusa nova,
        # escrita sem olhar as irmãs, reabre.
        erro = ctx.err(f"'{motor.name_of(quem)}' não abriu o que sabe sobre isso")
        erro.update({"lembra_de_voce": motor.remembered_about(quem, ctx.actor),
                     "saldo_afeto": saldo})
        return erro, False
    # UMA op, com o Z e as FONTES. As fontes viajam porque é delas que a primitiva tira
    # `involved`, valência, intensidade e grau — nunca do texto do Z.
    ops = [{"fonte": quem, "sobre": sobre, "trecho": z,
            "fontes_reconto": fontes_fm,
            "disposicao": disposicao, "atitude": ""}]
    start = len(ctx.queue["hearsay_ops"])
    ctx.queue["hearsay_ops"].extend(ops)
    out = motor.apply_resolution(ctx.actor, ctx.sub("hearsay_ops", ops),
                                 ensure_action=False)
    aplicados = out.get("hearsay_ops_applied") or []
    rejeitados = out.get("rejected") or []
    if not aplicados:
        del ctx.queue["hearsay_ops"][start:]
        rej0 = rejeitados[0] if rejeitados else None
        erro = ctx.err((rej0 or {}).get("why") or f"'{quem}' não quis se abrir sobre isso",
                       rej=rej0)
        erro.update({"lembra_de_voce": motor.remembered_about(quem, ctx.actor),
                     "saldo_afeto": saldo})
        return erro, False
    ctx.seen_len["hearsay_ops"] = len(ctx.queue["hearsay_ops"])
    ctx.merge(out)
    return {"ok": True, "quem": quem, "sobre": sobre, "episodios": episodios,
            "registrado": len(aplicados),
            "lembra_de_voce": motor.remembered_about(quem, ctx.actor),
            "saldo_afeto": saldo}, False


def _learn_routes(name: str, args: dict, ctx) -> tuple[dict, bool]:
    brutas = args.get("rotas")
    if isinstance(brutas, (str, dict)):
        brutas = [brutas]
    if not isinstance(brutas, list) or not brutas:
        return ctx.err("informe ao menos um caminho que o conteúdo descreve", "rotas"), False
    pares, sem_trecho = [], []
    for it in brutas:
        if isinstance(it, dict):
            rid = it.get("rota") or it.get("id")
            trecho = (it.get("trecho") or "").strip()
        else:
            rid, trecho = it, ""
        if not trecho:
            sem_trecho.append(rid)
        pares.append({"rota": rid, "trecho": trecho})
    if sem_trecho:
        return ctx.err("informe o 'trecho' do conteúdo que descreve cada caminho: "
                       f"{', '.join(map(str, sem_trecho))}", "rotas"), False
    rotas = [p["rota"] for p in pares]
    invalidas = [r for r in rotas if r not in ctx.cand["rotas_do_mundo"]]
    if invalidas:
        return ctx.err(f"não existe caminho assim: {', '.join(map(str, invalidas))}",
                       "rotas", [{"id": r, "nome": r} for r in ctx.cand["rotas_do_mundo"]]), False
    chave = (None, tuple(sorted(rotas)))
    if chave in ctx.lido:
        return ctx.err("esses caminhos já foram estudados neste turno — o mundo "
                       "resolve o que ele absorveu; NÃO repita: siga para outra ação "
                       "ou narrate"), False
    ctx.lido.add(chave)
    ctx.queue["learn_ops"].append({"rotas": rotas, "citacoes": pares})
    return {"ok": True, "aplicado": {"rotas": rotas,
                                     "nota": "o mundo decide o que ele absorveu"}}, False


def _rotas_schema(s):
    return {"type": "array", "items": {
        "type": "object",
        "properties": {
            "rota": {"type": "string", "enum": s.cand["rotas_do_mundo"]},
            "trecho": {"type": "string"},
        },
        "required": ["rota", "trecho"],
    }}


RECOGNIZE = tool_spec(ToolSpec(
    names=("recognize",),
    description=("Faz o personagem OLHAR com atenção para algo "
                 "percebido e deixar a VIVÊNCIA dele aflorar — quem é "
                 "aquela pessoa para ele, que história tem com aquela "
                 "coisa ou lugar. Use quando o sussurro pede observar, "
                 "analisar ou reparar em alguém/algo. Não muda nada e "
                 "não gasta o turno. IMPORTANTE: você apenas BUSCA a "
                 "impressão — NÃO a descreva você mesmo, e NÃO a ponha "
                 "no seu resumo; quem a narra é o próprio personagem. "
                 "Chame e siga."),
    params={"alvo": _STR},
    required=("alvo",),
    enum_sources={"alvo": "examinar"},
    apply=_recognize,
))


EXAMINE = tool_spec(ToolSpec(
    names=("examine",),
    description=("Debruça-se sobre algo percebido e LÊ o que ele diz de "
                 "si — a inscrição de uma lâmina, os rabiscos de um "
                 "mapa, o que uma carta conta. Devolve o texto para "
                 "você interpretar. Não muda nada no mundo e não gasta "
                 "o turno: use antes de decidir o que fazer com o que "
                 "está escrito."),
    params={"alvo": _STR},
    required=("alvo",),
    enum_sources={"alvo": "examinar"},
    apply=_examine,
))


ASK_DIRECTIONS = tool_spec(ToolSpec(
    names=("ask_directions",),
    juizo=("disposicao", REGUA_DISPOSICAO),
    description=("Pergunta a OUTRO personagem presente por onde se vai — como "
                 "se chega a algum lugar, que caminhos existem, o que ele "
                 "conhece da região. Se ele responde depende dele: de quem é, "
                 "do que está fazendo, e sobretudo do que guarda de quem "
                 "pergunta — quem apanhou não indica caminho. Se ele topar, "
                 "cada caminho que souber e ainda lembrar já fica aprendido "
                 "NESTA MESMA chamada; não é preciso mais nada depois."),
    params={"quem": _STR, "disposicao": _NOTA},
    required=("quem", "disposicao"),
    enum_sources={"quem": "perguntar_a"},
    apply=_ask_directions,
))


ASK_ABOUT = tool_spec(ToolSpec(
    names=("ask_about",),
    juizo=("disposicao", REGUA_CONFIDENCIA),
    description=("Pergunta a OUTRO presente o que ele sabe ou lembra de ALGUÉM "
                 "(presente ou ausente) OU de um LUGAR (a cena atual, ou um "
                 "lugar que o próprio personagem já conhece — nunca invente um "
                 "lugar). O que se sabe de alguém é moeda e escudo: o normal é "
                 "guardar, e quem se abre o faz por afinidade, interesse ou "
                 "gosto de falar. Se ele contar, o que for dito já fica como "
                 "lembrança sua NESTA MESMA chamada."),
    params={"quem": _STR, "sobre": _STR, "disposicao": _NOTA},
    required=("quem", "sobre", "disposicao"),
    enum_sources={"quem": "perguntar_a"},
    apply=_ask_about,
))


LEARN_ROUTES = tool_spec(ToolSpec(
    names=("learn_routes",),
    description=("Registra os caminhos que o personagem acabou de "
                 "APRENDER de um MATERIAL — mapa, carta, inscrição na "
                 "parede, ou qualquer coisa que ele analise/estude/"
                 "leia/examine e que descreva caminhos (nunca uma "
                 "PESSOA explicando de viva voz — isso é "
                 "ask_directions, que já resolve tudo sozinho). "
                 "Informe de uma vez TODOS os caminhos que o "
                 "conteúdo descreve. Para CADA caminho informe também "
                 "o 'trecho': as palavras EXATAS do conteúdo, COPIADAS "
                 "LETRA POR LETRA como aparecem ali. Pode sobrar ou "
                 "faltar uma palavra nas pontas, e nada mais. NÃO "
                 "resuma, NÃO reescreva, NÃO explique, e NUNCA escreva "
                 "coisas como 'o texto menciona' ou 'a carta fala de' — "
                 "isso é paráfrase, não citação. O trecho tem de poder "
                 "ser encontrado no conteúdo por busca literal. Se você "
                 "não consegue COPIAR um trecho que descreva aquele "
                 "caminho, então o conteúdo não o descreve: não o "
                 "informe, nem que ele lhe venha à cabeça por outro "
                 "motivo. O que o personagem LEMBRA não é o que o texto "
                 "DIZ. Quem decide se ele conseguiu absorver cada "
                 "caminho é o mundo."),
    params={"rotas": _rotas_schema},
    required=("rotas",),
    enum_sources={"rotas": "rotas_do_mundo"},
    apply=_learn_routes,
))
