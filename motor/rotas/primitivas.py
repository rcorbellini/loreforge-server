"""O Motor / rotas (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
"""
from __future__ import annotations

import os
import random
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import fisica, io, memoria
from ..fisica import (
    _CROSSING_BY_SIZE,
)
from ..io import (
    arquivos_em,
    arquivos_no_mundo,
    WORLD_DIR,
    read_doc,
)
from ..memoria import (
    ROTA,
    _is_alive,
    _iter_memories,
    memory_about,
    memory_kind,
)


def all_route_ids() -> list[str]:
    """Todos os caminhos que existem no mundo — enum de `learn_routes`.

    Consulta de SERVER (Princípio IX): o client nunca recebe a lista de rotas
    distantes. É o que impede prosa de virar id novo — o Árbitro escolhe entre
    caminhos REAIS e nada mais (FR-006/FR-007), e o erro de digitação do autor
    deixa de criar caminho fantasma.
    """
    out = []
    for path in arquivos_no_mundo("route.md"):
        fm, _ = read_doc(path)
        if fm.get("id"):
            out.append(fm["id"])
    return sorted(set(out))


def _memorias_de_rota(character_id: str, route_id: str):
    """As memórias de `character_id` que falam DESTA rota — pela aresta `sobre`.

    Memória de rota carrega `about: <id da rota>`, e o índice já a indexa como aresta.
    Sem índice, devolve todas as dele: o `memory_about(fm) == route_id` de quem chama
    continua no lugar e faz o mesmo recorte, varrendo.

    O ganho aqui foi o maior de toda a spec depois de `read_doc`: `knows_route` era
    chamada uma vez por rota por personagem, e cada chamada varria as 804 memórias da
    Mira — 385 920 leituras de documento numa única montagem de face.
    """
    try:
        folder = io.find_character_folder(character_id)
    except io.MotorError:
        # NÃO usar `except Exception` aqui. A primeira versão usava, e engoliu um
        # NameError (`find_character_folder` não estava importado neste módulo): a
        # função devolvia [] em silêncio, `knows_route` virava False para todo mundo,
        # e a capacidade `travel_to` sumia da face inteira. Só a comparação
        # byte-a-byte contra a linha de base pegou — nenhum teste teria pego, porque
        # o resultado era plausível.
        return []
    arquivos = io.arquivos_sobre(folder / "memories", route_id)
    if arquivos is None:
        return _iter_memories(character_id)
    out = []
    for path in arquivos:
        fm, _ = read_doc(path)
        if fm.get("type") == "memory":
            out.append(fm)
    return out


def knows_route(character_id: str, route_id: str) -> bool:
    """Sabe percorrer este caminho? Exige memória de rota VIVA.

    Se bastasse a vencida, ninguém esqueceria caminho nenhum e a renovação pelo
    uso perderia o sentido — é esta função que a spec 012 consome.
    """
    return any(
        memory_kind(fm) == ROTA and memory_about(fm) == route_id and _is_alive(fm)
        for fm in _memorias_de_rota(character_id, route_id)
    )


def recognizes_route(character_id: str, route_id: str) -> bool:
    """Já esteve por aqui? Basta a lembrança, mesmo vencida — reconhecer ≠ saber."""
    return any(
        memory_kind(fm) == ROTA and memory_about(fm) == route_id
        for fm in _memorias_de_rota(character_id, route_id)
    )


def find_route(route_id: str) -> tuple[Path, dict, str] | None:
    path = io.arquivo_por_id("route.md", route_id)
    if path is None:
        return None
    fm, body = read_doc(path)
    return path.parent, fm, body


def _location_folder_by_id(loc_id: str) -> Path | None:
    path = io.arquivo_por_id("location.md", loc_id)
    return path.parent if path is not None else None


def _location_name(loc_id: str) -> str:
    folder = _location_folder_by_id(loc_id)
    if folder:
        fm, _ = read_doc(folder / "location.md")
        return fm.get("name") or loc_id
    return loc_id


def _route_destination(route_fm: dict, from_loc_id: str) -> str | None:
    """Destino de uma rota a partir de uma location (respeita bidirecional)."""
    frm, to = route_fm.get("from"), route_fm.get("to")
    if frm == from_loc_id:
        return to
    if bool(route_fm.get("bidirectional")) and to == from_loc_id:
        return frm
    return None


def crossing_time(loc_fm: dict) -> int:
    """Tempo de cruzar uma location, do ponto onde se entra ao onde se sai.

    Sem isto o viajante saltaria de rota em rota sem nunca estar num lugar — e a
    promessa de ser alcançável no meio do caminho (Q3) seria vazia, porque
    metade do trajeto não teria onde acontecer.

    NENHUM degrau custa zero, nem o menor: custo zero faria o viajante atravessar
    e sair no MESMO instante, e ele voltaria a ser inobservável — a Q3 valeria só
    para lugares grandes. A FR-010a pede que atravessar custe tempo, e zero não
    é custo.
    """
    return _CROSSING_BY_SIZE.get(loc_fm.get("size"), _CROSSING_BY_SIZE["M"])


def _crossing_time_of(loc_id: str) -> int:
    folder = _location_folder_by_id(loc_id)
    if folder is None:
        return 0
    fm, _ = read_doc(folder / "location.md")
    return crossing_time(fm)


def _available_routes(loc_id: str | None) -> list[dict]:
    """Rotas que partem da location atual (para o contexto e o prompt do Árbitro)."""
    if not loc_id:
        return []
    out = []
    for path in arquivos_no_mundo("route.md"):
        fm, _ = read_doc(path)
        dest = _route_destination(fm, loc_id)
        if dest:
            out.append({
                "id": fm.get("id"),
                "name": fm.get("name"),
                "destination_id": dest,
                "destination_name": _location_name(dest),
            })
    return out


_STATIC_PREREQ_TYPES = {None, "none", "item", "attribute"}


def _is_static_prereq(prereq: dict) -> bool:
    return prereq.get("type") in _STATIC_PREREQ_TYPES


def _has_item(actor_folder: Path, item_id: str) -> bool:
    for path in actor_folder.rglob("item.md"):
        fm, _ = read_doc(path)
        if fm.get("id") == item_id:
            return True
    return False


def _eval_prereq(prereq: dict, actor_folder: Path, actor_fm: dict) -> str | None:
    """Avalia um prerequisite. Retorna o motivo da negação, ou None se passa."""
    ptype = prereq.get("type")
    if ptype in (None, "none"):
        return None
    if ptype == "item":
        req = prereq.get("required")
        if req and not _has_item(actor_folder, req):
            return prereq.get("deny_reason") or f"você não carrega o necessário para seguir."
        return None
    if ptype == "attribute":
        attr = prereq.get("attribute")
        minimum = prereq.get("min", 0)
        value = (actor_fm.get("attributes") or {}).get(attr, 0)
        if not isinstance(value, int) or value < minimum:
            return prereq.get("deny_reason") or "suas forças não bastam para este caminho."
        return None
    if ptype == "status":  # contextual: depende do estado atual do ator/mundo
        field = prereq.get("field")
        expected = prereq.get("equals")
        current = (actor_fm.get("status") or {}).get(field)
        if current != expected:
            return prereq.get("deny_reason") or "as condições não permitem seguir agora."
        return None
    # tipo desconhecido: permissivo (o validador de schema não conhece semântica).
    return None


def _check_prerequisites(route_fm: dict, actor_folder: Path, actor_fm: dict) -> str | None:
    """Avalia prerequisites em ordem: estáticos primeiro, contextuais por último.

    A primeira negação interrompe a avaliação e devolve o motivo (FR-019).
    """
    prereqs = route_fm.get("prerequisites") or []
    statics = [p for p in prereqs if isinstance(p, dict) and _is_static_prereq(p)]
    contextuals = [p for p in prereqs if isinstance(p, dict) and not _is_static_prereq(p)]
    for prereq in statics + contextuals:
        reason = _eval_prereq(prereq, actor_folder, actor_fm)
        if reason:
            return reason
    return None


# As duas faixas mais altas de `fatigue_label` — o que a spec 030 chamava de
# "fadiga alta". Ficam nomeadas aqui para o dia em que os rótulos mudarem de
# novo: a comparação passa a quebrar o teste, não a virar código morto.
_FADIGA_QUE_ATRASA = ("muito cansado", "exausto")


def _travel_modifier(base: int, actor_fm: dict) -> int:
    """Modificador de tempo real de viagem (FR-020): fadiga alta atrasa a jornada.

    CONSERTADO em 2026-08-12. Isto comparava `status.fatigue` com as strings
    `("alto", "exausto")` — resíduo de quando a fadiga era RÓTULO. Ela virou
    NÚMERO (`fatigue`/`fatigue_max`) e a comparação passou a ser sempre falsa:
    medido, um personagem com 120/120 viajava tão rápido quanto um descansado.

    O sintoma era silencioso, que é o pior tipo — nada falha, nada aparece no
    log, e a regra simplesmente deixa de existir. Agora deriva do MESMO corte
    que `fatigue_penalty` usa para piorar a DC, em vez de ter faixa própria.
    """
    fadiga, teto = fisica.ensure_fatigue(actor_fm)
    if memoria.fatigue_label(fadiga, teto) in _FADIGA_QUE_ATRASA:
        return round(base * 0.5)
    return 0
