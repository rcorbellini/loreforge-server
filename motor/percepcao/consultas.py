"""O Motor / percepcao (spec 021 — extraído de __init__).

Parte do pacote em níveis. Ver research.md (T001) para o grafo de dependências.
"""
from __future__ import annotations

import os
import random
import re
import threading
import time
import uuid
import unicodedata
from pathlib import Path

import frontmatter
import validator

from .. import deslocamento, fisica, intencoes, io, memoria, registro, rotas
from ..deslocamento import (
    lazy_evaluate,
)
from ..fisica import (
    hunger_label,
    fatigue_label,
    _inside_closed,
    _direct_items,
    _is_wide_open,
    _walk_open_items,
    body_of,
    carried_item_ids,
    carried_weight,
    carry_capacity,
    effective_weight,
    grasp_slot_of,
    has_accessible_item,
    is_closed,
    is_currency,
    is_down,
    is_for_sale,
    is_negotiable,
    item_own_weight,
    item_size,
    item_slot,
    push_capacity,
    slot_capacity,
    slots_in_use,
    value_of,
)
from ..io import (
    MotorError,
    WORLD_DIR,
    _char_fm,
    _is_valid,
    find_character_folder,
    find_entity,
    read_doc,
)
from ..memoria import (
    ROTA,
    _FAMILIARIDADE_PISO,
    _INTENSITY_ORDER,
    _MEMORY_CONTEXT_CAP,
    _expire_memories,
    _is_alive,
    _memory_salience,
    _recency_label,
    _short_summary,
    sentiment_label,
    dono,
    familiarity_label,
    familiarity_with,
    get_active_memories,
    memory_involved,
    memory_kind,
    sentiment_toward,
)
from ..rotas import (
    _available_routes,
)


def item_physics(fm: dict, folder: Path | None = None) -> dict:
    """Bloco físico de um item para o contexto (Mente e guarda do Árbitro)."""
    container = fm.get("container")
    cont = None
    if isinstance(container, dict) and container.get("max_size"):
        cont = {
            "max_size": container.get("max_size"),
            "max_items": container.get("max_items"),
            "itens": len(_direct_items(folder)) if folder else 0,
            "fechado": is_closed(fm),
        }
    wearable = fm.get("wearable")
    bloco = {
        "size": item_size(fm),
        "weight_kg": round(effective_weight(folder) if folder else item_own_weight(fm), 3),
        "veste_em": wearable.get("slot") if isinstance(wearable, dict) else None,
        "container": cont,
        "slot": item_slot(fm),
    }
    # Comércio (spec 011). Estas marcas descem ao contexto pelo critério do
    # Princípio IX — PERCEPÇÃO, não conveniência: uma banca mostra o que está à
    # venda e por quanto, e o que não está exposto simplesmente não se vê como
    # disponível. Só aparecem quando declaradas; item sem marca não vira ruído.
    if is_for_sale(fm):
        bloco["for_sale"] = True
    if is_negotiable(fm):
        bloco["negotiable"] = True
    if is_currency(fm):
        bloco["currency"] = True
    preco = value_of(fm)
    if preco is not None:
        bloco["value"] = preco
    return bloco


def _character_summary(folder: Path, self_id: str) -> dict:
    fm, _ = read_doc(folder / "character.md")
    status = fm.get("status") or {}
    # spec 019: "mãos" na verdade é o SLOT DE PEGA deste corpo (a boca do cão), e
    # a capacidade sai dele. Os nomes maos_* seguem no contrato por estabilidade.
    pega = grasp_slot_of(fm)
    hands = (slots_in_use(folder).get(pega) or []) if pega else []
    cap_pega = slot_capacity(fm, pega) if pega else 0
    return {
        "id": fm.get("id"),
        "name": fm.get("name"),
        "state": "self" if fm.get("id") == self_id else "idle",
        "action": status.get("action"),
        "mood": status.get("mood"),
        "conditions": status.get("conditions") or [],
        # O que os OUTROS veem: apenas o acoplado ao corpo (vestido/segurado).
        # Item guardado dentro de contêiner é invisível a terceiros (spec 004,
        # FR-009) — o que está no bolso não se vê. Pra SI MESMO (spec 036,
        # FR-010) a visão é a mesma que `self.inventory`/`get_inventory` já
        # usam — `_nested_item_refs`, recursiva e sem a opacidade de
        # terceiro — não `_visible_item_refs`, que ficaria incorreta pro
        # próprio personagem quando `visible_entities` virar simétrica.
        "carrying": (_nested_item_refs(folder) if fm.get("id") == self_id
                    else _visible_item_refs(folder)),
        # física visível do corpo: pega e folga de carga (a guarda do Árbitro
        # valida dar/receber sem expor atributos crus de terceiros)
        "fisico": {
            "maos_livres": max(0, cap_pega - len(hands)),
            "maos_totais": cap_pega,
            "pega_slot": pega,
            "maos_ocupadas_por": hands,
            "carga_livre_kg": round(carry_capacity(fm) - carried_weight(folder), 3),
        },
    }


# --------------------------------------------------------------------------- #
# Pertencimento por memória (spec 036) — primitivos de nível 0.
#
# Quatro perguntas, quatro funções, um consumidor cada: `carried_item_ids` (física
# pura), `is_blocked` (barreira física condicional), `reachable_entities` (furto/
# transferência), `visible_entities` (narração), `dono` (memória — a única que
# precisa dela) e `offerable_entities` (comércio, walk próprio). Ver
# specs/036-pertencimento-por-memoria/data-model.md para as fórmulas.
# --------------------------------------------------------------------------- #

def is_blocked(personagem_id: str, no_folder: Path, no_fm: dict) -> bool:
    """Barreira física: fechado E sem chave acessível. `is_closed` sozinho
    NÃO basta — um contêiner fechado cuja chave o ator carrega não bloqueia
    (reusa `has_accessible_item`, spec 005, a mesma checagem que a ação de
    abrir já usa)."""
    if not is_closed(no_fm):
        return False
    locks = no_fm.get("locks") if isinstance(no_fm.get("locks"), dict) else {}
    camadas = locks.get("open") or []
    if not camadas:
        return True  # fechado, sem trava declarada: nenhuma chave possível
    try:
        actor_folder = find_character_folder(personagem_id)
    except MotorError:
        return True
    for lock in camadas:
        if not isinstance(lock, dict) or lock.get("type") != "item":
            continue
        required = lock.get("required")
        if not required or not has_accessible_item(actor_folder, required, no_folder):
            return True
    return False


def _walk_scene(location_folder: Path, para_em, incluir_barrado: bool = True) -> dict[str, dict]:
    """Anda pela cena inteira (personagens presentes, objects, itens soltos) e
    recursivamente pelo que cada um contém, parando de descer sempre que
    `para_em(pasta, fm, tipo)` for True.

    `incluir_barrado` distingue dois usos: `reachable_entities`/`visible_entities` querem o nó
    BARRADO ainda assim visível como objeto — só o que está DENTRO dele que
    some (a mochila fechada continua ali, opaca por dentro). `offerable_entities`
    quer o oposto — barrado por `dono` significa EXCLUÍDO de vez, não só
    "recursão parada" (não é seu, não aparece, ponto). `tipo` é
    'character', 'object' ou 'item'."""
    out: dict[str, dict] = {}

    def _no(child: Path, fm: dict, tipo: str) -> None:
        eid = fm.get("id")
        if not eid:
            return
        barrado = para_em(child, fm, tipo)
        if not barrado or incluir_barrado:
            out[eid] = {"folder": child, "fm": fm, "tipo": tipo}
        if not barrado:
            for neto, nfm in _direct_items(child):
                _no(neto, nfm, "item")

    for child in sorted(location_folder.iterdir()):
        if not child.is_dir():
            continue
        if (child / "character.md").exists():
            fm, _ = read_doc(child / "character.md")
            _no(child, fm, "character")
        elif (child / "object.md").exists():
            fm, _ = read_doc(child / "object.md")
            _no(child, fm, "object")
        elif (child / "item.md").exists():
            fm, _ = read_doc(child / "item.md")
            _no(child, fm, "item")
    return out


def _location_folder_of(personagem_id: str) -> Path | None:
    try:
        folder = find_character_folder(personagem_id)
    except MotorError:
        return None
    return folder.parent


def reachable_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` consegue TOCAR fisicamente na cena atual — walk
    parando SÓ em `is_blocked`. Nenhuma checagem de dono; QUALQUER personagem
    presente (o próprio ou outro) é atravessado pela mesma regra — um
    personagem só barra a recursão se ELE MESMO estiver bloqueado (hoje
    nenhum declara isso). Consumidor: `itens._find_item_folder_in_scene`
    (alvo de `item_transfers`/`steal`) — amplia o alvo hoje possível para
    dentro do conteúdo guardado (aberto) de terceiros."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}
    return _walk_scene(loc, lambda f, fm, t: is_blocked(personagem_id, f, fm))


def _is_imperceptible(personagem_id: str, no_folder: Path, no_fm: dict) -> bool:
    """Um recipiente VESTIDO/SEGURADO (`state.slot` presente) por QUALQUER
    personagem — o próprio incluído — é opaco por dentro, independente de
    aberto/fechado — EXCETO se declarado ESCANCARADO (`state.fechado:
    false` explícito, spec 011): aí o gesto deliberado de exibir vence, e o
    conteúdo se vê como qualquer contêiner aberto. Sem slot (location/
    object), a percepção usa `is_blocked` como proxy."""
    if item_slot(no_fm):
        return not _is_wide_open(no_fm)
    return is_blocked(personagem_id, no_folder, no_fm)


def visible_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` PERCEBE/nomeia na cena atual — walk parando em
    não-perceptível. Simétrico: nem o próprio dono percebe o conteúdo do
    que veste/segura (sabe por `dono`, memória, nunca por percepção).
    Consumidor: `_visible_item_refs` (contexto de cena/narração)."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}
    return _walk_scene(
        loc, lambda f, fm, t: _is_imperceptible(personagem_id, f, fm)
    )


def offerable_entities(personagem_id: str) -> dict[str, dict]:
    """O que `personagem_id` pode OFERECER — walk PRÓPRIO (não interseção de
    outros primitivos: uma interseção ingênua reabriria o furo que esta
    checagem fecha, ver research.md §6/§10), parando em `is_blocked` OU em
    `dono(nó, personagem_id) != personagem_id` — a MESMA checagem pra
    qualquer tipo de nó. `object` nunca aciona a segunda condição (nunca é
    alvo de `dono` de ninguém — não é tipo possuível); `location` nem chega
    a ser nó, é só a raiz do walk. Consumidor: `comercio.py`, exclusivamente."""
    loc = _location_folder_of(personagem_id)
    if loc is None:
        return {}

    def _para(f: Path, fm: dict, tipo: str) -> bool:
        if is_blocked(personagem_id, f, fm):
            return True
        if tipo == "object":
            return False
        return dono(fm.get("id"), personagem_id) != personagem_id

    return _walk_scene(loc, _para, incluir_barrado=False)


def _visible_item_refs(char_folder: Path) -> list[dict]:
    """Itens visíveis de um personagem para TERCEIROS: os filhos diretos
    (vestidos/segurados), com o slot e a física de cada um. O conteúdo dos
    contêineres fica oculto (FR-009), mas a existência do contêiner não.

    EXCEÇÃO — o contêiner ESCANCARADO (spec 011): quem declara `state.fechado:
    false` deixou a coisa aberta DE PROPÓSITO, e o que está dentro se vê. É a
    banca do mascate com a caixa aberta na praça: não precisa perguntar, está à
    mostra. Estar à venda continua não bastando — o que basta é estar aberto.

    Por que a marca explícita e não a mera ausência: `fechado` ausente é o estado
    de toda bolsa do mundo (ninguém declara), então tratar ausência como "à
    mostra" tornaria público o dinheiro que cada um carrega no bolso. Ausente
    segue privado-mas-usável; `false` é o gesto deliberado de escancarar.
    """
    refs = []
    for child, fm in _direct_items(char_folder):
        if not _is_valid(fm):
            continue
        refs.append({"id": fm.get("id"), "name": fm.get("name"),
                     **item_physics(fm, child)})
        if _is_wide_open(fm):
            for neto, nfm in _walk_open_items(child):
                if not _is_valid(nfm):
                    continue
                refs.append({"id": nfm.get("id"), "name": nfm.get("name"),
                             "a_mostra_em": fm.get("id"),
                             **item_physics(nfm, neto)})
    return refs


def _nested_item_refs(container_folder: Path) -> list[dict]:
    """Itens aninhados dentro de um contêiner — object (loot de um baú) ou personagem
    (inventário), com aninhamento arbitrário.

    Não vão para `items_present` (ficam fora da lista ambiente — spec 002, Decisão 2), mas
    A Mente e o Árbitro precisam desta referência para poder revelar/transferir o item
    quando uma ação o justificar. Para o PRÓPRIO personagem, cada entrada traz a física e
    o estado (vestido/segurado/guardado); para terceiros use _visible_item_refs (FR-009).
    """
    is_char = (container_folder / "character.md").exists()
    # spec 019: "segurado" é o que está no slot de PEGA deste corpo (ou legado sem
    # slot), o resto é "vestido".
    pega = grasp_slot_of(_char_fm(container_folder)) if is_char else None
    refs = []
    # atravessa só contêineres ABERTOS: o que está em contêiner fechado é
    # invisível até para o portador (spec 005, FR-002)
    for child, fm in _walk_open_items(container_folder):
        if not _is_valid(fm):
            continue
        ref = {"id": fm.get("id"), "name": fm.get("name"),
               **item_physics(fm, child)}
        if is_char:
            if child.parent == container_folder:
                slot = item_slot(fm)
                ref["estado"] = "segurado" if slot in (pega, None) else "vestido"
            else:
                ref["estado"] = "guardado"
        refs.append(ref)
    return refs


def _location_lineage(place_folder: Path) -> dict | None:
    """A location mais PRÓXIMA que contém `place_folder`, com um ponteiro
    recursivo `pertence_a` pra quem contém ELA — mesma forma da árvore de
    pastas de verdade (spec 035: região contém cidade, cidade contém lugar,
    lugar contém quarto). É uma ESTRUTURA aninhada, não uma lista: quem lê não
    precisa de nenhuma convenção de ordem pra saber quem está dentro de quem,
    é literal — `pertence_a.pertence_a.pertence_a...` até `None` (o lugar não
    está aninhado em nada, ou chegou ao topo da árvore). A chave se repete de
    propósito em cada nível: é a MESMA relação (X pertence a Y) aplicada de
    novo a Y, não uma relação diferente — dois nomes pra isso só confundiria
    quem lê sem ganhar nada.

    Puramente derivado da árvore de pastas para exibição (Fluxo 2, leitura):
    não é dado novo em frontmatter algum. Carrega também o `narrative` (body)
    de cada nível — não só pra UI (que só precisa de `name`), mas pra A Mente
    poder tecer a cidade/região na narração sem repetir prosa em cada location
    filha (mesmo canal de `location.narrative`, um nível acima).
    """
    cur = place_folder.parent
    while cur != WORLD_DIR and cur.parent != cur:
        loc_file = cur / "location.md"
        if loc_file.exists():
            fm, body = read_doc(loc_file)
            if fm.get("id"):
                return {
                    "id": fm["id"],
                    "name": fm.get("name"),
                    "narrative": body,
                    "pertence_a": _location_lineage(cur),
                }
        cur = cur.parent
    return None


def get_context(character_id: str) -> dict:
    """Monta o proximity_context do lugar atual do personagem.

    O "lugar" pode ser uma location OU uma route (personagem em trânsito). Nos dois
    casos, quem estiver na mesma pasta coexiste e pode interagir (FR-021).

    Roda a avaliação preguiçosa antes de montar o bundle (FR-020, FR-022, FR-028).
    """
    lazy_evaluate()

    char_folder = find_character_folder(character_id)
    place_folder = char_folder.parent
    route_file = place_folder / "route.md"
    loc_file = place_folder / "location.md"
    in_transit = route_file.exists()
    place_file = route_file if in_transit else loc_file
    if place_file.exists():
        place_fm, place_body = read_doc(place_file)
    else:
        place_fm, place_body = {}, ""

    characters_present = []
    items_present = []
    objects_present = []
    for child in sorted(place_folder.iterdir()):
        if not child.is_dir():
            continue
        if (child / "character.md").exists():
            fm_c, _ = read_doc(child / "character.md")
            if not _is_valid(fm_c):  # inválido: fora do mundo jogável (FR-010)
                continue
            characters_present.append(_character_summary(child, character_id))
        elif (child / "object.md").exists():
            obj_fm, _ = read_doc(child / "object.md")
            if not _is_valid(obj_fm):
                continue
            # itens aninhados dentro deste object (ex.: loot de um baú) não entram em
            # items_present — ficam ocultos da lista ambiente até uma ação os liberar
            # (spec 002, Decisão 2). Mas o Árbitro precisa SABER que existem para poder
            # revelá-los/transferi-los — "contains" carrega essa referência interna.
            objects_present.append({
                "id": obj_fm.get("id"),
                "name": obj_fm.get("name"),
                "interactions": obj_fm.get("interactions"),
                # fechado esconde o conteúdo até do Árbitro-contexto (spec 005)
                "contains": [] if is_closed(obj_fm) else _nested_item_refs(child),
                "fechado": is_closed(obj_fm),
                # tem fecho declarado? (para o manifest de open/close)
                "tem_fecho": ("fechado" in (obj_fm.get("state") or {})
                              or bool(obj_fm.get("locks"))),
            })
        elif (child / "item.md").exists():
            item_fm, _ = read_doc(child / "item.md")
            if not _is_valid(item_fm):
                continue
            entry = {
                "id": item_fm.get("id"),
                "name": item_fm.get("name"),
                "interactions": item_fm.get("interactions"),
                **item_physics(item_fm, child),
            }
            # contêiner ABERTO no chão expõe o que tem (spec 005); fechado, nada
            if isinstance(item_fm.get("container"), dict):
                entry["contains"] = [] if is_closed(item_fm) \
                    else _nested_item_refs(child)
            items_present.append(entry)

    self_fm, self_body = read_doc(char_folder / "character.md")
    _self_pega = grasp_slot_of(self_fm)  # spec 019: slot de pega do ator (mão/boca)
    routes = [] if in_transit else _available_routes(place_fm.get("id"))

    return {
        "location": {
            "id": place_fm.get("id"),
            "name": place_fm.get("name"),
            "narrative": place_body,
            "pertence_a": _location_lineage(place_folder),
        },
        "in_transit": in_transit,
        "routes": routes,
        "characters_present": characters_present,
        "items_present": items_present,
        "objects_present": objects_present,
        # a cena EVOCA: quem está presente e onde se está decidem o que volta à
        # mente, junto com o que está vívido por si (spec 013)
        "memories": get_active_memories(
            char_folder,
            evoked_by={c["id"] for c in characters_present if c.get("id")}
            | ({place_fm.get("id")} if place_fm.get("id") else set()),
        ),
        # o que o personagem PRETENDE — nunca o que viveu (spec 026). Consultivo
        # de client (Princípio IX nível 2), disponível à Mente antes de decidir,
        # por sussurro ou pelo gatilho autônomo.
        "intentions": intencoes.get_active_intentions(char_folder),
        "self": {
            "id": self_fm.get("id"),
            "name": self_fm.get("name"),
            "attributes": self_fm.get("attributes") or {},
            "skills": self_fm.get("skills") or {},
            "status": self_fm.get("status") or {},
            # A NECESSIDADE EM RÓTULO (item 51, fatia 1). ADITIVO: `status` segue
            # cru ao lado, porque a régua do Motor precisa do número. Isto é o que
            # desce à Mente — e o que faltava para o personagem poder SABER que
            # está com fome. Ver `fisica.hunger_label`.
            "necessidade": {
                "fome": hunger_label(self_fm),
                "cansaco": fatigue_label(self_fm),
            },
            "body": self_body,
            "inventory": _nested_item_refs(char_folder),
            # física do corpo (spec 004): a Mente narra esforço, a guarda valida
            "fisico": {
                "capacidade_carga_kg": carry_capacity(self_fm),
                "capacidade_empurrar_kg": push_capacity(self_fm),
                "peso_carregado_kg": round(carried_weight(char_folder), 3),
                # spec 019: "mãos" = o slot de pega do corpo (mão / boca / ...)
                "maos_livres": max(0, slot_capacity(self_fm, _self_pega)
                               - len(slots_in_use(char_folder).get(_self_pega) or []))
                               if _self_pega else 0,
                "maos_totais": slot_capacity(self_fm, _self_pega) if _self_pega else 0,
                "pega_slot": _self_pega,
                # spec 019: o próprio corpo do ator (mapa slot->capacidade). É a
                # anatomia dele — expô-la ao próprio dono não é metagaming, e o
                # guard de equipar precisa da capacidade de um slot QUALQUER.
                "corpo": body_of(self_fm),
                "slots_ocupados": {s: ids for s, ids
                                   in slots_in_use(char_folder).items()},
            },
        },
    }


def get_character(character_id: str) -> dict:
    folder = find_character_folder(character_id)
    fm, body = read_doc(folder / "character.md")
    return {"frontmatter": fm, "body": body}


def list_characters() -> list[dict]:
    """Lista todos os personagens do mundo (para o seletor do client)."""
    chars = []
    for path in sorted(WORLD_DIR.rglob("character.md")):
        fm, _ = read_doc(path)
        if not _is_valid(fm):  # personagem inválido não entra no seletor (FR-010)
            continue
        location = path.parent.parent
        loc_file = location / "location.md"
        loc_name = None
        if loc_file.exists():
            loc_fm, _ = read_doc(loc_file)
            loc_name = loc_fm.get("name")
        chars.append({
            "id": fm.get("id"),
            "name": fm.get("name"),
            "location": loc_name,
        })
    return chars


def _inventory_nodes(folder: Path) -> list[dict]:
    """Coleta recursivamente os itens (pastas com item.md) sob `folder`."""
    nodes = []
    for child in sorted(folder.iterdir()):
        if not child.is_dir() or child.name == "memories":
            continue
        item_file = child / "item.md"
        if item_file.exists():
            fm, body = read_doc(item_file)
            if not _is_valid(fm):  # item inválido some da árvore (FR-010)
                continue
            nodes.append({
                "id": fm.get("id"),
                "name": fm.get("name"),
                "kind": "item",
                # acoplamento ao corpo (spec 004): presente só nos filhos diretos
                # do personagem — o HUD rotula "às costas", "na mão" etc.
                "slot": item_slot(fm),
                # fechado esconde os filhos até do dono (spec 005)
                "fechado": is_closed(fm),
                "children": [] if is_closed(fm) else _inventory_nodes(child),
            })
    return nodes


def get_inventory(character_id: str) -> dict:
    folder = find_character_folder(character_id)
    fm, _ = read_doc(folder / "character.md")
    return {
        "id": fm.get("id"),
        "name": fm.get("name"),
        "kind": "character",
        "children": _inventory_nodes(folder),
    }


def get_entity_detail(entity_id: str) -> dict:
    found = find_entity(entity_id)
    if found is None:
        raise MotorError(f"entidade não encontrada: '{entity_id}'.")
    _, fm, body = found
    detail = {"name": fm.get("name"), "kind": fm.get("type"), "description": body}
    # atributos/skills/status são in-world para um personagem
    if fm.get("type") == "character":
        detail["attributes"] = fm.get("attributes") or {}
        detail["skills"] = fm.get("skills") or {}
        detail["status"] = fm.get("status") or {}
    return detail


def _observer_can_look(character_id: str) -> None:
    """Quem está CAÍDO não observa (spec 018, bug de percepção): um incapacitado ou
    morto não olha em volta. Barra a consulta na origem — o olho não é ação, mas
    percepção, e a percepção também cessa quando se cai.
    """
    try:
        fm, _ = read_doc(find_character_folder(character_id) / "character.md")
    except MotorError:
        return
    if is_down(fm):
        raise MotorError("não há como observar enquanto se está caído.")


def _perceivable_ids(ctx: dict) -> set:
    """Os ids que o personagem PERCEBE agora (anti-metagaming): o lugar, as saídas,
    quem/o que está presente, o que ele carrega, e o conteúdo de contêiner aberto.

    Extraído do `observe_entity` para o reconhecer (spec 018) reusar o MESMO
    recorte — o reconhecimento nunca alcança o que o olhar não alcança.
    """
    allowed = {(ctx.get("location") or {}).get("id")}
    for r in ctx.get("routes", []):
        allowed.add(r.get("id"))
    for c in ctx.get("characters_present", []):
        allowed.add(c.get("id"))
    for o in ctx.get("objects_present", []):
        allowed.add(o.get("id"))
    for it in ctx.get("items_present", []):
        allowed.add(it.get("id"))
        for sub in it.get("contains") or []:  # contêiner aberto no chão (spec 005)
            allowed.add(sub.get("id"))
    for it in (ctx.get("self") or {}).get("inventory") or []:
        allowed.add(it.get("id"))
    allowed.discard(None)
    return allowed


def observe_entity(character_id: str, entity_id: str) -> dict:
    """Descreve uma entidade que o personagem PERCEBE agora — leitura pura, sem LLM.

    Recorte de percepção (anti-metagaming): só o lugar atual, as saídas, quem/o que
    está presente na cena e os próprios pertences. Conteúdo de contêiner fechado e
    entidades de outros lugares são negados — o que o jogador lê nunca ultrapassa o
    que o personagem vê. Nenhuma escrita: é a face consultiva da fronteira do server.
    """
    _observer_can_look(character_id)
    ctx = get_context(character_id)
    if entity_id not in _perceivable_ids(ctx):
        raise MotorError("isso não está ao alcance do seu olhar agora.")
    detail = get_entity_detail(entity_id)
    status = detail.get("status") or {}
    rec = recognition_of(character_id, entity_id)  # o mesmo recorte já validou o alcance
    return {
        "observer": (ctx.get("self") or {}).get("name"),
        "name": detail.get("name"),
        "kind": detail.get("kind"),
        "description": detail.get("description") or "",
        "action": status.get("action"),
        "mood": status.get("mood"),
        # spec 018: o olho passa a levar o RECONHECIMENTO (vivência) para A Mente
        # tecer. Rótulos + episódios, nunca número.
        "familiaridade": rec["familiaridade"],
        "afeto": rec["afeto"],
        "grau": rec["grau"],
        "memorias_vivas": rec["memorias_vivas"],
    }


# _scene_entities MUDOU para io.py (nível 0, spec 025), reexportado aqui para os
# chamadores antigos (`from .percepcao import _scene_entities`) seguirem válidos.
from ..io import _scene_entities  # noqa: E402,F401


def prose_of(character_id: str, entity_id: str) -> str | None:
    """O texto descritivo de uma entidade ao alcance — a prosa, como está escrita.

    Este é o encanamento que faltava. Até a spec 014, a descrição de um item era
    DESCARTADA antes de chegar a quem arbitra: `get_context` não a punha em
    `items_present`, e o prompt recortava de novo. Só `location` levava texto.
    O projeto dependia de campo declarado porque a alternativa era fisicamente
    impossível (Princípio XI).

    Vai SOB DEMANDA, nunca no contexto de toda cena: a taverna tem 26 itens
    presentes, e embutir a descrição de todos degradaria as decisões de todo
    turno, não só as de leitura.

    O texto vai COMO ESTÁ — sem resumo e sem interpretação prévia. Resumir seria
    decidir por quem lê, e a prosa é justamente o insumo da decisão.

    Devolve None se não houver nada ao alcance com esse id, ou se o que há não
    tiver texto nenhum.
    """
    if not entity_id:
        return None
    try:
        actor = find_character_folder(character_id)
    except MotorError:
        return None
    place = actor.parent

    # o lugar onde ele está, e as entidades dentro dele ou dele mesmo
    for filename in ("location.md", "route.md"):
        f = place / filename
        if f.exists():
            fm, body = read_doc(f)
            if fm.get("id") == entity_id:
                return (body or "").strip() or None

    for base in (actor, place):
        for filename in ("item.md", "object.md", "character.md"):
            for path in base.rglob(filename):
                fm, body = read_doc(path)
                if fm.get("id") != entity_id:
                    continue
                # o fecho esconde o conteúdo de TODOS os caminhos de leitura,
                # e este não é exceção (FR-018)
                if _inside_closed(path.parent, base):
                    return None
                return (body or "").strip() or None
    return None


def recognition_of(character_id: str, entity_id: str) -> dict:
    """O RECONHECIMENTO de uma entidade percebida (spec 018) — leitura pura, sem LLM.

    Compõe o que 013/015/016 já produzem: a PROSA (o que a coisa é), a
    FAMILIARIDADE e o AFETO (peso e rumo, em RÓTULO — nunca número) e as MEMÓRIAS
    VIVAS (o porquê). É material para A MENTE tecer; o servidor não interpreta, e
    o número não sai. Respeita o mesmo recorte de percepção do `observe_entity`.

    GRADUADO (saber/reconhecer da 013): memória viva → NÍTIDO (com episódios);
    familiaridade acima do piso mas sem memória viva → VAGO (a história desbotou);
    senão → AUSENTE (só o estático).
    """
    _observer_can_look(character_id)
    ctx = get_context(character_id)
    if entity_id not in _perceivable_ids(ctx):
        raise MotorError("isso não está ao alcance do seu olhar agora.")
    detail = get_entity_detail(entity_id)
    fam = familiarity_with(character_id, entity_id)
    saldo = sentiment_toward(character_id, entity_id)
    vivas = remembered_about(character_id, entity_id)
    if vivas:
        grau = "nitido"
    elif fam > _FAMILIARIDADE_PISO:
        grau = "vago"
    else:
        grau = "ausente"
    afeto = sentiment_label(saldo)
    return {
        "id": entity_id,   # para o client deduplicar (ambiente + tool) e referenciar
        "name": detail.get("name"),
        "kind": detail.get("kind"),
        "prosa": detail.get("description") or "",
        "familiaridade": familiarity_label(fam),
        # None quando não pende, para A Mente não inventar sentimento
        "afeto": afeto if abs(saldo) >= 2 else None,
        "grau": grau,
        # o porquê: só no nítido, e só o texto e a recência (nunca número)
        "memorias_vivas": ([{"conteudo": m.get("content") or m.get("summary") or "",
                             "recencia": m.get("recency")} for m in vivas]
                           if grau == "nitido" else []),
    }


_RECOGNITION_SCENE_CAP = 6


def scene_recognitions(character_id: str) -> list[dict]:
    """Os reconhecimentos das entidades PERCEBIDAS com vivência (spec 018).

    Cor ambiente: A Mente tinge a narração de cada turno com a história do
    personagem. Só entra quem PESA (grau nítido, ou vago com familiaridade
    acima de um piso mais alto) — a maioria dos itens de uma cena não gera nada,
    e a narração não incha. Teto de N.
    """
    try:
        _observer_can_look(character_id)
    except MotorError:
        return []   # caído não reconhece nada — a cena não se tinge
    ctx = get_context(character_id)
    self_id = (ctx.get("self") or {}).get("id")
    out = []
    for eid in _perceivable_ids(ctx):
        if eid == self_id:
            continue
        try:
            pac = recognition_of(character_id, eid)
        except MotorError:
            continue
        if pac["grau"] == "nitido" or (
                pac["grau"] == "vago"
                and familiarity_with(character_id, eid) >= 3 * _FAMILIARIDADE_PISO):
            out.append(pac)
    # os mais fortes primeiro; teto
    out.sort(key=lambda p: (p["grau"] != "nitido", ))
    return out[:_RECOGNITION_SCENE_CAP]


def remembered_about(quem_id: str, sobre_id: str) -> list[dict]:
    """O que `quem` guarda A RESPEITO DE `sobre` — consulta de SERVER (spec 015).

    Este é o encanamento que faltava, e é a terceira vez que o projeto esbarra
    na mesma parede: `_character_summary` entrega de cada presente apenas id,
    nome, ação, humor, condições e o que ele veste — nada do que ele lembra. O
    Árbitro era, portanto, INCAPAZ de saber que o homem a quem se pergunta o
    caminho é o mesmo que levou uma surra de quem pergunta, ainda que o mundo
    tenha gravado a surra fielmente. A nota de disposição sairia do nada.

    O recorte é pela RELAÇÃO, nunca a mente inteira: só as memórias que envolvem
    `sobre`. Mandar tudo viraria dump da vida interior alheia e ainda diminuiria
    o sinal — o modelo teria de achar a agressão no meio de trinta lembranças de
    taverna.

    Só as VIVAS. É o que faz o rancor esfriar sem nenhum mecanismo de perdão: o
    relógio da spec 013 já faz esse trabalho, e uma segunda regra de
    esquecimento seria duas verdades sobre a mesma relação.

    Irmã textual de `familiarity_with`, que já lê a mesma interseção para medir
    intimidade por volume. Aquela devolve um número; esta devolve o que foi
    vivido, porque quem vai ler é uma inteligência e não uma fórmula.

    Genérica de propósito (FR-007d): persuadir, negociar e atacar podem passar a
    ler a relação por aqui, sem campo novo e sem duplicar a predicação de vida.
    """
    try:
        folder = find_character_folder(quem_id)
    except MotorError:
        return []
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return []
    _expire_memories(folder)  # preguiçoso, no escopo de quem está sendo lido
    now = time.time()
    out = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        if not _is_alive(fm, now):
            continue
        if sobre_id not in memory_involved(fm):
            continue
        ts_start = fm.get("timestamp_start") or now
        age = max(0.0, now - ts_start)
        out.append({
            "id": fm.get("id"),
            "intensity": fm.get("intensity"),
            "summary": (fm.get("summary") or "").strip() or _short_summary(body),
            "content": body,
            "timestamp_start": ts_start,
            "recency": _recency_label(age),
            "salience": _memory_salience(fm.get("intensity"), age),
        })
    out.sort(key=lambda m: (
        0 if m.get("salience") == "vivida" else 1,
        _INTENSITY_ORDER.get(m.get("intensity"), 99),
        -(m.get("timestamp_start") or 0),
    ))
    return out[:_MEMORY_CONTEXT_CAP]


# --------------------------------------------------------------------------- #
# consultar_memoria (spec 040) — a Mente PUXA um fato da própria memória.
#
# Co-localizada aqui porque reusa o MESMO maquinário de `remembered_about`/
# `get_active_memories` (vida, saliência, recência, `memory_involved`). LEITURA:
# devolve PROSA, nunca número/valência (Princípios V/IX); a escrita segue no
# Árbitro (Princípio III). Lane de consulta paralela — não toca a mutação.
# --------------------------------------------------------------------------- #

_THEME_EVENTS = ("witness_theft", "theft", "steal")


def recall(character_id: str, args: dict | None = None) -> dict:
    """O que o personagem lembra a respeito de `sobre` (prosa livre). Filtra as
    PRÓPRIAS memórias vivas por SUJEITO (id/nome citado em `sobre`) e por TEMA
    (domínio/evento — ex.: furto→crime). Devolve `{sobre, lembra}` em prosa;
    ausência é reportada como ausência, nunca inventada."""
    sobre = ((args or {}).get("sobre") or "").strip()
    low = sobre.lower()
    ausencia = {"sobre": sobre, "lembra": "Você não guarda nenhuma lembrança sobre isso."}
    try:
        folder = find_character_folder(character_id)
    except MotorError:
        return ausencia
    mem_dir = folder / "memories"
    if not mem_dir.is_dir():
        return ausencia
    _expire_memories(folder)
    now = time.time()
    quer_tema = any(k in low for k in ("furt", "roub", "ladr", "crime"))
    hits = []
    for path in sorted(mem_dir.glob("*.md")):
        fm, body = read_doc(path)
        if fm.get("type") != "memory" or memory_kind(fm) == ROTA:
            continue
        if not _is_alive(fm, now):
            continue
        sujeito = False
        for inv in memory_involved(fm):
            for tok in str(inv).lower().split("-"):
                if len(tok) >= 3 and tok in low:
                    sujeito = True
                    break
            if sujeito:
                break
        tema = quer_tema and (fm.get("domain") == "crime"
                              or str(fm.get("evento") or "") in _THEME_EVENTS)
        # PELO TEXTO também (item 52.2). Antes só `involved` (ids) e tema casavam — e
        # aí o que a memória diz EM PALAVRAS era inconsultável. Ficou evidente com a
        # memória de pergunta-sem-resposta: o ASSUNTO ("o deus do santuário") não é
        # entidade, então não pode estar em `involved`; ele mora no texto. Sem isto o
        # personagem gravava "já perguntei isso" e não conseguia achar de volta —
        # metade do conserto do laço, e a metade que faltava.
        #
        # Piso de 4 letras e no mínimo DUAS palavras casando: com 3 letras, "que"/
        # "com"/"uma" faziam qualquer pergunta casar qualquer memória, e um recall que
        # devolve tudo é igual a um que devolve nada.
        texto_mem = ((fm.get("summary") or "") + " " + (body or "")).lower()
        palavras = {w for w in re.findall(r"[a-záàâãéêíóôõúç]{4,}", low)}
        casadas = sum(1 for w in palavras if w in texto_mem)
        pelo_texto = casadas >= 2
        if not (sujeito or tema or pelo_texto):
            continue
        ts_start = fm.get("timestamp_start") or now
        age = max(0.0, now - ts_start)
        hits.append({
            "salience": _memory_salience(fm.get("intensity"), age),
            "recency": _recency_label(age),
            "intensity": fm.get("intensity"),
            "timestamp_start": ts_start,
            "text": (fm.get("summary") or "").strip() or _short_summary(body) or body.strip(),
        })
    if not hits:
        return ausencia
    hits.sort(key=lambda m: (
        0 if m["salience"] == "vivida" else 1,
        _INTENSITY_ORDER.get(m["intensity"], 99),
        -(m["timestamp_start"] or 0),
    ))
    linhas = "\n".join(f"- ({m['recency']}) {m['text']}"
                       for m in hits[:_MEMORY_CONTEXT_CAP])
    return {"sobre": sobre, "lembra": "Sobre isso, você lembra:\n" + linhas}


registro.consult_spec(registro.ConsultSpec(
    name="consultar_memoria",
    description=(
        "Consulta a SUA MEMÓRIA sobre um fato — o que você viu, viveu ou soube. "
        "Chame quando precisar confirmar algo antes de decidir: se alguém roubou, se "
        "houve furto num lugar, o que você sabe de uma pessoa. Passe 'sobre' com a "
        "pergunta em prosa."
    ),
    params={"sobre": {"type": "string"}},
    query=recall,
))
