"""DECLARAÇÃO + CORPO das TRÊS capacidades de EXTRAÇÃO (specs 054/071).

`mine`, `chop` e `forage` tiram matéria-prima de um alvo — o LUGAR atual ou um
`object` presente e alcançável — lendo a prosa dele. Três `ToolSpec` com
`description` própria sobre **um** corpo e **uma** régua, molde exato de
`forge_weapon`/`forge_armor` (spec 052).

**A ÚNICA diferença de juízo entre as três é a MATÉRIA, e ela desce como DADO.**
Não há bloco de vocabulário por matéria, nem cláusula de exclusão em prosa: o
payload leva `materia_pedida`, e a régua é idêntica palavra por palavra.

POR QUE ASSIM, e este é o achado mais caro da spec (research R10, cinco rodadas e
138 chamadas ao modelo real). A restrição de matéria escrita em PROSA falha dos
dois lados:

  sem cláusula          uma moita de amora pontua 10 para minério — o modelo
                        INVENTA um produto ("Pedaço de Madeira" numa amoreira)
                        para justificar a nota
  com cláusula forte    o vazamento fecha, mas o modelo passa a RECUSAR o ato
                        legítimo: "não posso fornecer informações sobre
                        atividades ilegais", 3/3 na cena da picareta no veio

Reescrever o mesmo parágrafo mais gentil (VG) piorou; mudá-lo de posição (VI)
não resolveu. Como DADO no payload: 5/5 cenas, zero recusa, 15/15 repetições
estáveis. A regra que sai daí vale além desta spec — **restrição que o Motor já
conhece desce como dado, nunca como proibição em prosa**: prosa é para o que o
modelo precisa JULGAR; escrever "não pontue X" convida-o a tratar X como assunto
proibido e a recusar a cena inteira.

`forage` NÃO pergunta a nota de FERRAMENTA. Colher com a mão é o caso base do
mundo, e a régua de ferramenta pontua mão vazia como 0 — correto para pedra,
destruiria a colheita. É a mesma marca (`exige_ferramenta`) que faz `mine`/`chop`
sumirem do manifest quando não há nada empunhável.
"""
from __future__ import annotations

import json

from .. import juizo
from ..registro import ToolSpec, inworld, tool_spec
from .primitivas import MATERIAS, sanear_tamanho

_STR = {"type": "string"}

# --------------------------------------------------------------------------- #
# A RÉGUA — uma só, para as três
# --------------------------------------------------------------------------- #

_ABERTURA = """\
Você vai julgar UMA tentativa de extrair matéria-prima de um alvo. A chave
`materia_pedida` do payload diz QUAL matéria esta tentativa busca. Leia a
descrição REAL do alvo com cuidado — nunca invente detalhe que não esteja nela."""

REGUA_ALVO = """\
Régua da MATÉRIA NO ALVO — uma pergunta só: quanto da `materia_pedida` a descrição deste
alvo mostra?
  0  o que há ali é outra matéria
  3  há traço dela, misturado e escasso
  5  há, e a descrição não deixa claro quanto
  8  clara e em quantidade
  10 evidente e farta
Pontue a MATÉRIA PEDIDA que a descrição mostra, não o quanto o alvo parece útil.
Um alvo cheio de coisa aproveitável que seja de OUTRA matéria é 0 nesta régua, e
isso é um resultado correto."""

REGUA_FERRAMENTA = """\
Régua da SERVENTIA DA FERRAMENTA — uma pergunta só: o que está NA MÃO consegue arrancar a
`materia_pedida` deste alvo?
  0  foi feito para outra coisa, ou não há nada na mão
  3  serve de improviso, mal
  5  serve, sem ser própria
  8  própria para isso
  10 própria e em bom estado
Julgue apenas o objeto que está na mão. Outras coisas que existam na cena não
entram nesta nota."""

REGUA_RENDIMENTO = """\
Régua do RENDIMENTO (só importa se as anteriores forem > 0): quanto há de
aproveitável AGORA, pela abundância e pelo estado do que está descrito?
  0  nada aproveitável — esgotado, já revirado, estéril (sem teste)
  3  escasso
  5  comum — algo se aproveita, sem fartura
  8  farto
  10 fartura densa (sem teste)
A nota é segredo do mundo. Entre 1 e 9 há um teste resolvido no Motor."""

REGUA_RENOVACAO = """\
Régua da RENOVAÇÃO: o quanto este alvo volta a render sozinho depois de
trabalhado? Julgue a NATUREZA do alvo, nunca a pressa de quem extrai.
  0  não volta: uma veia de metal arrancada não se refaz, um bloco de pedra
     tirado não cresce de novo
  3  volta em anos — uma árvore antiga, um barranco que a chuva refaz devagar
  5  volta em estações
  8  volta em dias
  10 volta em horas — folha, broto, mato rasteiro
A nota é segredo do mundo. Nota 0 deixa o alvo esgotado PARA SEMPRE."""

REGUA_TAMANHO = """\
Régua do TAMANHO de CADA porção extraída (a escala do mundo, do menor ao maior):
"PP", "P", "M", "G", "XG". Um punhado de ervas ou um torrão de argila é P; uma
tábua ou uma laje é G; um tronco inteiro é XG."""

REGUA_BANDAS = """\
A rolagem que decide a banda final (pobre/comum/rica) acontece DEPOIS desta
resposta, no Motor — você não sabe qual vai sair. Por isso escreva TRÊS pares de
nome+descrição: o QUE SAIU do alvo em cada banda, nunca o alvo de onde saiu.
  pobre: o que mãos desajeitadas trariam
  comum: o que uma tentativa comum rende
  rica:  o que alguém que conhece a matéria traria daqui
O NOME é sempre da coisa extraída. ERRADO: extrair da "Macieira da Praça" e
nomear "Macieira da Praça". CERTO: "Maçã", "Galho de Macieira".

Escreva também `descricao_extraida`: o que ESTE alvo passaria a dizer de si logo
depois de ser trabalhado."""

REGUA_PRAZO = """\
Escreva `urgencia` e `descricao_vencida` SOMENTE se o que foi extraído se
deteriora sozinho com o tempo (folha murcha, fruta apodrece). Pedra, metal,
argila e madeira não se deterioram: para eles, devolva as duas chaves VAZIAS."""

_CONTRATO = ('{%s"rendimento": <inteiro 0-10>, "renovacao": <inteiro 0-10>, '
             '"tamanho": "<PP|P|M|G|XG>", '
             '"nome_pobre": "<nome curto>", "descricao_pobre": "<texto factual>", '
             '"nome_comum": "<nome curto>", "descricao_comum": "<texto factual>", '
             '"nome_rica": "<nome curto>", "descricao_rica": "<texto factual>", '
             '"descricao_extraida": "<texto factual do alvo depois>", '
             '"urgencia": "<uma frase, ou vazio>", '
             '"descricao_vencida": "<texto factual, ou vazio>"}')

_FECHO = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE com estas
chaves (todas OBRIGATÓRIAS):

%s"""


def _monta_regua(exige_ferramenta: bool) -> str:
    blocos = [_ABERTURA, REGUA_ALVO]
    chaves = '"materia_no_alvo": <inteiro 0-10>, '
    if exige_ferramenta:
        blocos.append(REGUA_FERRAMENTA)
        chaves += '"serventia_da_ferramenta": <inteiro 0-10>, '
    blocos += [REGUA_RENDIMENTO, REGUA_RENOVACAO, REGUA_TAMANHO, REGUA_BANDAS,
               REGUA_PRAZO, _FECHO % (_CONTRATO % chaves)]
    return "\n\n".join(blocos)


REGUAS = {n: _monta_regua(m["exige_ferramenta"]) for n, m in MATERIAS.items()}

_TEXTO_CAMPOS = {"tamanho": "P", "nome_pobre": "", "descricao_pobre": "",
                 "nome_comum": "", "descricao_comum": "", "nome_rica": "",
                 "descricao_rica": "", "descricao_extraida": "",
                 "urgencia": "", "descricao_vencida": ""}


# --------------------------------------------------------------------------- #
# A VOZ
# --------------------------------------------------------------------------- #

@inworld("extracao_ops_applied")
def _iw_extracao(op):
    return {
        "mine": "arrancou o que a pedra deu",
        "chop": "abriu a madeira e tirou o que servia",
    }.get(op.get("capacidade"), "colheu, olhando com atenção onde a mão ia")


# --------------------------------------------------------------------------- #
# O CORPO — um só, para as três
# --------------------------------------------------------------------------- #

def _extrair(name: str, args: dict, ctx) -> tuple[dict, bool]:
    materia = MATERIAS[name]
    onde = args.get("onde")
    if not onde:
        return ctx.err("informe 'onde'"), False
    disponiveis = ctx.cand["extracao_onde"]
    if onde not in disponiveis:
        # o enum mistura objects e o LUGAR — montar o mapa por `ctx.objects[o]`
        # levantaria KeyError no id do lugar (molde de `cook_fonte`).
        return ctx.err(f"'{onde}' não está disponível para isso", "onde",
                       ctx.validos({o: ctx.objects.get(o)
                                    or {"name": (ctx.context["scene"]["place"]).get("name") or o}
                                    for o in disponiveis})), False

    ferramenta = args.get("ferramenta")
    if materia["exige_ferramenta"]:
        empunhaveis = ctx.cand.get("empunhavel") or []
        if not ferramenta:
            return ctx.err("informe 'ferramenta' — sem nada na mão não se faz isso",
                           "ferramenta", ctx.validos(
                               {i: ctx.items[i] for i in empunhaveis})), False
        if ferramenta not in empunhaveis:
            return ctx.err(f"'{ferramenta}' não está na sua mão", "ferramenta",
                           ctx.validos({i: ctx.items[i] for i in empunhaveis})), False

    chave = (name, onde)
    if chave in ctx.forage_asked:
        return ctx.err("isso já foi tentado neste turno — o desfecho sai na "
                       "aplicação; NÃO repita: siga para outra ação ou narrate"), False

    # CONTRATO DE ANÁLISE: a régua lê o alvo, a ferramenta e a MATÉRIA PEDIDA — e
    # mais nada da cena. `materia_pedida` é o que substitui a cláusula de exclusão
    # em prosa que provocava recusa (research R10).
    entrada = {"materia_pedida": materia["materia"], "onde": ctx.describe(onde)}
    if materia["exige_ferramenta"]:
        entrada["ferramenta"] = ctx.describe(ferramenta)

    campos = {"materia_no_alvo": 5, "rendimento": 5, "renovacao": 5}
    if materia["exige_ferramenta"]:
        campos["serventia_da_ferramenta"] = 5
    julgado = juizo.julgamento(
        ctx.ask(REGUAS[name], json.dumps(entrada, ensure_ascii=False, indent=2)),
        campos=campos, texto_campos=_TEXTO_CAMPOS)
    ctx.forage_asked.add(chave)

    base = {"onde": onde, "capacidade": name}
    if ferramenta:
        base["ferramenta"] = ferramenta

    def _enfileira(extra: dict):
        rej, rolled = ctx.apply_arbitrated("extracao_ops", {**base, **extra})
        if rej:
            return ctx.arb_deny(rolled, (name, onde), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False

    # OS DOIS GATES DE ADMISSÃO, na ordem em que barateiam: alvo sem a matéria não
    # chega a perguntar da ferramenta, e vice-versa. O executor revalida.
    if julgado["materia_no_alvo"] <= 0:
        return _enfileira({"alvo": 0})  # nota do ALVO zerada
    if materia["exige_ferramenta"] and julgado["serventia_da_ferramenta"] <= 0:
        return _enfileira({"alvo": julgado["materia_no_alvo"], "ferramenta_nota": 0})
    if julgado["rendimento"] <= 0:
        return _enfileira({"alvo": julgado["materia_no_alvo"],
                           "ferramenta_nota": julgado.get("serventia_da_ferramenta", 10),
                           "rendimento": 0})

    return _enfileira({
        "alvo": julgado["materia_no_alvo"],
        "ferramenta_nota": julgado.get("serventia_da_ferramenta", 10),
        "rendimento": julgado["rendimento"],
        "renovacao": julgado["renovacao"],
        "tamanho": sanear_tamanho(julgado["tamanho"]),
        "nome_pobre": julgado["nome_pobre"], "descricao_pobre": julgado["descricao_pobre"],
        "nome_comum": julgado["nome_comum"], "descricao_comum": julgado["descricao_comum"],
        "nome_rica": julgado["nome_rica"], "descricao_rica": julgado["descricao_rica"],
        "descricao_extraida": julgado["descricao_extraida"],
        "urgencia": julgado.get("urgencia") or "",
        "descricao_vencida": julgado.get("descricao_vencida") or ""})


# --------------------------------------------------------------------------- #
# AS TRÊS FACES
# --------------------------------------------------------------------------- #
#
# Três `description`, um corpo. É por causa DELAS que a spec tem três capacidades
# em vez de uma genérica: desde a 043 a `description` é a fonte única do que o
# jogador e A Mente leem, e "tire matéria de um alvo com o que tiver na mão" não
# ajuda ninguém a escolher. Some a isso o manifest que se poda sozinho (sem nada
# empunhável, `mine` e `chop` nem aparecem) e a matéria que a régua pode excluir
# porque a capacidade já a fixa.

_PARAMS = {
    "onde": {"type": "string",
             "description": "o lugar onde se está, ou uma coisa presente e "
                            "alcançável de onde se tira"},
}
_PARAMS_COM_FERRAMENTA = {
    **_PARAMS,
    "ferramenta": {"type": "string",
                   "description": "o que se tem em mãos para fazer o serviço"},
}
_JUIZO_CAMPOS = ("materia_no_alvo", "rendimento", "renovacao", "tamanho",
                 "nome_pobre", "descricao_pobre", "nome_comum", "descricao_comum",
                 "nome_rica", "descricao_rica", "descricao_extraida",
                 "urgencia", "descricao_vencida")


def _spec(nome: str, description: str) -> ToolSpec:
    m = MATERIAS[nome]
    campos = _JUIZO_CAMPOS + (("serventia_da_ferramenta",) if m["exige_ferramenta"] else ())
    return ToolSpec(
        names=(nome,),
        juizo=tuple((c, REGUAS[nome]) for c in campos),
        description=description,
        params=dict(_PARAMS_COM_FERRAMENTA if m["exige_ferramenta"] else _PARAMS),
        # `ferramenta` OBRIGATÓRIA não é só validação: parâmetro obrigatório com
        # enum vazio faz a tool SUMIR do turno (`arbiter_tools/base.py`). É o que
        # tira `mine`/`chop` da frente de quem está de mãos vazias.
        required=("onde", "ferramenta") if m["exige_ferramenta"] else ("onde",),
        enum_sources=({"onde": "extracao_onde", "ferramenta": "empunhavel"}
                      if m["exige_ferramenta"] else {"onde": "extracao_onde"}),
        apply=lambda name, args, ctx: _extrair(name, args, ctx),
    )


# A DESCRIPTION É PARA A LLM QUE ESCOLHE, não para o jogador ler (disciplina de
# `docs/validacao-de-descriptions.md`). Três regras que vieram de MEDIÇÃO e valem
# para as três, herdadas de `forage`/`kindle_fire`:
#
#   1. NADA de "o mundo julga, pela descrição, se X" — medido em
#      `sondagem_forage.py` (qwen3:8b, 3 variantes x 5 cenas x 5 rodadas): empatou
#      EXATAMENTE (FN=9, FP=0) com a variante que a remove. Não move a decisão de
#      chamar-ou-não; é peso morto para a Mente. No lugar entra CONTRATO DO
#      PARÂMETRO concreto.
#   2. NADA de enumerar USO do que sai ("ervas medicinais, lenha, fruta") — medido
#      pior no `kindle_fire`: congela a capacidade nos usos que hoje se imaginam, e
#      rendeu MENOS encadeamento.
#   3. Nada de alardear custo.
#
# A `forage` volta com a redação medida, palavra por palavra. As duas novas seguem
# o molde e acrescentam só o que é PRÓPRIO delas: a ferramenta em mãos, e o aviso
# de que o que sai pode ser pesado demais para carregar — que é o que leva a Mente
# a encadear com arrastar em vez de tentar pegar.

MINE = tool_spec(_spec("mine",
    "Arranca pedra, minério, argila ou sal de um lugar ou de algo presente e "
    "alcançável — uma parede de rocha, um veio exposto, um barranco, uma pedreira. "
    "Em `onde` vai o id de onde está: o lugar atual, ou algo da cena; em "
    "`ferramenta`, o id do que se tem em mãos para bater e soltar. O que sair fica "
    "ali, e pode ser pesado demais para levar na mão. Nem tudo que se arranca "
    "torna a se refazer."))

CHOP = tool_spec(_spec("chop",
    "Corta madeira de um lugar ou de algo presente e alcançável — uma árvore, um "
    "tronco caído, um portão apodrecido, uma viga. Em `onde` vai o id de onde ela "
    "está: o lugar atual, ou algo da cena; em `ferramenta`, o id do que se tem em "
    "mãos para cortar. O que sair fica ali, e pode ser pesado demais para levar na "
    "mão."))

FORAGE = tool_spec(_spec("forage",
    "Colhe matéria vegetal de um lugar ou de algo presente e "
    "alcançável — uma clareira, uma moita, um canteiro, uma árvore. Em `onde` "
    "vai o id de onde ela está: o lugar atual, ou algo da cena. Um alvo sem "
    "vegetação de verdade não rende nada."))
