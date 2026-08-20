"""DECLARAÇÃO + CORPO da tool de COZINHAR (spec 048).

`cook` combina N ingredientes sobre uma fonte de calor, julgados numa ÚNICA
chamada ao Árbitro (`REGUA_COZINHAR`, molde de `REGUA_COMER`/`REGUA_BEBER_ITEM`)
— com uma divergência de formato deliberada: como a BANDA do resultado só
existe DEPOIS da rolagem (que acontece no Motor, depois que o Árbitro já
respondeu), a mesma chamada pede TRÊS descriptions candidatas (uma por banda)
em vez de uma só — o Motor escolhe qual usar só depois de rolar (R1 do plano).
O corpo ENFILEIRA via `ctx.apply_arbitrated` (mesmo padrão de `eat`/`drink`,
para poder decidir a resposta na hora sobre os dois GATES de admissão), sem
importar o Árbitro.
"""
from __future__ import annotations

import json
from .. import juizo

from ..registro import ToolSpec, inworld, tool_spec


# --- As quatro réguas de `cook` (spec 048) ----------------------------------- #
# Duas de ADMISSÃO (gates — nota 0 recusa sem julgar o resto) e duas que só
# importam quando as de admissão são > 0: FAVORABILIDADE (rolada, decide a
# banda) e DURAÇÃO (classificação pura, convertida em tempo real pelo Motor).

REGUA_FONTE_DE_CALOR = """\
Régua da FONTE DE CALOR (o quanto, PELA DESCRIÇÃO, ela fornece calor
utilizável AGORA para cozinhar — não se É uma fonte de calor em tese):
  0  nenhum calor algum — apagada, cinzas frias, decorativa, nunca esteve
     acesa, ou apagada há tempo suficiente para não sobrar brasa nenhuma
     (sem teste)
  1  quase nada — só um vestígio morno, insuficiente pra qualquer preparo
  2  calor muito fraco — mal chega a aquecer, não cozinha nada de verdade
  3  fraco — esquentaria por muito tempo, mal dá pra algo simples
  4  abaixo do ideal — funciona, mas de forma capenga
  5  calor comum — dá conta de um preparo simples, sem chama viva declarada
  6  bom calor — chama ou brasa visível, preparo comum sem problema
  7  calor forte — fogo aceso, pronto para qualquer preparo comum
  8  calor muito forte — brasas vivas ou chama alta, declaradamente pronta
  9  calor excelente — fogo forte e estável, ideal pra qualquer prato
  10 calor perfeito — fornalha, fogo bravo, mais que suficiente (sem teste)
Uma fonte CLARAMENTE apagada (cinzas frias, poeira, sem brasa nenhuma) é 0,
não 1 — não hesite no extremo quando a descrição já diz que não há calor
nenhum ali. A nota é segredo do mundo: nunca o número na narrativa; nota 0
faz a tentativa ser recusada, mesmo que as outras notas venham preenchidas."""

REGUA_COZINHABILIDADE = """\
Régua da COZINHABILIDADE (o quanto os ingredientes escolhidos, PELA
DESCRIÇÃO COMBINADA de todos eles, formam algo que faz sentido cozinhar
juntos — não o quanto ficaria gostoso):
  0  não faz sentido nenhum — um ou mais itens claramente NÃO são
     ingrediente (ferramenta, material bruto, objeto), ou juntos não formam
     nada (sem teste)
  1  quase certamente não — nada ali sugere prato algum
  2  muito improvável — combinação sem nexo culinário nenhum
  3  duvidoso — algum ingrediente real, mas a combinação não convence
  4  incerto — serviria em desespero, sem nenhuma lógica de prato
  5  ambíguo — a descrição não decide se aquilo forma um prato
  6  provável — os itens são ingredientes plausíveis, combinação razoável
  7  bastante provável — ingredientes reais que combinam bem entre si
  8  combinação boa — ingredientes claramente complementares
  9  combinação muito boa — quase uma receita óbvia
  10 combinação perfeita e evidente — não há dúvida nenhuma (sem teste)
Um item que NÃO é ingrediente (ferramenta, pedra, metal) MISTURADO com
ingredientes reais deve DERRUBAR a nota — ele não desaparece da leitura por
estar acompanhado de itens de verdade. A nota é segredo do mundo: nunca o
número na narrativa; nota 0 faz a tentativa ser recusada, mesmo que as
outras notas venham preenchidas."""

REGUA_FAVORABILIDADE = """\
Régua da FAVORABILIDADE (o quanto o calor disponível e a qualidade/frescor
dos ingredientes favorecem um BOM resultado — leia a cena, nunca a vontade
de quem cozinha; só importa quando fonte de calor e cozinhabilidade já são
maiores que 0):
  0  tudo contra — calor mal dá conta, ingredientes murchos, estragados ou
     minguados (sem teste)
  1  quase inviável — quase nada ajuda
  2  muito contra — calor fraco E ingredientes ruins
  3  desfavorável — falta calor OU frescor pra um resultado decente
  4  levemente contra — dá pra tentar, mas nada colabora
  5  comum — nem ajuda nem atrapalha; o resultado sai mediano
  6  levemente a favor — calor e ingredientes um pouco acima do comum
  7  favorável — bom calor, ingredientes frescos, deve sair bem
  8  muito favorável — calor forte, ingredientes fartos e frescos
  9  quase ideal — quase tudo a favor
  10 perfeito — calor ideal e ingredientes no ponto, resultado exemplar
     (sem teste)
A nota é segredo do mundo: nunca o número na narrativa. Entre 1 e 9 há um
teste resolvido na aplicação — não narre o resultado como certo."""

REGUA_DURACAO = """\
Régua da DURAÇÃO (o quanto este preparo, PELA sua complexidade, EXIGE de
tempo e cuidado — não a pressa de quem cozinha):
  0  quase instantâneo — grelhar algo simples, sem preparo nenhum
  1  muito rápido — quase nada de preparo
  2  rápido — poucos passos
  3  rápido — um preparo direto
  4  comum-rápido — preparo simples com mais de um ingrediente
  5  comum — um prato com preparo normal, mistura e cozimento
  6  comum-demorado — alguns passos a mais
  7  demorado — vários ingredientes, precisa de atenção e tempo
  8  bem demorado — preparo elaborado, várias etapas
  9  muito trabalhoso — quase um banquete
  10 elaboradíssimo — um preparo com muitas etapas, o máximo de cuidado
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a
nota num tempo real de preparo — não é julgamento de sorte, é classificação."""

# spec 048 — UMA chamada combinada (mesmo custo/latência que `eat`/`drink` já
# fixaram): as quatro notas + nome + TRÊS descriptions candidatas (uma por
# banda — ruim/média/ótima) saem da MESMA resposta. As três descriptions
# existem porque a banda só é decidida DEPOIS da rolagem, que acontece no
# Motor — o Árbitro não pode saber, nesta chamada, qual delas vai valer.
REGUA_COZINHAR = f"""\
Você vai julgar UMA tentativa de cozinhar, combinando ingredientes sobre uma
fonte de calor. Leia as descrições REAIS fornecidas com cuidado antes de
responder — nunca invente detalhes que não estejam nelas.

{REGUA_FONTE_DE_CALOR}

{REGUA_COZINHABILIDADE}

{REGUA_FAVORABILIDADE}

{REGUA_DURACAO}

A rolagem que decide qual das TRÊS bandas (ruim/média/ótima) vale só
acontece DEPOIS desta resposta, no Motor — você não sabe qual banda vai
sair. Por isso, escreva um nome curto para o prato e TRÊS descriptions
candidatas do resultado, uma para CADA banda possível, todas plausíveis a
partir dos MESMOS ingredientes reais — nunca descreva sabor, nojo ou
satisfação de quem comeu (isso é interpretação exclusiva de quem narra ao
jogador depois).

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de
explicação, EXATAMENTE com estas oito chaves (todas OBRIGATÓRIAS, mesmo que
fonte_de_calor ou cozinhabilidade sejam 0):

{{"fonte_de_calor": <inteiro 0-10>, "cozinhabilidade": <inteiro 0-10>, "favorabilidade": <inteiro 0-10>, "duracao": <inteiro 0-10>, "nome": "<nome curto do prato>", "descricao_ruim": "<texto factual do prato malfeito/comprometido — ainda É o prato tentado, nunca sumido>", "descricao_media": "<texto factual do prato comum, bem cozido>", "descricao_otima": "<texto factual do prato bem executado>"}}"""

_STR = {"type": "string"}


@inworld("cozinha_ops_applied")
def _iw_cook(op):
    return "começou a cozinhar, atento ao fogo"


def _cook(name: str, args: dict, ctx) -> tuple[dict, bool]:
    ingredientes = args.get("ingredientes")
    fonte_calor = args.get("fonte_calor")
    if not isinstance(ingredientes, list) or not ingredientes:
        return ctx.err("informe ao menos um ingrediente presente/na posse"), False
    ingredientes = list(dict.fromkeys(ingredientes))  # sem duplicata, mantém ordem
    disponiveis = ctx.cand["cook_ingredientes"]
    for iid in ingredientes:
        if iid not in disponiveis:
            return ctx.err(f"'{iid}' não está ao alcance para cozinhar", "ingredientes",
                           ctx.validos({i: ctx.items[i] for i in disponiveis})), False
    fontes = ctx.cand["cook_fonte"]
    if fonte_calor not in fontes:
        # spec 052: `fontes` passou a incluir o LUGAR além dos objects, então montar
        # o mapa por `ctx.objects[o]` levantaria KeyError no id do lugar — a lista de
        # válidos morreria justamente na recusa que existe para orientar quem errou.
        return ctx.err(f"'{fonte_calor}' não é uma fonte de calor presente", "fonte_calor",
                       ctx.validos({o: ctx.objects.get(o)
                                    or {"name": (ctx.context.get("location") or {}).get("name") or o}
                                    for o in fontes})), False
    chave = (tuple(sorted(ingredientes)), fonte_calor)
    if chave in ctx.cooked_asked:
        return ctx.err("cozinhar esses ingredientes nessa fonte já foi tentado neste "
                       "turno — o desfecho sai na aplicação; NÃO repita: siga para "
                       "outra ação ou narrate"), False
    # spec 048 — CONTRATO DE ANÁLISE: a régua combinada lê a fonte de calor E
    # todos os ingredientes juntos, numa chamada só.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_COZINHAR, json.dumps({
            "fonte_calor": ctx.describe(fonte_calor),
            "ingredientes": [ctx.describe(i) for i in ingredientes],
        }, ensure_ascii=False, indent=2)),
        campos={"fonte_de_calor": 5, "cozinhabilidade": 5, "favorabilidade": 5,
                "duracao": 5},
        texto_campos={"nome": "", "descricao_ruim": "", "descricao_media": "",
                      "descricao_otima": ""})
    ctx.cooked_asked.add(chave)
    base = {"ingredientes": ingredientes, "fonte_calor": fonte_calor}
    fonte_de_calor = julgado["fonte_de_calor"]
    if fonte_de_calor == 0:
        rej, rolled = ctx.apply_arbitrated("cozinha_ops", {**base, "fonte_de_calor": 0})
        if rej:
            return ctx.arb_deny(rolled, ("cook", tuple(ingredientes), fonte_calor), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    cozinhabilidade = julgado["cozinhabilidade"]
    if cozinhabilidade == 0:
        rej, rolled = ctx.apply_arbitrated("cozinha_ops", {
            **base, "fonte_de_calor": fonte_de_calor, "cozinhabilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("cook", tuple(ingredientes), fonte_calor), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("cozinha_ops", {
        **base, "fonte_de_calor": fonte_de_calor, "cozinhabilidade": cozinhabilidade,
        "favorabilidade": julgado["favorabilidade"], "duracao": julgado["duracao"],
        "nome": julgado["nome"], "descricao_ruim": julgado["descricao_ruim"],
        "descricao_media": julgado["descricao_media"],
        "descricao_otima": julgado["descricao_otima"]})
    if rej:
        return ctx.arb_deny(rolled, ("cook", tuple(ingredientes), fonte_calor), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


COOK = tool_spec(ToolSpec(
    names=("cook",),
    juizo=(
        ("fonte_de_calor", REGUA_COZINHAR),
        ("cozinhabilidade", REGUA_COZINHAR),
        ("favorabilidade", REGUA_COZINHAR),
        ("duracao", REGUA_COZINHAR),
        ("nome", REGUA_COZINHAR),
        ("descricao_ruim", REGUA_COZINHAR),
        ("descricao_media", REGUA_COZINHAR),
        ("descricao_otima", REGUA_COZINHAR),
    ),
    description=("Cozinha, combinando os ingredientes escolhidos (em qualquer lugar ao "
     "alcance — mão, chão, dentro de um contêiner aberto) sobre uma fonte de calor "
     "presente na cena. O mundo decide, lendo as descrições, se a fonte fornece calor "
     "de verdade, se os ingredientes formam um prato, e o quanto vai ficar bom. "
     "Cozinhar leva tempo de verdade; o prato não fica pronto na hora, e nada mais "
     "pode ser feito enquanto ele está no fogo. Ingredientes que não fazem sentido "
     "juntos, ou uma fonte sem calor de verdade, são recusados."),
    params={"ingredientes": {"type": "array", "items": {"type": "string"}},
            "fonte_calor": _STR,
            "fonte_de_calor": {"type": "integer", "minimum": 0, "maximum": 10},
            "cozinhabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "favorabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "duracao": {"type": "integer", "minimum": 0, "maximum": 10},
            "nome": _STR, "descricao_ruim": _STR, "descricao_media": _STR,
            "descricao_otima": _STR},
    required=("ingredientes", "fonte_calor", "fonte_de_calor", "cozinhabilidade",
             "favorabilidade", "duracao", "nome", "descricao_ruim", "descricao_media",
             "descricao_otima"),
    enum_sources={"ingredientes": "cook_ingredientes", "fonte_calor": "cook_fonte"},
    apply=_cook,
))
