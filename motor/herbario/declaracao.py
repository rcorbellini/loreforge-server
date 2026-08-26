"""DECLARAÇÃO + CORPO da tool de COLHER (spec 054).

`forage` lê a prosa de um alvo — o LUGAR atual ou um `object` presente e
alcançável — e extrai matéria vegetal dele, julgado numa ÚNICA chamada ao
Árbitro (`REGUA_COLHER`, molde reduzido de `REGUA_COZINHAR`): DUAS notas
(HERBABILIDADE categórica, RIQUEZA graduada) + TRÊS pares nome/description (uma
por banda — divergência deliberada de `butcher`, que reaproveita UMA description
porque lá a banda decide só quantidade; aqui decide O QUE se trouxe) + o texto do
estado colhido, usado só quando o alvo é `object`. O corpo ENFILEIRA via
`ctx.apply_arbitrated` (mesmo padrão de `cook`/`butcher`), sem importar o
Árbitro. Nunca escreve em `location.md` (FR-013)."""
from __future__ import annotations

import json
from .. import juizo

from ..registro import ToolSpec, inworld, tool_spec


REGUA_HERBABILIDADE = """\
Régua da HERBABILIDADE (o quanto, PELA DESCRIÇÃO, há neste alvo matéria vegetal
que se possa colher de verdade — folha, raiz, casca, graveto, fruto — não o
quanto quem colhe seria bom nisso, e não se é um lugar bonito):
  0  categoricamente não há vegetal nenhum — convés calafetado, salão de pedra,
     câmara de mina, forja, porão de sal (sem teste)
  1  quase certamente não — quase nada na descrição sugere vegetação
  2  muito improvável — indícios fracos demais
  3  duvidoso — a descrição não convence
  4  incerto — poderia ser, poderia não ser
  5  ambíguo — a descrição não decide
  6  provável — indícios razoáveis de vegetação
  7  bastante provável — claramente algo cresce ali
  8  vegetação evidente — presença clara de planta
  9  vegetação muito evidente — descrição rica em detalhes de planta
  10 vegetação evidente e abundante — floresta, mata, canteiro plantado
     (sem teste)
Um alvo CLARAMENTE sem nada vivo (metal, pedra maciça, água salgada) é 0, não 1
ou 2 — não hesite no extremo quando a descrição já diz que não há vegetal
nenhum ali. A nota é segredo do mundo: nunca o número na narrativa; nota 0 faz
a tentativa ser recusada, SEM perguntar riqueza."""

REGUA_RIQUEZA = """\
Régua da RIQUEZA (só importa se herbabilidade > 0 — o quanto, PELA ABUNDÂNCIA
e ESTADO do que está descrito, há matéria vegetal aproveitável AGORA — não o
quanto o alvo É vegetal):
  0  nada aproveitável — queimado, arrancado rente, pisoteado, morto (sem teste)
  1  quase nada — só resquícios
  2  muito pouco — a maior parte se perdeu
  3  escasso — pouca coisa, mal cuidada
  4  abaixo do comum — modesto
  5  comum — algo se aproveita, sem fartura
  6  razoável — mais do que o comum
  7  bom — bastante aproveitável
  8  farto — bastante e no ponto
  9  muito farto — quase tudo aproveitável
  10 fartura — densa, viçosa, no ponto (sem teste)
A nota é segredo do mundo. Entre 1 e 9 há um teste resolvido na aplicação."""

_STR = {"type": "string"}


@inworld("forage_ops_applied")
def _iw_forage(op):
    return "colheu, olhando com atenção onde a mão ia"


def _forage(name: str, args: dict, ctx) -> tuple[dict, bool]:
    onde = args.get("onde")
    if not onde:
        return ctx.err("informe 'onde'"), False
    disponiveis = ctx.cand["forage_onde"]
    if onde not in disponiveis:
        # spec 054 (molde de cook_fonte): o enum mistura objects e o LUGAR — montar
        # o mapa por `ctx.objects[o]` levantaria KeyError no id do lugar.
        return ctx.err(f"'{onde}' não está disponível para colher", "onde",
                       ctx.validos({o: ctx.objects.get(o)
                                    or {"name": (ctx.context.get("location") or {}).get("name") or o}
                                    for o in disponiveis})), False
    if onde in ctx.forage_asked:
        return ctx.err("colher desse alvo já foi tentado neste turno — o "
                       "desfecho sai na aplicação; NÃO repita: siga para outra "
                       "ação ou narrate"), False
    # spec 054 — CONTRATO DE ANÁLISE: a régua combinada lê só o alvo.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_COLHER, json.dumps({
            "onde": ctx.describe(onde),
        }, ensure_ascii=False, indent=2)),
        campos={"herbabilidade": 5, "riqueza": 5},
        texto_campos={"nome_mato": "", "descricao_mato": "",
                      "nome_util": "", "descricao_util": "",
                      "nome_seleta": "", "descricao_seleta": "",
                      "descricao_colhida": ""})
    ctx.forage_asked.add(onde)
    base = {"onde": onde}
    herbabilidade = julgado["herbabilidade"]
    if herbabilidade == 0:
        rej, rolled = ctx.apply_arbitrated("forage_ops", {**base, "herbabilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("forage", onde), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    riqueza = julgado["riqueza"]
    if riqueza == 0:
        rej, rolled = ctx.apply_arbitrated("forage_ops", {
            **base, "herbabilidade": herbabilidade, "riqueza": 0})
        if rej:
            return ctx.arb_deny(rolled, ("forage", onde), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("forage_ops", {
        **base, "herbabilidade": herbabilidade, "riqueza": riqueza,
        "nome_mato": julgado["nome_mato"], "descricao_mato": julgado["descricao_mato"],
        "nome_util": julgado["nome_util"], "descricao_util": julgado["descricao_util"],
        "nome_seleta": julgado["nome_seleta"],
        "descricao_seleta": julgado["descricao_seleta"],
        "descricao_colhida": julgado["descricao_colhida"]})
    if rej:
        return ctx.arb_deny(rolled, ("forage", onde), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


# spec 054 — UMA chamada combinada (mesmo custo/latência que `butcher` já fixou,
# mais sete chaves de texto porque a banda decide O QUE se trouxe, não só quanto
# — divergência deliberada de `butcher`, ver US2 da spec).
REGUA_COLHER = f"""\
Você vai julgar UMA tentativa de colher matéria vegetal de um alvo — um lugar
ou uma coisa presente. Leia a descrição REAL fornecida com cuidado antes de
responder — nunca invente detalhes que não estejam nela.

{REGUA_HERBABILIDADE}

{REGUA_RIQUEZA}

A rolagem que decide a banda final (mato/útil/seleta) só acontece DEPOIS desta
resposta, no Motor — você não sabe qual banda vai sair, e não precisa saber:
por isso escreva TRÊS pares de nome+descrição, um para CADA banda — o que
alguém sem olho para plantas traria (mato), o que uma colheita comum rende
(util), e o que alguém que conhece bem plantas traria daqui (seleta). As três
descrevem o MESMO alvo, lido da mesma descrição real — nunca invente uma
planta que a descrição não sustenta.

Escreva também `descricao_colhida`: o que este alvo específico passaria a
dizer de si logo depois de ser colhido (arrancado, revirado, com menos do que
tinha) — mesmo que a colheita não renda nada de bom. Esse texto só é usado
quando o alvo é algo que se possa marcar como colhido; escreva-o sempre assim
mesmo.

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas nove chaves (todas OBRIGATÓRIAS, mesmo que herbabilidade
ou riqueza sejam 0):

{{"herbabilidade": <inteiro 0-10>, "riqueza": <inteiro 0-10>, \
"nome_mato": "<nome curto>", "descricao_mato": "<texto factual>", \
"nome_util": "<nome curto>", "descricao_util": "<texto factual>", \
"nome_seleta": "<nome curto>", "descricao_seleta": "<texto factual>", \
"descricao_colhida": "<texto factual do alvo depois de colhido>"}}"""


FORAGE = tool_spec(ToolSpec(
    names=("forage",),
    juizo=(
        ("herbabilidade", REGUA_COLHER),
        ("riqueza", REGUA_COLHER),
        ("nome_mato", REGUA_COLHER), ("descricao_mato", REGUA_COLHER),
        ("nome_util", REGUA_COLHER), ("descricao_util", REGUA_COLHER),
        ("nome_seleta", REGUA_COLHER), ("descricao_seleta", REGUA_COLHER),
        ("descricao_colhida", REGUA_COLHER),
    ),
    # A DESCRIPTION É PARA A LLM QUE ESCOLHE, não para o jogador ler (disciplina
    # de `docs/validacao-de-descriptions.md`, medida em `kindle_fire`,
    # 2026-08-25). MEDIDO em `tests/exploracao/sondagem_forage.py` (2026-08-26,
    # qwen3:8b, think:false, 3 variantes × 5 cenas × 5 rodadas): a frase "o mundo
    # julga, pela descrição, se X" — herdada do molde de cook/butcher/kindle_fire
    # — empatou EXATAMENTE (FN=9, FP=0) contra uma variante que a REMOVE por
    # completo. Ela não move a decisão de chamar-ou-não; é peso morto pro
    # consumidor real desta API (a Mente), então saiu. No lugar entrou CONTRATO
    # DO PARÂMETRO mais concreto — exemplos do que `onde` aceita — que a medição
    # não cobriu (não é redação PROVADA superior — é redação sem o texto morto).
    # Deliberadamente NÃO enumera USO do que se colhe ("ervas medicinais, lenha,
    # fruta") — isso sim foi medido como pior no `kindle_fire` (congela a tool
    # nos usos que hoje se imaginam, e mediu MENOS encadeamento). Também não
    # alardeia custo.
    description=("Colhe matéria vegetal de um lugar ou de algo presente e "
     "alcançável — uma clareira, uma moita, um canteiro, uma árvore. Em `onde` "
     "vai o id de onde ela está: o lugar atual, ou algo da cena. Um alvo sem "
     "vegetação de verdade não rende nada."),
    params={"onde": _STR,
            "herbabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
            "riqueza": {"type": "integer", "minimum": 0, "maximum": 10},
            "nome_mato": _STR, "descricao_mato": _STR,
            "nome_util": _STR, "descricao_util": _STR,
            "nome_seleta": _STR, "descricao_seleta": _STR,
            "descricao_colhida": _STR},
    required=("onde", "herbabilidade", "riqueza",
              "nome_mato", "descricao_mato",
              "nome_util", "descricao_util",
              "nome_seleta", "descricao_seleta",
              "descricao_colhida"),
    enum_sources={"onde": "forage_onde"},
    apply=_forage,
))
