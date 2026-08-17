"""O Motor / deslocamento — REAÇÃO ao barramento de fatos (spec 038, L1).

A interrupção-de-viagem (spec 012, FR-008), que era um passe do `_finalize_turn`,
vira um subscriber: qualquer ato DIRIGIDO a quem viaja encerra a jornada — o
aplicado E o rejeitado (o golpe que ERRA aborda o viajante do mesmo jeito). Mora
em `deslocamento` (não em `fatos`/`memoria`) porque é ela que sabe cancelar viagem;
reusa `_interrupt_travels` com um outcome de UMA op, byte-equivalente.
"""
from __future__ import annotations

from .. import fatos
from .primitivas import _interrupt_travels

# canais cujo APLICADO aborda o alvo (os mesmos que `_interrupt_travels` colhe).
# O REJEITADO de QUALQUER canal também aborda (lido de `rejected`).
_INTERRUPT_APPLIED = {
    "attack_ops": "attack_ops_applied",
    "carry_ops": "carry_ops_applied",
    "persuade_ops": "persuade_ops_applied",
    "trade_ops": "trade_ops_applied",
    "item_transfers": "item_transfers_applied",
}


@fatos.reacao()  # todo fato — o rejeitado de qualquer canal pode abordar um viajante
def react_interrupt_travel(fato, actor_folder, present) -> list:
    """Cancela a viagem de quem foi ALVO da op (applied ou rejected). Devolve as
    entradas `{"personagem": ...}` — o chamador (apply_op) as separa das memórias.
    Cancelar de novo quem já parou é no-op (`_cancel_travel` devolve False), então
    não há entrada duplicada quando dois atos miram o mesmo viajante."""
    if fato.status == "applied":
        key = _INTERRUPT_APPLIED.get(fato.canal)
        if not key:
            return []
        outcome = {key: [fato.payload]}
    else:
        outcome = {"rejected": [fato.payload]}
    return _interrupt_travels(fato.actor, present, outcome)
