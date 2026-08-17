"""O Motor / fatos (spec 038, L1) — o BARRAMENTO DE FATOS.

O 5º ancoradouro (Observer) que a spec 038 cravou: cada op aplicada/rejeitada é
embrulhada num `Fato` auto-descritivo e PUBLICADA no instante em que acontece
(por-op, dentro de `turno.apply_op`). Reações registradas (`@fatos.reacao`) que
declaram interesse no `kind` do fato rodam e devolvem as memórias/efeitos que
antes moravam espalhados: a gravação do ATOR, o leque de TESTEMUNHA (024), a
interrupção-de-viagem (012). Adicionar tool não toca reação; adicionar reação
não toca tool (open/closed).

NÍVEL 0 (primitiva): NÃO importa nenhum outro módulo do Motor — só define o dado
e o registro. As reações é que importam `fatos` e se registram (mesmo padrão de
`registro`/handlers). Assim não há ciclo: `turno` (nível 2) importa `fatos` e os
módulos de reação; importá-los já popula o registro.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Fato:
    """Uma op aplicada/rejeitada, auto-descritiva (data-model.md).

    `status` = `applied` | `rejected` — um golpe que ERRA ainda é fato (interrompe
    a viagem do alvo). `valence`/`relevance`/`intensity` são o JUÍZO da tool sobre
    o ato (viajam no fato, não numa tabela central). `perceivers` são os presentes
    que podiam testemunhar. `payload` é o applied/rejected cru, para a reação compor
    o conteúdo. `canal` é o canal mutador de origem (a família), o que a reação de
    memória do ator usa para despachar ao recordador certo.
    """
    kind: str
    actor: str
    canal: str
    target: str | None = None
    status: str = "applied"
    valence: str | None = None
    relevance: str | None = None
    intensity: str | None = None
    perceivers: list = field(default_factory=list)
    payload: dict = field(default_factory=dict)


# (kinds, fn): kinds é None/"*" (todo fato), uma str, ou uma tupla de str.
_REACTIONS: list[tuple[object, object]] = []


def reacao(kinds=None):
    """Registra um subscriber transversal. `kinds`: str, tupla de str, ou "*"/None
    para TODO fato. O subscriber é `(fato, actor_folder, present) -> list[created]`.
    """
    if isinstance(kinds, str) and kinds != "*":
        kinds = (kinds,)
    elif isinstance(kinds, (list, tuple)):
        kinds = tuple(kinds)

    def deco(fn):
        _REACTIONS.append((kinds, fn))
        return fn

    return deco


def _matches(kinds, kind: str) -> bool:
    if kinds is None or kinds == "*":
        return True
    return kind in kinds


def publish(fato: Fato, actor_folder, present: dict) -> list:
    """Publica o fato: roda cada reação interessada, na ordem de registro, e
    ACUMULA as memórias criadas. Reações são independentes por desenho (memória do
    ator, testemunha, cancelar viagem — nenhuma depende da outra); se uma
    dependência aparecer, declara-se prioridade aqui. Devolve `created`."""
    created: list = []
    for kinds, fn in _REACTIONS:
        if not _matches(kinds, fato.kind):
            continue
        out = fn(fato, actor_folder, present)
        if out:
            created.extend(out)
    return created
