"""O Motor / itens — EXECUTORES (item 31 §3: DDD por domínio).

`_apply_*_ops` (valida contra os arquivos, rola, aplica) e os `@registro.handler`
`_h_*` (encadeiam memória). Chamam as primitivas do domínio. Sem LLM/turno.
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

from .. import combate, deslocamento, estado, fisica, intencoes, io, memoria, percepcao, registro, rolagem
from ..combate import (
    roll_push_check,
)
from ..deslocamento import (
    _enter_route_locked,
)
from ..estado import (
    _set_field,
)
from ..fisica import (
    HAND_SLOT,
    _direct_items,
    _walk_open_items,
    carried_weight,
    carry_capacity,
    check_carga,
    check_empurrar,
    check_encaixe,
    check_mao,
    check_slot,
    check_vaga,
    effective_weight,
    porter_of,
    grasp_slot_of,
    has_accessible_item,
    is_closed,
    item_size,
    item_slot,
    push_capacity,
    slot_capacity,
    slots_in_use,
)
from ..io import (
    MotorError,
    _GROUND_WORDS,
    _char_fm,
    _fail,
    _rejection,
    _slugify,
    find_character_folder,
    read_doc,
    write_doc,
)
from ..memoria import (
    _write_memory,
)



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
    roll_steal_check,
    transfer_item,
)

def _apply_movement(character_id: str, route_id: str) -> dict:
    """Deslocamento como resolução: entra na rota, ou registra a tentativa negada.

    Assume o WRITE_LOCK já em mãos (chamado de dentro de apply_resolution).
    Inclui um narrative_hint próprio, pois o desfecho real (partiu / não partiu)
    só é conhecido aqui — não no Árbitro.
    """
    result = _enter_route_locked(character_id, route_id)
    if result.get("moved"):
        hint = (
            f"Você deixa o lugar e segue pela {result['route_name']} "
            f"rumo a {result['destination_name']}."
        )
        # ANDAR é a ação mais comum do jogo, e não deixava lembrança nenhuma:
        # este caminho faz early-return de `apply_resolution`, então
        # `_record_events` nunca rodava aqui. A viagem era narrada (o hint acima)
        # e esquecida no mesmo instante.
        try:
            _write_memory(
                find_character_folder(character_id),
                f"Segui pela {result['route_name']} rumo a "
                f"{result['destination_name']}.",
                intensity="small",  # spec 038 (T016): ex-_RELEVANCE_BY_EVENT["travel"]
            )
        except MotorError:
            pass
        return {
            "applied": [{
                "target": character_id, "movement": route_id,
                "destination": result["destination"], "reason": "entrou na rota",
            }],
            "rejected": [],
            "movement": result,
            "narrative_hint": hint,
        }

    # negado: FR-014 — há consequência, mas sem sair do lugar.
    reason = result.get("reason") or "o caminho não se abriu"
    actor_folder = find_character_folder(character_id)
    action = f"tentou partir, mas {reason}"
    _set_field(actor_folder, "status.action", action)
    return {
        "applied": [{
            "target": character_id, "path": "status.action", "value": action,
            "reason": "tentativa de deslocamento negada (FR-014)",
        }],
        "rejected": [{"movement": route_id, "why": reason}],
        "movement": result,
        "narrative_hint": action[0].upper() + action[1:],
    }


def _apply_equip_ops(
    character_id: str, actor_folder: Path, resolution: dict,
    rolls: list | None = None,
) -> tuple[list[dict], list[dict]]:
    """Aplica as operações de vestir/tirar decididas pelo Árbitro (`equip_ops`),
    revalidando o pipeline físico contra os arquivos reais (autoritativo).

    - equip {item}: acopla no slot declarado no `wearable.slot` do próprio item;
      move a pasta para o personagem quando o item vem de fora da estrutura dele.
    - unequip {item, to}: libera o slot; `to` = o próprio ator (vai para a mão,
      pasta não se move), um contêiner com vaga, ou o chão (id do lugar).
    """
    applied, rejected = [], []
    if not resolution.get("equip_ops"):
        return applied, rejected
    location_folder = actor_folder.parent
    present_chars, present_objects, present_items = io._scene_entities(location_folder)  # cena fresca (025)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected

    for op in resolution.get("equip_ops") or []:
        if not isinstance(op, dict) or op.get("op") not in ("equip", "unequip"):
            continue
        kind = op.get("op")
        item_id = op.get("item")
        item_folder = _find_item_folder_in_scene(item_id, actor_folder) if item_id else None
        if item_folder is None:
            rejected.append(_rejection(op, _fail("item_inacessivel", item=item_id)))
            continue
        item_fm, _ = read_doc(item_folder / "item.md")

        if kind == "equip":
            # AUTORIDADE ÚNICA (item 31): não se veste o que está com OUTRA pessoa —
            # regra que era pré-voo da tool. Recusa corrigível, com os vestíveis à mão.
            if porter_of(item_folder) not in (None, actor_folder):
                rejected.append(_corrigivel_reject(op, "item_alheio",
                                                   _equippable_items(actor_folder, present_items)))
                continue
            wearable = item_fm.get("wearable")
            slot = wearable.get("slot") if isinstance(wearable, dict) else None
            # spec 019: "não se veste" é o item SEM slot declarado. Se ele declara
            # um slot mas o corpo do ator não o tem, isso é recusa de check_slot
            # (`corpo_sem_slot`), não "não vestível".
            if not isinstance(slot, str) or not slot:
                rejected.append(_rejection(op, _fail("item_nao_vestivel", item=item_id)))
                continue
            in_use = slots_in_use(actor_folder).get(slot) or []
            if item_id in in_use:
                continue  # já vestido — nada a fazer
            rej = check_slot(item_id, slot, in_use, slot_capacity(actor_fm, slot))
            if rej is None and porter_of(item_folder) != actor_folder:
                peso = effective_weight(item_folder)
                total_apos = carried_weight(actor_folder) + peso
                rej = check_carga(character_id, item_id, peso, total_apos,
                                  carry_capacity(actor_fm))
            if rej:
                rejected.append(_rejection(op, rej))
                continue
            dest = actor_folder / item_folder.name
            if dest != item_folder:
                if dest.exists():
                    rejected.append({**op, "why": "colisão de nome no destino"})
                    continue
                io.move_entity(item_folder, dest)
            _set_item_slot(dest, slot)
            applied.append({"op": "equip", "item": item_id, "slot": slot})
            continue

        # unequip — só se tira o que está VESTIDO em quem age (item 31: autoridade
        # única, era pré-voo da tool). Recusa corrigível, com os vestidos como validos.
        # Item na mão (slot de pega) não conta como vestido — não há o que "tirar".
        hand = grasp_slot_of(actor_fm) or HAND_SLOT
        slot_atual = item_slot(item_fm)
        if item_folder.parent != actor_folder or not slot_atual or slot_atual == hand:
            rejected.append(_corrigivel_reject(op, "nao_vestido_em_voce",
                                               _equipped_items(actor_folder, present_items)))
            continue
        to = op.get("to") or character_id
        if to == character_id:  # para o slot de pega (mão/boca): só o state.slot muda
            pega = grasp_slot_of(actor_fm)
            hands = slots_in_use(actor_folder).get(pega) or [] if pega else []
            if item_id in hands:
                continue  # já está na mão/boca
            rej = check_mao(character_id, hands,
                            slot_capacity(actor_fm, pega) if pega else 0)
            if rej:
                rejected.append(_rejection(op, rej))
                continue
            _set_item_slot(item_folder, pega)
            applied.append({"op": "unequip", "item": item_id, "to": character_id})
            continue
        # para um contêiner ou para o chão: mesma física de qualquer movimentação
        place_fm = {}
        for fname in ("location.md", "route.md"):
            if (location_folder / fname).exists():
                place_fm, _ = read_doc(location_folder / fname)
                break
        if to == place_fm.get("id"):
            dest_root, dest_kind = location_folder, "place"
        else:
            dest_root = _find_item_folder_in_scene(to, actor_folder)
            dest_kind = "container"
        if dest_root is None:
            rejected.append(_rejection(op, _fail("destino_inacessivel", destino=to)))
            continue
        if dest_root == item_folder or item_folder in dest_root.parents:
            rejected.append({**op, "why": "um contêiner não pode entrar em si mesmo"})
            continue
        rej = _validate_move(actor_folder, item_folder, item_fm, dest_kind,
                             dest_root, rolls)
        if rej:
            rejected.append(_rejection(op, rej))
            continue
        dest = dest_root / item_folder.name
        if dest.exists():
            rejected.append({**op, "why": "colisão de nome no destino"})
            continue
        io.move_entity(item_folder, dest)
        _set_item_slot(dest, None)
        applied.append({"op": "unequip", "item": item_id, "to": to})
    return applied, rejected


def _apply_item_transfers(
    character_id: str, actor_folder: Path, resolution: dict,
    rolls: list | None = None,
) -> tuple[list[dict], list[dict]]:
    """`give`/`take`/`stow`/`drop` — ORQUESTRA `transfer_item` (spec 037). Este corpo
    é o SENTIDO da tool `give`: resolve as referências FROUXAS do Árbitro
    ('Frasco de Tintura Vermelha', 'chão da praça') para ids exatos, chama a primitiva
    `transfer_item` para a física, e faz `intention_id`/`emprestimo` atravessarem até o
    applied (a memória e o dono-de-fato moram em `memoria._record_transfer`, no wrapper
    `_h_transfer`). `item` MUST estar presente; `to` MUST ser personagem, contêiner ou
    o próprio lugar. Entradas inválidas voltam em `rejected` (devlog), nunca descarte
    silencioso.
    """
    applied, rejected = [], []
    if not resolution.get("item_transfers"):
        return applied, rejected
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    location_folder = actor_folder.parent
    place_id, place_name = None, ""
    for fname in ("location.md", "route.md"):
        place_file = location_folder / fname
        if place_file.exists():
            place_fm, _ = read_doc(place_file)
            place_id = place_fm.get("id")
            place_name = place_fm.get("name") or ""
            break

    # spec 025 (Fase C): a cena é LIDA FRESCA aqui, não recebida congelada.
    present_chars, present_objects, present_items = io._scene_entities(location_folder)
    scene = {"chars": present_chars, "objects": present_objects,
             "items": present_items, "location_folder": location_folder,
             "place_id": place_id}

    # índice id+nome da cena para resolver referências frouxas do Árbitro.
    def _entries(folders: dict, filename: str) -> list[tuple[str, str]]:
        out = []
        for eid, folder in folders.items():
            fm, _ = read_doc(folder / filename)
            out.append((eid, fm.get("name") or ""))
        return out

    item_entries = _entries(present_items, "item.md")
    dest_entries = (
        _entries(present_chars, "character.md")
        + _entries(present_objects, "object.md")
        + item_entries
        + ([(place_id, place_name)] if place_id else [])
    )

    for transfer in resolution.get("item_transfers") or []:
        if not isinstance(transfer, dict):
            continue
        item_ref = transfer.get("item")
        to_ref = transfer.get("to")
        if not item_ref or not to_ref:
            continue
        # "chão"/"solo" na referência ganham precedência (intenção de largar).
        if place_id and (_GROUND_WORDS & set(_slugify(to_ref).split("-"))):
            to = place_id
        else:
            to = _match_scene_ref(to_ref, dest_entries)
        item_id = _match_scene_ref(item_ref, item_entries)
        if item_id is None:
            # a referência era um OBJECT da cena? mobília, não item portável (spec 002/004)
            obj_entries = _entries(present_objects, "object.md")
            obj_ref = _match_scene_ref(item_ref, obj_entries)
            if obj_ref is not None:
                rejected.append(_rejection({**transfer, "item": obj_ref},
                                          _fail("objeto_fixo", objeto=obj_ref)))
                continue
            rejected.append({**transfer,
                             "why": "item não existe na cena nem em inventário presente"})
            continue
        # AUTORIDADE ÚNICA (item 31): a posse/slot/soltura que a tool pré-checava mora
        # aqui agora, no executor, e a recusa é CORRIGÍVEL — leva os `validos` (o que é
        # possível) para o modelo trocar de item sem re-tentar às cegas.
        # give/drop: só o que o ATOR tem na mão · give/drop/stow: item DESVESTIDO ·
        # shove: só o que NINGUÉM carrega (empurra-se o solto, larga-se o que se segura).
        mode = transfer.get("mode")
        if mode in ("give", "drop", "stow", "shove"):
            item_folder = present_items.get(item_id)
            hand = grasp_slot_of(actor_fm) or HAND_SLOT
            if mode in ("give", "drop") and porter_of(item_folder) != actor_folder:
                rejected.append(_corrigivel_reject(transfer, "nao_possui_item",
                                                   _held_items(actor_folder, present_items)))
                continue
            if mode == "shove" and porter_of(item_folder) is not None:
                rejected.append(_corrigivel_reject(transfer, "item_carregado",
                                                   _loose_items(present_items)))
                continue
            it_fm, _ = read_doc(item_folder / "item.md")
            slot = (it_fm.get("state") or {}).get("slot")
            if mode != "shove" and slot and slot != hand:
                rejected.append(_corrigivel_reject(transfer, "item_vestido",
                                                   _held_items(actor_folder, present_items)))
                continue
        ap, rej = transfer_item(item_id, actor_folder, to, scene, rolls)
        if rej is not None:
            rejected.append(rej)
            continue
        if ap is None:
            continue  # já está no destino — nada a fazer
        # SENTIDO do give: intention_id (spec 027) e emprestimo (spec 036) atravessam
        # até o applied; a física em si não sabe nada deles.
        if transfer.get("intention_id"):
            ap["intention_id"] = transfer["intention_id"]
        if transfer.get("emprestimo"):
            ap["emprestimo"] = True
        applied.append(ap)
    return applied, rejected


# --------------------------------------------------------------------------- #
# Roubar (spec 023) — subtrair um item de outro presente SEM consentimento.
# Furtividade (DEX) vs a exposição do furto (nota do Árbitro, lida da prosa).
# Três desfechos por distância à DC: limpo · flagrado-mas-levou · flagrado-vazio.
# --------------------------------------------------------------------------- #

def _apply_steal_ops(character_id: str, actor_folder: Path, resolution: dict,
                     rolls: list | None = None) -> tuple[list, list]:
    """Furtar itens de outros presentes (spec 023). LIMPO/FLAGRADO-levou movem o
    item ao ladrão; FLAGRADO-vazio não move. O flagrante vira memória negativa no
    DONO (large → portão de trauma), gravada em _record_stolen. Assume WRITE_LOCK."""
    applied, rejected = [], []
    if not resolution.get("steal_ops"):
        return applied, rejected
    present_chars, present_objects, present_items = io._scene_entities(actor_folder.parent)  # cena fresca (025)
    actor_fm, _ = read_doc(actor_folder / "character.md")
    if fisica.is_resting(actor_fm):  # spec 031: auto-suficiência, nível 0
        rejected.append(_fail("descansando"))
        return applied, rejected
    for op in resolution.get("steal_ops") or []:
        alvo = op.get("alvo")
        item_id = op.get("item")
        exposicao = op.get("exposicao")
        base = {"roubar": item_id, "de": alvo}
        if alvo == character_id:
            rejected.append({**base, "why": "não se rouba de si mesmo"})
            continue
        if alvo not in present_chars:
            rejected.append(_rejection(base, _fail("personagem_inacessivel", alvo=alvo)))
            continue
        if _find_item_under(present_chars[alvo], item_id) is None:
            rejected.append(_rejection(base, _fail("item_nao_e_do_alvo", item=item_id, alvo=alvo)))
            continue
        desfecho, info = roll_steal_check(
            actor_fm, character_id, alvo, item_id, exposicao, rolls)
        if desfecho == "impossivel":
            rejected.append(_rejection(base, _fail("furto_impossivel", item=item_id)))
            continue
        levou = desfecho in ("limpo", "flagrado_levou")
        flagrado = desfecho in ("flagrado_levou", "flagrado_vazio")
        if levou:
            # spec 037: reusa a PRIMITIVA de transferência (nunca a tool give). O
            # SENTIDO do furto (memória negativa no dono, se flagrado) mora em
            # _record_stolen — a primitiva não grava nada.
            scene = {"chars": present_chars, "objects": present_objects,
                     "items": present_items, "location_folder": actor_folder.parent,
                     "place_id": None}
            t_ap, t_rej = transfer_item(item_id, actor_folder, character_id, scene, rolls)
            if t_ap is None:
                why = (t_rej or {}).get("why", "não coube na mão do ladrão")
                rejected.append({**base, "why": why})
                continue
        applied.append({"de": alvo, "item": item_id, "flagrado": flagrado,
                        "levou": levou, "virada": bool(info.get("virada")),
                        "exposicao": exposicao})   # spec 024: ruído do leque de testemunha
        # spec 030: tensão/agilidade. spec 043: o furto que FALHOU (flagrado sem levar)
        # já cansava o CHEIO — agora cansa um degrau abaixo, para não punir demais quem
        # tentou e não levou nada.
        fisica.spend_fatigue(character_id,
                             "medio" if levou else fisica.custo_da_falha("medio"))
    return applied, rejected


@registro.handler("equip_ops")
def _h_equip(cid, af, res, rolls):
    applied, rejected = _apply_equip_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória do ator via react_actor_memory (spec 038)


@registro.handler("item_transfers")
def _h_transfer(cid, af, res, rolls):
    applied, rejected = _apply_item_transfers(cid, af, res, rolls)
    for ap in applied:
        # spec 027: fechar a PRÓPRIA intenção é um bônus sobre a transferência,
        # NUNCA pode virar `rejected` — `give` aplica por-op via _apply_op_now
        # (arbiter.py), que trata QUALQUER rejeição como "a op inteira foi
        # negada", mas a transferência real já aconteceu neste ponto. Falha
        # aqui fica só anotada dentro do próprio applied (contracts/, FR-007).
        intention_id = ap.pop("intention_id", None)
        if intention_id:
            ap["intention_closed"] = intencoes.close_intention(af, intention_id)
    # memória do ator (e do receptor/dono-de-fato) via react_actor_memory (spec 038):
    # a reação recompõe a cena com o MESMO `io._scene_entities(af.parent)`.
    return applied, rejected, []


@registro.handler("steal_ops")
def _h_steal(cid, af, res, rolls):
    applied, rejected = _apply_steal_ops(cid, af, res, rolls)
    return applied, rejected, []  # memória (ladrão e dono flagrado) via react_actor_memory (spec 038)
