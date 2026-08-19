"""O Motor / acougue — PRIMITIVAS (item 31 §3: DDD por domínio; spec 050).

Funções puras (rolagem, física de porções). Sem turno/LLM aqui. Ver executores.py.

Divergência deliberada de `motor/cozinha/primitivas.py` (research R6): SEM resolução
preguiçosa — esquartejar não tem um "tempo de preparo" real que justifique o mesmo
mecanismo que `cook` usa (`lazy_evaluate`/`_resolve_pratos`). Tudo aqui é síncrono.
"""
from __future__ import annotations

from .. import rolagem


def roll_esquartejar_check(actor_fm: dict, nota: int, nivel_acougue: float = 0.0,
                           rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (banda, roll_info). banda ∈ {'fraco', 'medio', 'farto'}.

    Nota 0-10 = RENDIMENTO (Árbitro, régua REGUA_ESQUARTEJAR) — só chamada quando
    ESQUARTEJABILIDADE já é > 0 (gate anterior, no executor). Extremos deterministas
    (mesmo molde de `roll_cook_check`): nota<=0 -> fraco, sem dado; nota>=10 -> farto,
    sem dado. Entre 1-9: `d20 + mod(DEX) + nivel_acougue` vs `persuade_dc(nota)` —
    MESMA curva que `cook`/`cura`/persuadir já usam (rendimento alto = DC baixa) — SEM
    DC nova (research R4). Proficiência soma DIRETO no total, decidindo a PRÓPRIA
    banda, mesmo papel que `nivel_cozinha` cumpre em `cook` (divergência deliberada de
    `cura`). DEX (não INT/STR) porque esquartejar é precisão de faca, não força bruta
    nem conhecimento de preparo (research R4). Nota/DC nunca saem do `roll_info`
    (segredo do mundo)."""
    nota = max(0, min(10, int(nota)))
    if nota <= 0:
        info = {"tipo": "acougue", "resultado": "fraco", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "fraco", info
    if nota >= 10:
        info = {"tipo": "acougue", "resultado": "farto", "virada": False,
                "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "farto", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("DEX", 10))
    dc = rolagem.persuade_dc(nota)
    total = d20 + mod + float(nivel_acougue)
    if total < dc:
        banda = "fraco"
    elif total - dc <= 5:
        banda = "medio"
    else:
        banda = "farto"
    info = {
        "tipo": "acougue", "resultado": banda,
        # virada: a nota dizia fácil (farto) e deu fraco, ou dizia difícil e deu bem
        "virada": (nota >= 6 and banda == "fraco") or (nota <= 4 and banda == "farto"),
        "critico": (d20 == 20) or (d20 == 1) or None,
        "rolagem": {"d20": d20, "mod": mod, "nivel_acougue": round(float(nivel_acougue), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return banda, info


_FRACAO_POR_BANDA = {"fraco": 0.10, "medio": 0.20, "farto": 0.35}
_PORCAO_PADRAO_KG = 0.5
_PESO_MINIMO_KG = 0.05


def porcoes_de_carne(peso_corpo_kg: float, banda: str) -> list[float]:
    """Quantas porções de carne o corpo rende, e o peso de cada uma — física
    determinística (research R2), NUNCA julgada pelo Árbitro. O peso TOTAL é uma
    fração do peso do corpo (calibrável por `_FRACAO_POR_BANDA`), dividido em porções
    de tamanho padrão (`_PORCAO_PADRAO_KG`) — sempre N >= 1 (uma criatura pequena
    ainda rende UMA porção ínfima, nunca zero itens só por ser pequena; distinto de
    RENDIMENTO 0, que é recusa de mérito e nunca chega aqui)."""
    fracao = _FRACAO_POR_BANDA.get(banda, 0.0)
    peso_total = max(_PESO_MINIMO_KG, float(peso_corpo_kg or 0) * fracao)
    n = max(1, round(peso_total / _PORCAO_PADRAO_KG))
    peso_cada = round(peso_total / n, 3)
    return [peso_cada] * n
