"""O Motor / itens — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras do domínio (validação, rolagem, transferência, helpers).
Sem estado de turno, sem LLM — o livro de regras. Ver executores.py.
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
    open_container_for,
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


def _find_item_under(char_folder: Path, item_id: str):
    """(pasta, frontmatter) do item que está COM este personagem — vestido, na mão
    ou guardado em contêiner aberto. None se não está com ele."""
    for sub, fm in _walk_open_items(char_folder):
        if fm.get("id") == item_id:
            return sub, fm
    return None


def _match_scene_ref(ref: str, entries: list[tuple[str, str]]) -> str | None:
    """Resolve uma referência do Árbitro ao id canônico de uma entidade da cena.

    Modelos pequenos escrevem 'Frasco de Tintura Vermelha' ou 'chão da praça do
    mercado' onde o protocolo pede o id exato — em vez de descartar a ação, casamos
    a referência (normalizada) contra id E nome de cada candidato, por igualdade ou
    continência. Só resolve se casar com EXATAMENTE um candidato; ambiguidade ou
    nenhum match devolvem None (quem chama rejeita com motivo, nunca chuta).
    """
    ids = {eid for eid, _ in entries}
    if ref in ids:
        return ref
    s = _slugify(ref)
    if not s:
        return None
    matches = set()
    for eid, name in entries:
        for cand in {_slugify(eid), _slugify(name)}:
            if cand and (s == cand or cand in s or s in cand):
                matches.add(eid)
    return matches.pop() if len(matches) == 1 else None


def _find_item_folder_in_scene(item_id: str, actor_folder: Path | None = None) -> Path | None:
    """Localiza a pasta de um item ALCANÇÁVEL na cena atual — via
    `percepcao.reachable_entities` (spec 036): reach físico puro (is_blocked/chave),
    sem checagem de dono. AMPLIA o que valia antes: hoje um terceiro
    presente só expunha alvo o que tinha DIRETO (vestido/segurado); passa a
    alcançar também o conteúdo GUARDADO dele, se acessível (decisão
    deliberada do mantenedor, FR-008 — ver contracts/steal_e_transfer_alvo.md).
    Retorna None se não estiver ao alcance — quem chama trata como
    movimentação inválida, sem erro fatal.
    """
    if actor_folder is None:
        return None
    actor_fm, _ = read_doc(actor_folder / "character.md")
    actor_id = actor_fm.get("id")
    if not actor_id:
        return None
    achado = percepcao.reachable_entities(actor_id).get(item_id)
    if achado is None or achado["tipo"] != "item":
        return None
    return achado["folder"]


def _validate_move(actor_folder: Path, item_folder: Path, item_fm: dict,
                   dest_kind: str, dest_folder: Path | None,
                   rolls: list | None = None) -> dict | None:
    """Pipeline físico B→C→D de uma movimentação já resolvida (o eixo A — acesso —
    é feito por quem chama, na resolução de referências). Guichê único: a guarda
    do Árbitro valida com os mesmos check_* a partir do contexto; aqui é a versão
    autoritativa sobre os arquivos reais (contracts/equip-tools.md).

    dest_kind: "character" | "container" | "object" | "place".
    """
    item_id = item_fm.get("id")
    actor_fm, _ = read_doc(actor_folder / "character.md")
    actor_id = actor_fm.get("id")
    porter_origem = porter_of(item_folder)
    if dest_kind == "character":
        porter_dest = dest_folder
    elif dest_kind == "container":
        porter_dest = porter_of(dest_folder)
    else:
        porter_dest = None
    peso_item = effective_weight(item_folder)

    # B — origem move: item que não está com o ator, indo para destino sem portador.
    # Zonas determinísticas primeiro; na zona intermediária, TESTE DE FORÇA com
    # rolagem — única, aqui no ponto autoritativo (spec 006).
    if porter_dest is None and porter_origem != actor_folder:
        rej = check_empurrar(actor_id, item_id, peso_item, push_capacity(actor_fm))
        if rej:
            return rej
        rej, roll_info = roll_push_check(actor_fm, actor_id, item_id, peso_item)
        if roll_info is not None and rolls is not None:
            rolls.append(roll_info)
        if rej:
            return rej

    # C — recebedor comporta (contêiner imediato / mão); chão: bypass; object:
    # bypass de encaixe/vaga, mas fechado não recebe (spec 005)
    if dest_kind == "character":
        dest_fm, _ = read_doc(dest_folder / "character.md")
        pega = grasp_slot_of(dest_fm)
        hands = slots_in_use(dest_folder).get(pega) or [] if pega else []
        if item_id not in hands:
            rej = check_mao(dest_fm.get("id"), hands,
                            slot_capacity(dest_fm, pega) if pega else 0)
            if rej:
                return rej
    elif dest_kind == "container":
        cont_fm, _ = read_doc(dest_folder / "item.md")
        cont = cont_fm.get("container")
        if not isinstance(cont, dict) or cont.get("max_size") not in validator.SIZE_ORDER:
            return _fail("nao_e_container", container=cont_fm.get("id"))
        if is_closed(cont_fm):
            return _fail("container_fechado", container=cont_fm.get("id"))
        rej = check_encaixe(item_id, item_size(item_fm),
                            cont_fm.get("id"), cont["max_size"])
        if rej:
            return rej
        rej = check_vaga(cont_fm.get("id"), int(cont.get("max_items") or 0),
                         len(_direct_items(dest_folder)))
        if rej:
            return rej
    elif dest_kind == "object":
        obj_fm, _ = read_doc(dest_folder / "object.md")
        if is_closed(obj_fm):
            return _fail("container_fechado", container=obj_fm.get("id"))

    # D — portador final do destino aguenta o peso (bypass sem portador; a
    # reorganização dentro do mesmo portador não muda o total)
    if porter_dest is not None and porter_dest != porter_origem:
        pd_fm, _ = read_doc(porter_dest / "character.md")
        total_apos = carried_weight(porter_dest) + peso_item
        rej = check_carga(pd_fm.get("id"), item_id, peso_item, total_apos,
                          carry_capacity(pd_fm))
        if rej:
            return rej
    return None


def _set_item_slot(item_folder: Path, slot: str | None) -> None:
    """Grava/limpa `state.slot` do item (invariante: filho direto de personagem ⟺
    slot presente). Escrita atômica via write_doc."""
    fm, body = read_doc(item_folder / "item.md")
    state = fm.get("state") if isinstance(fm.get("state"), dict) else {}
    if slot is None:
        state.pop("slot", None)
    else:
        state["slot"] = slot
    if state:
        fm["state"] = state
    else:
        fm.pop("state", None)
    write_doc(item_folder / "item.md", fm, body)


def _accommodate(dest_root: Path, item_id: str, item_folder: Path,
                 item_fm: dict) -> tuple[Path, str, dict | None]:
    """ACOMODAR o que chega, quando as mãos de quem recebe estão cheias (item 44).

    O caso que abriu os itens 44/45 foi este: dar uma moeda a alguém que segurava uma
    chave e uma veste, recusado por `maos_ocupadas`. Mecanicamente correto, e o
    resultado é que NINGUÉM segurando duas coisas recebe nada — nem uma moeda. Numa
    cena social isso é o gesto mais comum do jogo virando turno perdido. Medido em
    jogo: o Torvin ficou dois dias sem conseguir entregar uma moeda ao Obadiah, que
    estava de mãos cheias justamente com o que Torvin queria receber.

    Duas saídas, nesta ordem — a menos invasiva primeiro:

    (A) O QUE CHEGA vai para um contêiner aberto de quem recebe. Nenhuma mão se
        mexe; ele só não segura o que ganhou. É o que o COMÉRCIO já fazia desde
        sempre para poder pagar com três moedas.
    (B) Se o que chega não cabe em contêiner nenhum (grande demais, tudo lotado),
        LIBERA uma vaga da pega: guarda algo que já estava na mão, e o recebido
        ocupa a vaga aberta. Só desloca o que ACHA onde guardar.

    Nunca larga nada no chão, e nunca desloca o próprio item da ação. Se as duas
    saídas falham, devolve tudo como estava e a recusa `maos_ocupadas` segue valendo —
    agora honesta: não há mesmo onde pôr.

    Devolve (dest_root, dest_kind, acomodacao|None) — `acomodacao` é o que precisa
    ser NARRADO (Princípio X: efeito que ninguém pediu não pode ser silencioso).
    """
    dest_fm, _ = read_doc(dest_root / "character.md")
    pega = grasp_slot_of(dest_fm)
    maos = list(slots_in_use(dest_root).get(pega) or []) if pega else []
    if item_id in maos:
        return dest_root, "character", None
    if check_mao(dest_fm.get("id"), maos,
                 slot_capacity(dest_fm, pega) if pega else 0) is None:
        return dest_root, "character", None      # há vaga: nada a acomodar

    # (A) o recebido cabe numa bolsa dele? Então nenhuma mão precisa se mexer.
    abrigo = open_container_for(dest_root, item_fm, item_folder)
    if abrigo is not None:
        abrigo_fm, _ = read_doc(abrigo / "item.md")
        return abrigo, "container", {
            "modo": "guardou_o_que_recebeu", "quem": dest_fm.get("id"),
            "item": item_id, "para": abrigo_fm.get("id")}

    # (B) abrir uma vaga na pega, guardando o que já estava lá.
    for ocupado in maos:
        if ocupado == item_id:
            continue                              # nunca o item da própria ação
        preso = _find_item_under(dest_root, ocupado)
        if preso is None:
            continue
        preso_folder, preso_fm = preso
        abrigo = open_container_for(dest_root, preso_fm, preso_folder)
        if abrigo is None:
            continue
        destino = abrigo / preso_folder.name
        if destino.exists():
            continue
        io.move_entity(preso_folder, destino)
        _set_item_slot(destino, None)             # guardado não é segurado
        abrigo_fm, _ = read_doc(abrigo / "item.md")
        return dest_root, "character", {
            "modo": "liberou_a_mao", "quem": dest_fm.get("id"),
            "item": ocupado, "para": abrigo_fm.get("id")}

    return dest_root, "character", None           # sem saída: a recusa segue valendo


def transfer_item(
    item_id: str, actor_folder: Path, dest_id, scene: dict,
    rolls: list | None = None,
) -> tuple[dict | None, dict | None]:
    """A PRIMITIVA de transferência (spec 037, Princípio XII): move UM item para um
    destino, revalidando o pipeline físico único contra os arquivos. SEM memória,
    SEM emprestimo/intenção — só a FÍSICA (acessibilidade→encaixe→vaga→slot→mão→carga)
    e o deslocamento de pasta (via `io.move_entity`). Quem dá SENTIDO (a memória de
    doação, o dono de fato, a intenção cumprida) é o CHAMADOR: `give` a orquestra e
    grava; `steal` e `persuade_give` reusam a MESMA primitiva (nunca tool→tool).

    `item_id` e `dest_id` são ids EXATOS (já resolvidos). `scene` traz a cena lida
    fresca: {chars, objects, items, location_folder, place_id}. `actor_folder` é a
    pasta da ORIGEM — em `persuade_give`, o ALVO/doador; nunca se assume o ator do
    turno. Devolve (applied|None, rejection|None); (None, None) = já estava no destino.
    Assume o WRITE_LOCK.
    """
    present_chars = scene["chars"]
    present_objects = scene["objects"]
    present_items = scene["items"]
    location_folder = scene["location_folder"]
    place_id = scene["place_id"]
    base = {"item": item_id, "to": dest_id}
    # destino: personagem, object (baú), item-contêiner (bolsa) presentes, ou o
    # próprio lugar (largar no chão).
    if dest_id in present_chars:
        dest_root, dest_kind = present_chars[dest_id], "character"
    elif dest_id in present_objects:
        dest_root, dest_kind = present_objects[dest_id], "object"
    elif dest_id in present_items:
        # itens re-resolvem a pasta na hora — um transfer anterior pode tê-la movido
        dest_root, dest_kind = _find_item_folder_in_scene(dest_id, actor_folder), "container"
    elif dest_id is not None and dest_id == place_id:
        dest_root, dest_kind = location_folder, "place"
    else:
        dest_root, dest_kind = None, ""
    if dest_root is None:
        return None, {**base, "why": "destinatário não presente na cena (ou ambíguo)"}
    item_folder = _find_item_folder_in_scene(item_id, actor_folder) if item_id else None
    if item_folder is None:
        return None, {**base, "why": "item não existe na cena nem em inventário presente"}
    if dest_root == item_folder or item_folder in dest_root.parents:
        return None, {**base, "why": "um contêiner não pode entrar em si mesmo"}
    if dest_root / item_folder.name == item_folder:
        return None, None  # já está no destino — nada a fazer
    item_fm, _ = read_doc(item_folder / "item.md")
    # ITEM 44 — quem recebe ACOMODA, em vez de recusar por mãos cheias. Pode
    # REDIRECIONAR o destino (para uma bolsa dele) ou deslocar o que estava na mão,
    # e por isso roda ANTES de `dest` ser fixado e do pipeline físico validar.
    acomodou = None
    if dest_kind == "character":
        dest_root, dest_kind, acomodou = _accommodate(dest_root, item_id,
                                                      item_folder, item_fm)
    dest = dest_root / item_folder.name
    if dest == item_folder:
        return None, None
    if dest.exists():
        return None, {**base, "why": "colisão de nome no destino"}
    # pipeline físico único (spec 004): B origem move; C recebedor comporta;
    # D portador final aguenta. A primeira falha nega com motivo estruturado.
    rej = _validate_move(actor_folder, item_folder, item_fm, dest_kind,
                         dest_root, rolls)
    if rej:
        return None, _rejection(base, rej)
    io.move_entity(item_folder, dest)  # rename atômico, mesmo padrão de enter_route
    # invariante do acoplamento: filho direto de personagem ⟺ state.slot.
    # spec 019: o slot é o de PEGA do recebedor (mão/boca), não fixo em "mao".
    slot_pega = (grasp_slot_of(_char_fm(dest_root)) or HAND_SLOT) \
        if dest_kind == "character" else None
    _set_item_slot(dest, slot_pega)
    saida = dict(base)
    if acomodou:
        # VIAJA no applied para virar frase: o Princípio X não admite que o mundo
        # guarde algo de alguém em silêncio. Quem narra é o `@inworld` do canal.
        saida["acomodou"] = acomodou
    return saida, None


def _corrigivel_reject(transfer: dict, regra: str, validos: list[dict]) -> dict:
    """Empacota uma recusa CORRIGÍVEL (item 31): erro de ESCOLHA do Árbitro (item
    errado), não veredito do mundo. Marca `corrigivel` e leva os `validos` (o que é
    possível agora) — é o que o porteiro fazia no pré-voo, agora vindo da autoridade.
    O `arbiter._err` a formata sem o "não refaça" do Princípio X."""
    base = {k: v for k, v in transfer.items() if k in ("item", "to")}
    rej = _rejection(base, _fail(regra))
    rej["corrigivel"] = True
    rej["validos"] = sorted(validos, key=lambda v: v["id"])
    return rej


def _held_items(actor_folder: Path, present_items: dict) -> list[dict]:
    """Itens que o ATOR realmente segura na mão (não vestidos) — os validos de uma
    recusa de posse/slot em give/drop/stow."""
    actor_fm, _ = read_doc(actor_folder / "character.md")
    hand = grasp_slot_of(actor_fm) or HAND_SLOT
    out = []
    for iid, folder in present_items.items():
        if porter_of(folder) != actor_folder:
            continue
        ifm, _ = read_doc(folder / "item.md")
        slot = (ifm.get("state") or {}).get("slot")
        if slot and slot != hand:  # vestido não conta como "na mão"
            continue
        out.append({"id": iid, "nome": ifm.get("name") or ""})
    return out


def _loose_items(present_items: dict) -> list[dict]:
    """Itens SOLTOS (sem portador — no chão ou dentro de object) — os validos de uma
    recusa de shove (empurra-se só o que ninguém carrega)."""
    out = []
    for iid, folder in present_items.items():
        if porter_of(folder) is not None:
            continue
        ifm, _ = read_doc(folder / "item.md")
        out.append({"id": iid, "nome": ifm.get("name") or ""})
    return out


def _equippable_items(actor_folder: Path, present_items: dict) -> list[dict]:
    """Itens VESTÍVEIS ao alcance do ator (soltos ou já dele) — validos de uma recusa
    de equip (não se veste o que está com outra pessoa)."""
    out = []
    for iid, folder in present_items.items():
        if porter_of(folder) not in (None, actor_folder):
            continue
        ifm, _ = read_doc(folder / "item.md")
        w = ifm.get("wearable")
        if isinstance(w, dict) and w.get("slot"):
            out.append({"id": iid, "nome": ifm.get("name") or ""})
    return out


def _equipped_items(actor_folder: Path, present_items: dict) -> list[dict]:
    """Itens VESTIDOS no ator (filhos diretos, slot ≠ mão) — validos de uma recusa de
    unequip (só se tira o que está vestido em quem age)."""
    actor_fm, _ = read_doc(actor_folder / "character.md")
    hand = grasp_slot_of(actor_fm) or HAND_SLOT
    out = []
    for iid, folder in present_items.items():
        if folder.parent != actor_folder:
            continue
        ifm, _ = read_doc(folder / "item.md")
        slot = (ifm.get("state") or {}).get("slot")
        if slot and slot != hand:
            out.append({"id": iid, "nome": ifm.get("name") or ""})
    return out


def roll_steal_check(actor_fm: dict, char_id: str, alvo_id: str, item_id: str,
                     exposicao: int, nivel_crime: float = 0.0,
                     rolls: list | None = None) -> tuple[str, dict]:
    """Devolve (desfecho, roll_info). desfecho ∈
    {'impossivel','limpo','flagrado_levou','flagrado_vazio'}.

    Curva da persuasão (persuade_dc), UMA rolagem: `d20 + mod(DEX) + nivel_crime`
    vs DC. Extremos deterministas: exposição 0 = impossível às claras (sem dado);
    10 = trivial, limpo (sem dado) — a proficiência NUNCA entra neles. Entre 1-9,
    a DISTÂNCIA à DC governa o flagrante:
      passou (total ≥ DC) → LIMPO; falhou por ≤5 → FLAGRADO mas levou (o agarrão);
      falhou por >5 → FLAGRADO e vazio. Nota/DC são segredo do mundo.

    `nivel_crime` (spec 051) é a proficiência do ladrão no domínio `"crime"`
    (`memoria.proficiencies_for`, fator contínuo assintótico) — todo furto já
    carimbava `domain: "crime"` desde a spec 029, e agora esse acúmulo VOLTA como
    bônus. Soma DIRETO no total, decidindo o PRÓPRIO desfecho — mesmo papel que
    `nivel_cozinha` cumpre em `cook` e `nivel_acougue` em `butcher`, divergência
    deliberada de `cura` (lá a proficiência só ajusta a magnitude depois do
    desfecho já decidido).
    """
    exposicao = int(exposicao)
    if exposicao <= 0:
        info = {"tipo": "furto", "personagem": char_id, "alvo": alvo_id,
                "item": item_id, "resultado": "impossivel",
                "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "impossivel", info
    if exposicao >= 10:
        info = {"tipo": "furto", "personagem": char_id, "alvo": alvo_id,
                "item": item_id, "resultado": "limpo",
                "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return "limpo", info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("DEX", 10))
    dc = rolagem.persuade_dc(exposicao)
    total = d20 + mod + float(nivel_crime)
    if total >= dc:
        desfecho = "limpo"
    elif dc - total <= 5:
        desfecho = "flagrado_levou"
    else:
        desfecho = "flagrado_vazio"
    info = {
        "tipo": "furto", "personagem": char_id, "alvo": alvo_id, "item": item_id,
        "resultado": desfecho,
        # virada: um furto que a nota dizia fácil (exposição alta) e deu ruim, ou vice
        "virada": (exposicao >= 6 and desfecho != "limpo")
                  or (exposicao <= 4 and desfecho == "limpo"),
        "critico": ("sucesso" if (d20 == 20 and desfecho == "limpo")
                    else "falha" if (d20 == 1 and desfecho == "flagrado_vazio") else None),
        "rolagem": {"d20": d20, "mod": mod,
                    "nivel_crime": round(float(nivel_crime), 2),
                    "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return desfecho, info


def roll_toxicidade_check(actor_fm: dict, char_id: str, item_id: str,
                          toxicidade: int, rolls: list | None = None) -> tuple[bool, dict]:
    """Devolve (adoeceu, roll_info) — o teste de resistência de `eat` (spec 046).

    Curva PRÓPRIA (`rolagem.toxin_dc`, inclinação inversa de `persuade_dc`: nota
    ALTA = mais arriscado = DC mais alta). UMA rolagem: d20 + mod(CON) vs DC.
    Extremos deterministas: toxicidade 0 = nunca adoece (sem dado); 10 = sempre
    adoece (sem dado). O Árbitro só julgou O RISCO; quem decide se o personagem
    de fato adoeceu é este teste — nunca a nota sozinha."""
    toxicidade = int(toxicidade)
    if toxicidade <= 0:
        info = {"tipo": "toxicidade", "personagem": char_id, "item": item_id,
                "adoeceu": False, "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return False, info
    if toxicidade >= 10:
        info = {"tipo": "toxicidade", "personagem": char_id, "item": item_id,
                "adoeceu": True, "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return True, info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("CON", 10))
    dc = rolagem.toxin_dc(toxicidade)
    total = d20 + mod
    adoeceu = total < dc
    info = {
        "tipo": "toxicidade", "personagem": char_id, "item": item_id,
        "adoeceu": adoeceu,
        # virada: a nota dizia arriscado (>=6) e resistiu, ou dizia seguro (<=4) e adoeceu
        "virada": (toxicidade >= 6 and not adoeceu) or (toxicidade <= 4 and adoeceu),
        "critico": ("sucesso" if (d20 == 20 and not adoeceu)
                    else "falha" if (d20 == 1 and adoeceu) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return adoeceu, info


def roll_embriaguez_check(actor_fm: dict, char_id: str, alvo_id: str,
                          embriaguez: int, rolls: list | None = None) -> tuple[bool, dict]:
    """Devolve (embebedou, roll_info) — o teste de resistência de `drink` (spec
    047), INDEPENDENTE de `roll_toxicidade_check` (o mesmo item/fonte pode falhar
    nos dois testes ao mesmo tempo — R9 do research).

    MESMA forma de `roll_toxicidade_check`: `rolagem.alcohol_dc`, UMA rolagem
    `d20 + mod(CON)` vs DC. Extremos deterministas: embriaguez 0 = nunca embebeda
    (sem dado); 10 = sempre embebeda (sem dado). `alvo_id` é o id de um ITEM ou de
    um OBJECT (fonte ambiental) — a função não distingue, o teste é o mesmo."""
    embriaguez = int(embriaguez)
    if embriaguez <= 0:
        info = {"tipo": "embriaguez", "personagem": char_id, "alvo": alvo_id,
                "embebedou": False, "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return False, info
    if embriaguez >= 10:
        info = {"tipo": "embriaguez", "personagem": char_id, "alvo": alvo_id,
                "embebedou": True, "virada": False, "critico": None, "rolagem": None}
        if rolls is not None:
            rolls.append(info)
        return True, info
    d20 = rolagem._roll_d20()
    mod = rolagem.attr_modifier((actor_fm.get("attributes") or {}).get("CON", 10))
    dc = rolagem.alcohol_dc(embriaguez)
    total = d20 + mod
    embebedou = total < dc
    info = {
        "tipo": "embriaguez", "personagem": char_id, "alvo": alvo_id,
        "embebedou": embebedou,
        # virada: a nota dizia forte (>=6) e resistiu, ou dizia fraca (<=4) e embebedou
        "virada": (embriaguez >= 6 and not embebedou) or (embriaguez <= 4 and embebedou),
        "critico": ("sucesso" if (d20 == 20 and not embebedou)
                    else "falha" if (d20 == 1 and embebedou) else None),
        "rolagem": {"d20": d20, "mod": mod, "total": total, "dc": dc},
    }
    if rolls is not None:
        rolls.append(info)
    return embebedou, info


