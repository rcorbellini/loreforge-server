"""DECLARAÇÃO + CORPO da tool `craft` (spec 057).

`craft` cria item, object OU location a partir do que a cena real oferece —
generaliza `forja`/`cozinha`/`botica` num único corpo, sem receita fixa: a
narração livre é o único insumo além dos materiais apontados; o Árbitro decide,
numa chamada só, se é viável, o quanto vale, que TIPO de coisa nasce, e o tempo
que exige.

UMA chamada ao Árbitro, na ABERTURA, e só — retomada é aritmética pura, molde
idêntico ao de `forge_weapon`/`forge_armor` (spec 052).

Por que `materiais` é PARÂMETRO explícito, e não lido livremente da cena
(desvio da Decisão D original da spec, corrigido nesta implementação): TODA
tool julgada do projeto (`forge_*`, `cook`, `brew`) já usa este padrão —
apontar o que se usa não é "receita fixa" (nenhum item declara o que serve;
quem aponta é quem chama a tool, contra o enum real da cena). O que a spec
queria evitar — um schema de receita DECLARADO no mundo — continua evitado. O
que NÃO tem parâmetro, herdado de verdade do gate de FERRAMENTAL de `forja`, é
a leitura do LUGAR/objetos presentes: a viabilidade ambiental.
"""
from __future__ import annotations

import json

from .. import juizo
from ..registro import ToolSpec, inworld, tool_spec
from .primitivas import sanear_tamanho, sanear_tipo

REGUA_CRAFT = """\
Você vai julgar UMA tentativa de CRIAR algo — item, objeto fixo ou até um
pequeno lugar —, a partir de materiais escolhidos, do que o lugar oferece, e
da narração livre de quem tenta. Não existe lista de receitas: julgue SÓ pelo
que as descrições REAIS dizem — narração e materiais são a fonte; o lugar
empresta ambiente e ferramentas, não o vocabulário do que nasce. Nunca invente
detalhe que não esteja nelas.

Régua da VIABILIDADE (o quanto os materiais + o lugar + a narração, juntos,
sustentam o que se pretende criar — não o quanto ficaria bom):
  0  impossível — nada ali sustenta a ideia (sem material nenhum aproveitável,
     ou o pedido contraria a física do que existe) (sem teste)
  1  quase certamente não — nada ali sugere aquilo
  2  muito improvável — falta quase tudo
  3  duvidoso — há algo aproveitável, mas pouco
  4  incerto — daria pra tentar, sem nenhuma lógica clara
  5  ambíguo — a descrição não decide se aquilo sai ou não
  6  provável — o material e o lugar sustentam, combinação plausível
  7  bastante provável — reúne o que a ideia pede
  8  bom — material e lugar próprios para isso, sem dúvida
  9  muito bom — quase pede para virar aquilo
  10 evidente — é exatamente o que se faz com aquilo ali (sem teste)
Um material que NÃO serve, misturado com o que serve, deve DERRUBAR a nota —
ele não desaparece da leitura por estar acompanhado. A nota é segredo do
mundo: nunca o número na narrativa; nota 0 recusa a tentativa. SEM material
nenhum apontado, a nota normalmente fica baixa (1-3), a não ser que a própria
narração descreva usar algo que já está na mão de quem tenta.

Régua da DURAÇÃO (o quanto o que se pretende criar, PELA sua complexidade,
exige de tempo — não a pressa de quem tenta):
  0  quase nada — um gesto, segundos
  1-2 muito rápido — poucos minutos
  3-4 rápido — cabe numa pausa curta
  5-6 comum — leva uma boa sessão de trabalho
  7-8 demorado — exige etapas, várias sessões
  9  muito trabalhoso — obra de dias
  10 obra — o máximo de tempo e cuidado imaginável para algo feito à mão
A nota é segredo do mundo: nunca o número na narrativa. O Motor converte a
nota num tempo real.

Régua do TAMANHO físico do que nasce (mesma escala do resto do mundo, do
menor ao maior): "PP", "P", "M", "G", "XG", "XXG", "XXXG", "XXXXG", "XXXXXG".
Calibre pelo que já existe: uma moeda ou um diário são PP; uma bolsa de ervas,
uma vela ou uma capa são P; uma corneta ou uma trouxa de roupa são M; um baú
pequeno é G. Coisa feita à mão, por uma pessoa só, numa sessão: quase sempre
PP, P ou M — G já é incomum, e acima disso não é craft manual.

Classifique também "tipo" — EXATAMENTE um destes três: "item" (dá pra
carregar), "object" (fica fixo no lugar), "location" (um lugar novo e pequeno,
dentro de onde já se está). Na dúvida entre item e object: dá pra carregar?
Então é item.

NÃO julgue ofício, atributo do corpo, nem se cabe na mão — isso o Motor deriva
sozinho do "tamanho" e do "tipo".

Escreva um nome curto para o que nasce e DUAS descriptions candidatas, ambas
plausíveis a partir dos MESMOS materiais: uma para o resultado bem executado,
outra para o mesmo resultado saindo malfeito. As duas PRECISAM ser claramente
distinguíveis por um leitor que não sabe qual é qual — "descricao_baixa" NÃO é
uma versão levemente pior de "descricao_alta": é a MESMA coisa com um DEFEITO
CONCRETO e visível — torta, rachada, mal encaixada, incompleta, instável, com
uma junta solta, algo que falha ou range. Descreva SEMPRE A COISA — nunca a
experiência de quem a fez.

Responda SOMENTE com um objeto JSON, nada antes nem depois, EXATAMENTE com
estas chaves (todas obrigatórias):
{"viabilidade": <inteiro 0-10>, "duracao": <inteiro 0-10>, "tipo": "<item|object|location>", "tamanho": "<PP|P|M|G|XG|XXG|XXXG|XXXXG|XXXXXG>", "nome": "<nome curto>", "descricao_alta": "<texto factual do resultado bem executado>", "descricao_baixa": "<texto factual do MESMO resultado, comprometido — ainda É a coisa, nunca sumida>"}"""

_JUIZO_CAMPOS = ("viabilidade", "duracao", "tipo", "tamanho",
                 "nome", "descricao_alta", "descricao_baixa")


@inworld("craft_ops_applied")
def _iw_craft(op):
    if op.get("concluido"):
        return "terminou o que estava fazendo"
    if op.get("retomada"):
        return "voltou ao que estava fazendo antes"
    return "começou a criar algo"


def _craft(name: str, args: dict, ctx) -> tuple[dict, bool]:
    """O corpo de `craft`. Dois caminhos, molde EXATO de `_forjar` (spec 052):

    - RETOMADA (veio `peca`): reconhece a peça pelo arquivo, zero LLM.
    - ABERTURA: uma chamada só, que congela tudo — nota, tipo, domínio,
      atributo, duração, nome, os dois textos.
    """
    peca = args.get("peca")
    narracao = (args.get("narracao") or "").strip()

    # --- RETOMADA: zero LLM ------------------------------------------------ #
    if peca:
        if peca not in ctx.cand["craft_pecas_abertas"]:
            return ctx.err(f"'{peca}' não é um trabalho seu em processo ao alcance",
                           "peca",
                           ctx.validos({i: ctx.items[i]
                                        for i in ctx.cand["craft_pecas_abertas"]})), False
        chave = ("craft", "retomar", peca)
        if chave in ctx.craft_asked:
            return ctx.err("retomar esse trabalho já foi tentado neste turno — o "
                           "desfecho sai na aplicação; NÃO repita: siga para outra "
                           "ação ou narrate"), False
        ctx.craft_asked.add(chave)
        base = {"peca": peca, "narracao": narracao}
        rej, rolled = ctx.apply_arbitrated("craft_ops", {**base, "retomada": True})
        if rej:
            return ctx.arb_deny(rolled, ("craft", "retomar", peca), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False

    # --- ABERTURA ------------------------------------------------------------ #
    if not narracao:
        return ctx.err("descreva o que está tentando criar em 'narracao', ou "
                       "informe 'peca' para retomar um trabalho em processo"), False
    materiais = list(dict.fromkeys(args.get("materiais") or []))
    disponiveis = ctx.cand["craft_materiais"]
    for mid in materiais:
        if mid not in disponiveis:
            return ctx.err(f"'{mid}' não está ao alcance para usar", "materiais",
                           ctx.validos({i: ctx.items[i] for i in disponiveis})), False
    chave = ("craft", "abrir", narracao, tuple(sorted(materiais)))
    if chave in ctx.craft_asked:
        return ctx.err("essa tentativa já foi feita neste turno — o desfecho sai "
                       "na aplicação; NÃO repita: siga para outra ação ou narrate"), False

    julgado = juizo.julgamento(
        ctx.ask(REGUA_CRAFT, json.dumps({
            "narracao": narracao,
            "materiais": [ctx.describe(m) for m in materiais],
            "lugar": ctx.describe(ctx.place_id),
            "objetos_presentes": [ctx.describe(o) for o in sorted(ctx.objects)],
        }, ensure_ascii=False, indent=2)),
        campos={"viabilidade": 5, "duracao": 5},
        texto_campos={"tipo": "item", "tamanho": "P", "nome": "",
                     "descricao_alta": "", "descricao_baixa": ""})
    ctx.craft_asked.add(chave)

    base = {"materiais": materiais, "narracao": narracao}
    op = {**base, "viabilidade": julgado["viabilidade"]}
    if julgado["viabilidade"] <= 0:
        rej, rolled = ctx.apply_arbitrated("craft_ops", op)
        if rej:
            return ctx.arb_deny(rolled, ("craft", "abrir", narracao), base, rej)
        return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False

    op.update({
        "duracao": julgado["duracao"],
        "tipo": sanear_tipo(julgado["tipo"]),
        "tamanho": sanear_tamanho(julgado["tamanho"]),
        "nome": julgado["nome"], "descricao_alta": julgado["descricao_alta"],
        "descricao_baixa": julgado["descricao_baixa"],
    })
    rej, rolled = ctx.apply_arbitrated("craft_ops", op)
    if rej:
        return ctx.arb_deny(rolled, ("craft", "abrir", narracao), base, rej)
    return {"ok": True, "aplicado": {"nota": "o desfecho sai na aplicação"}}, False


CRAFT = tool_spec(ToolSpec(
    names=("craft",),
    juizo=tuple((p, REGUA_CRAFT) for p in _JUIZO_CAMPOS),
    description=(
        "Cria algo novo — item, objeto fixo ou até um pequeno lugar — a partir "
        "do que a cena oferece e do que o personagem narra querer fazer. SÃO "
        "DOIS USOS EXCLUSIVOS: para COMEÇAR, passe 'narracao' (e, se usar "
        "material, 'materiais'); para CONTINUAR um trabalho já em processo, "
        "passe 'narracao' (o que faz nesta sessão) e 'peca'. Sem lista de "
        "receitas: narre a intenção. Os materiais e o lugar contam. O "
        "trabalho pode levar tempo "
        "real e ser retomado quantas vezes forem precisas."
    ),
    params={
        "narracao": {"type": "string",
                     "description": "o que o personagem está tentando criar "
                                    "(ao retomar: o que está fazendo nesta "
                                    "sessão)"},
        "materiais": {"type": "array", "items": {"type": "string"},
                      "description": "materiais alcançáveis a usar na criação "
                                     "(opcional — não use ao retomar)"},
        "peca": {"type": "string",
                 "description": "id de um trabalho já em processo, ao alcance, "
                                "para retomar de onde parou"},
        "viabilidade": {"type": "integer", "minimum": 0, "maximum": 10},
        "duracao": {"type": "integer", "minimum": 0, "maximum": 10},
        "tipo": {"type": "string"}, "tamanho": {"type": "string"},
        "nome": {"type": "string"},
        "descricao_alta": {"type": "string"}, "descricao_baixa": {"type": "string"},
    },
    required=("narracao",),
    enum_sources={"materiais": "craft_materiais", "peca": "craft_pecas_abertas"},
    omit_if_empty=("peca",),
    apply=lambda name, args, ctx: _craft(name, args, ctx),
))
