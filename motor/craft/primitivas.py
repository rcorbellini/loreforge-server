"""O Motor / craft — PRIMITIVAS (spec 057).

Funções puras: a duração convertida em tempo real, a rolagem de banda, e o
saneamento dos campos de texto que o Árbitro devolve (tipo/tamanho — só
`julgamento()` sabe extrair número e texto livre; um valor fora do vocabulário
fechado cai no default aqui, nunca propaga cru). Sem turno, sem LLM, sem arquivo.

Domínio e atributo NÃO são saneados aqui porque pararam de ser julgados: são
fixos no executor (`_DOMINIO`/`_ATRIBUTO`, molde de `forja/executores.py`), a
mesma revisão que trocou `posicao` (o Árbitro escolhendo direto
com_personagem/solto_na_location) por `tamanho` (o Árbitro só descreve o
tamanho físico; quem decide onde a coisa fica, comparando peso contra
`fisica.carry_capacity`, é o Motor).
"""
from __future__ import annotations

import validator

from .. import rolagem

BANDAS = ("falha", "comum", "incomum", "raro", "lendario")
_IDX = {b: i for i, b in enumerate(BANDAS)}

TIPOS = ("item", "object", "location")
# spec 057 (US5): só ITEM pergunta — object fica sempre fixo na location, e
# location nasce sempre como subpasta da location atual (decisão determinística
# do executor, sem julgamento). Um item grande/impróprio pra carregar fica
# SOLTO; o default é o autor sair segurando o que acabou de fazer.
POSICOES = ("com_personagem", "solto_na_location")

# Segundos de trabalho por nota de DURAÇÃO (0-10). Espalhamento GEOMÉTRICO, não
# linear (ao contrário de `duracao_segundos_forja`): craft cobre de "amarrar um
# nó" a "erguer uma casa", faixas que uma reta não capta. Calibração de primeira
# passada (research.md, R3) — ajuste fino é trabalho de medição futura, não
# desta spec.
_DURACAO_TABELA_S = {
    0: 20, 1: 60, 2: 180, 3: 420,
    4: 900, 5: 1800, 6: 3600,
    7: 10800, 8: 28800, 9: 86400, 10: 259200,
}

# Abaixo disto, o trabalho conclui NO MESMO ATO (molde de `forage`: sem bloco
# `trabalho`, nunca uma peça em processo). Igual ou acima, nasce peça em processo
# no relógio de ESFORÇO (molde de `forja`) — a primeira chamada NUNCA conclui,
# exatamente como `forge_weapon` nunca conclui na abertura.
LIMIAR_SINCRONO_S = 600


def indice(banda: str) -> int:
    return _IDX.get(banda, 0)


def duracao_segundos_craft(nota: int) -> int:
    return _DURACAO_TABELA_S[max(0, min(10, int(nota)))]


def sanear_tipo(valor: str | None) -> str:
    v = (valor or "").strip().lower()
    return v if v in TIPOS else "item"


def sanear_tamanho(valor: str | None) -> str:
    """Régua COMPARTILHADA de tamanho (`validator.SIZES`) — a mesma que já
    decide se um item cabe num contêiner ou o porte de uma location (spec 004/
    012). Craft não inventa escala própria; só usa faixas plausíveis pra algo
    feito à mão (raramente acima de "G", mas o vocabulário inteiro é aceito)."""
    v = (valor or "").strip().upper()
    return v if v in validator.SIZES else "P"


def roll_craft_check(actor_fm: dict, nota: int, atributo: str,
                     rolls: list | None = None) -> tuple[str, str | None, dict]:
    """Devolve (banda, extremo, roll_info) — molde EXATO de `roll_forge_check`
    (spec 052): `d20 + mod(atributo)` vs `persuade_dc(nota)`, mesma curva
    reaproveitada (nunca uma calibração nova). A nota 0 já foi recusada ANTES de
    chegar aqui (gate no executor); a nota 10 baixa o DC a 0, tornando o sucesso
    garantido pela própria curva — sem precisar de um branch "sem teste"."""
    nota = max(0, min(10, int(nota)))
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get(atributo, 10))
    dc = rolagem.persuade_dc(nota)
    margem = d20 + mod - dc
    if margem < 0:
        banda = "falha"
    elif margem <= 4:
        banda = "comum"
    elif margem <= 9:
        banda = "incomum"
    else:
        banda = "raro"
    extremo = "sucesso" if d20 == 20 else "falha" if d20 == 1 else None
    info = {
        "tipo": "craft", "resultado": banda,
        "virada": (nota >= 6 and banda in ("falha", "comum"))
                  or (nota <= 4 and banda in ("incomum", "raro")),
        "critico": extremo,
        "rolagem": {"d20": d20, "mod": mod, "atributo": atributo,
                    "total": d20 + mod, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, extremo, info


def desloca(banda: str, degraus: int, teto: str = "lendario") -> str:
    alvo = max(0, min(indice(banda) + degraus, indice(teto)))
    return BANDAS[alvo]


def banda_final(banda: str, extremo: str | None) -> str:
    """Igual `forja.banda_final`, sem teto de material — craft não tem uma
    régua de qualidade de material separada (Decisão C: uma nota só)."""
    if extremo == "sucesso":
        return desloca(banda, +1)
    if extremo == "falha":
        return desloca(banda, -1)
    return banda
