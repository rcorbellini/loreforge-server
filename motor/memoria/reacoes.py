"""O Motor / memoria — REAÇÕES ao barramento de fatos (spec 038, L1).

As duas reações de memória que subscrevem FATOS (`motor/fatos.py`), no lugar do
antigo passe por-família: a gravação de quem AGIU (`react_actor_memory`, ex-`_record_X`
chamado dentro do executor) e o leque de TESTEMUNHA (`react_witness`, spec 024, ex-
`_record_witness` no `_finalize_turn`). Adicionar uma tool não as toca; adicionar uma
reação não toca as tools (open/closed).

Elas REUSAM as primitivas de escrita já existentes, alimentando-as com um outcome
de UMA op só (`{<canal>_applied: [op]}`) — a lógica de texto/valência/intensidade
não se move, só o LUGAR de onde é acionada. Byte-equivalente por desenho.
"""
from __future__ import annotations

from .. import fatos
from .primitivas import (
    remember,
    remember_recurring,
    _record_attack,
    _record_carry,
    _record_cura,
    _record_equip,
    _record_hearsay_narrator,
    _record_learn,
    _record_lock,
    _record_mutations,
    _record_persuade,
    _record_persuade_give,
    _record_stolen,
    _record_trade,
    _record_transfer,
    _record_travel,
    _record_witness,
)

# canal → chave `<canal>_applied` que `_record_witness`/`_witness_facts` já leem.
# Só os canais que PRODUZEM testemunha (spec 024/036).
_WITNESS_CANAIS = {
    "steal_ops": "steal_ops_applied",
    "item_transfers": "item_transfers_applied",
    "attack_ops": "attack_ops_applied",
    "cura_ops": "cura_ops_applied",
    "trade_ops": "trade_ops_applied",
    "persuade_give_ops": "persuade_give_ops_applied",
    "accuse_ops": "accuse_ops_applied",
    "expel_ops": "expel_ops_applied",  # spec 041: expulsão é ato PÚBLICO
}

# canais cuja MEMÓRIA DO ATOR/PARTICIPANTE vinha de um `_record_X` no executor.
# `accuse` (grava direto no executor) e `intentions/promise/rest` (sem memória de
# ato) NÃO estão aqui — de propósito.
_ACTOR_CANAIS = frozenset({
    "attack_ops", "item_transfers", "steal_ops", "trade_ops", "cura_ops",
    "carry_ops", "persuade_ops", "persuade_give_ops", "equip_ops", "lock_ops",
    "travel_ops", "learn_ops", "hearsay_ops", "mutations",
})


@fatos.reacao()  # TODO fato: o legado despacha por canal; a tool NOVA traz o contrato
def react_actor_memory(fato, actor_folder, present) -> list:
    """A lembrança de quem AGIU (e do participante direto), derivada do fato.

    DOIS caminhos, e é o que fecha o SC-003 (uma tool nova não edita esta reação):
    - LEGADO: para os canais das ~14 famílias antigas, despacha ao recordador de
      sempre, com a op ÚNICA do fato (o golpe que ERRA é o único rejeitado que vira
      memória — a (des)confiança na arma, spec 016).
    - GENÉRICO (spec 038, US1): a tool nova EMBUTE o próprio contrato de memória no
      applied OU no rejected (`op["memory"] = {content, valence, intensity, involved,
      event, domain, summary}`), e a reação o consome via o sink `remember` — sem
      canal hardcoded aqui, sem entrada em tabela — uma tool NOVA grava a própria
      memória sem editar esta reação (SC-003). Lê `rejected` também (spec 046,
      `eat`): uma recusa de MÉRITO (não um erro corrigível de id/alcance, que nunca
      chega a virar fato) é um evento que aconteceu e pode merecer lembrança — o
      mesmo padrão que `attack` já dava ao golpe que erra, agora disponível para
      qualquer tool nova sem precisar entrar no caminho LEGADO."""
    cid, op, canal = fato.actor, fato.payload, fato.canal
    if canal not in _ACTOR_CANAIS:
        # GENÉRICO: o contrato viaja no fato; a reação não conhece a tool. Lê
        # applied E rejected — quem decide se uma recusa vira memória é a TOOL,
        # embutindo (ou não) `op["memory"]` no payload que ela mesma constrói.
        if fato.status not in ("applied", "rejected") or not isinstance(op, dict):
            return []
        mem = op.get("memory")
        if not isinstance(mem, dict) or not mem.get("content"):
            return []
        # O FATO QUE SE REPETE, declarado pela própria tool (SC-003: uma tool nova
        # não edita esta reação). Com `about` no contrato, a repetição RENOVA e
        # ADENSA em vez de criar arquivo novo — é o que impede a recusa re-tentada
        # de virar o assunto mais importante da vida do personagem, e daí
        # combustível do tick autônomo. Sem `about`, nada muda: grava como sempre.
        if mem.get("about"):
            mid, vezes = remember_recurring(
                cid, mem["content"], about=mem["about"], evento=mem.get("event"),
                involved=mem.get("involved"), summary=mem.get("summary", ""),
                intensity=mem.get("intensity", "small"),
                frag=mem.get("reincidencia", ""), valence=mem.get("valence"))
            return ([{"target": cid, "id": mid, "event": mem.get("event"),
                      "vezes": vezes}] if mid else [])
        mid = remember(cid, mem["content"],
                       intensity=mem.get("intensity", "medium"),
                       involved=mem.get("involved"), valence=mem.get("valence"),
                       evento=mem.get("event"), domain=mem.get("domain"),
                       summary=mem.get("summary", ""))
        return [{"target": cid, "id": mid, "event": mem.get("event")}] if mid else []
    if fato.status == "rejected":
        if canal == "attack_ops":
            return _record_attack(cid, [], [op])
        return []
    if canal == "attack_ops":
        return _record_attack(cid, [op], [])
    if canal == "item_transfers":
        return _record_transfer(cid, [op], present)
    if canal == "steal_ops":
        return _record_stolen(cid, [op])
    if canal == "trade_ops":
        return _record_trade(cid, [op])
    if canal == "cura_ops":
        return _record_cura(cid, [op])
    if canal == "carry_ops":
        return _record_carry(cid, [op])
    if canal == "persuade_ops":
        return _record_persuade(cid, [op])
    if canal == "persuade_give_ops":
        return _record_persuade_give(cid, actor_folder, [op], present)
    if canal == "equip_ops":
        return _record_equip(cid, [op])
    if canal == "lock_ops":
        return _record_lock(cid, [op])
    if canal == "travel_ops":
        return _record_travel(cid, [op])
    if canal == "learn_ops":
        return _record_learn(cid, [op])
    if canal == "hearsay_ops":
        return _record_hearsay_narrator(cid, [op])
    if canal == "mutations":
        return _record_mutations(cid, [op])
    return []


@fatos.reacao(kinds=tuple(_WITNESS_CANAIS))
def react_witness(fato, actor_folder, present) -> list:
    """O leque de TESTEMUNHA (spec 024): espalha memória factual pelos presentes
    que PERCEBEM a op. Só o APLICADO tem plateia (um ato negado não aconteceu para
    quem olha — a única exceção é a viagem interrompida, que é outra reação)."""
    if fato.status != "applied":
        return []
    key = _WITNESS_CANAIS.get(fato.canal)
    if not key:
        return []
    return _record_witness(fato.actor, actor_folder, present, {key: [fato.payload]})
