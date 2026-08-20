"""DECLARAÇÃO + CORPO das tools de FORJAR (spec 052).

`forge_weapon` e `forge_armor` transformam material bruto em equipamento, num
trabalho que ATRAVESSA O TEMPO e pode ser retomado. Duas declarações, UM corpo
(`_forjar`): relógio, catraca, extremos, memórias e recusas são o mesmo código —
divergir ali seria defeito, não desenho.

POR QUE DUAS TOOLS, e não uma com um parâmetro de tipo (desvio declarado do
Princípio XII, item 2): NÃO é para enxugar a régua — as réguas nunca chegam à face
(os parâmetros de juízo são removidos do manifest em `arbiter_tools/base.py`, e a
régua só existe na consulta ao Árbitro), então uma tool única com `tipo:` teria
exatamente a mesma régua, escolhida aqui dentro. O motivo real é a FACE: com duas
capacidades, a escolha entre arma e armadura deixa de ser um valor de enum e passa
a ser o NOME da tool — e modelos fracos erram valor de enum com muito mais
frequência do que erram nome de capacidade.

UMA chamada ao Árbitro, na ABERTURA, e só. Toda retomada é aritmética: o Motor
reconhece a peça pelo bloco `trabalho` no arquivo e não gasta nenhuma LLM.
"""
from __future__ import annotations

import json

from .. import juizo, trabalho
from ..registro import ToolSpec, inworld, tool_spec


# --- As cinco réguas de forjar (spec 052) ----------------------------------- #
# Três de ADMISSÃO (gates — nota 0 recusa sem julgar o resto) que TAMBÉM alimentam
# a favorabilidade, mais a QUALIDADE DO MATERIAL (que é gate, favorabilidade e teto
# de banda) e a DURAÇÃO (classificação pura, convertida em tempo real pelo Motor).

REGUA_FORJABILIDADE_ARMA = """\
Régua da FORJABILIDADE (o quanto os materiais escolhidos, PELA DESCRIÇÃO
COMBINADA deles, podem virar uma ARMA batida no fogo — não o quanto ela ficaria
boa):
  0  não dá para forjar arma com isso — um ou mais itens claramente não são
     material de forja (comida, tecido, madeira solta, uma ferramenta pronta,
     um objeto que já é outra coisa) (sem teste)
  1  quase certamente não — nada ali sugere metal de trabalho
  2  muito improvável — material que o fogo não conforma
  3  duvidoso — há algo aproveitável, mas quase nada
  4  incerto — daria para tentar, sem nenhuma lógica de arma
  5  ambíguo — a descrição não decide se aquilo vira lâmina ou ponta
  6  provável — material de forja plausível, dá para tirar uma arma dali
  7  bastante provável — metal de trabalho, claramente forjável
  8  bom — material próprio para arma, sem dúvida
  9  muito bom — quase pede para virar arma
  10 evidente — é exatamente do que se fazem armas (sem teste)
Um item que NÃO é material de forja MISTURADO com metal de verdade deve DERRUBAR
a nota — ele não desaparece da leitura por estar acompanhado. A nota é segredo do
mundo: nunca o número na narrativa; nota 0 faz a tentativa ser recusada, mesmo que
as outras notas venham preenchidas."""

REGUA_FORJABILIDADE_ARMADURA = """\
Régua da FORJABILIDADE (o quanto os materiais escolhidos, PELA DESCRIÇÃO
COMBINADA deles, podem virar uma PEÇA DE PROTEÇÃO vestível — não o quanto ela
ficaria boa):
  0  não dá para forjar proteção com isso — um ou mais itens claramente não são
     material de forja (comida, tecido solto, madeira, uma ferramenta pronta, um
     objeto que já é outra coisa) (sem teste)
  1  quase certamente não — nada ali cobre nem sustenta golpe
  2  muito improvável — material que o fogo não conforma em chapa
  3  duvidoso — há algo aproveitável, mas quase nada
  4  incerto — daria para tentar, sem nenhuma lógica de proteção
  5  ambíguo — a descrição não decide se aquilo vira placa ou malha
  6  provável — material de forja plausível, dá para tirar proteção dali
  7  bastante provável — metal de trabalho, claramente conformável
  8  bom — material próprio para armadura, sem dúvida
  9  muito bom — quase pede para virar peça de proteção
  10 evidente — é exatamente do que se fazem armaduras (sem teste)
Um item que NÃO é material de forja MISTURADO com metal de verdade deve DERRUBAR
a nota. A nota é segredo do mundo: nunca o número na narrativa; nota 0 faz a
tentativa ser recusada, mesmo que as outras notas venham preenchidas."""

REGUA_QUALIDADE_MATERIAL = """\
Régua da QUALIDADE DO MATERIAL (o quanto o material, PELA DESCRIÇÃO, é bom no
que ele é — não se ele serve para forjar, que a régua anterior já decidiu):
  0  imprestável — ferrugem pura, metal podre, refugo que não sustenta forma
     (sem teste)
  1  péssimo — sucata que mal se aproveita
  2  muito ruim — cheio de impureza, quebradiço
  3  ruim — serve, mas é material de última hora
  4  medíocre — comum e mal cuidado
  5  comum — o metal do dia a dia, sem nada de especial
  6  bom — material limpo, bem guardado
  7  muito bom — liga cuidada, sem falha aparente
  8  excelente — material de encomenda, notável
  9  raríssimo — metal de que se fala, difícil de conseguir
  10 lendário — material sobre o qual existem histórias (sem teste)
Julgue o que a descrição REALMENTE diz: ferrugem, mossa e sujeira derrubam; liga
nomeada, pureza e procedência sobem. Não confunda o VALOR de um objeto com a
qualidade do metal dele. A nota é segredo do mundo: nunca o número na narrativa;
nota 0 faz a tentativa ser recusada."""

REGUA_FOGO_DE_FORJA = """\
Régua do FOGO DE FORJA (o quanto aquele fogo, PELA DESCRIÇÃO, dá conta de
trabalhar METAL agora — não se é uma fonte de calor em tese, e não se serviria
para cozinhar):
  0  nenhum calor útil — apagado, cinzas frias, decorativo, ou nunca esteve
     aceso (sem teste)
  1  só um vestígio morno — não amolece nada
  2  fogo fraco de cozinha — aquece comida, não metal
  3  fogueira comum — nem perto do necessário
  4  fogo forte de lareira — ainda insuficiente para conformar metal
  5  brasas contidas com algum sopro — no limite do que amolece ferro
  6  forja modesta acesa — dá para trabalhar, com esforço
  7  forja bem acesa — fogo próprio de oficina
  8  forja forte, fole trabalhando — metal cede sem drama
  9  forja excelente — calor estável e alto, exatamente o que o ofício pede
  10 fornalha — mais calor do que qualquer peça precisa (sem teste)
ATENÇÃO à diferença que esta régua existe para marcar: a fogueira que assa carne
NÃO funde metal. Um fogo que seria ótimo para cozinhar é 2 ou 3 aqui. Só sobe de
5 o que a descrição indicar como fogo DE TRABALHO — forja, fornalha, fole,
brasas contidas e sopradas. A nota é segredo do mundo: nunca o número na
narrativa; nota 0 faz a tentativa ser recusada."""

REGUA_FERRAMENTAL = """\
Régua do FERRAMENTAL (o quanto HÁ COM QUE TRABALHAR naquele lugar — bigorna,
martelo, tenaz, bancada, água para têmpera —, lido tanto na descrição do LUGAR
quanto na dos objetos presentes):
  0  não há nada com que trabalhar ali (sem teste)
  1  quase nada — um objeto solto que mal serviria
  2  muito precário — falta o essencial
  3  precário — dá para improvisar muito mal
  4  incompleto — falta peça importante do ferramental
  5  mínimo — o essencial, e nada além
  6  razoável — dá para trabalhar sem improviso
  7  oficina de verdade — o ferramental do ofício está ali
  8  oficina bem montada — nada falta
  9  oficina excelente — ferramental farto e cuidado
  10 oficina exemplar — tudo o que o ofício pode pedir (sem teste)
LEIA A DESCRIÇÃO DO LUGAR COM ATENÇÃO: numa oficina, a bigorna e o martelo
costumam estar escritos na prosa do ambiente, e não existir como objetos
separados. "A bigorna ocupa o centro, cercada de tenazes e martelos" é
ferramental farto, mesmo que nenhum objeto esteja listado. A nota é segredo do
mundo: nunca o número na narrativa; nota 0 faz a tentativa ser recusada."""

REGUA_DURACAO = """\
Régua da DURAÇÃO (o quanto esta peça, PELA sua complexidade, EXIGE de tempo e
cuidado — não a pressa de quem forja):
  0  quase nada — endireitar ou afiar algo simples
  1  muito rápido — uma peça tosca
  2  rápido — poucas batidas e está feito
  3  rápido — trabalho direto, sem acabamento
  4  comum-rápido — peça simples com acabamento mínimo
  5  comum — o trabalho normal de uma peça inteira
  6  comum-demorado — algumas etapas a mais
  7  demorado — exige têmpera, acabamento, atenção
  8  bem demorado — peça elaborada, várias etapas
  9  muito trabalhoso — quase uma obra
  10 obra — o máximo de etapas e cuidado que o ofício conhece
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a nota
num tempo real de trabalho — não é julgamento de sorte, é classificação."""

_SCHEMA_COMUM = """\
Responda SOMENTE com um objeto JSON, nada antes nem depois, nada de explicação,
EXATAMENTE com estas chaves (todas OBRIGATÓRIAS, mesmo que alguma nota seja 0):"""

_INSTRUCAO_TEXTOS = """\
A rolagem que decide o quanto a peça saiu boa só acontece DEPOIS desta resposta,
no Motor — você não sabe qual será o desfecho. Por isso, escreva um nome curto
para a peça e DUAS descriptions candidatas do resultado, ambas plausíveis a
partir dos MESMOS materiais reais: uma para a peça bem executada e outra para a
mesma peça saindo comprometida. Descreva SEMPRE o OBJETO — nunca a experiência de
forjar, nunca o que quem forjou sentiu (isso é interpretação exclusiva de quem
narra ao jogador depois)."""


def _regua_combinada(tipo: str) -> str:
    forjabilidade = (REGUA_FORJABILIDADE_ARMA if tipo == "arma"
                     else REGUA_FORJABILIDADE_ARMADURA)
    peca = "uma arma" if tipo == "arma" else "uma peça de armadura"
    extra_chave = ("" if tipo == "arma" else
                   ', "slot": "<parte do corpo que a peça protege>"')
    extra_nota = ("" if tipo == "arma" else
                  "\n\nO campo \"slot\" nomeia a PARTE DO CORPO que a peça protege "
                  "(por exemplo: cabeca, torso, bracos, pernas, pes, maos). É "
                  "classificação do que a peça é, não julgamento de valor.")
    return f"""\
Você vai julgar UMA tentativa de forjar {peca}, a partir de material bruto, sobre
uma fonte de calor e com o ferramental de um lugar. Leia as descrições REAIS
fornecidas com cuidado antes de responder — nunca invente detalhes que não estejam
nelas.

{forjabilidade}

{REGUA_QUALIDADE_MATERIAL}

{REGUA_FOGO_DE_FORJA}

{REGUA_FERRAMENTAL}

{REGUA_DURACAO}

{_INSTRUCAO_TEXTOS}{extra_nota}

{_SCHEMA_COMUM}

{{"forjabilidade": <inteiro 0-10>, "qualidade_material": <inteiro 0-10>, "fogo_de_forja": <inteiro 0-10>, "ferramental": <inteiro 0-10>, "duracao": <inteiro 0-10>, "nome": "<nome curto da peça>", "descricao_alta": "<texto factual da peça bem executada>", "descricao_baixa": "<texto factual da MESMA peça, comprometida — ainda É a peça, nunca sumida>"{extra_chave}}}"""


REGUA_FORJAR_ARMA = _regua_combinada("arma")
REGUA_FORJAR_ARMADURA = _regua_combinada("armadura")

_STR = {"type": "string"}
_NOTA = {"type": "integer", "minimum": 0, "maximum": 10}


@inworld("forja_ops_applied")
def _iw_forja(op):
    if op.get("concluido"):
        return "tirou da bigorna a peça terminada"
    if op.get("retomada"):
        return "voltou à bigorna e retomou o trabalho"
    return "começou a bater o metal no calor"


def _forjar(tipo: str, regua: str, name: str, args: dict, ctx) -> tuple[dict, bool]:
    """O corpo ÚNICO das duas tools. `tipo` ∈ {'arma', 'armadura'}.

    Dois caminhos, e a diferença entre eles é o coração desta spec:
    - RETOMADA (veio `peca`): reconhece a peça pelo arquivo e NÃO consulta o
      Árbitro em hipótese nenhuma. Custo zero de LLM, quantas vezes forem.
    - ABERTURA: uma chamada só, que congela tudo — notas, nome, os dois textos.
    """
    peca = args.get("peca")

    # --- RETOMADA: zero LLM (spec 052, FR-019) ----------------------------- #
    if peca:
        chave_cand = "forge_peca_arma" if tipo == "arma" else "forge_peca_armadura"
        if peca not in ctx.cand[chave_cand]:
            return ctx.err(f"'{peca}' não é uma peça em processo ao alcance desta "
                           "capacidade", "peca",
                           ctx.validos({i: ctx.items[i]
                                        for i in ctx.cand[chave_cand]})), False
        chave = (tipo, "peca", peca)
        if chave in ctx.forged_asked:
            return ctx.err("trabalhar nessa peça já foi tentado neste turno — o "
                           "desfecho sai na aplicação; NÃO repita: siga para outra "
                           "ação ou narrate"), False
        ctx.forged_asked.add(chave)
        base = {"peca": peca, "tipo": tipo}
        rej, rolled = ctx.apply_arbitrated("forja_ops", {**base, "retomada": True})
        if rej:
            return ctx.arb_deny(rolled, ("forge", tipo, peca), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False

    # --- ABERTURA ---------------------------------------------------------- #
    materiais = args.get("materiais")
    fonte_calor = args.get("fonte_calor")
    if not isinstance(materiais, list) or not materiais:
        return ctx.err("informe ao menos um material presente/na posse, ou uma "
                       "'peca' em processo para retomar"), False
    materiais = list(dict.fromkeys(materiais))  # sem duplicata, mantém ordem
    disponiveis = ctx.cand["forge_materiais"]
    for mid in materiais:
        if mid not in disponiveis:
            return ctx.err(f"'{mid}' não está ao alcance para forjar", "materiais",
                           ctx.validos({i: ctx.items[i] for i in disponiveis})), False
    fontes = ctx.cand["forge_fonte"]
    if fonte_calor not in fontes:
        # o LUGAR está no universo de fontes: montar o mapa só por `ctx.objects`
        # levantaria KeyError no id dele, matando a lista de válidos justamente na
        # recusa que existe para orientar quem errou.
        return ctx.err(f"'{fonte_calor}' não é uma fonte de calor presente",
                       "fonte_calor",
                       ctx.validos({o: ctx.objects.get(o)
                                    or {"name": (ctx.context.get("location") or {}).get("name") or o}
                                    for o in fontes})), False
    chave = (tipo, tuple(sorted(materiais)), fonte_calor)
    if chave in ctx.forged_asked:
        return ctx.err("forjar com esses materiais nessa fonte já foi tentado neste "
                       "turno — o desfecho sai na aplicação; NÃO repita: siga para "
                       "outra ação ou narrate"), False

    # CONTRATO DE ANÁLISE (spec 052, R3): as três entradas chegam de origens
    # diferentes de propósito. `lugar` NÃO é opcional — numa oficina escrita no
    # idioma deste projeto, é ali que a bigorna está.
    campos_texto = {"nome": "", "descricao_alta": "", "descricao_baixa": ""}
    if tipo == "armadura":
        campos_texto["slot"] = "torso"
    julgado = juizo.julgamento(
        ctx.ask(regua, json.dumps({
            "materiais": [ctx.describe(m) for m in materiais],
            "fonte_calor": ctx.describe(fonte_calor),
            "lugar": ctx.describe(ctx.place_id),
            "objetos_presentes": [ctx.describe(o) for o in sorted(ctx.objects)],
            "intencao": (args.get("intencao") or "").strip(),
        }, ensure_ascii=False, indent=2)),
        campos={"forjabilidade": 5, "qualidade_material": 5, "fogo_de_forja": 5,
                "ferramental": 5, "duracao": 5},
        texto_campos=campos_texto)
    ctx.forged_asked.add(chave)

    base = {"materiais": materiais, "fonte_calor": fonte_calor, "tipo": tipo}
    op = {**base}
    # Os GATES em ordem: o primeiro que zerar recusa, e os seguintes nem viajam.
    for gate in ("forjabilidade", "qualidade_material", "fogo_de_forja", "ferramental"):
        op[gate] = julgado[gate]
        if julgado[gate] == 0:
            rej, rolled = ctx.apply_arbitrated("forja_ops", op)
            if rej:
                return ctx.arb_deny(rolled, ("forge", tipo, fonte_calor), base, rej)
            return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False
    op.update({"duracao": julgado["duracao"], "nome": julgado["nome"],
               "descricao_alta": julgado["descricao_alta"],
               "descricao_baixa": julgado["descricao_baixa"]})
    if tipo == "armadura":
        op["slot"] = julgado.get("slot") or "torso"
    rej, rolled = ctx.apply_arbitrated("forja_ops", op)
    if rej:
        return ctx.arb_deny(rolled, ("forge", tipo, fonte_calor), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


_DESC_COMUM = (
    "SÃO DOIS USOS EXCLUSIVOS: para COMEÇAR uma peça, passe 'materiais' e "
    "'fonte_calor'; para CONTINUAR uma peça que já está no meio do trabalho, passe "
    "SÓ 'peca'. O trabalho leva tempo real e pode ser interrompido e retomado quantas "
    "vezes for preciso, até a peça ficar pronta. O mundo decide, lendo as descrições, "
    "se os materiais servem e o quanto valem, se o fogo dá conta de metal, e se há com "
    "que trabalhar no lugar. Material imprestável, fogo que não funde metal ou um lugar "
    "sem ferramental são recusados."
)

_PARAMS_COMUNS = {
    "materiais": {"type": "array", "items": {"type": "string"},
                  "description": "PARA COMEÇAR uma peça nova: o material bruto a "
                                 "consumir. Não use ao retomar uma peça já começada."},
    "fonte_calor": {"type": "string",
                    "description": "PARA COMEÇAR uma peça nova: o fogo de forja (um "
                                   "object presente, ou o próprio lugar). Não use ao "
                                   "retomar."},
    # MEDIDO (spec 052, T074): com `materiais`/`fonte_calor` em `required`, o modelo
    # preenchia os dois SEMPRE e abria uma peça nova em vez de retomar — 0 de 5. O
    # schema dizia que retomar era inválido. `required` ficou vazio (o corpo valida
    # os dois caminhos, com mensagem que ensina) e a descrição de cada parâmetro diz
    # a qual dos dois caminhos ele pertence.
    "peca": {"type": "string",
             "description": "PARA CONTINUAR uma peça já começada que está ao seu "
                            "alcance. Passe SOMENTE este parâmetro (sem 'materiais' "
                            "nem 'fonte_calor') para retomar o trabalho de onde parou."},
    "intencao": {"type": "string",
                 "description": "o que se pretende fazer, em palavras livres"},
    "forjabilidade": _NOTA, "qualidade_material": _NOTA, "fogo_de_forja": _NOTA,
    "ferramental": _NOTA, "duracao": _NOTA,
    "nome": _STR, "descricao_alta": _STR, "descricao_baixa": _STR,
}

_JUIZO_COMUM = ("forjabilidade", "qualidade_material", "fogo_de_forja", "ferramental",
                "duracao", "nome", "descricao_alta", "descricao_baixa")


FORGE_WEAPON = tool_spec(ToolSpec(
    names=("forge_weapon",),
    juizo=tuple((p, REGUA_FORJAR_ARMA) for p in _JUIZO_COMUM),
    description=("Forja uma ARMA a partir de material bruto, sobre uma fonte de calor e "
                 "com o ferramental de uma oficina. " + _DESC_COMUM),
    params=dict(_PARAMS_COMUNS),
    required=(),  # ver a nota em `_PARAMS_COMUNS`: os dois caminhos são exclusivos
    enum_sources={"materiais": "forge_materiais", "fonte_calor": "forge_fonte",
                  "peca": "forge_peca_arma"},
    omit_if_empty=("peca",),
    apply=lambda name, args, ctx: _forjar("arma", REGUA_FORJAR_ARMA, name, args, ctx),
))


FORGE_ARMOR = tool_spec(ToolSpec(
    names=("forge_armor",),
    juizo=tuple((p, REGUA_FORJAR_ARMADURA) for p in _JUIZO_COMUM + ("slot",)),
    description=("Forja uma PEÇA DE ARMADURA a partir de material bruto, sobre uma fonte "
                 "de calor e com o ferramental de uma oficina. " + _DESC_COMUM),
    params={**_PARAMS_COMUNS, "slot": _STR},
    required=(),  # ver a nota em `_PARAMS_COMUNS`: os dois caminhos são exclusivos
    enum_sources={"materiais": "forge_materiais", "fonte_calor": "forge_fonte",
                  "peca": "forge_peca_armadura"},
    omit_if_empty=("peca",),
    apply=lambda name, args, ctx: _forjar("armadura", REGUA_FORJAR_ARMADURA, name, args, ctx),
))
