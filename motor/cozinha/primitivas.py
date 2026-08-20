"""O Motor / cozinha — PRIMITIVAS (item 31 §3: DDD por domínio; spec 048).

Funções puras (validação, rolagem, conversão de tempo) + a resolução PREGUIÇOSA
do prato (spec 048, R7 — molde EXATO de `deslocamento.primitivas.lazy_evaluate`/
`_resolve_arrivals`: o tempo "passa" na consulta ao mundo, sem processo de
fundo, Princípio VII). Sem turno/LLM aqui. Ver executores.py.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, rolagem, trabalho
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
    """A panela cujo tempo se cumpriu VIRA o prato (spec 048, migrada na 052).

    A resolução é a mesma de sempre — o tempo "passa" quando o mundo é consultado,
    sem processo de fundo (Princípio VII), no molde de `_resolve_arrivals`. O que
    mudou é a FONTE: antes esta função varria `character.md` atrás de um campo
    `status.cozinhando`; agora varre as PEÇAS EM PROCESSO com relógio de PRAZO. O
    prato não é mais criado do nada num lugar guardado: **a própria panela vira o
    prato, onde quer que ela esteja** — se alguém a tirou do fogo e levou embora, é
    lá que a comida fica pronta.

    Só PRAZO passa por aqui. Forjar conta ESFORÇO e conclui num ATO: decidir na
    trilha de LEITURA do mundo é justamente o que a avaliação preguiçosa evita
    fazer com decisões (spec 052, FR-049).
    """
    for pasta, bloco in trabalho.vencidas_por_prazo():
        prato = bloco.get("prato") or {}
        nome = prato.get("nome") or "Prato"
        trabalho.encerrar(pasta, {"name": nome},
                          prato.get("description") or "Um prato preparado.")
        # Princípio X: o efeito precisa CHEGAR a quem viveu. `status.action` é o
        # canal de sempre — a narração do momento seguinte relata o que aconteceu.
        ator = bloco.get("ator")
        try:
            char_folder = io.find_character_folder(ator) if ator else None
        except Exception:
            char_folder = None
        if char_folder is not None:
            fm, body = read_doc(char_folder / "character.md")
            status = dict(fm.get("status") or {})
            status["action"] = "o prato que estava no fogo ficou pronto"
            fm["status"] = status
            write_doc(char_folder / "character.md", fm, body)
