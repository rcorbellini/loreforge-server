"""O Motor / registro — a tabela de despacho canal→handler (spec 025, 021 Fase C).

NÍVEL 0: não importa nenhum executor (nível 1), para não criar ciclo. Cada tool
REGISTRA o próprio handler AUTO-CONTIDO no seu módulo (`@registro.handler("canal")`),
e o despachante (`turno.apply_op`) só CONSULTA. É o Open/Closed do SOLID: acrescentar
uma tool é registrar um handler; nunca editar o despachante.

Um handler tem a assinatura uniforme:
    handler(character_id, actor_folder, res, rolls) -> (applied, rejected, created)
onde `res` é a mini-resolução {canal: [op], ...contexto...}. Toda a heterogeneidade
(a fase do lock, a cena que o recorder precisa, o travel sem rolls) é absorvida DENTRO
do handler — o despachante fica uniforme.
"""
from __future__ import annotations

from dataclasses import dataclass, field

_HANDLERS: dict = {}


def handler(canal: str):
    """Decorator: registra `fn` como o handler do `canal`. Roda no import do módulo
    da tool (por isso importar o pacote já popula a tabela)."""
    def deco(fn):
        _HANDLERS[canal] = fn
        return fn
    return deco


def get(canal: str):
    """O handler do canal, ou None se não há tool para ele."""
    return _HANDLERS.get(canal)


# --------------------------------------------------------------------------- #
# A DECLARAÇÃO da tool (spec 038, L2) — o `ToolSpec`, co-localizado com o corpo.
#
# É o dado de que os mecanismos genéricos do Árbitro DERIVAM em vez de repetir à
# mão: o builder de FACE (`arbiter/face.py`) monta o manifest do turno a partir de
# `params`+`enum_sources`; o despacho genérico roda o corpo (`apply`). Vive no
# MOTOR (nível 0) por ser DADO — o corpo é um callable que opera sobre o `ctx` do
# turno (duck-typed), mas registro.py NÃO importa o Árbitro: a fronteira segue
# intacta (o Árbitro é que LÊ este registro). Um `.md` novo não muda; uma tool
# nova é UM lugar (este descritor + o corpo ao lado + a primitiva, se nova).
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ToolSpec:
    """Auto-declaração de uma tool (data-model.md). `enum_sources[param]` é a chave
    de `scene_candidates` (str) OU um callable(scene)->list que compõe o enum;
    `params` é o schema JSON de cada propriedade SEM o `enum` (que o builder injeta);
    `description` é str OU callable(scene)->str (a FACE às vezes cita a cena, ex.: o
    id do lugar); `apply(name, args, ctx)->(result, done)` é o CORPO (o antigo
    `tool_X`), co-localizado. Um `ToolSpec` gera N entradas de FACE (open/close,
    buy/trade) via `names`, um só corpo."""
    names: tuple[str, ...]
    description: object                                # str | callable(scene) -> str
    params: dict = field(default_factory=dict)         # {param: schema-sem-enum}
    required: tuple[str, ...] = ()
    enum_sources: dict = field(default_factory=dict)   # {param: key-str | callable}
    omit_if_empty: tuple[str, ...] = ()                # param OPCIONAL some se enum vazio
    apply: object = None                               # callable(name, args, ctx)
    # spec 043 — O JUÍZO: (param, régua-em-prosa). Declarar isto diz DUAS coisas de
    # uma vez, e é por isso que é UM campo e não dois: que a capacidade tem desfecho
    # lido de um texto, e QUAL parâmetro esse texto preenche.
    #
    # A classificação do parâmetro CAI daqui — não existe campo de visibilidade em
    # lugar nenhum (Princípio XI, e o veredito "Estruturado vs Descritivo" da spec).
    # Um rótulo `classe: juizo` paralelo à régua seria uma segunda fonte de verdade
    # sobre o mesmo fato, e no dia em que divergisse venceria calado — deixando uma
    # nota descer à Mente, que é exatamente o que o Princípio IX existe para impedir.
    #
    # Consequências, todas derivadas:
    #   - o param SOME da face (ninguém de fora o preenche — nem a Mente, nem o Árbitro);
    #   - o corpo pede a nota ao mundo (`ctx.ask` + a régua que mora aqui do lado);
    #   - valor que chegue de fora é DESCARTADO, sem erro ao jogador.
    juizo: tuple = ()                                  # () | (param, REGUA)
    # spec 043 — A CANETA DO MUNDO. Capacidade que fixa o PESO e a DURAÇÃO do que fica
    # gravado, ou que escreve estado direto. Não é agência de personagem: é o mundo
    # registrando. Fica INTEIRA fora do que desce (Princípio IX, classe 2).
    #
    # Por que aqui é DECLARAÇÃO e não derivação — ao contrário do `juizo`: não existe
    # nenhum outro fato no código de onde isto caia. O `juizo` se deriva porque a
    # RÉGUA já existe e diz tudo; "esta capacidade é a caneta do mundo" não tem
    # equivalente. Declarar o que não se pode derivar não é preguiça; duplicar o que
    # já existe é que seria (Princípio XI).
    interna: bool = False
    # spec 031/item 50 — A CAPACIDADE DE QUEM DORME. Diz DUAS coisas de uma vez, e por
    # isso é UM booleano e não dois: (a) esta capacidade só existe enquanto o ator
    # dorme; (b) enquanto ele dorme, SÓ as capacidades assim existem.
    #
    # Por que aqui e não no Árbitro: o gate de descanso escrevia a face de `sleep` À
    # MÃO dentro de `build_tools` — um dicionário de manifest hardcoded no meio do
    # montador. Enquanto era UMA tool alternadora dava para fingir que era detalhe;
    # partindo em `sleep`/`wake_up`, a face de acordar passaria a existir em dois
    # lugares (o registro e aquele dicionário), e no dia em que divergissem venceria a
    # cópia. Com o fato declarado aqui, o gate volta a ser o que devia: um filtro de
    # uma linha que não conhece nome de tool nenhum (Open/Closed, item 38).
    only_while_resting: bool = False


_TOOL_SPECS: dict = {}


def tool_spec(spec: ToolSpec):
    """Registra a DECLARAÇÃO (um por tool, N nomes). Roda no import do módulo da
    tool — importar o domínio já popula o registro, igual ao `@handler`."""
    for n in spec.names:
        _TOOL_SPECS[n] = spec
    return spec


def specs() -> dict:
    """O registro de `ToolSpec` por nome (o Árbitro deriva FACE/despacho daqui)."""
    return _TOOL_SPECS


def get_spec(name: str):
    return _TOOL_SPECS.get(name)


# --------------------------------------------------------------------------- #
# A FRASE in-world do canal (spec 038, T041) — co-localizada com a tool.
#
# `app.inworld_effects` DEIXA de repetir, bloco a bloco, o que cada canal narra:
# cada domínio registra aqui o construtor da sua frase, e o app só itera. Chave = a
# CHAVE do outcome que o construtor lê (`<canal>_applied`, ou `applied` p/ mutações).
# `fn(op) -> str | None` (None = pula esta op). A ORDEM das frases é irrelevante — os
# consumidores checam PERTINÊNCIA (substring/`any`), nunca sequência.
# --------------------------------------------------------------------------- #

_INWORLD: dict = {}


def inworld(outcome_key: str):
    """Registra o construtor da frase in-world de um canal (spec 038, T041)."""
    def deco(fn):
        _INWORLD[outcome_key] = fn
        return fn
    return deco


def inworld_phrases() -> dict:
    """{chave-do-outcome: fn(op)->str|None} — o app itera para narrar o que ACONTECEU."""
    return _INWORLD


# --------------------------------------------------------------------------- #
# LANE PARALELA DE CONSULTA (spec 040) — read-only, aditiva.
#
# NÃO toca `ToolSpec`/`tool_spec`/`_TOOL_SPECS`/`@handler` acima (o caminho de
# MUTAÇÃO do Árbitro fica intocado — restrição não-negociável). Uma consulta é
# uma capacidade de LEITURA que a Mente PUXA (via `/api/consult`) e que o Árbitro
# pode reusar como juízo (dois gatilhos, `loreforge-arbiter-boundary` regra 4). O
# corpo (`query`) devolve PROSA/rótulo — nunca número (Princípios V/IX). Auto-
# declarada e co-localizada com o corpo, igual ao `tool_spec`: importar o módulo
# popula o registro.
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class ConsultSpec:
    """Auto-declaração de uma tool de CONSULTA (leitura). `query(character_id,
    args)->dict` é o corpo, que devolve o payload de prosa. `params` é o schema
    JSON dos argumentos (o client deriva o manifest daqui)."""
    name: str
    description: str
    params: dict = field(default_factory=dict)
    query: object = None                               # callable(character_id, args) -> dict


_CONSULT_SPECS: dict = {}


def consult_spec(spec: ConsultSpec):
    """Registra a DECLARAÇÃO de uma consulta (roda no import do módulo do corpo)."""
    _CONSULT_SPECS[spec.name] = spec
    return spec


def consult_specs() -> dict:
    """{name: ConsultSpec} — o despacho `/api/consult` e o Árbitro leem daqui."""
    return _CONSULT_SPECS
