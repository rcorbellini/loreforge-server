"""O Motor / cozinha — PRIMITIVAS (item 31 §3: DDD por domínio; spec 048).

Funções puras (validação, rolagem, conversão de tempo) + a resolução PREGUIÇOSA
do prato (spec 048, R7 — molde EXATO de `deslocamento.primitivas.lazy_evaluate`/
`_resolve_arrivals`: o tempo "passa" na consulta ao mundo, sem processo de
fundo, Princípio VII). Sem turno/LLM aqui. Ver executores.py.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, rolagem
from ..io import read_doc, write_doc
from ..rotas import _location_folder_by_id


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


def lazy_evaluate() -> None:
    """Resolve pratos pendentes na consulta ao mundo (spec 048).

    Sem processo de fundo: o tempo "passa" quando o mundo é consultado
    (Princípio VII), exatamente como `deslocamento.lazy_evaluate` já faz para
    chegada de rota — esta é a SEGUNDA família de resolução preguiçosa do
    projeto, no mesmo molde.
    """
    with io.WRITE_LOCK:
        _resolve_pratos()


def _resolve_pratos() -> None:
    """Prato pendente cujo tempo se cumpriu materializa: `io.create_entity` no
    LUGAR onde o ato começou (mesmo se o ator já não estiver mais lá — FR-015),
    `status.cozinhando` é removido, e `status.action` é ajustado para que a
    narração do momento seguinte relate o efeito (Princípio X) — MESMO
    mecanismo que `_resolve_arrivals` já usa para "acabou de chegar", nenhum
    canal de relato novo precisou ser inventado."""
    now = time.time()
    for char_file in list(io.WORLD_DIR.rglob("character.md")):
        fm, body = read_doc(char_file)
        cozinhando = (fm.get("status") or {}).get("cozinhando")
        if not isinstance(cozinhando, dict):
            continue
        if now < (cozinhando.get("pronto_ts") or 0):
            continue
        char_folder = char_file.parent
        local_folder = (_location_folder_by_id(cozinhando.get("local"))
                        or char_folder.parent)
        prato = cozinhando.get("prato") or {}
        entity_id = prato.get("id")
        if entity_id and not (local_folder / entity_id).exists():
            io.create_entity(local_folder, entity_id, "item.md", {
                "type": "item", "id": entity_id,
                "name": prato.get("nome") or "Prato",
                "weight_kg": prato.get("peso_kg") or 0.3,
                "origin": "emergente",
            }, prato.get("description") or "Um prato preparado.")
        status = dict(fm.get("status") or {})
        status.pop("cozinhando", None)
        status["action"] = "o prato que estava no fogo ficou pronto"
        fm["status"] = status
        write_doc(char_file, fm, body)
