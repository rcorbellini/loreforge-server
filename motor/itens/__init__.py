"""O Motor / itens (pacote, item 31 §3) — fachada do domínio.

Reexporta a API por NOME (primitivas + executores) para que
`from ..itens import X` e `motor.itens.X` sigam inalterados. Importar
executores REGISTRA os handlers (@registro.handler) no import do pacote.
"""
from .primitivas import (  # noqa: F401
    _corrigivel_reject,
    _equippable_items,
    _equipped_items,
    _find_item_folder_in_scene,
    _find_item_under,
    _held_items,
    _loose_items,
    _match_scene_ref,
    _set_item_slot,
    _validate_move,
    has_accessible_item,
    roll_steal_check,
    roll_toxicidade_check,
    transfer_item,
)
from .executores import (  # noqa: F401
    _apply_eat_ops,
    _apply_equip_ops,
    _apply_item_transfers,
    _apply_movement,
    _apply_steal_ops,
    _h_eat,
    _h_equip,
    _h_steal,
    _h_transfer,
)
from . import declaracao  # noqa: F401  (importar registra os ToolSpec no registro)
