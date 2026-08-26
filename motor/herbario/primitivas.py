"""O Motor / herbario — PRIMITIVAS (item 31 §3: DDD por domínio; spec 054).

Funções puras: a rolagem de riqueza, a física de porções, e a constante de
rebrota. A resolução do prazo de rebrota NÃO mora aqui — é
`trabalho.resolver_vencidas`, genérica para todo domínio de prazo (mesmo caminho
que a fonte de fogo, spec 053, já usa). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

from .. import rolagem


def roll_colher_check(actor_fm: dict, nota: int, nivel_herbalismo: float = 0.0,
                      rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'mato', 'util', 'seleta'}.

    Nota 0-10 = RIQUEZA (Árbitro, régua REGUA_RIQUEZA) — só chamada quando
    HERBABILIDADE já é > 0 (gate anterior, no executor). Extremos deterministas
    (mesmo molde de `roll_esquartejar_check`/`roll_cook_check`): nota<=0 -> 'mato'
    sem dado (nunca chega aqui — RIQUEZA 0 é recusa, R1); nota>=10 -> 'seleta' sem
    dado. Entre 1-9: `d20 + mod(WIS) + nivel_herbalismo` vs `persuade_dc(nota)` —
    MESMA curva que `cook`/`cura`/`butcher`/`kindle_fire` já usam (research R3).

    WIS, não INT/DEX/STR: colher é perceber o TERRENO e reconhecer o que cresce
    nele — observação de campo, não conhecimento de bancada (`cook`, INT) nem
    precisão de faca (`butcher`, DEX). Proficiência soma DIRETO no total, decidindo
    a PRÓPRIA banda (papel de `cozinha`/`acougue`, não o papel passivo de `cura`).

    Nota e DC nunca saem do `roll_info` (segredo do mundo, Princípio IX)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "herbalismo", "resultado": "mato", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "mato", info
    if nota >= 10:
        info = {"tipo": "herbalismo", "resultado": "seleta", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "seleta", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("WIS", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel_herbalismo)
    if total < dc:
        banda = "mato"
    elif total - dc <= 5:
        banda = "util"
    else:
        banda = "seleta"
    info = {
        "tipo": "herbalismo", "resultado": banda,
        # virada: a cena dizia farto e saiu mato, ou dizia pobre e saiu seleta
        "virada": (nota >= 6 and banda == "mato") or (nota <= 4 and banda == "seleta"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod,
                    "nivel_herbalismo": round(float(nivel_herbalismo), 2),
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
