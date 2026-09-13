"""A FACE EXPOSTA — o que o personagem enxerga que pode tentar AQUI (spec 043).

O problema que isto resolve: o personagem não sabia o que sabe fazer. A Mente escrevia
prosa às cegas, ancorada num livro de 13 frases escrito à mão no client que não casava
com capacidade nenhuma — e 77,6% dos turnos não mudavam nada no mundo (baseline da
spec 039). A face é o mundo respondendo "isto é o que cabe agora, com estes alvos".

NÃO é um menu para o jogador. É contexto para A MENTE. Um menu de ações chamáveis
renderizado na tela é violação do Princípio V, e a fronteira entre as duas coisas é
o que a emenda constitucional v2.0.0 cravou.

O QUE DESCE: ESCOLHA e VOZ. O que NÃO desce, e por quê:
  - o parâmetro de JUÍZO — some por construção, no `build_face`, porque a capacidade
    o declara (`juizo=`) e ela mesma pede a nota ao mundo;
  - a capacidade INTERNA (`interna=True`) — a caneta do mundo não é agência de ninguém.

POR QUE MORA AQUI e não em `motor/`: a face precisa da CENA (`_scene_index` /
`scene_candidates`), que ainda vive em `arbiter.py`. O Motor não importa o Árbitro —
essa fronteira é o que mantém 43 fases de selftest rodando sem modelo. Mover a cena
para o Motor é o refactor certo e é trabalho à parte; até lá este módulo fica na raiz
do server, no mesmo nível de `arbiter.py` e `openapi.py`, podendo ver os dois.
"""
from __future__ import annotations

import arbiter
import motor


# OS ENUMS QUE FICAM NA FACE EXPOSTA.
#
# O critério não é o tipo do dado, é a ORIGEM da informação:
#   · lista da CENA (itens, pessoas, objetos, rotas) -> SAI. A Mente já vê tudo isso
#     no contexto; o enum é a segunda cópia, e a cópia é que custa.
#   · subconjunto CALCULADO (quem está caído, o que dá para empunhar, que trabalho
#     está em processo) -> FICA. O contexto não diz isso de um jeito que ela use: o
#     enum é a ÚNICA fonte, e ali ele INFORMA em vez de restringir.
#   · vocabulário FECHADO (ativa/concluida/abandonada) -> FICA. Não é id.
#   · lugar que ele SABE alcançar -> FICA. Deriva de memória de rota.
#
# ESTA LISTA VEIO DO CLIENTE (item 77, 2026-09-11). Ela morava em `mente.js`
# (`_ENUM_QUE_FICA`): 17 pares `tool:parâmetro` DO MUNDO, mantidos à mão num
# arquivo que não sabe quando uma tool nasce ou muda de parâmetro — acoplamento que
# apodrecia calado, e apodreceu: `accuse:memoria_id` não estava lá, contra o que o
# próprio comentário afirmava. Aqui ela fica ao lado de quem declara os parâmetros.
#
# E o enum SAIR DAQUI não enfraquece validação nenhuma: quem valida é o Motor, pelo
# manifesto de `arbiter.build_tools`, que continua inteiro. É a separação que a
# própria docstring de `mcp_core.input_schema` já defendia — "o que o schema NÃO
# entrega é o CONTEÚDO do enum".
_ENUM_QUE_FICA = frozenset({
    "heal:alvo", "butcher:alvo",                    # subconjunto calculado
    "write:instrumento", "sing:instrumento",        # o que dá para empunhar
    "craft:peca", "forge_weapon:peca", "forge_armor:peca", "cook:peca",
    "brew:peca",                                    # trabalho em processo
    "set_intention:status", "give:intention_id", "trade:intention_id",
    "promise:intention_id",                         # vocabulário fechado / intenção
    "travel_to:destino", "ask_about:sobre_lugar",   # lugar que ele sabe alcançar
    "learn_routes:rotas",                           # rotas do MUNDO, não da cena
})

# A frase que substitui o enum. Curta de propósito: responde "como eu chamo?", que é
# a única pergunta que o enum respondia de útil, e nada além disso.
DICA_DE_ALVO = "o NOME daquilo, como aparece na cena"


def _alvos(props: dict, tool: str = "") -> dict:
    """Os alvos possíveis por parâmetro — só o que EXISTE na cena, agora.

    Vem do enum que o próprio manifesto do turno já monta: a face não recalcula
    candidatos, senão haveria duas respostas possíveis para "quem está aqui".

    Lista de CENA não desce (ver `_ENUM_QUE_FICA`): ela vira `DICA_DE_ALVO` em
    `mcp_core.input_schema`, e A Mente aponta por nome.
    """
    out = {}
    for nome, schema in (props or {}).items():
        enum = schema.get("enum")
        if enum is None and schema.get("type") == "array":
            enum = (schema.get("items") or {}).get("enum")
        if enum and f"{tool}:{nome}" in _ENUM_QUE_FICA:
            out[nome] = list(enum)
    return out


def _sem_enum(props: dict, tool: str) -> dict:
    """Os parâmetros que TINHAM enum de cena, com os ids que o manifesto validou.

    O enum carregava DUAS coisas, e só uma prestava:

      · RESTRINGIR o modelo — medido inútil (spec 060: id fora do enum saiu 4/5),
        caro (35% do bloco) e nocivo (paralisia no ambíguo, substituição silenciosa).
      · ALIMENTAR A RESOLUÇÃO no cliente — o que permite A Mente apontar "Nerissa,
        a Boticária" e o conector converter para o id. Isso presta, e muito: medido
        em 14 de 15 chamadas reais, inclusive numa em que o modelo abreviou o nome.

    Então elas se separam. A lista sai do `inputSchema` (o modelo não a vê mais) e
    desce em `annotations.byName`, que é metadado de tool: o conector lê, o runtime
    de tool-calling não põe no prompt.

    ISSO NÃO É O ENUM DE VOLTA POR OUTRA PORTA. A diferença é quem lê: antes ela ia
    ao MODELO, competindo com a cena e custando tokens; agora vai ao CONECTOR, que é
    quem precisava dela desde sempre. E continua sem autoridade — quem valida é o
    Motor (Princípio III), como a docstring de `mcp_core.input_schema` já dizia.
    """
    fora = {}
    for nome, schema in (props or {}).items():
        enum = schema.get("enum")
        if enum is None and schema.get("type") == "array":
            enum = (schema.get("items") or {}).get("enum")
        if enum and f"{tool}:{nome}" not in _ENUM_QUE_FICA:
            fora[nome] = list(enum)
    return fora


def build(context: dict) -> list[dict]:
    """A face da cena para A Mente. Lista vazia é resposta legítima (caído/morto).

    Deriva do MESMO manifesto que a engine usa (`arbiter.build_tools`) — não é uma
    segunda montagem. Isso importa: se a face divergisse do manifesto, a Mente
    proporia coisas que o mundo recusaria, e o erro seria invisível dos dois lados.

    Os gates já vêm de lá e são preservados: capacidade sem candidato para um alvo
    obrigatório não aparece; capacidade fora do manifesto de ativação do mundo não
    aparece; quem dorme só vê a capacidade de acordar.
    """
    caido = _gate_de_caido(context)
    if caido is not None:
        return caido
    exposta = []
    for t in arbiter.build_tools(context):
        spec = motor.registro.get_spec(t["name"])
        if spec is not None and spec.interna:
            continue                      # a caneta do mundo não desce (classe 2)
        params = (t.get("parameters") or {}).get("properties") or {}
        exposta.append({
            "nome": t["name"],
            "descricao": t.get("description") or "",
            "alvos": _alvos(params, t["name"]),
            "por_nome": _sem_enum(params, t["name"]),
            "exige": list((t.get("parameters") or {}).get("required") or []),
            "consulta": False,
        })
    # QUEM DORME NÃO PERGUNTA. O gate de descanso do manifesto é um early-return que
    # deixa só a capacidade de acordar; se a consulta entrasse por fora dele, um dormindo
    # checaria a hora. spec 067: o contexto ENTREGA o booleano derivado — antes esta
    # linha remontava um `fm` falso a partir do `status` cru só para chamar
    # `fisica.is_resting`, e o cronômetro (`descansando_desde`) saiu do contrato por ser
    # maquinário do Motor. A definição segue única; muda só de onde a resposta vem.
    if not (context.get("self") or {}).get("is_resting"):
        exposta.extend(_consultas())
    return sorted(exposta, key=lambda c: c["nome"])


def _gate_de_caido(context: dict) -> list[dict] | None:
    """O que desce a quem CAIU — `None` quando ele está de pé (a face segue normal).

    A autoridade sobre agir caído sempre foi do servidor (`_refuse_if_down`, em
    `app.py`): nenhuma ação em nome de um caído chega ao Árbitro ou ao Motor. Mas o
    "não OFERECER" ficou delegado ao client, como cortesia — e o client que existe
    hoje é A Mente por MCP, que não faz cortesia nenhuma. Ela recebia as 23
    capacidades de um MORTO, propunha `attack`, e o mundo respondia "está morto".

    O custo não era teórico: uma vez inteira queimada numa chamada de modelo cujo
    desfecho o servidor já conhecia antes de perguntar. E era incoerente com o gate
    de sono, que já esconde o vocabulário de quem não pode agir — morrer é condição
    mais forte que dormir — e com `_observer_can_look`, que crava a regra irmã na
    percepção ("não há como observar enquanto se está caído").

    A distinção entre os dois estados é a que o próprio gate de recusa já faz:

      MORTO         — NADA. Não age, não pensa, não pergunta as horas.
      INCAPACITADO  — só a lane de CONSULTA. Ele ainda é alguém: lembra, sabe que
                      anoiteceu, e A Mente narra o desamparo. Sair dali depende de
                      OUTRA pessoa (`heal`, `carry`), nunca de uma escolha dele, e
                      por isso nenhuma capacidade de mutação faz sentido aqui.
    """
    fm = {"status": (context.get("self") or {}).get("status") or {}}
    # `is_down` é a ÚNICA definição de "caiu" no código, e ela GUARDA contra
    # `conditions` que não é lista (`isinstance(conds, list) else []`). Escrever o
    # teste à mão aqui era um furo real, não hipotético: há personagem neste mundo com
    # `conditions` gravado como STRING, e aí `motor.DEAD in conds` deixa de ser
    # "está na lista" e passa a ser BUSCA DE SUBSTRING — uma condição escrita como
    # "não está morto de cansaço" apagaria a face de alguém vivo e de pé.
    if not motor.is_down(fm):
        return None
    conds = (fm["status"].get("conditions")
             if isinstance(fm["status"].get("conditions"), list) else [])
    # morto vence incapacitado (quem morreu carrega as duas condições), então a
    # verdade mais forte decide primeiro — mesma ordem de `_refuse_if_down`.
    if motor.DEAD in conds:
        return []
    return sorted(_consultas(), key=lambda c: c["nome"])


def _consultas() -> list[dict]:
    """A LANE DE CONSULTA na face (spec 040, lane paralela) — o que a Mente pode
    PERGUNTAR ao mundo antes de decidir.

    Por que isto precisou de código próprio: `arbiter.build_tools` itera
    `motor.registro.specs()`, que é o registro de MUTAÇÃO. `consult_specs()` é um
    dicionário separado, e nenhum ponto da cadeia
    `get_context -> face.build -> mcp_core.tools()` o lia — a consulta existia no
    Motor, era servida por `/api/consult`, e simplesmente não chegava à Mente.
    Uma intenção condicional ("ao fim do dia", "se houve furto") era portanto
    inverificável: o personagem agia sobre o palpite. Ver a análise da Hulda.

    NÃO passa pelo manifesto de ativação (`motor.ativacao`) de propósito. Aquele
    filtro é `todas - desativadas` sobre `set(registro.specs())`, onde nome de
    consulta não existe: qualquer mundo com manifesto declarado apagaria as duas
    consultas sem nunca as ter citado. Perguntar não muda o mundo, então não há o
    que um mundo precise desligar aqui.

    Sem gate de cena: `consultar_memoria` lê a própria memória e
    `consultar_momento` lê o relógio — nenhuma das duas depende de quem está
    presente. Daí `alvos` vazio (não há enum de cena a impor) e `exige` = todos os
    params declarados: uma ConsultSpec só declara o que de fato precisa.
    """
    return [{
        "nome": spec.name,
        "descricao": spec.description or "",
        "alvos": {},
        "exige": list(spec.params or {}),
        "consulta": True,
    } for spec in motor.consult_specs().values()]
