"""Auto-teste da Fase 5 — Object e Interactions Consultivas (spec 002, US1).

Cobre:
  - World Validator aceita `object` com `interactions`/`state`, e `item` com `interactions`
  - moeda dentro do baú fechado NÃO aparece em items_present (fica oculta até revelada)
  - mutation em state.<campo> de um object presente persiste no arquivo (sem depender de
    memória ativa) e é rejeitada quando tenta mudar identidade (id/name/type/interactions)
  - item_transfers move um item presente na cena para o inventário do personagem atuante
    (pegar/saquear) e depois para o inventário de outro personagem presente (dar), de forma
    atômica — nunca em duas posses ao mesmo tempo

Roda sobre uma CÓPIA temporária do mundo de teste. Uso:  python3 server/selftest_phase5.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import validator  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


try:
    # --- mundo-semente (com a fixture do baú) é íntegro --------------------- #
    check("mundo com fixture do baú sem problemas de schema", motor.validate_world() == [],
          str(motor.validate_world()))

    bau_fm, _ = motor.read_doc(motor.WORLD_DIR / "taverna-do-gancho" / "bau-trancado" / "object.md")
    check("validator: bau-trancado (object + interactions + state) válido",
          validator.validate(bau_fm) == [])

    moeda_fm, _ = motor.read_doc(
        motor.WORLD_DIR / "taverna-do-gancho" / "bau-trancado" / "moeda-de-ouro" / "item.md"
    )
    check("validator: moeda-de-ouro (item aninhado) válido", validator.validate(moeda_fm) == [])

    check("validator: rejeita object com state que não é mapa",
          len(validator.validate({"type": "object", "id": "x", "name": "X", "state": "ruim"})) > 0)
    check("validator: rejeita item com state que não é mapa",
          len(validator.validate({"type": "item", "id": "x", "name": "X", "state": "ruim"})) > 0)
    check("validator: aceita item com state mapa (item pode quebrar/gastar)",
          validator.validate({"type": "item", "id": "x", "name": "X",
                              "state": {"quebrado": True}}) == [])
    check("validator: rejeita interaction sem 'action'",
          len(validator.validate({"type": "item", "id": "x", "name": "X",
                                   "interactions": [{"requires": None}]})) > 0)

    # --- baú presente na cena, moeda oculta enquanto dentro dele ------------- #
    ctx = motor.get_context("torvin-ferreiro")
    objects_by_id = {o["id"]: o for o in ctx["objects_present"]}
    check("motor: bau-trancado presente em objects_present", "bau-trancado" in objects_by_id)
    check("motor: interactions do bau chegam no contexto",
          bool(objects_by_id.get("bau-trancado", {}).get("interactions")))
    contains_ids = {c["id"] for c in objects_by_id.get("bau-trancado", {}).get("contains") or []}
    check("motor: 'contains' do bau referencia a moeda (Árbitro sabe que ela existe)",
          "moeda-de-ouro" in contains_ids)
    items_ids = {it["id"] for it in ctx["items_present"]}
    check("motor: moeda-de-ouro NÃO aparece em items_present (ainda dentro do baú)",
          "moeda-de-ouro" not in items_ids)

    # --- inventário visível no contexto (Mente/Árbitro sabem o que se carried_item_ids) - #
    inv_ids = {it["id"] for it in ctx["self"].get("inventory") or []}
    check("motor: inventário do ator no contexto (bolsa-de-couro)",
          "bolsa-de-couro" in inv_ids)
    check("motor: inventário do ator inclui itens aninhados (frasco-de-oleo)",
          "frasco-de-oleo" in inv_ids)
    presentes = {c["id"]: c for c in ctx["characters_present"]}
    check("motor: presentes trazem 'carrying' (o que cada um carried_item_ids)",
          "carrying" in presentes.get("elga-taverneira", {}))

    # --- resolução simulada do Árbitro: arromba o baú e saqueia a moeda ------ #
    resolution = {
        "narrative_hint": "força a fechadura do baú até ela ceder",
        "movement": None,
        "mutations": [
            {"target": "bau-trancado", "path": "state.trancado", "value": False,
             "reason": "arrombado com sucesso"},
            # tentativa de mutar identidade — deve ser rejeitada
            {"target": "bau-trancado", "path": "name", "value": "Baú Arrombado (hack)",
             "reason": "não deveria aplicar"},
        ],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "torvin-ferreiro"}],
        "memories": [],
    }
    outcome = motor.apply_resolution("torvin-ferreiro", resolution)
    check("apply_resolution: mutation de state aplicada",
          any(a.get("path") == "state.trancado" for a in outcome["applied"]))
    check("apply_resolution: mutation de identidade rejeitada",
          any(r.get("path") == "name" and r.get("why") == "identidade é imutável por ação"
              for r in outcome["rejected"]))
    check("apply_resolution: item_transfer (pegar) aplicado",
          outcome["item_transfers_applied"] == [{"item": "moeda-de-ouro", "to": "torvin-ferreiro"}])

    # --- state persiste em nova consulta, sem depender de memória ativa ------ #
    bau_fm2, _ = motor.read_doc(
        motor.WORLD_DIR / "taverna-do-gancho" / "bau-trancado" / "object.md"
    )
    check("state.trancado persistido no arquivo após a mutação",
          bau_fm2.get("state", {}).get("trancado") is False)
    check("interactions preservadas no arquivo após a mutação (não foram apagadas)",
          bool(bau_fm2.get("interactions")))
    check("origin preservado no arquivo após a mutação (round-trip íntegro)",
          bau_fm2.get("origin") == "editorial")

    ctx2 = motor.get_context("torvin-ferreiro")
    objects_by_id2 = {o["id"]: o for o in ctx2["objects_present"]}
    check("motor: bau continua presente, identidade intacta (name não mudou)",
          objects_by_id2.get("bau-trancado", {}).get("name") == "Baú de ferro trancado")

    inv_torvin = motor.get_inventory("torvin-ferreiro")
    torvin_item_ids = {c["id"] for c in inv_torvin["children"]}
    check("moeda-de-ouro agora no inventário de torvin (pegar)", "moeda-de-ouro" in torvin_item_ids)

    # --- dar a moeda para outro personagem presente (elga-taverneira) ------- #
    resolution_dar = {
        "narrative_hint": "entrega a moeda a Elga",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "elga-taverneira"}],
        "memories": [],
    }
    outcome_dar = motor.apply_resolution("torvin-ferreiro", resolution_dar)
    check("apply_resolution: item_transfer (dar) aplicado",
          outcome_dar["item_transfers_applied"] == [{"item": "moeda-de-ouro", "to": "elga-taverneira"}])

    inv_torvin2 = motor.get_inventory("torvin-ferreiro")
    inv_elga = motor.get_inventory("elga-taverneira")
    torvin_ids2 = {c["id"] for c in inv_torvin2["children"]}
    elga_ids = {c["id"] for c in inv_elga["children"]}
    check("moeda saiu do inventário de torvin", "moeda-de-ouro" not in torvin_ids2)
    check("moeda está no inventário de elga (posse atômica: só num lugar)",
          "moeda-de-ouro" in elga_ids)

    ctx_dar = motor.get_context("torvin-ferreiro")
    elga_ctx = next(c for c in ctx_dar["characters_present"] if c["id"] == "elga-taverneira")
    check("motor: 'carrying' de elga no contexto reflete a moeda recebida",
          "moeda-de-ouro" in {it["id"] for it in elga_ctx.get("carrying") or []})

    # --- dar um item do próprio inventário (o caso 'dê sua faca a fulano') --- #
    resolution_dar_inv = {
        "narrative_hint": "entrega a bolsa de couro a Elga",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "bolsa-de-couro", "to": "elga-taverneira"}],
        "memories": [],
    }
    outcome_dar_inv = motor.apply_resolution("torvin-ferreiro", resolution_dar_inv)
    check("apply_resolution: dar item do PRÓPRIO inventário aplicado",
          outcome_dar_inv["item_transfers_applied"] == [{"item": "bolsa-de-couro",
                                                         "to": "elga-taverneira"}])
    elga_ids2 = {c["id"] for c in motor.get_inventory("elga-taverneira")["children"]}
    check("bolsa-de-couro agora no inventário de elga", "bolsa-de-couro" in elga_ids2)

    # --- item_transfer inválido é rejeitado com motivo, sem erro fatal -------- #
    resolution_invalida = {
        "narrative_hint": "tenta pegar algo que não existe",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "item-inexistente", "to": "torvin-ferreiro"}],
        "memories": [],
    }
    outcome_invalida = motor.apply_resolution("torvin-ferreiro", resolution_invalida)
    check("item_transfer inválido não é aplicado (lista vazia, sem exceção)",
          outcome_invalida["item_transfers_applied"] == [])
    check("item_transfer inválido aparece em rejected com o motivo (não silencioso)",
          any(r.get("item") == "item-inexistente" and r.get("why")
              for r in outcome_invalida["rejected"]))
    check("mesmo com transfer inválido, ainda há consequência (FR-014)",
          len(outcome_invalida["applied"]) >= 1)

    # --- mutation de state.* em ITEM presente (quebrar/gastar), onde estiver - #
    # o frasco-de-oleo está aninhado na bolsa-de-couro, agora no inventário de elga:
    # ainda é cena — item presente pode mudar de estado onde quer que esteja.
    resolution_quebra = {
        "narrative_hint": "o frasco escorrega e racha no chão de pedra",
        "movement": None,
        "mutations": [
            {"target": "frasco-de-oleo", "path": "state.quebrado", "value": True,
             "reason": "caiu no chão"},
            # identidade de item continua imutável
            {"target": "frasco-de-oleo", "path": "name", "value": "Caco de Vidro",
             "reason": "não deveria aplicar"},
        ],
        "item_transfers": [], "memories": [],
    }
    outcome_quebra = motor.apply_resolution("torvin-ferreiro", resolution_quebra)
    check("apply_resolution: mutation de state em item aplicada",
          any(a.get("path") == "state.quebrado" for a in outcome_quebra["applied"]))
    check("apply_resolution: identidade de item rejeitada",
          any(r.get("path") == "name" for r in outcome_quebra["rejected"]))
    frasco_fm, _ = motor.read_doc(
        motor.WORLD_DIR / "taverna-do-gancho" / "elga-taverneira" / "bolsa-de-couro"
        / "frasco-de-oleo" / "item.md"
    )
    check("state.quebrado persistido no arquivo do item",
          frasco_fm.get("state", {}).get("quebrado") is True)
    check("identidade do item intacta no arquivo", frasco_fm.get("name") == "Frasco de Óleo")

    # --- memórias em VÁRIOS presentes na mesma resolução (briga no bar) ------ #
    resolution_briga = {
        "narrative_hint": "a discussão vira empurra-empurra diante de todos",
        "movement": None, "mutations": [], "item_transfers": [],
        "memories": [
            {"target": "torvin-ferreiro", "content": "Perdi a cabeça e empurrei Elga.",
             "summary": "empurrei Elga", "intensity": "medium", "ttl_seconds": 3600},
            {"target": "elga-taverneira", "content": "Torvin me empurrou na frente de todos.",
             "summary": "Torvin me empurrou", "intensity": "large", "ttl_seconds": 7200},
        ],
    }
    outcome_briga = motor.apply_resolution("torvin-ferreiro", resolution_briga)
    check("memórias criadas para VÁRIOS presentes na mesma ação",
          {m["target"] for m in outcome_briga["memories_created"]}
          == {"torvin-ferreiro", "elga-taverneira"})
    mem_elga = motor.get_active_memories(motor.WORLD_DIR / "taverna-do-gancho" / "elga-taverneira")
    check("memória da testemunha/afetada ativa e na perspectiva dela",
          any("me empurrou" in (m.get("content") or "") for m in mem_elga))

    # --- guardar item DENTRO de um contêiner (bolsa = item, baú = object) ---- #
    # a moeda está solta com elga; a bolsa-de-couro também está com elga.
    resolution_guardar = {
        "narrative_hint": "guarda a moeda dentro da bolsa de couro",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "bolsa-de-couro"}],
        "memories": [],
    }
    outcome_guardar = motor.apply_resolution("torvin-ferreiro", resolution_guardar)
    check("item_transfer para item-contêiner (guardar na bolsa) aplicado",
          outcome_guardar["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                         "to": "bolsa-de-couro"}])
    check("moeda agora vive aninhada dentro da bolsa",
          (motor.WORLD_DIR / "taverna-do-gancho" / "elga-taverneira" / "bolsa-de-couro"
           / "moeda-de-ouro" / "item.md").exists())
    elga_inv = {c["id"] for c in motor._nested_item_refs(
        motor.WORLD_DIR / "taverna-do-gancho" / "elga-taverneira")}
    check("moeda segue no inventário (flat) de elga, só que dentro da bolsa",
          "moeda-de-ouro" in elga_inv)

    # spec 004 (FR-009): o que está dentro do contêiner de OUTRO personagem é
    # invisível/inacessível a terceiros — estas ações agora são da própria Elga,
    # que alcança o que carried_item_ids.
    resolution_ciclo = {
        "narrative_hint": "tenta guardar a bolsa dentro do frasco",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "bolsa-de-couro", "to": "frasco-de-oleo"}],
        "memories": [],
    }
    outcome_ciclo = motor.apply_resolution("elga-taverneira", resolution_ciclo)
    check("ciclo (contêiner dentro de si mesmo) rejeitado com motivo",
          outcome_ciclo["item_transfers_applied"] == []
          and any("si mesmo" in (r.get("why") or "") for r in outcome_ciclo["rejected"]))

    resolution_bau = {
        "narrative_hint": "esconde a moeda dentro do baú",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "bau-trancado"}],
        "memories": [],
    }
    outcome_bau = motor.apply_resolution("elga-taverneira", resolution_bau)
    check("item_transfer para object (esconder no baú) aplicado",
          outcome_bau["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                     "to": "bau-trancado"}])
    ctx_bau = motor.get_context("torvin-ferreiro")
    check("moeda escondida no baú some de items_present e volta ao 'contains'",
          "moeda-de-ouro" not in {it["id"] for it in ctx_bau["items_present"]}
          and "moeda-de-ouro" in {c["id"] for o in ctx_bau["objects_present"]
                                  if o["id"] == "bau-trancado"
                                  for c in o.get("contains") or []})

    # --- largar item no CHÃO (to = id do local atual) ------------------------ #
    resolution_chao = {
        "narrative_hint": "deixa a moeda cair no chão da taverna",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "taverna-do-gancho"}],
        "memories": [],
    }
    outcome_chao = motor.apply_resolution("torvin-ferreiro", resolution_chao)
    check("item_transfer para o local (largar no chão) aplicado",
          outcome_chao["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                      "to": "taverna-do-gancho"}])
    check("moeda agora é filha direta da location",
          (motor.WORLD_DIR / "taverna-do-gancho" / "moeda-de-ouro" / "item.md").exists())
    ctx_chao = motor.get_context("torvin-ferreiro")
    check("moeda largada no chão reaparece em items_present (visível a todos)",
          "moeda-de-ouro" in {it["id"] for it in ctx_chao["items_present"]})

    # --- referências frouxas do Árbitro (nome por extenso, 'chão de...') ----- #
    # modelos pequenos escrevem nome em vez de id; o Motor canoniza sem chutar.
    resolution_frouxa = {
        "narrative_hint": "recolhe a moeda do chão",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "Moeda de Ouro", "to": "Torvin, o Ferreiro"}],
        "memories": [],
    }
    outcome_frouxa = motor.apply_resolution("torvin-ferreiro", resolution_frouxa)
    check("referência por NOME resolve para os ids canônicos",
          outcome_frouxa["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                        "to": "torvin-ferreiro"}])

    resolution_chao2 = {
        "narrative_hint": "deixa a moeda cair de novo no chão",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "chão da taverna do gancho"}],
        "memories": [],
    }
    outcome_chao2 = motor.apply_resolution("torvin-ferreiro", resolution_chao2)
    check("'chão da <location>' resolve para o local atual",
          outcome_chao2["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                       "to": "taverna-do-gancho"}])
    check("moeda de volta ao chão da taverna",
          (motor.WORLD_DIR / "taverna-do-gancho" / "moeda-de-ouro" / "item.md").exists())

    resolution_inexistente = {
        "narrative_hint": "procura algo que não está aqui",
        "movement": None, "mutations": [],
        "item_transfers": [{"item": "moeda-de-ouro", "to": "espelho de prata"}],
        "memories": [],
    }
    outcome_inexistente = motor.apply_resolution("torvin-ferreiro", resolution_inexistente)
    check("referência frouxa sem correspondência ainda é rejeitada (não chuta)",
          outcome_inexistente["item_transfers_applied"] == []
          and any("destinatário" in (r.get("why") or "")
                  for r in outcome_inexistente["rejected"]))

    # --- rejeições viram frases de mundo para o narrador (failed_effects) ---- #
    import app as server_app
    frases = server_app.inworld_failures(outcome_inexistente["rejected"])
    check("app: transferência negada vira frase de mundo para a narração",
          any("continua onde estava" in f for f in frases))
    frases_mut = server_app.inworld_failures(
        [{"target": "bau-trancado", "path": "state.trancado", "value": False,
          "why": "alvo não presente na cena"}])
    check("app: mutação negada vira frase de mundo para a narração",
          any("não se concretizou" in f for f in frases_mut))

    # --- US2: inspecionar sempre disponível, com ou sem interactions -------- #
    mesa_detail = motor.get_entity_detail("mesa-de-madeira")
    check("US2: object SEM interactions retorna nome diegético",
          mesa_detail.get("name") == "Mesa de madeira maciça")
    check("US2: object SEM interactions retorna descrição diegética",
          bool((mesa_detail.get("description") or "").strip()))
    check("US2: detalhe do object não vaza campos de sistema (sem 'interactions'/'state' crus)",
          "interactions" not in mesa_detail and "state" not in mesa_detail)

    moeda_detail = motor.get_entity_detail("moeda-de-ouro")
    check("US2: item COM interactions ainda inspeciona normalmente (nome)",
          moeda_detail.get("name") == "Moeda de ouro antiga")
    check("US2: detalhe do item não vaza o bloco 'interactions' cru",
          "interactions" not in moeda_detail)

    # --- US3: objects presentes no contexto (location e rota) --------------- #
    ctx3 = motor.get_context("torvin-ferreiro")
    objects_ids3 = {o["id"] for o in ctx3["objects_present"]}
    check("US3: bau-trancado e mesa-de-madeira presentes juntos na location",
          {"bau-trancado", "mesa-de-madeira"} <= objects_ids3)

    move = motor.enter_route("torvin-ferreiro", "portao-lateral")
    check("US3: torvin entrou na rota portao-lateral", move.get("moved") is True)
    ctx_rota = motor.get_context("torvin-ferreiro")
    check("US3: torvin está em trânsito (na rota)", ctx_rota.get("in_transit") is True)
    objects_rota_ids = {o["id"] for o in ctx_rota["objects_present"]}
    check("US3: object ancorado na rota (placa-de-aviso) presente para quem está em trânsito",
          "placa-de-aviso" in objects_rota_ids)

    # --- resultado --------------------------------------------------------- #
    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 5 (US1-US3) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
