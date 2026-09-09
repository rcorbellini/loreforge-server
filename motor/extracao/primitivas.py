"""O Motor / extracao — PRIMITIVAS (item 31 §3: DDD por domínio; specs 054/071).

Funções puras: a rolagem de riqueza, a física de porções, e a constante de
rebrota. A resolução do prazo de rebrota NÃO mora aqui — é
`trabalho.resolver_vencidas`, genérica para todo domínio de prazo (mesmo caminho
que a fonte de fogo, spec 053, já usa). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

import validator

from .. import fisica, rolagem

# --------------------------------------------------------------------------- #
# AS TRÊS MATÉRIAS (spec 071)
# --------------------------------------------------------------------------- #
#
# Uma entrada por capacidade. É a ÚNICA coisa que difere entre `mine`, `chop` e
# `forage` no juízo — a régua é a mesma, palavra por palavra, e a matéria desce ao
# modelo como DADO (`materia_pedida` no payload), nunca como proibição em prosa.
#
# MEDIDO (research R10): pôr a restrição de matéria em prosa vazava (uma moita de
# amora pontuava 10 para minério) e, quando escrita forte o bastante para não
# vazar, fazia o modelo RECUSAR o ato legítimo 3/3. Como dado no payload, os dois
# problemas somem de uma vez — 5/5 cenas, zero recusa, 15/15 repetições estáveis.
#
# `exige_ferramenta` decide DUAS coisas de uma vez: se a nota de FERRAMENTA é
# perguntada, e se a capacidade some do manifest quando não há nada empunhável
# (parâmetro obrigatório com enum vazio, `arbiter_tools/base.py`). Colher com a
# mão é o caso base do mundo — pedir ferramenta ali quebraria a `forage`, e a
# régua de ferramenta pontua mão vazia como 0 de propósito (é o certo para pedra).
MATERIAS = {
    "mine": {
        "materia": "mineral (pedra, minério, argila, sal)",
        "dominio": "mineracao", "atributo": "STR", "exige_ferramenta": True,
        "prefixo_id": "minerio", "generico": "Matéria mineral",
    },
    "chop": {
        "materia": "lenhosa (tronco, galho, tábua, lenha, casca)",
        "dominio": "lenha", "atributo": "STR", "exige_ferramenta": True,
        "prefixo_id": "lenho", "generico": "Madeira",
    },
    "forage": {
        "materia": "vegetal (folha, raiz, casca, graveto, fibra, fruto)",
        "dominio": "herbalismo", "atributo": "WIS", "exige_ferramenta": False,
        "prefixo_id": "erva", "generico": "Matéria vegetal",
    },
}

# --------------------------------------------------------------------------- #
# RENOVAÇÃO — a nota nova (spec 071)
# --------------------------------------------------------------------------- #
#
# Segundos até o alvo voltar a render. Espalhamento GEOMÉTRICO: a régua cobre de
# "mato rasteiro em horas" a "veia de metal que não volta nunca", e uma reta não
# capta essa faixa (mesma razão da tabela de duração de `craft`).
#
# **A nota 0 é o coração da spec e não está nesta tabela de propósito**: 0 não é
# "volta em muito tempo", é NÃO VOLTA. O executor não instala prazo nenhum, e é a
# AUSÊNCIA de promessa de volta que significa esgotado — nunca um campo dizendo
# isso (Princípio XI).
#
# Isto REVERTE deliberadamente a decisão R5 da spec 054, que recusou uma régua de
# rebrota com o argumento de que seria "uma terceira régua para um número que
# ninguém no jogo pode ver". O argumento valia para erva, e cai aqui: a diferença
# entre "volta" e "nunca mais volta" é a coisa mais visível de um jogo com
# extração.
_RENOVACAO_TABELA_S = {
    1: 90 * 24 * 3600,   # gerações — um carvalho centenário
    2: 30 * 24 * 3600,
    3: 14 * 24 * 3600,   # anos/estações — um barranco que a chuva refaz
    4: 7 * 24 * 3600,
    5: 3 * 24 * 3600,    # estações
    6: 24 * 3600,
    7: 12 * 3600,        # dias
    8: 6 * 3600,
    9: 3 * 3600,         # o `_REBROTA_S` da 054, preservado como referência
    10: 3600,            # horas — mato rasteiro
}


def renovacao_s(nota: int) -> int | None:
    """Segundos até render de novo, ou **None** quando não renova nunca.

    `None` não é "erro" nem "muito tempo": é o esgotamento permanente, e o
    executor o traduz em não instalar prazo algum."""
    nota = max(0, min(10, int(nota)))
    return None if nota == 0 else _RENOVACAO_TABELA_S[nota]


# Os portes que a régua de fato OFERECE. Subconjunto de `validator.SIZES`, e o
# recorte é deliberado (achado do exploratório da 071): `fisica.DEFAULT_WEIGHT_BY_SIZE`
# não cobre `XXXXG`/`XXXXXG`, então aceitá-los fazia o peso cair no default de `P`
# e nascer uma laje "XXXXXG" de 1 kg. Uma porção extraída à mão nunca é maior que
# um tronco; se um dia for, a tabela de peso é que precisa crescer primeiro.
TAMANHOS = ("PP", "P", "M", "G", "XG")


def sanear_tamanho(valor: str | None) -> str:
    """Régua COMPARTILHADA de porte — a mesma escala que decide se algo cabe num
    contêiner desde a spec 004, recortada no que a régua oferece e a física pesa.
    Substitui o `_PESO_PORCAO_KG` de 0,2 kg fixo da 054, que fazia um tronco de
    carvalho pesar o mesmo que um punhado de folhas."""
    v = (valor or "").strip().upper()
    return v if v in TAMANHOS else "P"


def peso_da_porcao(tamanho: str) -> float:
    """Peso derivado do PORTE, pela mesma tabela que todo o resto do mundo usa.

    É o que faz o loop da spec fechar sem verbo novo: um tronco XG passa da
    capacidade de carga, cai no chão, e `shove` (que já existe) o arrasta."""
    assert tamanho in TAMANHOS, f"porte fora do vocabulário da extração: {tamanho}"
    return fisica.DEFAULT_WEIGHT_BY_SIZE[tamanho]


def roll_colher_check(actor_fm: dict, nota: int, nivel: float = 0.0,
                      rolls: list | None = None, *, atributo: str = "WIS",
                      dominio: str = "herbalismo") -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'mato', 'util', 'seleta'}.

    Nota 0-10 = RIQUEZA (Árbitro, régua REGUA_RIQUEZA) — só chamada quando
    HERBABILIDADE já é > 0 (gate anterior, no executor). Extremos deterministas
    (mesmo molde de `roll_esquartejar_check`/`roll_cook_check`): nota<=0 -> 'mato'
    sem dado (nunca chega aqui — RIQUEZA 0 é recusa, R1); nota>=10 -> 'seleta' sem
    dado. Entre 1-9: `d20 + mod(WIS) + nivel_herbalismo` vs `persuade_dc(nota)` —
    MESMA curva que `cook`/`cura`/`butcher`/`kindle_fire` já usam (research R3).

    ATRIBUTO E DOMÍNIO vêm da MATÉRIA (spec 071), não são mais fixos: colher é
    WIS — perceber o TERRENO e reconhecer o que cresce nele, observação de campo,
    não bancada (`cook`, INT) nem precisão de faca (`butcher`, DEX). Minerar e
    cortar são STR: ali o gargalo é o braço contra a matéria, não o olho sobre o
    terreno. Proficiência soma DIRETO no total, decidindo a PRÓPRIA banda (papel
    de `cozinha`/`acougue`, não o passivo de `cura`) — e cada capacidade alimenta
    a SUA: praticar mineração não faz herbalismo crescer.

    Nota e DC nunca saem do `roll_info` (segredo do mundo, Princípio IX)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": dominio, "resultado": "mato", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "mato", info
    if nota >= 10:
        info = {"tipo": dominio, "resultado": "seleta", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "seleta", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get(atributo, 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel)
    if total < dc:
        banda = "mato"
    elif total - dc <= 5:
        banda = "util"
    else:
        banda = "seleta"
    info = {
        "tipo": dominio, "resultado": banda,
        # virada: a cena dizia farto e saiu mato, ou dizia pobre e saiu seleta
        "virada": (nota >= 6 and banda == "mato") or (nota <= 4 and banda == "seleta"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod,
                    "nivel_herbalismo": round(float(nivel), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, info


_PORCOES_POR_BANDA = {"mato": 1, "util": 2, "seleta": 3}
_PESO_PORCAO_KG = 0.2


def porcoes_de_erva(banda: str) -> list[float]:
    """Quantas porções a colheita rende, e o peso de cada uma — física
    determinística (research R2), NUNCA julgada pelo Árbitro. Divergência
    deliberada de `porcoes_de_carne` (butcher): ali o peso TOTAL deriva do
    `weight_kg` do corpo; aqui NÃO há peso de origem — um `location.md` não tem
    peso, e um `object` colhido também não deveria precisar de um só para isto.
    Quantidade e peso saem inteiramente da banda e de constantes calibráveis.
    Sempre N >= 1 (banda `mato` ainda rende UMA porção da coisa errada; voltar de
    mãos vazias é RIQUEZA 0, recusa de mérito que nunca chega aqui)."""
    n = _PORCOES_POR_BANDA.get(banda, 1)
    return [_PESO_PORCAO_KG] * n


_REBROTA_S = 3 * 3600


def rebrota_s() -> int:
    """Quanto tempo real um `object` colhido leva para voltar a render.

    Constante calibrável do Motor, nunca julgada pelo Árbitro — perguntar "quanto
    tempo o mato leva pra voltar" seria uma terceira régua para um número que
    ninguém no jogo pode ver (research R5/R1). Só usada quando o alvo é `object`;
    uma `location` nunca instala prazo nenhum (FR-013)."""
    return _REBROTA_S
