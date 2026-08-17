"""O Motor / rotas (pacote, item 31 §3) — domínio puro (primitivas).

Sem executores (nenhum @registro.handler): só primitivas. O __init__ reexporta a
API por NOME para `from ..rotas import X` e `motor.rotas.X` seguirem iguais.
"""
from .primitivas import (  # noqa: F401
    Path,
    ROTA,
    WORLD_DIR,
    _CROSSING_BY_SIZE,
    _STATIC_PREREQ_TYPES,
    _available_routes,
    _check_prerequisites,
    _crossing_time_of,
    _eval_prereq,
    _has_item,
    _is_alive,
    _is_static_prereq,
    _iter_memories,
    _location_folder_by_id,
    _location_name,
    _route_destination,
    _travel_modifier,
    all_route_ids,
    annotations,
    crossing_time,
    find_route,
    fisica,
    io,
    knows_route,
    memoria,
    memory_about,
    memory_kind,
    read_doc,
    recognizes_route,
)
