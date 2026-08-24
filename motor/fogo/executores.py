"""O Motor / fogo — EXECUTORES (item 31 §3: DDD por domínio; spec 053).

`_apply_fogo_ops` (valida contra os arquivos, rola, aplica) + o
`@registro.handler` `_h_fogo`. A ÚNICA decisão não-determinística é a rolagem de
IGNIÇÃO — o Árbitro julgou a cena, o Motor decide se pegou.

DUAS divergências deliberadas de `cook`, e as duas têm motivo:

  · os materiais são consumidos SÓ NO ÊXITO. Em `cook` os ingredientes somem no ato
    porque sempre nasce um prato, ainda que ruim — nada se perde. Aqui a falha não
    produz nada, então destruir o material seria punição dupla.
  · a fonte de fogo NÃO guarda `ator`. Um fogo aceso não ocupa quem o acendeu (ao
    contrário da panela), então `trabalho.is_busy` não o enxerga, e quem apagar é
    avisado pelos PRESENTES, não pelo dono.
"""
from __future__ import annotations

import time
from pathlib import Path

from .. import fisica, io, memoria, registro, trabalho
from ..io import _fail, _rejection, name_of, read_doc

from .primitivas import duracao_fogo_s, roll_kindle_check


def _apply_fogo_ops(character_id: str, actor_folder: Path, resolution: dict,
                    rolls: list | None = None) -> tuple[list, list]:
    """Acender fogo (spec 053). O gate de admissão (combustibilidade) rejeita — COM
    memória embutida (`op["memory"]`, small, recorrente, mesmo padrão de
    `cook`/`eat`/`drink`). Passando o gate: rola IGNIÇÃO (com a proficiência em
    "fogo" somada DIRETO no total) -> na falha, preserva os materiais e cobra fadiga
    de tentativa fracassada -> no êxito, consome os materiais e instancia a fonte."""
    applied, rejected = [], []
    if not resolution.get("fogo_ops"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if trabalho.is_busy(actor_folder):
        rejected.append(_fail("ocupado_para_acender"))
        return applied, rejected
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    _, _, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)

    for op in resolution.get("fogo_ops") or []:
        materiais = list(op.get("materiais") or [])
        base = {"acender": materiais}
        material_folders: list[tuple[str, Path]] = []
        faltando = None
        for mid in materiais:
            folder = present_items.get(mid)
            if folder is None:
                faltando = mid
                break
            material_folders.append((mid, folder))
        if faltando is not None:
            rejected.append(_rejection(base, _fail("material_inacessivel", item=faltando)))
            continue
        if not material_folders:
            rejected.append(_rejection(base, _fail("sem_combustivel")))
            continue

        if int(op.get("combustibilidade") or 0) <= 0:
            rejected.append({
                **base, "regra": "nao_queima", "valores": {"materiais": materiais},
                "why": io._WHY_BY_REGRA["nao_queima"],
                "memory": {
                    "content": "Tentei acender aquilo, mas não era coisa que queime.",
                    "intensity": "small", "involved": list(materiais),
                    "valence": {m: memoria.NEGATIVA for m in materiais},
                    # UMA memória por MOTIVO, sem o id do alvo — molde exato de
                    # `cozinhar\x00nao_cozinhavel`. Tentar pedra e depois metal é o
                    # MESMO fato ("isso não queima"), não dois. Sem `domain`: recusa
                    # de mérito não ensina ofício nenhum.
                    "about": "acender\x00nao_queima", "reincidencia": "tentei",
                    "event": "kindle_refused"}})
            continue

        favorabilidade = int(op.get("favorabilidade") or 5)
        nivel_fogo = memoria.proficiencies_for(character_id).get("fogo", 0.0)
        pegou, roll_info = roll_kindle_check(actor_fm, favorabilidade, nivel_fogo, rolls)

        if not pegou:
            # Os materiais CONTINUAM no mundo — a falha não destrói nada. Fadiga de
            # tentativa fracassada, um degrau abaixo do êxito (spec 043, 2.4.3).
            fisica.spend_fatigue(character_id, fisica.custo_da_falha("medio"))
            rejected.append({
                **base, "regra": "nao_pegou", "valores": {"materiais": materiais},
                "why": io._WHY_BY_REGRA["nao_pegou"],
                "virada": bool(roll_info.get("virada")),
                "memory": {
                    "content": "Tentei acender o fogo e a chama não pegou.",
                    "intensity": "small", "involved": list(materiais), "valence": None,
                    "about": "acender\x00nao_pegou", "reincidencia": "tentei",
                    "event": "kindle_falha"}})
            continue

        nome = (op.get("nome") or "").strip() or "Fogo"
        descricao = (op.get("descricao") or "").strip() or "Uma chama acesa."
        nome_final = (op.get("nome_final") or "").strip() or "Cinzas"
        descricao_final = (op.get("descricao_final") or "").strip() or "Cinzas frias."

        for _mid, folder in material_folders:
            io.remove_entity(folder)  # consumo total — exceção escopada do Princípio IV

        # A FONTE DE FOGO é um `object`: coisa do lugar, não posse. Por isso fica fora
        # de take/give/stow/drop sem NENHUMA guarda nova, e por isso entra de graça em
        # `cook_fonte`/`forge_fonte` — que são `sorted(idx["objects"]) + [place_id]`.
        fogo_id = io.new_id("fogo")
        io.create_entity(actor_folder.parent, fogo_id, "object.md", {
            "type": "object", "id": fogo_id, "name": nome, "origin": "emergente",
            trabalho.BLOCO: {
                "tool": "kindle_fire",
                "pronto_ts": time.time() + duracao_fogo_s(int(op.get("duracao") or 0)),
                # `extinto` faz a fonte SAIR de cena ao vencer, sem deletar o arquivo:
                # o vestígio fica com a data, para uma investigação futura achar.
                "resultado": {"nome": nome_final, "description": descricao_final,
                              "extinto": True},
            },
            # SEM `ator`: o fogo queima sozinho e não prende quem o acendeu.
        }, descricao)

        applied.append({
            "materiais": materiais, "fogo": fogo_id,
            "virada": bool(roll_info.get("virada")),
            "memory": {"content": f"Acendi {nome}.", "intensity": "small",
                       "involved": [fogo_id], "valence": None,
                       # SEM `about`: cada fogueira é fato PRÓPRIO. Com `about`, todas
                       # as fogueiras da vida virariam um arquivo de peso fixo e a
                       # proficiência congelaria — é o que faz a prática ensinar.
                       "event": "kindle_fire", "domain": "fogo"}})
    return applied, rejected


@registro.handler("fogo_ops")
def _h_fogo(cid, af, res, rolls):
    applied, rejected = _apply_fogo_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ator, applied E rejected) via react_actor_memory
