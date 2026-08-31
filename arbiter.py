"""O Árbitro — resolve a intenção contra o estado real e as regras do mundo.

Recebe a intenção estruturada (vinda d'A Mente, client-side) e o proximity_context,
monta um prompt, chama o modelo do server e devolve uma resolução estruturada:

    {
      "narrative_hint": "<o que de fato aconteceu, in-world, curto>",
      "mutations": [ {"target": "<char-id>", "path": "status.<campo>",
                      "value": <novo valor>, "reason": "<por quê>"} ],
      "memories": []   # Phase 3
    }

O Árbitro NUNCA escreve arquivos — quem aplica é o Motor. Aqui só se decide.
O `model_fn(system, user) -> str` é injetável (facilita teste sem Ollama).
"""

from __future__ import annotations

import json
import types

import arbiter_tools
import devlog
import motor
import validator
from llm import LLMError

# Régua canônica da vontade (spec 007, FR-002a): SEMPRE a mesma escala, lida do ALVO
# (corpo/personalidade, memórias, humor/ação, relação com quem pede e com o destino) —
# nunca do interesse de quem persuade. A nota é segredo do mundo: jamais na narrativa.
# (spec 020) SYSTEM_PROMPT, build_user_prompt e resolve() — o caminho clássico
# do Árbitro SEM tool-calling — foram removidos: runtime sem tools deixou de ser
# suportado (FR-011). `normalize` permanece (parseia prosa no loop de tools).


def _pertence_a(node: dict | None) -> dict | None:
    """spec 035: traduz a estrutura recursiva `location.pertence_a` (do Motor,
    já na forma final — mais próximo primeiro, cada nível apontando de novo
    pra `pertence_a` de quem o contém, MESMA chave em todo nível) pro
    vocabulário do prompt do Árbitro. Só renomeia campos; a forma aninhada em
    si não muda."""
    if not node:
        return None
    return {
        "nome": node.get("name"),
        "descricao": node.get("narrative"),
        "pertence_a": _pertence_a(node.get("pertence_a")),
    }


def _context_for_prompt(context: dict) -> dict:
    self_ = context.get("self", {})
    # destinos alcançáveis daqui, para medir o afeto de cada alvo por eles (spec 016)
    destinos = [(r.get("destination_id"), r.get("destination_name"))
                for r in context.get("routes", []) if r.get("destination_id")]
    present = []
    for c in context.get("characters_present", []):
        if c.get("id") == self_.get("id"):
            continue
        # afeto do ALVO por cada destino reachable_entities — insumo da vontade de ser
        # convencido a ir (spec 016). Só o que PESA entra, para não virar ruído;
        # o número morre no server, sai só o rótulo. Segredo do mundo.
        afeto_lugares = {}
        for dest_id, dest_nome in destinos:
            saldo = motor.sentiment_toward(c.get("id"), dest_id)
            if abs(saldo) >= 2:
                afeto_lugares[dest_nome or dest_id] = motor.sentiment_label(saldo)
        entry = {
            "id": c.get("id"),
            "name": c.get("name"),
            "action": c.get("action"),
            "mood": c.get("mood"),
            "conditions": c.get("conditions"),
            "carried_item_ids": c.get("carrying") or [],
            "fisico": c.get("fisico"),
        }
        if afeto_lugares:
            entry["afeto_por_lugar"] = afeto_lugares
        # como ESTE presente se sente a respeito de QUEM AGE (spec 016): insumo
        # da necessidade numa troca (detesta = cobra mais), e cor para a narração.
        # Só quando pesa; número morre no server, sai só o rótulo. Segredo do mundo.
        if self_.get("id"):
            saldo_voce = motor.sentiment_toward(c.get("id"), self_.get("id"))
            if abs(saldo_voce) >= 2:
                entry["afeto_por_voce"] = motor.sentiment_label(saldo_voce)
        present.append(entry)
    rotas = [
        {"id": r.get("id"), "name": r.get("name"), "para": r.get("destination_name")}
        for r in context.get("routes", [])
    ]
    # objects/items presentes, com interactions consultivas quando declaradas (spec 002)
    # e a física de cada item (spec 004): tamanho, peso, onde veste, o que guarda.
    objetos = [
        {"id": o.get("id"), "name": o.get("name"), "interactions": o.get("interactions"),
         "contem": o.get("contains")}
        for o in context.get("objects_present", [])
    ]
    itens = [
        {"id": it.get("id"), "name": it.get("name"),
         "interactions": it.get("interactions"),
         "tamanho": it.get("size"), "peso_kg": it.get("weight_kg"),
         "veste_em": it.get("veste_em"), "guarda": it.get("container")}
        for it in context.get("items_present", [])
    ]
    return {
        "location": {
            "id": context.get("location", {}).get("id"),
            "name": context.get("location", {}).get("name"),
            "descricao": context.get("location", {}).get("narrative"),
            # spec 035: a location que contém o lugar atual, estrutura aninhada
            # (mais próxima primeiro, mesma chave "pertence_a" se repetindo pra
            # quem a contém) — mesma forma do que vai pra A Mente (client/mente.js).
            # Aqui é só GROUND TRUTH de contexto pra julgar a cena (ex.: o que é
            # plausível num porto vs. numa vila do interior) — o Árbitro não
            # narra atmosfera com isso; "narrate" continua exigindo resumo
            # curto e factual, a evocação fica inteira com A Mente.
            "pertence_a": _pertence_a(context.get("location", {}).get("pertence_a")),
            "em_transito": context.get("in_transit", False),
        },
        "personagem_que_age": {
            "id": self_.get("id"),
            "name": self_.get("name"),
            "attributes": self_.get("attributes"),
            # `skills` SAIU daqui (spec 058, US6): era a segunda via para "quão
            # bom o personagem é" no exato domínio (`musica`) que a proficiência
            # derivada de memória (`proficiencies_for`) já cobre — com as duas,
            # o Árbitro veria a régua errada. `character.skills` segue como
            # campo legado, tolerado, nunca lido pelo server.
            "status": self_.get("status"),
            "personalidade": self_.get("body"),
            "inventario": self_.get("inventory") or [],
            "fisico": self_.get("fisico"),
        },
        "outros_presentes": present,
        "rotas_disponiveis": rotas,
        "objetos_presentes": objetos,
        "itens_presentes": itens,
    }


def normalize(raw: str | dict) -> dict:
    """Parseia e normaliza a resolução do modelo, tolerando pequenas variações."""
    if isinstance(raw, dict):
        data = raw
    else:
        data = _loads_lenient(raw)

    mutations = []
    for m in data.get("mutations") or []:
        if not isinstance(m, dict):
            continue
        target = m.get("target")
        path = m.get("path")
        if not target or not path:
            continue
        mutations.append({
            "target": target,
            "path": path,
            "value": m.get("value"),
            "reason": m.get("reason", ""),
        })

    movement = None
    mv = data.get("movement")
    if isinstance(mv, dict) and mv.get("enter_route"):
        movement = {"enter_route": mv["enter_route"]}

    item_transfers = []
    for t in data.get("item_transfers") or []:
        if not isinstance(t, dict):
            continue
        item = t.get("item")
        to = t.get("to")
        if not item or not to:
            continue
        item_transfers.append({"item": item, "to": to})

    memories = []
    for m in data.get("memories") or []:
        if not isinstance(m, dict):
            continue
        target = m.get("target")
        content = (m.get("content") or "").strip()
        if not target or not content:
            continue
        memories.append({
            "target": target,
            "content": content,
            "summary": m.get("summary"),
            "intensity": m.get("intensity"),
            "ttl_seconds": m.get("ttl_seconds"),
        })

    equip_ops = []
    for op in data.get("equip_ops") or []:
        if not isinstance(op, dict):
            continue
        kind = op.get("op")
        item = op.get("item")
        if kind not in ("equip", "unequip") or not item:
            continue
        entry = {"op": kind, "item": item}
        if kind == "unequip" and op.get("to"):
            entry["to"] = op["to"]
        equip_ops.append(entry)

    lock_ops = []
    for op in data.get("lock_ops") or []:
        if not isinstance(op, dict):
            continue
        if op.get("op") in ("open", "close") and op.get("target"):
            lock_ops.append({"op": op["op"], "target": op["target"]})

    persuade_ops = []
    for op in data.get("persuade_ops") or []:
        if not isinstance(op, dict):
            continue
        if op.get("personagem") and op.get("rota"):
            persuade_ops.append({"personagem": op["personagem"],
                                 "rota": op["rota"],
                                 "vontade": op.get("vontade")})

    attack_ops = []
    for op in data.get("attack_ops") or []:
        if not isinstance(op, dict):
            continue
        if op.get("alvo") or op.get("personagem"):
            attack_ops.append({"alvo": op.get("alvo") or op.get("personagem"),
                               "arma": op.get("arma"),
                               "vantagem": op.get("vantagem")})

    carry_ops = []
    for op in data.get("carry_ops") or []:
        if isinstance(op, dict) and (op.get("alvo") or op.get("personagem")) \
                and op.get("rota"):
            carry_ops.append({"alvo": op.get("alvo") or op.get("personagem"),
                              "rota": op["rota"]})

    learn_ops = []
    for op in data.get("learn_ops") or []:
        if not isinstance(op, dict):
            continue
        brutas = op.get("rotas")
        if isinstance(brutas, list) and brutas:
            pares = []
            for it in brutas:
                if isinstance(it, dict) and it.get("rota"):
                    pares.append({"rota": it["rota"],
                                  "trecho": (it.get("trecho") or "").strip()})
                elif isinstance(it, str):
                    pares.append({"rota": it, "trecho": ""})
            if pares:
                nova = {"rotas": [p["rota"] for p in pares], "citacoes": pares}
                # a FONTE atravessa o fallback só para não divergir do formato:
                # sem `ask_directions` não há fala em `lido`, a citação não
                # confere e nada é aprendido — que já é o comportamento vigente
                # desde a spec 014 neste caminho. Ver research.md §11.
                if op.get("fonte"):
                    nova.update({"fonte": op["fonte"],
                                 "disposicao": op.get("disposicao"),
                                 "atitude": (op.get("atitude") or "").strip()})
                learn_ops.append(nova)

    travel_ops = []
    for op in data.get("travel_ops") or []:
        if isinstance(op, dict) and op.get("destino"):
            travel_ops.append({"destino": op["destino"]})

    trade_ops = []
    for op in data.get("trade_ops") or []:
        if isinstance(op, dict) and op.get("parceiro") and op.get("dou") \
                and op.get("recebo"):
            trade_ops.append({"modo": "buy" if op.get("modo") == "buy" else "trade",
                              "parceiro": op["parceiro"],
                              "dou": list(op["dou"]), "recebo": list(op["recebo"]),
                              "necessidade": op.get("necessidade")})

    # boato (spec 017): atravessa o fallback só para não divergir do formato. Sem
    # `ask_about`/prosa em `lido`, a citação não confere e nada é gravado — como já
    # vale desde a 014 nesse caminho.
    hearsay_ops = []
    for op in data.get("hearsay_ops") or []:
        if isinstance(op, dict) and op.get("fonte") and op.get("sobre") \
                and (op.get("trecho") or "").strip():
            hearsay_ops.append({"fonte": op["fonte"], "sobre": op["sobre"],
                                "trecho": op["trecho"].strip(),
                                "disposicao": op.get("disposicao"),
                                "atitude": (op.get("atitude") or "").strip()})

    return {
        "narrative_hint": (data.get("narrative_hint") or "").strip(),
        "movement": movement,
        "mutations": mutations,
        "item_transfers": item_transfers,
        "equip_ops": equip_ops,
        "lock_ops": lock_ops,
        "persuade_ops": persuade_ops,
        "attack_ops": attack_ops,
        "carry_ops": carry_ops,
        "trade_ops": trade_ops,
        "travel_ops": travel_ops,
        "learn_ops": learn_ops,
        "hearsay_ops": hearsay_ops,
        "lido": [t for t in (data.get("lido") or []) if isinstance(t, str)],
        "memories": memories,
    }


def _item_entry(it: dict, porter: str | None, in_object: str | None = None) -> dict:
    """Ficha física de um item no índice da cena (dados vindos do contexto)."""
    return {
        "name": it.get("name") or "",
        "size": it.get("size") or "P",
        "weight": it.get("weight_kg") if isinstance(it.get("weight_kg"), (int, float))
                  else 1.0,
        "veste_em": it.get("veste_em"),
        "container": it.get("container"),
        "for_sale": it.get("for_sale"),
        "negotiable": it.get("negotiable"),
        "currency": it.get("currency"),
        "value": it.get("value"),
        "slot": it.get("slot"),
        "estado": it.get("estado"),
        "porter": porter,
        "in_object": in_object,
        # spec 052: peça em processo (lâmina na bigorna, panela no fogo) — carrega o
        # NOME da capacidade que a criou, para que a retomada seja oferecida só à
        # tool certa. O conteúdo do bloco (banda, tetos, tempos) continua fora.
        "em_trabalho": it.get("em_trabalho"),
    }


def _scene_index(context: dict) -> dict:
    """Índice físico da cena, derivado do proximity_context (sem consulta nova).

    items: id -> ficha física + quem porta (porter). A visibilidade já vem
    recortada do Motor: de terceiros só chega o que está acoplado ao corpo
    (FR-009) — o índice nunca expõe o que a cena não percebe.
    """
    self_ = context.get("self") or {}
    actor_id = self_.get("id")
    fis = self_.get("fisico") or {}
    chars, objects, items, char_fisico = {}, {}, {}, {}
    char_conditions = {}
    for c in context.get("characters_present", []):
        cid = c.get("id")
        if not cid:
            continue
        chars[cid] = c.get("name") or ""
        # derrota é pública na cena (spec 008): quem caiu, caiu à vista de todos
        char_conditions[cid] = list(c.get("conditions") or [])
        cf = c.get("fisico") or {}
        char_fisico[cid] = {
            # spec 019: a capacidade de mão vem do corpo (já derivada no summary);
            # o fallback é conservador (0), nunca o humano global.
            "maos_livres": cf.get("maos_livres", 0),
            "maos_totais": cf.get("maos_totais", 0),
            "maos_ocupadas_por": list(cf.get("maos_ocupadas_por") or []),
            "carga_livre_kg": cf.get("carga_livre_kg", float("inf")),
        }
        if cid != actor_id:
            for it in c.get("carrying") or []:
                if it.get("id"):
                    items[it["id"]] = _item_entry(it, porter=cid)
    if actor_id in char_fisico:
        char_fisico[actor_id] = {
            "maos_livres": fis.get("maos_livres", 0),
            "maos_totais": fis.get("maos_totais", 0),
            # spec 019: o corpo do ator (mapa slot->capacidade) — o guard de
            # equipar precisa da capacidade de um slot QUALQUER, não só da mão.
            "corpo": fis.get("corpo") or {},
            "maos_ocupadas_por": list((fis.get("slots_ocupados") or {})
                                      .get(motor.HAND_SLOT) or []),
            "carga_livre_kg": (fis.get("capacidade_carga_kg", float("inf"))
                               - fis.get("peso_carregado_kg", 0.0)),
            "capacidade_empurrar_kg": fis.get("capacidade_empurrar_kg", float("inf")),
            "slots_ocupados": {s: list(ids) for s, ids
                               in (fis.get("slots_ocupados") or {}).items()},
        }
    objects_info = {}
    for o in context.get("objects_present", []):
        if o.get("id"):
            objects[o["id"]] = o.get("name") or ""
            objects_info[o["id"]] = {"fechado": bool(o.get("fechado")),
                                     "tem_fecho": bool(o.get("tem_fecho")),
                                     # spec 057: RAW (não `bool()`) — igual `_item_entry`
                                     # já faz para item. Craft é o primeiro domínio a
                                     # precisar distinguir QUAL tool ocupa um object em
                                     # processo (`craft_pecas_abertas` filtra por
                                     # `== "craft"`, não só "há trabalho aqui"); truthiness
                                     # de string não-vazia preserva todo uso anterior.
                                     "em_trabalho": o.get("em_trabalho")}
        for it in o.get("contains") or []:
            if it.get("id"):
                items[it["id"]] = _item_entry(it, porter=None, in_object=o.get("id"))
    for it in context.get("items_present", []):
        if it.get("id"):
            items[it["id"]] = _item_entry(it, porter=None)
        for sub in it.get("contains") or []:  # contêiner aberto no chão (spec 005)
            if sub.get("id"):
                items[sub["id"]] = _item_entry(sub, porter=None)
    for it in self_.get("inventory") or []:
        if it.get("id"):
            items[it["id"]] = _item_entry(it, porter=actor_id)
    loc = context.get("location") or {}
    routes = {}
    if not context.get("in_transit"):
        for r in context.get("routes", []):
            if r.get("id"):
                routes[r["id"]] = f"{r.get('name') or ''} → {r.get('destination_name') or ''}"
    return {
        "chars": chars, "objects": objects, "objects_info": objects_info,
        "items": items, "char_conditions": char_conditions,
        "char_fisico": char_fisico, "actor_id": actor_id,
        "place_id": loc.get("id"), "place_name": loc.get("name") or "",
        "routes": routes,
    }


_MEMORY_INTENSITIES = ["small", "medium", "large", "giant"]
_INTENTION_STATUSES = ["ativa", "concluida", "abandonada"]  # spec 026


def _verb_candidates(idx: dict) -> dict:
    """Enums por verbo (matriz tool→eixos de contracts/equip-tools.md).

    A superfície é estreita por ergonomia da LLM; TODA validação real acontece no
    pipeline único (motor.check_*), na guarda e de novo na aplicação.
    """
    actor = idx["actor_id"]
    items = idx["items"]
    hand = motor.HAND_SLOT

    def worn(e):
        return e["porter"] == actor and e["slot"] and e["slot"] != hand

    def _livre(i):
        """Posse LIVRE ou própria — não posse de outro (conserto pós-057, ver
        `cook_ingredientes` abaixo para a justificativa completa)."""
        return motor.dono(i, actor) in (None, actor)

    return {
        # vestíveis ao alcance do ator (soltos, em objects, ou já com ele)
        "equip": sorted(i for i, e in items.items()
                        if e["veste_em"] and e["porter"] in (None, actor)),
        # vestidos do ator
        "unequip": sorted(i for i, e in items.items() if worn(e)),
        # pegável: tudo ao alcance que não está já na própria mão
        "take": sorted(i for i, e in items.items()
                       if not (e["porter"] == actor and e["slot"] == hand)),
        # dá-se o que está consigo (na mão ou guardado; o vestido tira-se antes)
        "give": sorted(i for i, e in items.items()
                       if e["porter"] == actor and not worn(e)),
        "give_to": sorted(c for c in idx["chars"] if c != actor),
        # guardável: qualquer item ao alcance
        "stow": sorted(i for i, e in items.items() if not worn(e)),
        # destinos de guarda: contêineres declarados ao alcance + objects da cena
        "stow_in": sorted(i for i, e in items.items()
                          if e["container"] and e["porter"] in (None, actor))
                   + sorted(idx["objects"]),
        # larga-se o que está consigo sem estar vestido
        "drop": sorted(i for i, e in items.items()
                       if e["porter"] == actor and not worn(e)),
        # come-se o que está ao alcance (na mão OU ainda solto na cena), nunca
        # vestido (spec 046) — mesma régua de alcance de `stow`
        "eat": sorted(i for i, e in items.items() if not worn(e)),
        # bebe-se o que está ao alcance (mesmo filtro de `eat`) OU direto de
        # QUALQUER object presente (fonte ambiental — rio, poço; sem conceito
        # de alcance/porte, mesmo universo cru que `examinar`/`stow_in`/
        # `shove_to` já usam — spec 047). A régua de BEBIBILIDADE, não um
        # filtro aqui, decide quem realmente é fonte de líquido.
        "drink": sorted(set(i for i, e in items.items() if not worn(e))
                        | set(idx["objects"])),
        # cozinha-se com ingredientes ao alcance (mesmo filtro de `eat` — mão,
        # chão, dentro de contêiner aberto, em qualquer lugar) sobre uma fonte
        # de calor presente na cena (mesmo universo cru de `shove_to`/`open` —
        # spec 048). As réguas de FONTE_DE_CALOR/COZINHABILIDADE, não um filtro
        # aqui, decidem se o object fornece calor e se os itens combinam.
        #
        # Conserto pós-057 (achado da exploração): as cinco chaves de material de
        # trabalho (esta e `brew_ingredientes`/`kindle_materiais`/
        # `forge_materiais`/`craft_materiais`) liam o índice físico bruto sem
        # NENHUMA checagem de posse — dava pra consumir o que outro personagem
        # presente carregava na mão. `_livre(i)` é o predicado novo
        # (`craftable_entities`, `percepcao/consultas.py`, aplicado aqui pelo
        # mesmo índice que as outras chaves usam, não pelo walk de pasta — mais
        # barato, mesmo resultado): passa por posse LIVRE (`dono() is None`) e
        # pela própria; para em posse RECONHECIDA de outro. Nem `alcançável`
        # (`steal`, sem checagem nenhuma) nem `disponível` (`comercio.py`, só
        # aceita posse COMPROVADA seu — bloquearia pegar uma fibra solta).
        "cook_ingredientes": sorted(i for i, e in items.items()
                                    if not worn(e) and not e.get("em_trabalho")
                                    and _livre(i)),
        # spec 052 (FR-043a): o LUGAR entra no universo de fontes de calor, ao lado
        # dos objects — molde EXATO de `shove_to`, logo abaixo. A lareira de uma
        # cozinha e as brasas de uma forja costumam estar escritas na prosa do
        # AMBIENTE, não instanciadas como entidade; sem isto, a mesma prosa serviria
        # para forjar e deixaria de servir para cozinhar. A régua não mudou: muda de
        # onde a descrição vem, nunca como ela é julgada.
        "cook_fonte": sorted(idx["objects"])
                      + ([idx["place_id"]] if idx["place_id"] else []),
        # spec 054 — colher. Cópia LITERAL de `cook_fonte`: objects presentes + o
        # LUGAR, mesmo argumento (a mata de uma encosta costuma estar escrita na
        # prosa do AMBIENTE, não instanciada). Um object com `em_trabalho` (um
        # canteiro já colhido, ainda não rebrotado; a panela; a fonte de fogo) sai
        # do enum — é o que dá FR-003 (recusa por cooldown) SEM chamada ao Árbitro,
        # sem precisar de um filtro estrutural à parte (molde de
        # `kindle_materiais`/`forge_materiais`, que já excluem `em_trabalho`). O
        # LUGAR nunca é filtrado: `location` não tem bloco `trabalho` (FR-013).
        "forage_onde": sorted(o for o in idx["objects"]
                              if not idx["objects_info"].get(o, {}).get("em_trabalho"))
                       + ([idx["place_id"]] if idx["place_id"] else []),
        # spec 055 — preparar. Cópias LITERAIS de `cook_ingredientes`/`cook_fonte`,
        # não a MESMA chave: um enum compartilhado entre duas tools impediria dar a
        # uma delas um filtro próprio no futuro sem afetar a outra em silêncio (research
        # R4 da spec 055) — mesmo motivo que já separa `kindle_materiais`/
        # `forge_materiais`/`cook_ingredientes`, três chaves com o MESMO corpo de
        # filtro. O recipiente NUNCA trava (divergência deliberada de `forage_onde`):
        # `brew` não escreve nele, então `em_trabalho` não precisa ser filtrado aqui —
        # um alambique nunca fica ocupado por causa de `brew`.
        "brew_ingredientes": sorted(i for i, e in items.items()
                                    if not worn(e) and not e.get("em_trabalho")
                                    and _livre(i)),
        "brew_recipiente": sorted(idx["objects"])
                           + ([idx["place_id"]] if idx["place_id"] else []),
        # spec 053 — acender. Reusa o filtro EXATO de `cook_ingredientes`: alcançável,
        # não vestido, e não `em_trabalho`. Este último por outro motivo que na forja —
        # lá é "metal batido não volta a ser barra", aqui é "a panela no fogo não é
        # lenha". Mesma regra, e herdá-la é reuso; reescrevê-la seria duplicação.
        "kindle_materiais": sorted(i for i, e in items.items()
                                   if not worn(e) and not e.get("em_trabalho")
                                   and _livre(i)),
        # spec 052 — forjar. `forge_materiais` reusa o filtro de `cook_ingredientes`
        # (mão, chão, dentro de contêiner aberto), MENOS as peças em processo: metal
        # batido não volta a ser barra. `forge_peca` é filtro ESTRUTURAL (o bloco de
        # trabalho no arquivo), zero LLM — e NÃO filtra por qual tool criou a peça:
        # a peça da outra oficina aparece e é recusada com motivo próprio, que
        # ensina; escondê-la só produziria silêncio.
        "forge_materiais": sorted(i for i, e in items.items()
                                  if not worn(e) and not e.get("em_trabalho")
                                  and _livre(i)),
        "forge_fonte": sorted(idx["objects"])
                       + ([idx["place_id"]] if idx["place_id"] else []),
        # MEDIDO na sondagem real (spec 052, T074): com UM enum único de peças, o
        # modelo escolheu `forge_armor` para terminar uma LÂMINA em 5 de 5
        # tentativas. A aposta original era que a recusa estrutural ensinaria — e o
        # dado desmentiu: o modelo não aprende dentro do turno, só gasta a chamada.
        # Filtrando por capacidade, a peça da outra oficina simplesmente não aparece
        # (e o parâmetro inteiro some, por `omit_if_empty`), então não há o que
        # errar. A recusa `peca_de_outra_oficina` fica como defesa em profundidade,
        # para quem chama pela bancada HTTP.
        "forge_peca_arma": sorted(i for i, e in items.items()
                                  if e.get("em_trabalho") == "forge_weapon"),
        "forge_peca_armadura": sorted(i for i, e in items.items()
                                      if e.get("em_trabalho") == "forge_armor"),
        # spec 057 — craft. Mesmo molde de `forge_materiais`/`forge_peca_arma`:
        # materiais alcançáveis, menos peças já em processo; peças em processo
        # filtradas ESTRUTURALMENTE por `em_trabalho == "craft"` (zero LLM). Cobre
        # peça-ITEM e peça-OBJECT (craft pode deixar uma prateleira em processo, não
        # só um item na mão) — `location` em processo fica de fora (US5, fora deste
        # lote: `_walk_scene` ainda não anda por `location.md` filha nenhuma).
        "craft_materiais": sorted(i for i, e in items.items()
                                  if not worn(e) and not e.get("em_trabalho")
                                  and _livre(i)),
        "craft_pecas_abertas": sorted(
            [i for i, e in items.items() if e.get("em_trabalho") == "craft"]
            + [o for o, info in idx["objects_info"].items()
               if info.get("em_trabalho") == "craft"]),
        # empurra-se o que ninguém carried_item_ids
        "shove": sorted(i for i, e in items.items() if e["porter"] is None),
        "shove_to": sorted(idx["objects"])
                    + ([idx["place_id"]] if idx["place_id"] else []),
        # abre-se o que está fechado; fecha-se contêiner aberto com fecho (spec 005)
        "open": sorted(i for i, e in items.items()
                       if e["container"] and e["container"].get("fechado")
                       and e["porter"] in (None, actor))
                + sorted(o for o, info in idx["objects_info"].items()
                         if info["fechado"]),
        "close": sorted(i for i, e in items.items()
                        if e["container"] and not e["container"].get("fechado")
                        and e["porter"] in (None, actor))
                 + sorted(o for o, info in idx["objects_info"].items()
                          if info["tem_fecho"] and not info["fechado"]),
        # persuade-se OUTRO personagem presente a partir por uma rota (spec 007)
        "persuade": sorted(c for c in idx["chars"] if c != actor),
        # persuade_give (spec 023): o DONO (outro presente) cede um item DELE; o item
        # é o que está com outro presente; o destinatário é o ator OU outro presente
        "persuade_give_alvo": sorted(c for c in idx["chars"] if c != actor),
        "persuade_give_item": sorted(
            i for i, e in items.items()
            if e["porter"] and e["porter"] != actor and e["porter"] in idx["chars"]),
        "persuade_give_para": sorted(idx["chars"]),
        # golpeia-se OUTRO personagem presente (spec 008); a arma é o que está na
        # própria mão — item sem bloco `weapon` vale como improvisado
        "attack": sorted(c for c in idx["chars"] if c != actor),
        # leva-se OUTRO presente pela rota, à força ou por estar caído (spec 010)
        "carry": sorted(c for c in idx["chars"] if c != actor),
        # socorre-se OUTRO presente que esteja incapacitado (spec 032) — nunca
        # morto (fora de escopo), nunca de pé (nada a socorrer)
        "heal": sorted(c for c in idx["chars"] if c != actor
                       and motor.INCAPACITATED in (idx["char_conditions"].get(c) or [])),
        # esquarteja-se OUTRO presente que já esteja MORTO (spec 050) — nunca
        # incapacitado, nunca de pé; matar continua exclusivo de `attack`
        "butcher_alvo": sorted(c for c in idx["chars"] if c != actor
                               and motor.DEAD in (idx["char_conditions"].get(c) or [])),
        # comércio (spec 011): o PORTÃO já filtra os enums — o modelo só enxerga
        # o que o mundo põe à mesa
        "negociar_com": sorted(c for c in idx["chars"] if c != actor),
        "pagar_com": sorted(i for i, e in items.items()
                            if e["porter"] == actor and e.get("currency")),
        "ofertar": sorted(i for i, e in items.items()
                          if e["porter"] == actor and e.get("negotiable")),
        # `comprar`/`pedir` NÃO saem do contexto: a mercadoria pode estar no
        # fundo da caixa do mascate, invisível a terceiros (spec 004 FR-009).
        # Quem enxerga é o Árbitro, lendo o mundo — consultivo de SERVER
        # (Princípio IX). Preenchidos em build_tools.
        "comprar": [],
        "pedir": [],
        "attack_with": sorted(i for i, e in items.items()
                              if e["porter"] == actor and e["slot"] == hand),
        # spec 058: instrumento de `sing` — algo que ele CARREGUE e possa empunhar.
        # Era estrito ("já na mão") e isso deixava o alaúde guardado na bolsa
        # invisível para a tool; hoje o Motor o traz à mão na aplicação
        # (`bring_to_hand`, o espelho do `_accommodate` do item 44). Vestido fica
        # de fora: tirar armadura para tocar é `unequip`, decisão do personagem.
        "sing_instrumento": sorted(i for i, e in items.items()
                                   if e["porter"] == actor
                                   and e["slot"] in (None, hand)),
        # spec 059: alvo de `write` — só ITENS (não objects/chars/local, ver
        # research.md R3 da 059): `rewrite_description` precisa do nome de
        # arquivo por tipo, e nenhum caso de uso desta spec escreve em pessoa,
        # objeto de cenário ou no próprio lugar.
        "write_alvo": sorted(items),
        # spec 059: instrumento de `write` — MESMO predicado do `sing_instrumento`
        # (research.md R4/R6): algo que ele CARREGUE e possa empunhar, não só o
        # que já está na mão. Obrigatório (não opcional como o de `sing`): sem
        # NADA que sirva, `write` some da face (FR-001b — o parâmetro é
        # `required`, `omit_if_empty` não se aplica aqui).
        "write_instrumento": sorted(i for i, e in items.items()
                                    if e["porter"] == actor
                                    and e["slot"] in (None, hand)),
        # viaja-se para lugar que ele SABE alcançar (spec 012). Também não sai do
        # contexto: o mapa do que ele sabe é memória de rota, que fica no server.
        "viajar_para": [],
        "ao_alcance": sorted(i for i, e in items.items()
                             if e["porter"] in (None, actor)),
        # examinar vale para QUALQUER coisa percebida: item, objeto, pessoa, lugar
        "examinar": [],
        # o enum de rotas é do MUNDO INTEIRO, não só das que partem daqui: um mapa
        # ensina caminho distante. Consulta de server (Princípio IX).
        "rotas_do_mundo": [],
    }


def scene_candidates(idx: dict) -> dict:
    """Candidatos de cada verbo, INCLUSIVE os que vêm de consulta de server.

    Extraída de `build_tools` porque as GUARDAS também precisam dela: elas
    conferem o que o modelo pediu contra o mesmo enum que foi oferecido. Enquanto
    isto vivia só dentro de `build_tools`, as guardas de `travel_to` e `study`
    referenciavam um `cand` que não existia no escopo delas — NameError no
    primeiro uso real, e nenhum teste exercitava esse caminho. Uma sondagem com o
    modelo real foi quem descobriu.
    """
    cand = _verb_candidates(idx)

    # O que os OUTROS oferecem é consulta de server: estar à venda não é estar à
    # vista. Sem isto, um mercador com a caixa cheia não venderia nada.
    a_venda, trocaveis = [], []
    for outro in cand["negociar_com"]:
        try:
            oferta = motor.offered_by(outro)
        except motor.MotorError:
            continue
        a_venda += [i["id"] for i in oferta["a_venda"]]
        trocaveis += [i["id"] for i in oferta["trocaveis"]]
    cand["comprar"] = sorted(set(a_venda))
    cand["pedir"] = sorted(set(trocaveis))

    # Destino que ele não sabe alcançar NÃO VIRA ENUM: a regra "só se sabe o
    # caminho" é cumprida aqui, antes de qualquer guarda.
    try:
        cand["viajar_para"] = motor.reachable_destinations(idx["actor_id"])
    except motor.MotorError:
        cand["viajar_para"] = []

    # examinar: tudo o que ele percebe agora, mais o próprio lugar
    place_id = idx["place_id"]
    # spec 034 (US2): lugares sobre os quais dá para perguntar — a cena atual
    # + tudo que ele já conhece/reconhece (MESMA fonte que `viajar_para` já
    # usa). Nunca texto livre: um lugar nunca visitado nem aparece como opção.
    cand["perguntar_sobre_lugar"] = sorted(
        ({place_id} if place_id else set()) | set(cand["viajar_para"]))
    cand["examinar"] = sorted(set(idx["items"]) | set(idx["objects"])
                              | set(idx["chars"])
                              | ({place_id} if place_id else set()))
    # aprender caminho: as rotas do MUNDO, não só as daqui (consulta de server)
    cand["rotas_do_mundo"] = sorted(motor.all_route_ids())
    # perguntar o caminho (spec 015): quem está presente e pode responder. Caído
    # ou morto sai daqui, e não da guarda — a mesma disciplina do `viajar_para`,
    # que cumpre "só se sabe o caminho" antes de qualquer validação.
    cand["perguntar_a"] = sorted(
        c for c in idx["chars"]
        if c != idx["actor_id"]
        and not (set(idx["char_conditions"].get(c) or [])
                 & set(motor.DOWN_CONDITIONS))
    )
    # acusar (spec 028): só existe evidência pra brandir se o ator REALMENTE
    # lembra de algo envolvendo o presente — consulta de server já genérica
    # (remembered_about, spec 015), sem campo novo. Guarda id→{sobre, resumo}
    # (não uma lista simples como os outros candidatos) porque build_tools
    # precisa do resumo pra descrever cada memória no manifest — um enum de
    # ids sem contexto não dá ao Árbitro como escolher com critério.
    evidencias: dict[str, dict] = {}
    for outro in idx["chars"]:
        if outro == idx["actor_id"]:
            continue
        try:
            mems = motor.remembered_about(idx["actor_id"], outro)
        except motor.MotorError:
            continue
        for m in mems:
            evidencias[m["id"]] = {"sobre": outro, "resumo": m.get("summary") or ""}
    cand["acusar_memorias"] = evidencias
    cand["acusar_alvo"] = sorted({v["sobre"] for v in evidencias.values()})

    # cantar (spec 058): SÓ se canta o que se lembra — todas as memórias VIVAS de
    # acontecimento do próprio ator, cada uma com o sujeito derivado do `involved`
    # dela (`motor.own_memories`). Ao contrário de `acusar_memorias`, não depende
    # de quem está presente: o feito cantado pode ser sobre alguém que nunca
    # esteve nesta cena — é o ponto da tool.
    sing_mem: dict[str, dict] = {}
    for m in motor.own_memories(idx["actor_id"]):
        sing_mem[m["id"]] = {"sobre": m["sobre"], "resumo": m["resumo"],
                             "conteudo": m["conteudo"], "intensity": m["intensity"]}
    cand["sing_memorias"] = sing_mem

    # escrever (spec 059): TODAS as memórias VIVAS de acontecimento do próprio
    # ator, INCLUSIVE as sem outro envolvido (`require_sobre=False`, research.md
    # R2) — diferente de `sing_memorias`, porque o caso motivador (a receita do
    # boticário) é justamente uma vivência solitária. `sobre` pode vir `None`;
    # a description trata esse caso (ver `motor/conhecimento/declaracao.py`).
    write_mem: dict[str, dict] = {}
    for m in motor.own_memories(idx["actor_id"], require_sobre=False):
        write_mem[m["id"]] = {"sobre": m["sobre"], "resumo": m["resumo"],
                              "conteudo": m["conteudo"], "intensity": m["intensity"]}
    cand["write_memorias"] = write_mem
    return cand


def build_tools(context: dict) -> list[dict]:
    """Manifest neutro do turno, com enums da cena — uma tool por verbo físico
    (contracts/equip-tools.md). Tools sem candidato válido são omitidas.

    Gate cosmético (spec 031): enquanto o próprio ator está descansando, o
    manifest oferece SÓ a capacidade de acordar — o Árbitro nem vê o
    vocabulário de outra tool (Princípio IX). Isto NÃO é a autoridade: quem
    realmente impede a mutação é cada executor, validando com os próprios
    meios (`fisica.is_resting`, chamado em CADA `_apply_X_ops` — spec 031,
    research.md §3). O gate é só UX.

    Item 50: este gate ESCREVIA a face de `sleep` à mão aqui — um dicionário de
    manifest hardcoded no meio do montador. Agora ele é o filtro de uma linha lá
    embaixo (`dormindo != spec.only_while_resting`), e a face de acordar sai do
    registro como todas as outras. Acrescentar tool não edita mais este ponto.
    """
    self_status = (context.get("self") or {}).get("status") or {}
    dormindo = motor.fisica.is_resting({"status": self_status})
    # spec 048/052: mesmo gate cosmético do descanso, generalizado — enquanto há
    # trabalho em curso, NENHUMA tool de mutação aparece.
    # spec 052: "ocupado" deixou de ser um campo do personagem. `get_context`
    # DERIVA o booleano da peça em processo na cena (nunca persistido, mesmo
    # espírito de `proficiencies_for`) — o gate lê o fato derivado, e `character.md`
    # segue sem campo nenhum de trabalho.
    cozinhando = bool((context.get("self") or {}).get("ocupado"))
    idx = _scene_index(context)
    cand = scene_candidates(idx)
    chars = sorted(idx["chars"])
    objects = sorted(idx["objects"])
    items = sorted(idx["items"])
    routes = sorted(idx["routes"])
    place_id = idx["place_id"]
    mut_targets = chars + objects + items
    # ids das intenções ATIVAS do PRÓPRIO ator — computado uma vez (give/trade/
    # prometer/set_intention compartilham o mesmo enum, specs 026/027).
    active_intention_ids = [i["id"] for i in (context.get("intentions") or [])
                            if i.get("id")]
    # A FACE de cada tool mora com ela (arbiter_tools.MANIFESTS); aqui só se monta
    # a CENA e itera o registro — acrescentar tool nunca edita este ponto
    # (Open/Closed, item 31). Tool sem candidato válido devolve None e some.
    scene = types.SimpleNamespace(
        cand=cand, chars=chars, routes=routes, place_id=place_id,
        mut_targets=mut_targets, active_intention_ids=active_intention_ids,
        actor_id=idx["actor_id"],
        MEMORY_INTENSITIES=_MEMORY_INTENSITIES,
        INTENTION_STATUSES=_INTENTION_STATUSES,
    )
    # A FACE dos domínios MIGRADOS (spec 038, L2) DERIVA da declaração `ToolSpec`
    # (motor.registro), via o builder genérico; os ainda-não-migrados seguem pelos
    # `manifest_X` à mão. Coexistem até a migração terminar. Um nome declarado tem
    # prioridade — o `manifest_X` legado (se sobrar) é ignorado.
    # spec 038 (US2): o MUNDO escolhe quais tools a engine oferece (manifesto de
    # ativação, `motor.ativacao`). None = todas as registradas (default). Filtra a
    # FACE — a tool desativada não aparece (e o _execute também a recusa).
    _ativas = motor.ativacao.active_tool_ids()
    faces: list[dict] = []
    declared: set[str] = set()
    seen: set[int] = set()
    for spec in motor.registro.specs().values():
        if id(spec) in seen:
            continue
        seen.add(id(spec))
        # spec 048: ocupado cozinhando, NENHUMA tool de mutação aparece — sem
        # exceção (não há `only_while_cooking`, ao contrário do descanso).
        if cozinhando:
            continue
        # O GATE DE DESCANSO, em uma linha e sem conhecer nome de tool nenhum
        # (item 50): dormindo, existem SÓ as capacidades marcadas
        # `only_while_resting`; de pé, existem todas MENOS elas. As duas metades da
        # regra caem do mesmo booleano, que mora na declaração da tool.
        if dormindo != spec.only_while_resting:
            continue
        for nm in spec.names:
            if _ativas is not None and nm not in _ativas:
                continue  # desativada neste mundo
            declared.add(nm)
            face = arbiter_tools.build_face(spec, nm, scene)
            if face is not None:
                faces.append(face)
    for nm, mf in arbiter_tools.MANIFESTS.items():
        if nm in declared:
            continue
        t = mf(scene)
        if t is not None:
            faces.append(t)
    return faces


def _validos(*maps: dict) -> list[dict]:
    out = []
    for m in maps:
        for k, v in sorted(m.items()):
            nome = v.get("name", "") if isinstance(v, dict) else v
            out.append({"id": k, "nome": nome})
    return out


def build_ctx(context: dict, emit=None, ask=None, prosa=None,
              orienta_laco: bool = True):
    """MONTA o contexto de turno (o `ctx`) a partir da CENA — spec 043, Fase A.

    Extraído de `resolve_with_tools` sem alterar uma linha do que faz: a cena
    (`_scene_index`/`scene_candidates`), o rastreio estático do turno (`loc`/`moved`/
    `fechado_state`), a fila e os acumuladores, e os closures que as tools usam pelo
    `ctx` (duck-typed, spec 038). NÃO conhece `loop_fn`, `intent` nem manifesto — é
    função PURA da cena, e é isso que a torna reusável fora do laço do Árbitro.

    Por que existe: a proposta que chega do client (spec 043) precisa exatamente deste
    `ctx` para a CHECAGEM FORTE de cada capacidade, sem que exista laço de LLM nenhum.
    Antes, montar o `ctx` era indissociável de rodar o Árbitro.

    A física NÃO é espelhada aqui (spec 021, Fase B): cada op mutadora é
    aplicada-e-registrada no ATO pelo EXECUTOR (motor.apply_resolution por-op, o
    flip da 020), que valida com os check_* autoritativos sobre os arquivos reais.
    A guarda só confere o ESTÁTICO da cena (ids/tipos/destinos, `loc`/`fechado_state`
    leves para a coerência entre ops do mesmo turno) e RELATA ao chamador a rejeição
    estruturada ({regra, valores}) que o executor devolveu.

    `emit` (spec 022): callback OPCIONAL `emit(ev_type, payload)` para o streaming do
    turno. Com `emit=None` (default) o comportamento é byte-a-byte o de hoje — nenhum
    chamador/teste que não streama muda. O APP é dono do ciclo do stream
    (`turn_start`/`heartbeat`/`done`); aqui só se emite `op_applied`/`failed` por efeito
    (Fase 2). Deve tolerar exceção do sink (uma queda de conexão não aborta o turno).
    """
    def _emit(ev, payload=None):
        if emit is None:
            return
        try:
            emit(ev, payload or {})
        except Exception:
            pass  # sink caiu (conexão do cliente): o turno segue e grava no mundo

    idx = _scene_index(context)
    chars, objects, items = idx["chars"], idx["objects"], idx["items"]
    cand = scene_candidates(idx)   # as guardas conferem contra o MESMO enum ofertado
    place_id, routes = idx["place_id"], idx["routes"]
    actor = idx["actor_id"]
    fis = idx["char_fisico"]
    # spec 019: a "mão" do ator é o slot de PEGA do corpo dele (mão/boca), não fixo.
    hand = fis.get(actor, {}).get("pega_slot") or motor.HAND_SLOT

    # spec 021 (Fase B) — o ESPELHO DA FÍSICA foi embora: a guarda não reexecuta
    # mais check_empurrar/mao/encaixe/vaga/carga/slot contra dicts espelhados
    # (hands/slots/carga_livre/hand_cap/actor_body/cont_count/empurrar_cap). A
    # física mora num lugar só — o executor, chamado por-op via apply_resolution
    # (o flip da 020). O que sobra aqui é o rastreio ESTÁTICO leve do turno, que
    # os checks estruturais (porter/slot/já-fechado) leem entre ops do mesmo turno:
    #   loc: item -> {porter, slot}  ·  moved: já movimentados  ·  fechado_state.
    loc = {i: {"porter": e["porter"], "slot": e["slot"]} for i, e in items.items()}
    moved: set = set()
    # estado de fecho do turno (spec 005): contêineres-item e objects
    fechado_state = {i: bool((e["container"] or {}).get("fechado"))
                     for i, e in items.items() if e.get("container")}
    fechado_state.update({o: info["fechado"]
                          for o, info in idx["objects_info"].items()})

    # spec 038 (L4): os canais MUTADORES não são mais lista à mão — DERIVAM do
    # registro de handlers do Motor (`registro._HANDLERS`), + `memories` (criado à
    # parte, sem handler). Acrescentar uma tool com canal novo já popula _MUT_CH/
    # _ACC_CH/_BEAT_CH/queue por tabela — some o dilema "esquecer um dos ~4 lugares".
    # Só resta editorial DO ÁRBITRO: os canais de MATERIAL consultivo (saídas que não
    # são op mutadora) e os SILENCIOSOS (aplicam sem virar cena/beat).
    _HANDLER_CH = tuple(motor.registro._HANDLERS)
    _MATERIAL_CH = ("wares", "reconhecimentos", "informes", "lido", "falas")
    _SILENT_CH = frozenset({"mutations", "intentions", "promise_ops",
                            "accuse_ops", "rest_ops"})

    queue = {"narrative_hint": "", "movement": None}
    queue.update({ch: [] for ch in _HANDLER_CH})
    queue.update({ch: [] for ch in _MATERIAL_CH})
    queue["memories"] = []

    # spec 020 — FASE ÚNICA: cada op é APLICADA-E-REGISTRADA por-op assim que a
    # tool a enfileira (o `queue` vira só o LOG do que se pediu), contra os
    # arquivos REAIS, na ordem em que o Árbitro chamou. A próxima tool lê o mundo
    # já mudado — é o que faz o portão de violência (atacar→pedir) disparar e o
    # afeto do presente pesar na persuasão do mesmo turno. `app` NÃO reaplica.
    _MUT_CH = _HANDLER_CH + ("memories",)
    _ACC_CH = ("applied", "rejected", "memories_created", "rolls",
               "viagens_interrompidas") \
        + tuple(ch + "_applied" for ch in _HANDLER_CH if ch != "mutations")
    acc = {k: [] for k in _ACC_CH}
    acc["movement"] = None
    acc["mov_hint"] = ""
    _seen_len = {ch: 0 for ch in _MUT_CH}
    _mov_done = [False]

    # famílias de efeito NARRÁVEIS que descem como beat `op_applied` (spec 022, Fase 2):
    # só as que viram cena; memories_created/rolls/applied(genérico)/rejected NÃO são
    # beat (memória e dado são internos; rejeição vai no failed_effects do `done`).
    # spec 038 (L4): DERIVA dos canais mutadores menos os SILENCIOSOS — não é mais
    # lista à mão (uma tool nova narrável já entra por tabela).
    _BEAT_CH = tuple(ch + "_applied" for ch in _HANDLER_CH if ch not in _SILENT_CH)

    def _inworld(kind: str, ops: list) -> list:
        """As frases IN-WORLD das ops deste beat (spec 043) — o FATO, já em linguagem
        de mundo, construído pela própria tool (`@registro.inworld`).

        Por que sobe no beat: elas já existiam e só eram usadas no DESFECHO, ao fim do
        turno. Mandá-las agora é o que tira a sensação de inércia — o jogador lê o que
        aconteceu no instante em que acontece, sem esperar A Mente e sem custar uma
        chamada de modelo. NÃO é narração: é o fato (fronteira Árbitro/Mente — o
        server dá o fato, A Mente tece a experiência). Sem número, sem mecânica.
        """
        frase = motor.registro.inworld_phrases().get(kind)
        if frase is None:
            return []
        ditos = []
        for op in ops:
            try:
                dito = frase(op)
            except Exception:
                dito = None      # frase que não sabe lidar com a op não derruba o turno
            if dito:
                ditos.append(dito)
        return ditos

    def _merge(out: dict) -> None:
        for k in _ACC_CH:
            v = out.get(k)
            if v:
                acc[k].extend(v)
                if k in _BEAT_CH:  # emite o beat com o MESMO shape do canal (V/IX)
                    _emit("op_applied", {"kind": k, "data": v,
                                         "inworld": _inworld(k, v)})
        if out.get("movement"):
            acc["movement"] = out["movement"]
            _emit("op_applied", {"kind": "movement", "data": out["movement"],
                                 "inworld": []})
        if out.get("narrative_hint") and not acc["mov_hint"]:
            acc["mov_hint"] = out["narrative_hint"]

    def _sub(ch: str, novas: list) -> dict:
        # a op vai junto do contexto CONSULTIVO acumulado (spec 020): learn confere
        # a citação contra `lido` e a fonte contra `falas`; hearsay confere o trecho
        # ouvido. Sem esse contexto, a citação verdadeira seria barrada.
        return {ch: list(novas), "lido": list(queue["lido"]),
                "falas": list(queue["falas"]), "informes": list(queue["informes"])}

    def _apply_queued_delta() -> None:
        """Aplica ao mundo real o que a última tool acabou de enfileirar."""
        for ch in _MUT_CH:
            n = len(queue[ch])
            if n > _seen_len[ch]:
                novas = queue[ch][_seen_len[ch]:]
                _seen_len[ch] = n
                _merge(motor.apply_resolution(actor, _sub(ch, novas),
                                              ensure_action=False))
        mov = queue.get("movement")
        if mov and not _mov_done[0]:
            _mov_done[0] = True
            _merge(motor.apply_resolution(actor, {"movement": mov},
                                          ensure_action=False))
    lido: set = set()       # conteúdos já usados para aprender neste turno (spec 014)
    perguntados: set = set()  # informantes já consultados neste turno (spec 015)
    perguntados_sobre: set = set()  # (fonte, sobre) já consultados (spec 017)
    ouvido: set = set()     # (fonte, sobre, trecho) já ouvidos neste turno (spec 017)
    viajado: set = set()    # destinos já pedidos neste turno (spec 012)
    persuaded: set = set()  # alvos já persuadidos neste turno (spec 007)
    gave_asked: set = set()  # (alvo,item) já pedidos via persuade_give (spec 023)
    stole_asked: set = set()  # (alvo,item) já tentados via steal (spec 023)
    eaten_asked: set = set()  # item já tentado via eat neste turno (spec 046)
    drunk_asked: set = set()  # alvo (item ou object) já tentado via drink (spec 047)
    cooked_asked: set = set()  # (ingredientes, fonte_calor) já tentado via cook (spec 048)
    kindled_asked: set = set()  # materiais já tentados via kindle_fire (spec 053)
    forged_asked: set = set()  # (tipo, materiais, fonte) / (tipo, peca) já tentado (spec 052)
    craft_asked: set = set()  # ("craft", "abrir"/"retomar", ...) já tentado (spec 057)
    butchered_asked: set = set()  # alvo já tentado via butcher neste turno (spec 050)
    forage_asked: set = set()  # onde já tentado via forage neste turno (spec 054)
    brewed_asked: set = set()  # (ingredientes, recipiente) já tentado via brew (spec 055)
    sung_asked: set = set()  # memoria_id já tentado via sing neste turno (spec 058)
    attacked: set = set()   # alvos já golpeados neste turno (spec 008)
    curados: set = set()    # alvos já socorridos neste turno (spec 032)
    carried: set = set()    # alvos já levantados neste turno (spec 010)
    expulsos: set = set()   # alvos já postos para fora neste turno (spec 041)
    negociados: set = set() # parceiros com quem já se negociou (spec 011)
    rejections: dict[tuple, dict] = {}

    def _err(erro: str, campo: str | None = None, validos: list | None = None,
             rej: dict | None = None) -> dict:
        out = {"ok": False, "erro": erro}
        if campo:
            out["campo"] = campo
        if validos:
            out["validos"] = validos
        if rej:
            out["regra"] = rej["regra"]
            # SEGREDO do mundo (Princípio IX): o dado/DC/tendência/virada nunca sobem
            # ao modelo — nem dentro da recusa que ele lê. Só o motivo estruturado. A
            # virada/crítico narram pelo CLIENT (fate_twists), a partir de `rolls`.
            out["valores"] = {k: v for k, v in (rej.get("valores") or {}).items()
                              if k not in ("rolagem", "virada", "critico",
                                           "tendencia", "resultado")}
            if rej.get("corrigivel"):
                # Recusa CORRIGÍVEL (item 31): erro de ESCOLHA (item/alvo errado), não
                # veredito do mundo — o modelo DEVE corrigir e seguir. Leva os `validos`
                # (o que é possível agora), como o porteiro fazia; sem o "não refaça".
                if rej.get("validos"):
                    out["validos"] = rej["validos"]
            elif orienta_laco:
                # Recusa do MUNDO (não é id/parâmetro a corrigir): o veredito está dado.
                # Orienta o modelo a NÃO re-tentar a MESMA ação mexendo na régua para virar
                # o resultado (Princípio X) — sem proibir a mesma ferramenta para OUTRO
                # alvo/item, que é trabalho legítimo.
                #
                # spec 043: SÓ no caminho do Árbitro (`orienta_laco`). É instrução para
                # uma LLM EM LAÇO, e cita "nota/régua" e "narrate" — vocabulário de
                # mecânica. No caminho de PROPOSTA não há laço a orientar, e mandar
                # isso à Mente vazaria mecânica (Princípios V e IX). A recusa que ela
                # recebe é só o motivo, em linguagem de mundo.
                out["erro"] += (" — o mundo decidiu: NÃO refaça a MESMA tentativa mudando a "
                                "nota/régua para virar o veredito; faça OUTRA coisa (a mesma "
                                "ferramenta vale para outro alvo/item) ou chame narrate para "
                                "encerrar")
        return out

    def _deny(item: str, to, rej: dict) -> dict:
        """Registra a rejeição física estruturada e devolve o erro para a LLM.

        Recusa CORRIGÍVEL (posse/slot, item 31) NÃO entra no ledger físico: é erro de
        escolha do modelo, não um fato do mundo a narrar (só o veredito do mundo vira
        fate_twist/prosa). O `_err` já a formata com os `validos`, sem o "não refaça"."""
        why = motor._WHY_BY_REGRA.get(rej["regra"], rej["regra"])
        if not rej.get("corrigivel"):
            rejections[("fis", item)] = {"item": item, "to": to, "regra": rej["regra"],
                                         "valores": rej["valores"], "why": why}
        return _err(why, rej=rej)

    def _stow_spot_for(item_id: str):
        """Onde ESTE item cabe, entre os contêineres abertos de quem age (item 44).

        É a guarda do `stow` SEM destino: guardar é o gesto com que se libera a mão, e
        exigir que A Mente escolha o contêiner é cobrar dela uma decisão que o corpo
        toma sozinho. Devolve o id do contêiner, ou None se não há onde.

        Roda sobre o ÍNDICE DA CENA, com os MESMOS `check_*` do pipeline físico
        (guichê único) — o autoritativo revalida contra os arquivos em
        `fisica.open_container_for`. Nunca devolve o chão: perder um item sem
        perceber é pior que a recusa que este caminho evita.
        """
        e = items.get(item_id) or {}
        for cont_id, ce in items.items():
            if cont_id == item_id or ce.get("porter") != actor:
                continue
            c = ce.get("container")
            if not isinstance(c, dict) or c.get("fechado"):
                continue
            if motor.check_encaixe(item_id, e.get("size") or "P",
                                   cont_id, c.get("max_size")):
                continue
            if motor.check_vaga(cont_id, int(c.get("max_items") or 0),
                                int(c.get("itens") or 0)):
                continue
            return cont_id
        return None

    def _porter_of_dest(dest_kind: str, dest_id: str | None):
        if dest_kind == "char":
            return dest_id
        if dest_kind == "cont":
            return loc.get(dest_id, {}).get("porter")
        return None

    def _track_move(item_id: str, dest_kind: str, dest_id: str | None,
                    new_slot: str | None):
        """Atualiza SÓ o rastreio estático (loc/moved) depois que o executor já
        aplicou de verdade — não há mais física espelhada a manter (spec 021)."""
        porter_d = dest_id if dest_kind == "char" else _porter_of_dest(dest_kind, dest_id)
        loc[item_id] = {"porter": porter_d, "slot": new_slot}
        moved.add(item_id)
        rejections.pop(("fis", item_id), None)

    def _apply_op_now(ch: str, op: dict) -> dict | None:
        """Fase única (020) + Fase B (021): enfileira UMA op mutadora, aplica-e-
        registra no ATO contra os arquivos reais, e devolve a rejeição ESTRUTURADA
        do EXECUTOR ({regra, valores, why}) se ele recusou — é assim que o modelo
        recebe o erro no mesmo turno, agora vindo da física ÚNICA (não do espelho).
        Em recusa, desfaz o enfileiramento (a fila é o log do que foi ACEITO)."""
        queue[ch].append(op)
        out = motor.apply_resolution(actor, _sub(ch, [op]), ensure_action=False)
        rej = (out.get("rejected") or [])
        if rej:
            queue[ch].pop()
            # A VIRADA/crítico de uma tentativa que FALHOU também narra (skill
            # arbitrated-action, Princípio X): o dado sobe a `acc["rolls"]` mesmo sem
            # aplicar a op — senão persuadir/atacar/furtar que erra o teste some sem
            # o jogador ler o momento. Só os rolls; a rejeição em si a TOOL registra
            # (tool_rejections), para não duplicar com o `rejected` do outcome.
            if out.get("rolls"):
                acc["rolls"].extend(out["rolls"])
            return rej[0]
        _seen_len[ch] = len(queue[ch])  # já flushado: execute() não reaplica
        _merge(out)
        return None

    def _apply_arbitrated(ch: str, op: dict) -> tuple[dict | None, bool]:
        """Como `_apply_op_now`, mas para a família ARBITRADA: devolve (rej, rolled).
        `rolled` = um DADO REAL foi lançado (info com `rolagem != None`) — então o
        desfecho é SEGREDO do mundo (Princípio IX) e a tool devolve neutro ao modelo,
        deixando o client narrar. Recusa DETERMINÍSTICA (veredito sem dado: nota 0,
        alvo caído/morto) tem rolled=False e sobe ao modelo (narração + veredito
        único). A virada, rolada ou não, sempre sobe a `acc["rolls"]` (fate_twists)."""
        queue[ch].append(op)
        out = motor.apply_resolution(actor, _sub(ch, [op]), ensure_action=False)
        rej_list = out.get("rejected") or []
        if rej_list:
            queue[ch].pop()
            # A rolagem sobe AQUI porque o caminho de recusa sai sem `_merge`. No
            # caminho de SUCESSO ela NÃO sobe aqui: `_merge` logo abaixo já estende
            # `acc["rolls"]` (rolls está em `_ACC_CH`). Estender nos dois fazia a
            # MESMA rolagem subir duas vezes, e `fate_twists` emitia a frase de
            # virada/crítico DUPLICADA ao jogador — a mesma linha, duas vezes.
            if out.get("rolls"):
                acc["rolls"].extend(out["rolls"])
            rolled = any(r.get("rolagem") is not None for r in (out.get("rolls") or []))
            return rej_list[0], rolled
        _seen_len[ch] = len(queue[ch])
        _merge(out)
        return None, False

    def _check_item(item, tool):
        if not item:
            return _err("informe 'item'")
        if item not in items:
            if item in objects:
                # tentou carregar mobília do lugar: motivo estruturado claro,
                # para a narração contar o porquê (spec 002/004 — objeto_fixo)
                rej = motor._fail("objeto_fixo", objeto=item)
                rejections[("fis", item)] = {
                    "item": item, "regra": rej["regra"], "valores": rej["valores"],
                    "why": motor._WHY_BY_REGRA["objeto_fixo"]}
                return _err(f"'{item}' faz parte do lugar — não se carried_item_ids",
                            rej=rej)
            if item in chars:
                # gente não é item: modelos tentam `take`/`equip` para "pegar
                # alguém no colo". Redireciona em vez de só negar — sem a dica o
                # modelo desiste e narra um feito que não aconteceu (spec 010).
                # Um corpo MORTO tem um destino diferente de quem só é carregado
                # (spec 050, research R3) — a dica aponta pra ferramenta certa.
                if motor.DEAD in (idx["char_conditions"].get(item) or []):
                    return _err(f"'{item}' é um CORPO, não um item — para "
                                "extrair algo dele use a ferramenta butcher",
                                "item", _validos(items))
                return _err(f"'{item}' é uma PESSOA, não um item — para levá-la "
                            "consigo use a ferramenta carry", "item",
                            _validos(items))
            rejections[("fis", item)] = {
                "item": item,
                "why": "item não existe na cena nem em inventário presente"}
            return _err(f"item '{item}' não reconhecido", "item", _validos(items))
        if item in moved:
            return _err(f"'{item}' já foi movimentado neste turno")
        return None

    seen_calls: set = set()  # chamadas idênticas já aceitas neste turno

    def execute(name: str, args: dict) -> tuple[dict, bool]:
        devlog.log("TOOL CHAMADA PELO ÁRBITRO", {"tool": name, "args": args})
        try:
            key = (name, json.dumps(args or {}, sort_keys=True, ensure_ascii=False))
        except (TypeError, ValueError):
            key = None
        if key is not None and key in seen_calls:
            # anti-loop: modelo repetindo a mesma chamada não gera efeito duplicado
            # nem "melhora" resultado — devolve ok neutro e manda seguir adiante.
            result = {"ok": True, "nota": "chamada idêntica já registrada neste "
                      "turno — repetição ignorada; prossiga (narrate encerra)"}
            devlog.log("RETORNO DA VALIDAÇÃO", result)
            return result, False
        result, done = _execute(name, args or {})
        # spec 020: se a tool enfileirou algo mutador, aplica-e-registra AGORA,
        # contra os arquivos reais — a próxima tool já lê o mundo mudado.
        if result.get("ok"):
            _apply_queued_delta()
        if key is not None and result.get("ok") and name != "narrate":
            seen_calls.add(key)
        devlog.log("RETORNO DA VALIDAÇÃO", result)
        return result, done

    ctx = types.SimpleNamespace(
        err=_err, deny=_deny, validos=_validos, apply_op_now=_apply_op_now,
        apply_arbitrated=_apply_arbitrated,
        check_item=_check_item, track_move=_track_move, porter_of_dest=_porter_of_dest,
        stow_spot_for=_stow_spot_for,
        queue=queue, loc=loc, moved=moved, rejections=rejections,
        fechado_state=fechado_state, chars=chars, objects=objects, items=items,
        cand=cand, routes=routes, place_id=place_id, actor=actor, fis=fis,
        hand=hand, idx=idx, context=context,
        sub=_sub, seen_len=_seen_len, merge=_merge,
        MEMORY_INTENSITIES=_MEMORY_INTENSITIES, INTENTION_STATUSES=_INTENTION_STATUSES,
        persuaded=persuaded, gave_asked=gave_asked, stole_asked=stole_asked,
        eaten_asked=eaten_asked, drunk_asked=drunk_asked, cooked_asked=cooked_asked,
        kindled_asked=kindled_asked,
        butchered_asked=butchered_asked, forged_asked=forged_asked,
        craft_asked=craft_asked,
        forage_asked=forage_asked, brewed_asked=brewed_asked, sung_asked=sung_asked,
        attacked=attacked, curados=curados, carried=carried, negociados=negociados,
        expulsos=expulsos,
        viajado=viajado, perguntados=perguntados, perguntados_sobre=perguntados_sobre,
        ouvido=ouvido, lido=lido,
    )
    # spec 038 (L2): o corpo declarado (`ToolSpec.apply`) usa a recusa arbitrada pelo
    # `ctx` (duck-typed) — o Motor não importa o Árbitro. Liga-se aqui, fechando sobre
    # o próprio ctx (o `_arb_deny` já toma o ctx como 1º arg).
    ctx.arb_deny = lambda rolled, narr_key, narr_base, rej: arbiter_tools.base._arb_deny(
        ctx, rolled, narr_key, narr_base, rej)

    def _execute(name: str, args: dict) -> tuple[dict, bool]:
        # spec 038 (L2): o Árbitro só DESPACHA. Tool MIGRADA roda o corpo declarado
        # (`ToolSpec.apply`, co-localizado no Motor); a ainda-não-migrada segue pelo
        # `arbiter_tools.HANDLERS` (tool_X). Os dois coexistem até a migração acabar.
        spec = motor.registro.get_spec(name)
        # spec 038 (US2): tool DESATIVADA neste mundo não resolve, mesmo se o modelo
        # a nomear por prosa — a FACE já a omitiu; aqui é a guarda do despacho.
        if spec is not None and not motor.ativacao.is_active(name):
            return _err(f"ferramenta '{name}' não está ativa neste mundo"), False
        if spec is not None:
            args, ruim = _tipos_ok(spec, args)
            if ruim:
                return _err(ruim[0], ruim[1]), False
        if spec is not None and spec.apply is not None:
            return spec.apply(name, args, ctx)
        h = arbiter_tools.HANDLERS.get(name)
        if h is not None:
            return h(name, args, ctx)
        return _err(f"ferramenta '{name}' não existe"), False

    # spec 043 (Fase A): o que a CAUDA do turno (o laço do Árbitro, ou o despacho de
    # propostas do client) precisa além do que as tools já usam. Expor pelo `ctx` é o
    # que permite `build_ctx` ser chamada sozinha, sem laço de LLM nenhum.
    ctx.acc = acc
    ctx.execute = execute
    ctx.apply_queued_delta = _apply_queued_delta
    ctx.MUT_CH = _MUT_CH
    ctx.ACC_CH = _ACC_CH

    # spec 043 — o JUÍZO, injetado. `ask` é TRANSPORTE PURO: não sabe o que é régua,
    # nota nem capacidade. Quem monta o system/user é cada tool, porque cada régua lê
    # coisas diferentes (a do furto lê a descrição do item; a da disposição lê o que o
    # informante guarda de quem pergunta). Injetar em vez de importar é o que mantém
    # `motor/` sem conhecer `llm` — a mesma fronteira de `ctx.arb_deny`.
    _descrito: dict = {}

    def _describe(ent_id):
        """A PROSA de uma entidade, para as réguas — delega à primitiva do Motor.

        As réguas leem DESCRIÇÃO, não campo: a de furto pesa a vistosidade do item
        pelo que o texto dele diz; a de vantagem lê a postura do alvo.

        NÃO lê mais do `proximity_context`, e a distinção é o conserto (spec 052). O
        bundle é uma VISTA montada para A Mente: ele serve para VALIDAR que a coisa
        está ao alcance — e cada tool já faz isso, contra o próprio enum, ANTES de
        chegar aqui. Ele não é a fonte do que a coisa É. Enquanto foi tratado como
        fonte, as réguas de item julgavam pelo nome, porque a prosa de item e object
        nunca esteve no bundle. A fonte é o arquivo, e quem toca arquivo é primitiva
        (`io.descricao_de`) — não o leitor de contexto do Árbitro.

        Cacheado por turno: a mesma régua costuma perguntar pela mesma entidade mais
        de uma vez, e o `.md` não muda no meio de uma leitura.
        """
        if not ent_id:
            return None
        if ent_id not in _descrito:
            _descrito[ent_id] = motor.descricao_de(ent_id) or {
                "nome": motor.name_of(ent_id)}
        return _descrito[ent_id]

    # spec 053: o que o ATOR CARREGA, entregue às réguas como contexto de LEITURA.
    # Não é enum e não vira parâmetro: A Mente não escolhe o que o corpo já tem. A
    # favorabilidade de acender lê isto para enxergar a pederneira sem que ela vire
    # combustível — dois papéis distintos, dois blocos distintos.
    ctx.em_maos = sorted(i for i, e in items.items() if e.get("porter") == actor)

    ctx.ask = ask if ask is not None else _sem_juizo
    # `prosa` (FR-018): o que o personagem está fazendo e dizendo. A régua lê COMO se
    # tentou, não só quem tentou. Vem da intenção; vazio quando não há.
    ctx.prosa = prosa or {}
    ctx.describe = _describe
    return ctx


def _sem_juizo(system: str, user: str) -> str:
    """`ctx.ask` quando NÃO há modelo ligado (todo o selftest roda assim).

    Devolve vazio de propósito: cada capacidade cai no PRÓPRIO default via
    `juizo.nota(raw, default)` — o neutro do golpe não é o neutro da troca. Falhar
    aqui derrubaria o turno inteiro por falta de um juízo que é, por desenho,
    degradável.
    """
    return ""


def _tipos_ok(spec, args: dict):
    """Confere o TIPO de cada argumento contra a declaração — spec 043.

    A checagem forte de cada capacidade valida EXISTÊNCIA ("esse alvo está na cena?").
    Ela pressupõe o tipo certo, e é uma suposição que quebra: um modelo pequeno manda
    `{"route": ["ladeira-do-sal"]}` onde se espera uma string, e o corpo estoura com
    `TypeError: unhashable type: 'list'` — 500 no server, turno perdido, e o jogador
    lê "erro na requisição" em vez de uma recusa do mundo. Aconteceu no primeiro turno
    da medição com llama3.1:8b.

    Duas atitudes, e a diferença importa:
      - LISTA DE UM ELEMENTO onde se espera escalar é CORRIGIDA. É o erro de
        serialização mais comum de modelo pequeno, a intenção é inequívoca, e recusar
        seria perder o turno por uma vírgula.
      - Qualquer outro descasamento é RECUSA ESTRUTURADA, com o campo. Adivinhar o
        que o modelo quis dizer, aí, seria inventar a ação do personagem.

    Devolve (args_corrigidos, None) ou (args, (mensagem, campo)).
    """
    saida = dict(args or {})
    for param, schema in (spec.params or {}).items():
        if param not in saida or callable(schema):
            continue
        esperado = (schema or {}).get("type")
        valor = saida[param]
        if esperado == "array":
            if valor is not None and not isinstance(valor, list):
                saida[param] = [valor]      # escalar onde se espera lista: envolve
            continue
        if esperado in ("string", "integer", "number") and isinstance(valor, list):
            if len(valor) == 1:
                saida[param] = valor[0]     # o caso comum: corrige e segue
                continue
            return args, (f"'{param}' precisa ser um valor só, não uma lista", param)
        if esperado == "string" and isinstance(valor, dict):
            return args, (f"'{param}' precisa ser o id, não um objeto", param)
    return saida, None


def finalize_turn(ctx, acao: str = "") -> dict:
    """FECHA o turno e monta o outcome — comum aos DOIS caminhos (spec 043).

    Extraído da cauda de `resolve_with_tools` porque o despacho de PROPOSTA
    (`/api/tools/<nome>`) precisa exatamente do mesmo fecho: o hint, o toque único da
    ação do ator (FR-014) e a montagem do outcome. Duplicar isso seria a receita para
    os dois caminhos divergirem no que o jogador lê.

    `acao` é a prosa do que se tentou, usada como hint quando nada mais o produziu.
    """
    queue, acc, rejections = ctx.queue, ctx.acc, ctx.rejections
    hint = queue["narrative_hint"] or acc["mov_hint"]
    if not hint and not acc["movement"]:
        algo_aplicado = any(acc[c] for c in (
            "item_transfers_applied", "equip_ops_applied", "lock_ops_applied",
            "attack_ops_applied", "carry_ops_applied", "trade_ops_applied",
            "persuade_ops_applied", "persuade_give_ops_applied", "steal_ops_applied",
            "learn_ops_applied", "hearsay_ops_applied"))
        if rejections and not algo_aplicado:
            hint = "tenta, mas não consegue completar o que pretendia"
        else:
            hint = (acao or "").strip()

    # FR-014: a ação do ator é tocada UMA vez no turno (não por-op) — spec 020
    touched = any(isinstance(a, dict) and a.get("target") == ctx.actor
                  for a in acc["applied"])
    if not touched:
        ctx.merge(motor.apply_resolution(ctx.actor, {"narrative_hint": hint},
                                         ensure_action=True))

    # o OUTCOME já-aplicado (spec 020): `app` NÃO reaplica. Spec 038 (L4): o espelho
    # dos canais aplicados DERIVA de `_ACC_CH` (não mais uma lista à mão que a 026/027
    # já esqueceu de sincronizar uma vez) — junta o que foi aplicado (acc) com o
    # material consultivo (queue).
    resultado = {k: acc[k] for k in ctx.ACC_CH}
    resultado.update({
        "narrative_hint": hint,
        "movement": acc["movement"],
        "tool_rejections": list(rejections.values()),
        "wares": queue["wares"], "lido": queue["lido"],
        "informes": queue["informes"], "falas": queue["falas"],
        "reconhecimentos": queue["reconhecimentos"],
        "_applied_in_loop": True,
    })
    # compat: também expõe os canais de INPUT que foram enfileirados (o LOG do que
    # se pediu), para quem lê `resultado["equip_ops"]` etc. `apply_resolution`
    # reconhece `_applied_in_loop` e devolve isto sem reaplicar.
    for ch in ctx.MUT_CH:
        resultado.setdefault(ch, queue[ch])
    devlog.log("OUTCOME (fase única)", resultado)
    return resultado


def _json_objects(raw: str) -> list:
    """Todos os objetos JSON parseáveis embutidos num texto livre (prosa com
    cercas ```json```, vários objetos separados, comentários ao redor)."""
    objs, i, dec = [], 0, json.JSONDecoder()
    while True:
        start = raw.find("{", i)
        if start == -1:
            break
        try:
            obj, end = dec.raw_decode(raw, start)
        except json.JSONDecodeError:
            i = start + 1
            continue
        objs.append(obj)
        i = end
    return objs


# chaves que identificam um objeto como resolução clássica (formato do SYSTEM_PROMPT)
_RESOLUTION_KEYS = {"narrative_hint", "mutations", "item_transfers",
                    "equip_ops", "persuade_ops", "attack_ops", "carry_ops", "trade_ops", "memories",
                    "movement"}


def _loads_lenient(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    # tolera cercas ```json```, texto ao redor e MÚLTIPLOS objetos no texto:
    # prefere o que tem cara de resolução; senão, o primeiro objeto válido.
    objs = [o for o in _json_objects(raw) if isinstance(o, dict)]
    for obj in objs:
        if _RESOLUTION_KEYS & set(obj):
            return obj
    if objs:
        return objs[0]
    raise LLMError("resolução do Árbitro não contém JSON.")
