"""DECLARAÇÃO + CORPO da tool de ESQUARTEJAR (spec 050).

`butcher` extrai carne de um corpo QUE JÁ ESTÁ MORTO, julgado numa ÚNICA chamada ao
Árbitro (`REGUA_ESQUARTEJAR`, molde reduzido de `REGUA_COZINHAR`) — DUAS notas em vez
de quatro, e UMA description em vez de três candidatas: a banda aqui decide
QUANTIDADE/peso das porções (física do Motor, `porcoes_de_carne`), nunca o texto —
diferente de `cook`, onde a banda muda a textura sensorial do prato. O corpo ENFILEIRA
via `ctx.apply_arbitrated` (mesmo padrão de `cook`/`eat`/`drink`), sem importar o
Árbitro. Nunca causa a morte de ninguém — a pré-condição dura (`alvo` já MORTO) é
checada pelo `enum_source` `butcher_alvo` (`arbiter.py::_verb_candidates`), zero LLM se
violada.
"""
from __future__ import annotations

import json
from .. import juizo

from ..registro import ToolSpec, inworld, tool_spec


# --- As duas réguas de `butcher` (spec 050) ---------------------------------- #
# Uma categórica (ESQUARTEJABILIDADE — gate: este corpo é feito de carne?) antes
# de uma graduada (RENDIMENTO — só perguntada se a primeira é > 0: quanto daquela
# carne está aproveitável agora?). Separadas por motivo análogo ao de `cook`
# (fonte_de_calor/cozinhabilidade): um erro de calibração ambíguo (2 em vez de 0
# num golem) nunca pode deixar a rolagem prosseguir — research R1.

REGUA_APROVEITAMENTO = """\
Régua do APROVEITAMENTO (o quanto, PELA DESCRIÇÃO, há neste corpo matéria que se
possa aproveitar — carne, gordura, couro, pele, osso, tendão, chifre, sebo — não
o quanto quem esquarteja seria bom nisso, e não se É um animal em tese):
  0  categoricamente não há nada a aproveitar — pedra, metal, energia, construto,
     névoa (sem teste)
  1  quase certamente não — quase nada na descrição sugere matéria aproveitável
  2  muito improvável — indícios fracos demais
  3  duvidoso — a descrição não convence
  4  incerto — poderia ser, poderia não ser
  5  ambíguo — a descrição não decide
  6  provável — indícios razoáveis de matéria orgânica
  7  bastante provável — claramente um corpo com o que tirar
  8  aproveitamento evidente — corpo orgânico comum, sem dúvida
  9  muito evidente — descrição rica em carne, couro ou osso
  10 evidente e farto — criatura grande e íntegra, sem ambiguidade (sem teste)
Um corpo CLARAMENTE de pedra, metal ou energia (um golem, um elemental) é 0, não
1 ou 2 — não hesite no extremo quando a descrição já diz que não há matéria
nenhuma ali. **Um esqueleto NÃO é 0**: osso é matéria aproveitável, e o que sai
dele é osso, não carne. A nota é segredo do mundo: nunca o número na narrativa;
nota 0 faz a tentativa ser recusada, SEM perguntar rendimento."""

REGUA_RENDIMENTO = """\
Régua do RENDIMENTO (só importa se aproveitamento > 0 — o quanto, PELO PORTE e
ESTADO DE CONSERVAÇÃO deste corpo específico, há matéria aproveitável AGORA — não
o quanto ele É aproveitável):
  0  nada sobrou — carbonizado, mutilado além do reconhecível, podre a ponto de
     não sobrar nada (sem teste)
  1  quase nada — só resquícios
  2  muito pouco — a maior parte se perdeu
  3  escasso — porte pequeno ou estado ruim
  4  abaixo do comum — porte modesto
  5  comum — porte médio, estado razoável
  6  acima do comum — porte bom, bem conservado
  7  farto — porte grande, boa conservação
  8  muito farto — porte grande, saudável antes de morrer
  9  quase perfeito — porte excelente, conservação ótima
  10 fartura máxima — porte enorme, saudável antes de morrer, conservação
     perfeita (sem teste)
A nota é segredo do mundo: nunca o número na narrativa. Entre 1 e 9 há um teste
resolvido na aplicação — não narre o resultado como certo."""

# spec 050/071 — UMA chamada combinada: as duas notas + TRÊS pares nome/descrição
# saem da MESMA resposta.
#
# A spec 050 usava UMA descrição só, com o argumento de que "a banda decide
# quantidade/peso (física do Motor), não o texto". Isso valia enquanto a única
# matéria era CARNE. Alargada a régua para couro, osso e tendão (spec 071), a banda
# passa a decidir também O QUE se conseguiu tirar — um esfolamento desastrado rende
# retalhos, um cuidadoso rende a pele inteira — e aí o molde certo é o de `forage`:
# três pares, um por banda.
REGUA_ESQUARTEJAR = f"""\
Você vai julgar UMA tentativa de esquartejar um corpo que já está morto. Leia a
descrição REAL fornecida com cuidado antes de responder — nunca invente detalhes
que não estejam nela.

{REGUA_APROVEITAMENTO}

{REGUA_RENDIMENTO}

A rolagem que decide a banda final (fraco/médio/farto) só acontece DEPOIS desta
resposta, no Motor — você não sabe qual vai sair. Por isso escreva TRÊS pares de
nome+descrição, o que se conseguiu tirar em cada uma:
  fraco:  o que mãos desastradas trariam deste corpo
  medio:  o que um trabalho comum rende
  farto:  o que alguém que conhece o ofício tiraria daqui
Os três saem do MESMO corpo — não invente uma criatura que a descrição não
sustenta. E saem da matéria que ELE tem: de um corpo de couro grosso sai couro,
de um esqueleto sai osso, de um bicho gordo sai carne e sebo. Nunca escreva sabor
nem apetite; descreva a COISA.

Escreva também dois textos sobre o TEMPO. "urgencia": o que está em jogo enquanto
o que se tirou ainda presta — uma frase curta, in-world, sobre a MATÉRIA.
"descricao_vencida": como ela fica depois de estragar — factual, e ainda É ela,
nunca sumida. **Só escreva os dois se a matéria de fato se deteriorar sozinha**:
carne e vísceras estragam; osso e chifre curado, não — para esses, devolva as duas
chaves VAZIAS.

Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas chaves (todas OBRIGATÓRIAS, mesmo que aproveitamento ou
rendimento sejam 0):

{{"aproveitamento": <inteiro 0-10>, "rendimento": <inteiro 0-10>, \
"nome_fraco": "<nome curto>", "descricao_fraco": "<texto factual>", \
"nome_medio": "<nome curto>", "descricao_medio": "<texto factual>", \
"nome_farto": "<nome curto>", "descricao_farto": "<texto factual>", \
"urgencia": "<uma frase, ou vazio>", "descricao_vencida": "<texto factual, ou vazio>"}}"""

_STR = {"type": "string"}


@inworld("esquartejar_ops_applied")
def _iw_butcher(op):
    return "esquartejou o corpo, com cuidado de açougueiro"


def _butcher(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    if not alvo:
        return ctx.err("informe 'alvo'"), False
    disponiveis = ctx.cand["butcher_alvo"]
    if alvo not in disponiveis:
        return ctx.err(f"'{alvo}' não está disponível para esquartejar", "alvo",
                       ctx.validos({c: ctx.chars[c] for c in disponiveis})), False
    if alvo in ctx.butchered_asked:
        return ctx.err("esquartejar esse corpo já foi tentado neste turno — o " "desfecho sai na aplicação; NÃO repita: siga para outra " "ação ou narrate"), False
    # spec 050 — CONTRATO DE ANÁLISE: a régua combinada lê só o corpo-alvo.
    julgado = juizo.julgamento(
        ctx.ask(REGUA_ESQUARTEJAR, json.dumps({
           "alvo": ctx.describe(alvo),
        }, ensure_ascii=False, indent=2)),
        campos={"aproveitamento": 5, "rendimento": 5},
        texto_campos={"nome_fraco": "", "descricao_fraco": "",
                      "nome_medio": "", "descricao_medio": "",
                      "nome_farto": "", "descricao_farto": "",
                      "urgencia": "", "descricao_vencida": ""})
    ctx.butchered_asked.add(alvo)
    base = {"alvo": alvo}
    aproveitamento = julgado["aproveitamento"]
    if aproveitamento == 0:
        rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
            **base, "esquartejabilidade": 0})
        if rej:
            return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rendimento = julgado["rendimento"]
    if rendimento == 0:
        rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
            **base, "esquartejabilidade": aproveitamento, "rendimento": 0})
        if rej:
            return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    rej, rolled = ctx.apply_arbitrated("esquartejar_ops", {
        **base, "esquartejabilidade": aproveitamento, "rendimento": rendimento,
       "nome_fraco": julgado["nome_fraco"], "descricao_fraco": julgado["descricao_fraco"],
       "nome_medio": julgado["nome_medio"], "descricao_medio": julgado["descricao_medio"],
       "nome_farto": julgado["nome_farto"], "descricao_farto": julgado["descricao_farto"],
       "urgencia": julgado.get("urgencia") or "",
       "descricao_vencida": julgado.get("descricao_vencida") or ""})
    if rej:
        return ctx.arb_deny(rolled, ("butcher", alvo), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


BUTCHER = tool_spec(ToolSpec(
    names=("butcher",),
    juizo=(
        ("aproveitamento", REGUA_ESQUARTEJAR),
        ("rendimento", REGUA_ESQUARTEJAR),
        ("nome_fraco", REGUA_ESQUARTEJAR), ("descricao_fraco", REGUA_ESQUARTEJAR),
        ("nome_medio", REGUA_ESQUARTEJAR), ("descricao_medio", REGUA_ESQUARTEJAR),
        ("nome_farto", REGUA_ESQUARTEJAR), ("descricao_farto", REGUA_ESQUARTEJAR),
    ),
    description=("Esquarteja um corpo que já está morto, extraindo carne crua. Um corpo sem matéria orgânica (pedra, osso, " "construto) não rende nada, e um corpo já esquartejado não pode ser " "esquartejado de novo. Nunca causa a morte de ninguém — só age sobre quem já " "está morto."),
    params={"alvo": _STR,
           "aproveitamento": {"type": "integer", "minimum": 0, "maximum": 10},
           "rendimento": {"type": "integer", "minimum": 0, "maximum": 10},
           "nome_fraco": _STR, "descricao_fraco": _STR,
            "nome_medio": _STR, "descricao_medio": _STR,
            "nome_farto": _STR, "descricao_farto": _STR},
    required=("alvo", "aproveitamento", "rendimento",
              "nome_fraco", "descricao_fraco", "nome_medio", "descricao_medio",
              "nome_farto", "descricao_farto"),
    enum_sources={"alvo": "butcher_alvo"},
    apply=_butcher,
))
