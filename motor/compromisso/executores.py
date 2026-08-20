"""O Motor / compromisso — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` + `@registro.handler` `_h_*`. Chamam as primitivas do domínio.
"""
from __future__ import annotations

from pathlib import Path

from .. import fisica, intencoes, memoria, registro, trabalho
from ..io import _fail, read_doc

# Relevância da memória de compromisso: "medium" (mesma faixa de `persuade`/`learn`)
# — um compromisso pesa mais que uma transferência comum. Spec 038 (T016): a nota
# viaja COM o ato (o arg `intensity` do `_rec` abaixo), não mais numa tabela central.
_PROMISE_INTENSITY = "medium"




def _apply_promise(character_id: str, actor_folder: Path, res: dict,
                   rolls: list | None = None) -> tuple[list, list, list]:
    """Aplica cada op de `promise_ops`: puramente verbal — memória nos dois
    lados (reusa `memoria._rec`, `kind` default ACONTECIMENTO — Decisão 2,
    research.md) e intenção só no ator (Decisão nenhuma-em-nome-de-outro,
    FR-008). Nunca move item — quem quiser reforçar um empréstimo mecânico
    usa `give` com `emprestimo=true` antes ou depois (spec 036).
    """
    applied, rejected, created = [], [], []
    if not res.get("promise_ops"):
        return applied, rejected, created
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or trabalho.is_busy(actor_folder):  # spec 031/048/052: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected, created
    for op in res.get("promise_ops") or []:
        para = op.get("para")
        expectativa = (op.get("expectativa") or "").strip()
        if not para or not expectativa:
            rejected.append({**op, "why": "'para' e 'expectativa' são obrigatórios"})
            continue

        eu = memoria._char_name(character_id)
        alvo_nome = memoria._char_name(para)
        memoria._rec(
            created, character_id,
            f"Prometi a {alvo_nome}: {expectativa}",
            "promise", [character_id, para], intensity=_PROMISE_INTENSITY)
        # spec 030: id da memória que ACABOU de nascer na perspectiva do
        # próprio ator — é o que a Frente D (dormir com pendência) vai
        # intensificar depois. `_rec` só faz efeito colateral (created.
        # append); pega a entrada que ele mesmo acabou de adicionar.
        mem_id_ator = created[-1]["id"] if created else None
        memoria._rec(
            created, para,
            f"{eu} me prometeu: {expectativa}",
            "promise", [character_id, para], intensity=_PROMISE_INTENSITY)

        intention_id = intencoes.create_intention(
            actor_folder, expectativa, status="ativa", memoria_id=mem_id_ator)
        applied.append({"para": para, "intention_id": intention_id})
    return applied, rejected, created


@registro.handler("promise_ops")
def _h_promise(character_id, actor_folder, res, rolls):
    return _apply_promise(character_id, actor_folder, res, rolls)
