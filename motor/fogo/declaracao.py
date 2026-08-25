"""DECLARAÇÃO + CORPO da tool de ACENDER FOGO (spec 053).

`kindle_fire` transforma materiais alcançáveis numa FONTE DE FOGO — um `object`
comum, cujo significado inteiro vive na prosa que o Árbitro escreve para ele.
Nenhum campo diz "isto é fogo", "isto esquenta 7" ou "serve para forja": `cook` e
`forge_*` leem a MESMA descrição e chegam às próprias conclusões, com as réguas
que já tinham.

TRÊS réguas, não as quatro de `cook`. Cozinhar tem dois universos independentes (a
fonte e os ingredientes) e por isso dois gates; acender tem um só. O MEIO de
ignição — pederneira, isqueiro, atrito — deliberadamente NÃO é gate: fogo por
fricção existe, então a falta de pederneira é *difícil*, não *impossível*, e entra
na favorabilidade. Fazer disso um gate obrigaria o Motor a saber o que é um
isqueiro — catálogo, ou seja, a solução estruturada pela porta dos fundos.

O corpo ENFILEIRA via `ctx.apply_arbitrated` (mesmo padrão de `cook`), sem importar
o Árbitro.
"""
from __future__ import annotations

import json

from .. import juizo
from ..registro import ToolSpec, inworld, tool_spec


REGUA_COMBUSTIBILIDADE = """\
Régua da COMBUSTIBILIDADE (o quanto os materiais escolhidos, PELA DESCRIÇÃO
COMBINADA de todos eles, podem realmente pegar fogo — não o quanto queimariam
bem):
  0  não queima de jeito nenhum — pedra, metal, água, terra, algo
     inequivocamente incombustível (sem teste)
  1  praticamente não queima — encharcado, verde demais, quase só mineral
  2  muito improvável — material vivo e úmido, sem nada seco junto
  3  duvidoso — queimaria com muita insistência e sorte
  4  incerto — há algo combustível ali, mas pouco e ruim
  5  ambíguo — a descrição não decide se aquilo pega ou não
  6  provável — material combustível comum, em estado razoável
  7  bastante provável — seco o bastante, em quantidade que sustenta chama
  8  bom combustível — seco, farto, do tipo que pega sem drama
  9  ótimo combustível — quase ideal: seco, resinoso, bem partido
  10 evidente — é exatamente aquilo de que se faz fogo (sem teste)
DOIS CASOS QUE COSTUMAM SAIR ERRADOS, leia os dois antes de responder:

  (1) LISTA SÓ COM COISA QUE NÃO QUEIMA — pedra, metal, sílex, vidro, água,
      ferramenta: é **0**, sempre, sem hesitar. Uma pederneira ACENDE fogo, mas
      não É combustível: sozinha, é 0. Uma ferramenta de fazer faísca na lista de
      materiais é 0, não 5.
  (2) LISTA MISTA — algo que não queima junto de material seco: DERRUBE a nota.
      Tudo o que está na lista vai para o fogo e se perde nele, então incluir o
      que não deveria queimar é uma tentativa mal feita, não uma tentativa boa
      com um passageiro. Duas pedras e um graveto não é nota 9.

A nota é segredo do mundo: nunca o número na narrativa; nota 0 faz a tentativa
ser recusada, mesmo que as outras notas venham preenchidas."""

REGUA_FAVORABILIDADE = """\
Régua da FAVORABILIDADE (o quanto as circunstâncias favorecem a IGNIÇÃO agora —
leia a cena e o que a pessoa tem em mãos, nunca a vontade dela; só importa quando
a combustibilidade já é maior que 0):
  0  impossível de tentar — não há nem como encostar fogo ali: debaixo d'água,
     em plena tempestade, vendaval que apaga tudo (sem teste)
  1  quase inviável — mãos nuas, material ruim, e o tempo contra
  2  muito contra — nenhuma ferramenta de fogo e material difícil
  3  desfavorável — falta a faísca OU falta material bom
  4  levemente contra — dá para tentar, mas nada colabora
  5  comum — nem ajuda nem atrapalha; é a tentativa de sempre
  6  levemente a favor — algo em mãos ajuda, ou o material está bom
  7  favorável — há com que fazer faísca e o material aceita bem
  8  muito favorável — ferramenta boa e material seco e farto
  9  quase ideal — quase tudo colabora
  10 perfeito — chama já disponível e material impecável (sem teste)
O que está EM MÃOS conta: pederneira, isqueiro, uma tocha acesa, óleo, palha
fina. Mas ATENÇÃO — não ter com que fazer faísca NÃO é nota 0. Fogo por atrito
existe: duas madeiras e paciência acendem. Sem ferramenta nenhuma e com material
bom e seco, a nota é 3 ou 4 — difícil, não impossível. Reserve o 0 para quando o
AMBIENTE torna a tentativa impraticável (chuva forte, vento que apaga, tudo
submerso), nunca para a falta de uma ferramenta. A nota é segredo do mundo: nunca
o número na narrativa. Entre 1 e 9 há um teste resolvido na aplicação — não narre
o resultado como certo."""

REGUA_DURACAO = """\
Régua da DURAÇÃO (o quanto este monte de material, PELA quantidade e pelo tipo,
sustenta chama — não a vontade de que dure):
  0  um sopro — um punhado de palha ou folha seca, some em minutos
  1  muito breve — gravetos finos e pouca coisa
  2  breve — um feixe pequeno de material leve
  3  curto — dá para uma fervura rápida e mais nada
  4  abaixo do comum — material leve, mas em quantidade razoável
  5  comum — uma fogueira de acampamento normal
  6  acima do comum — lenha de verdade, bem arrumada
  7  longo — bastante lenha, do tipo que queima devagar
  8  bem longo — toras, carvão, material denso e farto
  9  muito longo — combustível denso em grande quantidade
  10 quase a noite inteira — o máximo que um monte de material sustenta
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a nota
num tempo real de queima — não é julgamento de sorte, é classificação."""

# spec 053 — UMA chamada combinada (mesmo custo/latência de `cook`): as três notas,
# o nome/descrição da FONTE e o nome/descrição das CINZAS saem da MESMA resposta. As
# cinzas são decididas já aqui para que o vencimento do prazo resolva sem NENHUMA
# segunda chamada ao Árbitro.
REGUA_ACENDER = f"""\
Você vai julgar UMA tentativa de acender fogo com materiais que a pessoa juntou.
Leia as descrições REAIS fornecidas com cuidado antes de responder — nunca invente
detalhes que não estejam nelas.

O QUE ESTÁ EM MÃOS É FERRAMENTA, NÃO COMBUSTÍVEL. O bloco `em_maos` existe só
para você saber COM QUE a pessoa faria faísca — pederneira, isqueiro, uma tocha.
Nada que esteja em `em_maos` deve ser contado como material que queima, e a
presença de uma ferramenta ali NUNCA melhora a combustibilidade da carga: ela só
importa para a FAVORABILIDADE.

{REGUA_COMBUSTIBILIDADE}

{REGUA_FAVORABILIDADE}

{REGUA_DURACAO}

Se a chama pegar, nasce uma fonte de fogo no lugar. Escreva um nome curto e uma
descrição FACTUAL dela — o que qualquer um veria: que tipo de chama, que brasas,
que porte. Escreva TAMBÉM o nome e a descrição do que vai restar quando ela se
apagar (cinzas, tições, carvão frio). Descreva a COISA, nunca a experiência de
quem está perto: nada de conforto, alívio, medo ou aconchego — isso é
interpretação exclusiva de quem narra ao jogador depois.

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas sete chaves (todas OBRIGATÓRIAS, mesmo que a
combustibilidade seja 0):

{{"combustibilidade": <inteiro 0-10>, "favorabilidade": <inteiro 0-10>, "duracao": <inteiro 0-10>, "nome": "<nome curto da fonte de fogo>", "descricao": "<texto factual da chama que nasce>", "nome_final": "<nome curto do que resta depois>", "descricao_final": "<texto factual das cinzas/tições frios>"}}"""

_STR = {"type": "string"}


@inworld("fogo_ops_applied")
def _iw_kindle(op):
    return "acendeu fogo e o viu pegar"


def _kindle(name: str, args: dict, ctx) -> tuple[dict, bool]:
    materiais = args.get("materiais")
    if not isinstance(materiais, list) or not materiais:
        return ctx.err("informe ao menos um material presente/na posse para acender"), False
    materiais = list(dict.fromkeys(materiais))  # sem duplicata, mantém ordem
    disponiveis = ctx.cand["kindle_materiais"]
    for mid in materiais:
        if mid not in disponiveis:
            return ctx.err(f"'{mid}' não está ao alcance para acender", "materiais",
                           ctx.validos({i: ctx.items[i] for i in disponiveis})), False
    chave = tuple(sorted(materiais))
    if chave in ctx.kindled_asked:
        return ctx.err("acender esses materiais já foi tentado neste turno — o desfecho "
                       "sai na aplicação; NÃO repita: siga para outra ação ou narrate"), False
    # spec 053 — CONTRATO DE ANÁLISE: os materiais que serão CONSUMIDOS e, à parte, o
    # que o ator tem EM MÃOS, que a favorabilidade lê e nada consome. São dois blocos
    # porque são dois papéis: A Mente escolhe o combustível, o corpo já tem o resto.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_ACENDER, json.dumps({
            "materiais": [ctx.describe(m) for m in materiais],
            "em_maos": [ctx.describe(i) for i in ctx.em_maos],
        }, ensure_ascii=False, indent=2)),
        campos={"combustibilidade": 5, "favorabilidade": 5, "duracao": 5},
        texto_campos={"nome": "", "descricao": "", "nome_final": "",
                      "descricao_final": ""})
    ctx.kindled_asked.add(chave)
    base = {"materiais": materiais}
    combustibilidade = julgado["combustibilidade"]
    if combustibilidade == 0:
        rej, rolled = ctx.apply_arbitrated("fogo_ops", {**base, "combustibilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("kindle_fire", tuple(materiais)), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("fogo_ops", {
        **base, "combustibilidade": combustibilidade,
        "favorabilidade": julgado["favorabilidade"], "duracao": julgado["duracao"],
        "nome": julgado["nome"], "descricao": julgado["descricao"],
        "nome_final": julgado["nome_final"],
        "descricao_final": julgado["descricao_final"]})
    if rej:
        return ctx.arb_deny(rolled, ("kindle_fire", tuple(materiais)), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


KINDLE_FIRE = tool_spec(ToolSpec(
    names=("kindle_fire",),
    juizo=(
        ("combustibilidade", REGUA_ACENDER),
        ("favorabilidade", REGUA_ACENDER),
        ("duracao", REGUA_ACENDER),
        ("nome", REGUA_ACENDER),
        ("descricao", REGUA_ACENDER),
        ("nome_final", REGUA_ACENDER),
        ("descricao_final", REGUA_ACENDER),
    ),
    # A DESCRIPTION É PARA A LLM QUE ESCOLHE, não para o jogador ler (medido em
    # 2026-08-25, `tests/exploracao/lab_descriptions.py`). Descreve EFEITO e CONTRATO
    # DO PARÂMETRO, e deliberadamente NÃO enumera caso de uso: listar "para aquecer,
    # cozinhar, forjar" congela a tool nos usos que hoje imaginamos e mata o que
    # ninguém previu — e, medido, nem ajudava: a variante que listava usos foi a que
    # MENOS encadeou "não tenho fogo, preciso acender antes de cozinhar" (0/5 contra
    # 2/5). Também não alardeia o custo: a variante com "ato irreversível" derrubou a
    # chamada legítima a 0/3 — aviso de custo suprime uso, não educa.
    description=("Acende uma fonte de calor no lugar, queimando os materiais informados. "
     "Em `materiais` vão as coisas que devem virar combustível; a ferramenta de fazer "
     "faísca não entra — o mundo já considera sozinho o que está em mãos. O mundo "
     "julga, pela descrição, se aquilo pega fogo."),
    params={"materiais": {"type": "array", "items": {"type": "string"}},
            "combustibilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "favorabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "duracao": {"type": "integer", "minimum": 0, "maximum": 10},
            "nome": _STR, "descricao": _STR,
            "nome_final": _STR, "descricao_final": _STR},
    required=("materiais", "combustibilidade", "favorabilidade", "duracao",
              "nome", "descricao", "nome_final", "descricao_final"),
    enum_sources={"materiais": "kindle_materiais"},
    apply=_kindle,
))
