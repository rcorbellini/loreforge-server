"""O Motor / acougue — EXECUTORES (item 31 §3: DDD por domínio; spec 050).

`_apply_esquartejar_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_esquartejar` (encadeia memória). A ÚNICA decisão
não-determinística é a rolagem de RENDIMENTO (`roll_esquartejar_check`) — o
Árbitro julgou o corpo, o Motor decide a banda. `butcher` NUNCA mata (pré-condição
dura: `alvo` já MORTO, checada pelo `enum_source` antes de chegar aqui, revalidada
aqui de novo) e NUNCA apaga nem reescreve o `alvo` (`character` é exceção-zero ao
Princípio IV) — só marca `status.esquartejado`. Divergência deliberada de `cook`
(research R6): tudo síncrono, sem materialização preguiçosa.
"""
from __future__ import annotations

from pathlib import Path

from .. import fisica, io, memoria, registro
from ..estado import _set_field
from ..io import _fail, _rejection, name_of, read_doc

from .primitivas import porcoes_de_carne, roll_esquartejar_check


def _apply_esquartejar_ops(character_id: str, actor_folder: Path, resolution: dict,
                           rolls: list | None = None) -> tuple[list, list]:
    """Esquartejar (spec 050). Os dois GATES (esquartejabilidade, rendimento)
    rejeitam — COM memória embutida (`op["memory"]`, small/negativa, mesmo padrão
    de `cook`) e marcam `status.esquartejado` mesmo assim (corpo é recurso
    finito, esgotado na primeira tentativa resolvida, qualquer desfecho).
    Passando os dois: rola RENDIMENTO (com a proficiência em "acougue" somada
    DIRETO no total, mesmo papel que "cozinha" cumpre em `cook`) -> banda ->
    deriva N porções de carne (`porcoes_de_carne`, física determinística) -> cria
    N itens (`io.create_entity`, em loop, mesmo nome/description em todos) ->
    marca `alvo.status.esquartejado = True`."""
    applied, rejected = [], []
    if not resolution.get("esquartejar_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm) or fisica.is_cooking(actor_fm):
        rejected.append(_fail("descansando"))
        return applied, rejected
    present_chars, _po, _pi = io._scene_entities(actor_folder.parent)  # cena fresca (025)

    for op in resolution.get("esquartejar_ops") or []:
        alvo = op.get("alvo")
        base = {"alvo": alvo}
        alvo_folder = present_chars.get(alvo)
        if alvo_folder is None:
            rejected.append(_rejection(base, _fail("alvo_inacessivel", alvo=alvo)))
            continue
        alvo_fm, _ = read_doc(alvo_folder / "character.md")
        if not fisica.is_dead(alvo_fm):
            rejected.append(_rejection(base, _fail("alvo_nao_morto", alvo=alvo)))
            continue
        if (alvo_fm.get("status") or {}).get("esquartejado"):
            rejected.append(_rejection(base, _fail("ja_esquartejado", alvo=alvo)))
            continue

        esquartejabilidade = int(op.get("esquartejabilidade") or 0)
        if esquartejabilidade <= 0:
            _set_field(alvo_folder, "status.esquartejado", True)
            rejected.append({
                **base, "regra": "sem_carne", "valores": {"alvo": alvo},
                "why": io._WHY_BY_REGRA["sem_carne"],
                "memory": {
                    "content": f"Tentei esquartejar {name_of(alvo)}, mas aquilo "
                               "não era carne nenhuma.",
                    "intensity": "small", "involved": [alvo],
                    "valence": {alvo: memoria.NEGATIVA},
                    "event": "butcher_refused_esquartejabilidade"}})
            continue
        rendimento = int(op.get("rendimento") or 0)
        if rendimento <= 0:
            _set_field(alvo_folder, "status.esquartejado", True)
            rejected.append({
                **base, "regra": "nada_a_aproveitar", "valores": {"alvo": alvo},
                "why": io._WHY_BY_REGRA["nada_a_aproveitar"],
                "memory": {
                    "content": f"Esquartejei {name_of(alvo)}, mas não sobrou nada "
                               "aproveitável.",
                    "intensity": "small", "involved": [alvo],
                    "valence": {alvo: memoria.NEGATIVA},
                    "event": "butcher_refused_rendimento"}})
            continue

        nivel_acougue = memoria.proficiencies_for(character_id).get("acougue", 0.0)
        banda, roll_info = roll_esquartejar_check(actor_fm, rendimento, nivel_acougue,
                                                   rolls)
        nome = (op.get("nome") or "").strip() or "Carne"
        descricao = (op.get("descricao") or "").strip() or "Um corte de carne crua."

        peso_alvo = float(alvo_fm.get("weight_kg") or 0)
        pesos = porcoes_de_carne(peso_alvo, banda)
        criados = []
        for peso in pesos:
            item_id = io.new_id("carne")
            io.create_entity(actor_folder.parent, item_id, "item.md", {
                "type": "item", "id": item_id, "name": nome,
                "weight_kg": peso, "origin": "emergente",
            }, descricao)
            criados.append(item_id)

        _set_field(alvo_folder, "status.esquartejado", True)

        extremo_bom = banda == "farto"
        ruim = banda == "fraco"
        intensity = "medium" if extremo_bom else "small"
        content = (f"Esquartejei {name_of(alvo)} e rendeu fartura de carne."
                   if extremo_bom else
                   f"Esquartejei {name_of(alvo)}, mas rendeu pouco." if ruim else
                   f"Esquartejei {name_of(alvo)}.")
        applied.append({
            "alvo": alvo, "itens": criados, "banda": banda,
            "virada": bool(roll_info.get("virada")),
            "memory": {"content": content, "intensity": intensity, "involved": [],
                       "valence": None,
                       "event": "butcher_farto" if extremo_bom else
                                "butcher_fraco" if ruim else "butcher_medio",
                       "domain": "acougue"}})
    return applied, rejected


@registro.handler("esquartejar_ops")
def _h_esquartejar(cid, af, res, rolls):
    applied, rejected = _apply_esquartejar_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
