"""O Motor / cozinha — PRIMITIVAS (item 31 §3: DDD por domínio; spec 048).

Funções puras: validação, rolagem e conversão de tempo. A resolução preguiçosa do
prato NÃO mora mais aqui — desde a spec 053 ela é `trabalho.resolver_vencidas`,
genérica para todo domínio de prazo. Sem turno/LLM aqui. Ver executores.py.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import rolagem


def roll_cook_check(actor_fm: dict, nota: int, nivel_cozinha: float = 0.0,
                    rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'ruim', 'media', 'otima'}.

    Nota 0-10 = favorabilidade do calor/ingredientes (Árbitro, régua
    REGUA_COZINHAR). Extremos deterministas (mesmo molde de `roll_cura_check`):
    nota<=0 -> ruim, sem dado; nota>=10 -> ótima, sem dado. Entre 1-9:
    `d20 + mod(INT) + nivel_cozinha` vs `persuade_dc(nota)` — MESMA curva que
    `cura`/persuadir já usam (favorabilidade alta = DC baixa). Divergência
    DELIBERADA de `cura` (spec 048, Eixo 3): a proficiência soma DIRETO no
    total, decidindo a PRÓPRIA banda — em `cura`, `nivel_cura` só ajusta a
    magnitude DEPOIS da banda decidida. Nota/DC nunca saem do `roll_info`
    (segredo do mundo)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "cozinha", "resultado": "ruim", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "ruim", info
    if nota >= 10:
        info = {"tipo": "cozinha", "resultado": "otima", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "otima", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("INT", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel_cozinha)
    if total < dc:
        banda = "ruim"
    elif total - dc <= 5:
        banda = "media"
    else:
        banda = "otima"
    info = {
        "tipo": "cozinha", "resultado": banda,
        # virada: a nota dizia fácil (ótima) e deu ruim, ou dizia difícil e deu bem
        "virada": (nota >= 6 and banda == "ruim") or (nota <= 4 and banda == "otima"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod, "nivel_cozinha": round(float(nivel_cozinha), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, info


def duracao_segundos(nota: int) -> int:
    """Converte a nota 0-10 de DURAÇÃO (quão elaborado é o preparo) em tempo
    real de preparo — mesmo PAPEL que `crossing_time()` cumpre para
    `location.size`, mas LINEAR na nota em vez de indexado por enum (spec 048,
    R6): a duração não tem categorias fixas como PP/P/M/G, é uma régua
    contínua. 1 a 11 minutos reais — nunca julgado pelo Árbitro."""
    return 60 + 60 * max(0, min(10, int(nota)))


# spec 053: `lazy_evaluate`/`_resolve_pratos` foram REMOVIDAS daqui e viraram
# `trabalho.resolver_vencidas`, genérica. Elas iteravam TODAS as peças de prazo do
# mundo (não só as de `cook`) e liam `bloco["prato"]` — então a primeira peça de
# outro domínio a usar o mesmo relógio seria renomeada para "Prato" em silêncio.
# A resolução do prazo é operação do dono do bloco (Princípio XII), não de um
# domínio irmão.
