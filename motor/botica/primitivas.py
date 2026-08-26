"""O Motor / botica — PRIMITIVAS (item 31 §3: DDD por domínio; spec 055).

Funções puras: a rolagem de favorabilidade e a conversão da nota de duração em
tempo real. A resolução do prazo NÃO mora aqui — é `trabalho.resolver_vencidas`,
genérica para todo domínio de prazo (mesma que `cook`/`kindle_fire`/`forage`
já usam). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

from .. import rolagem


def roll_preparar_check(actor_fm: dict, nota: int, nivel_botica: float = 0.0,
                        rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'ruim', 'media', 'otima'}.

    Nota 0-10 = FAVORABILIDADE (Árbitro, régua REGUA_PREPARAR) — só chamada
    quando os dois gates (RECIPIENTE_ADEQUADO, PREPARABILIDADE) já são > 0.
    Extremos deterministas (mesmo molde de `roll_cook_check`): nota<=0 -> banda
    ruim sem dado (nunca chega aqui — favorabilidade 0 não é recusa, é o piso
    da rolagem); nota>=10 -> ótima sem dado. Entre 1-9:
    `d20 + mod(INT) + nivel_botica` vs `persuade_dc(nota)` — MESMA curva que
    `cook`/`cura`/`butcher`/`kindle_fire`/`forage` já usam.

    INT, igual a `cook` (spec 055, R2 do research): preparar é dose, ordem,
    conhecimento de técnica — mesma natureza de julgamento que cozinhar, ao
    contrário de `forage` (WIS, perceber o terreno) ou `butcher` (DEX, faca).
    Proficiência soma DIRETO no total, decidindo a PRÓPRIA banda.

    Nota e DC nunca saem do `roll_info` (segredo do mundo, Princípio IX)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "botica", "resultado": "ruim", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "ruim", info
    if nota >= 10:
        info = {"tipo": "botica", "resultado": "otima", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "otima", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("INT", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel_botica)
    if total < dc:
        banda = "ruim"
    elif total - dc <= 5:
        banda = "media"
    else:
        banda = "otima"
    info = {
        "tipo": "botica", "resultado": banda,
        # virada: a cena dizia fácil (ótima) e deu ruim, ou dizia difícil e deu bem
        "virada": (nota >= 6 and banda == "ruim") or (nota <= 4 and banda == "otima"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod, "nivel_botica": round(float(nivel_botica), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, info


def duracao_segundos_preparo(nota: int) -> int:
    """Converte a nota 0-10 de DURAÇÃO em tempo real de preparo.

    MESMA fórmula de `cozinha.duracao_segundos` (1 a 11 minutos), mas função
    PRÓPRIA — cada domínio de PRAZO calibra a própria constante (mesmo padrão
    que `fogo.duracao_fogo_s` já segue, uma década acima da de cook por razão
    física própria; aqui não há razão pra divergir, mas a independência de
    calibração é o que importa manter). Nunca julgada pelo Árbitro."""
    return 60 + 60 * max(0, min(10, int(nota)))
