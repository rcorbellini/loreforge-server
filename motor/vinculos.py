"""VÍNCULO — o fato declarado, e a primeira relação de FATO entre entidades (spec 066).

Este módulo nasce SEPARADO de `memoria/` de propósito, e a separação é o assunto da spec
inteira. Antes dela, todas as oito relações do mundo eram crença derivada de memória:

    dono(entidade, personagem)          knows_route(character, route)
    dono_reconhecido(entidade, pers.)   recognizes_route(character, route)
    has_trauma_from(quem, agressor)     familiarity_with(character, other)
    remembered_about(quem, sobre)       sentiment_toward(character, target)

Todas com `(observador, alvo)` na chave. O vínculo não é assim:

    AFETO   é escalar, acumula por repetição, decai, e tem TETO.
    VÍNCULO é discreto, declarado, não acumula e não decai.

Nenhuma quantidade de memória positiva atravessa de "melhor amigo" para "irmão" — e o
irmão que se odeia (vínculo positivo + afeto negativo) é a célula que um eixo só destrói.
Juntar os dois num módulo reabriria exatamente a conflação que a spec existe para desfazer.

O QUE ESTE MÓDULO NÃO FAZ, e é decisão, não omissão:
  - não escreve. `bonds` é editorial e imutável nesta fatia (FR-005); casamento,
    nascimento, adoção e renegar são atos futuros, e quando vierem nenhum lado poderá
    criar vínculo na conta do outro (`server-never-owns-character-agency`).
  - não soma em afeto nem em DC (FR-017, FR-018). O vínculo desce como rótulo; quem
    decide o peso dele na cena é o Árbitro (a nota) e A Mente (a decisão).
  - não interpreta o rótulo. `label` é texto opaco — é o que mata o enum de parentesco
    antes dele nascer e deixa caber "padrinho", "meia-irmã", "terra natal".
"""
from __future__ import annotations

from . import indice, io

# O nome da aresta no índice. Registrado em `indice._ARESTAS_FM` como
# ("vinculo", "target") — lista de mapas, id extraído por `target`.
ARESTA = "vinculo"


def _bonds_crus(character_id: str) -> list[dict]:
    """O bloco `bonds` do personagem, ou lista vazia. Sem sanear."""
    pasta = io.find_character_folder(character_id)
    if pasta is None:
        return []
    fm, _ = io.read_doc(pasta / "character.md")
    bonds = fm.get("bonds")
    return bonds if isinstance(bonds, list) else []


def bonds_of(character_id: str) -> list[dict]:
    """Os vínculos que ESTE personagem declarou, saneados.

    Devolve `[{"target": id, "label": texto}, ...]`, já sem entrada malformada, sem
    auto-referência e sem alvo repetido — o validador recusa essas na escrita, mas a
    leitura não pode depender disso: mundo editado à mão existe, e derrubar a cena por
    um bloco torto violaria o FR-007.

    NÃO confere se o alvo existe: aresta pendente é ausência, não erro (mesmo contrato
    de `name_of` e `dono`).
    """
    saida, vistos = [], set()
    for b in _bonds_crus(character_id):
        if not isinstance(b, dict):
            continue
        alvo, rotulo = b.get("target"), b.get("label")
        if not isinstance(alvo, str) or not alvo.strip():
            continue
        if not isinstance(rotulo, str) or not rotulo.strip():
            continue
        alvo = alvo.strip()
        if alvo == character_id or alvo in vistos:
            continue
        vistos.add(alvo)
        saida.append({"target": alvo, "label": rotulo.strip()})
    return saida


def bond_toward(character_id: str, target_id: str) -> str | None:
    """O rótulo que `character_id` declarou sobre `target_id`, ou None.

    É a consulta do CONTRATO 1: o mundo como ESTE personagem pode saber. Ela nunca
    responde pelo que o outro declarou — para isso existe `bonds_toward_me`, e ela é do
    Árbitro.
    """
    if not character_id or not target_id:
        return None
    for b in bonds_of(character_id):
        if b["target"] == target_id:
            return b["label"]
    return None


def bonds_toward_me(character_id: str) -> list[dict]:
    """Quem declarou vínculo COM este personagem — o lado que ele não sabe.

    **Só o Árbitro consome isto** (FR-015). Pôr o lado inverso no contexto quebraria a
    vista subjetiva e vazaria segredo do mundo para qualquer consumidor: é exatamente o
    que sustenta o enjeitado (o pai declara "filha", a filha não declara nada, e ela não
    sabe) e o impostor (todos declaram, e não há sangue em lugar nenhum para desmentir,
    porque sangue nunca foi modelado).

    Devolve `[{"quem": id, "label": texto}, ...]`. Usa o reverso do índice (spec 063) —
    microssegundos, sem varredura de mundo.
    """
    if not character_id:
        return []
    saida = []
    for outro in indice.reverso(character_id, ARESTA):
        rotulo = bond_toward(outro, character_id)
        if rotulo:
            saida.append({"quem": outro, "label": rotulo})
    return saida
