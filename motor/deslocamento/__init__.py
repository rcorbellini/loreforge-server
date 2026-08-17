"""O Motor / deslocamento (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME; importar executores registra os @registro.handler.
"""
from .primitivas import (  # noqa: F401
    _cancel_travel,
    _enter_route_locked,
    _interrupt_travels,
    _resolve_arrivals,
    _witness_movement,
    cancel_travel_plan,
    carry_time_penalty,
    current_location_id,
    directions_from,
    enter_route,
    known_routes,
    lazy_evaluate,
    reachable_destinations,
    roll_persuasion_check,
    route_plan,
    set_travel_plan,
)
from .executores import (  # noqa: F401
    _apply_carry_ops,
    _apply_persuade_ops,
    _apply_travel_ops,
    _h_carry,
    _h_persuade,
    _h_travel,
)
from . import reacoes  # noqa: F401  (importar registra a reação no barramento)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec de deslocamento)
