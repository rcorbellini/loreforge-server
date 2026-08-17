"""O Motor / cura — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

from pathlib import Path

from .. import estado, fisica, io, memoria, registro, rolagem
from ..io import _fail, _rejection, read_doc, write_doc


def roll_cura_check(actor_fm: dict, alvo_fm: dict, nota: int,
                    rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'baixa', 'media', 'alta'}.

    Nota 0-10 = favorabilidade da CENA pro socorro (Árbitro, régua
    canônica). Extremos deterministas (mesmo molde de `roll_steal_check`):
    nota <= 0 -> baixa, sem dado (situação não favorece nada); nota >= 10
    -> alta, sem dado (favorece plenamente). Entre 1-9: `d20 + mod(WIS do
    socorrista)` vs `persuade_dc(nota)` — a MESMA curva que persuadir/
    ceder/furtar já usam (loreforge-arbitrated-action: uma segunda curva
    pro mesmo formato de esforço é duas calibragens a manter em sincronia).
    A margem contra a DC decide o grau do SUCESSO (inverso do que
    `roll_steal_check` faz com o grau do FRACASSO): falhou (qualquer
    margem) -> baixa; passou por margem <= 5 -> media; passou por margem
    > 5 -> alta. Nota/DC nunca saem do `roll_info` (segredo do mundo)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "cura", "resultado": "baixa", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "baixa", info
    if nota >= 10:
        info = {"tipo": "cura", "resultado": "alta", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "alta", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("WIS", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod
    if total < dc:
        banda = "baixa"
    elif total - dc <= 5:
        banda = "media"
    else:
        banda = "alta"
    info = {
        "tipo": "cura", "resultado": banda,
        # virada: a nota dizia fácil (alta) e deu ruim, ou dizia difícil e deu bem
        "virada": (nota >= 6 and banda == "baixa") or (nota <= 4 and banda == "alta"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, info


_FRACAO_HP_POR_BANDA = {"baixa": 0.0, "media": 0.35, "alta": 0.55}


def _recovery_fraction(banda: str, nivel_cura: int = 0) -> float:
    """Fração do HP FALTANTE recuperada (research.md §2). Cada nível de
    proficiência (0-5) soma 5 pontos percentuais — o fator PREDOMINANTE
    (FR-005) só decide SE cura; aqui só ajusta a magnitude."""
    base = _FRACAO_HP_POR_BANDA.get(banda, 0.0)
    if base <= 0:
        return 0.0
    return min(1.0, base + 0.05 * nivel_cura)


