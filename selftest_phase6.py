"""Auto-teste da Fase 6 — Árbitro com Tool Calling (spec 003).

Cobre (tudo com transporte FAKE — nenhum teste chama LLM real):
  - build_tools: manifest com enums corretos da cena; tools omitidas sem candidato
  - US1: chamada com id errado recebe erro + "validos", corrige, e a resolução final
    aplica com ids canônicos (o mundo realmente muda)
  - conflito de fila: mesmo item duas vezes no turno é recusado
  - US2: degradação — texto em vez de tools (parse leniente no mesmo turno),
    ToolsUnsupported memorizado (segunda chamada nem tenta), tool_calling: off
  - US3: devlog registra manifest, chamadas, validações e resolução final
  - US4: quem insiste no erro até o limite não muta o mundo, e a sobra vira
    tool_rejections → failed_effects (narrativa coerente com o estado)

Roda sobre uma CÓPIA temporária do mundo de teste. Uso:  python3 server/selftest_phase6.py
"""

from __future__ import annotations

import json
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
os.environ["LOREFORGE_LOG"] = "0"  # silencia o devlog real; o teste captura via patch

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import devlog  # noqa: E402
import llm  # noqa: E402
import motor  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def scripted_loop(script, captured):
    """Transporte fake: executa o roteiro de chamadas contra o handler real do Árbitro."""
    def loop_fn(system, user, tools, execute, max_calls):
        calls = 0
        for name, args in script:
            calls += 1
            result, done = execute(name, args)
            captured.append(result)
            if done:
                return {"stopped": "narrate", "text": None, "calls": calls}
            if calls >= max_calls:
                return {"stopped": "limit", "text": None, "calls": calls}
        return {"stopped": "limit", "text": None, "calls": calls}
    return loop_fn


INTENT = {"action": "deixa a moeda no chão da taverna", "target": None,
          "utterance": None, "movement": None, "note": ""}

try:
    ctx = motor.get_context("torvin-ferreiro")

    # --- build_tools: enums da cena e omissões (spec 004: verbos físicos) ----- #
    tools = arbiter.build_tools(ctx)
    by_name = {t["name"]: t for t in tools}
    check("manifest: verbos físicos + básicas presentes numa cena completa",
          {"take", "stow", "drop", "shove", "equip", "mutate", "create_memory",
           "enter_route", "narrate"} <= set(by_name)
          and "transfer_item" not in by_name)
    take_enum = by_name["take"]["parameters"]["properties"]["item"]["enum"]
    check("manifest: take inclui o loot do baú (contem)", "moeda-de-ouro" in take_enum)
    check("manifest: take inclui inventário/carried_item_ids",
          {"bolsa-de-couro", "frasco-de-oleo"} <= set(take_enum))
    shove_to = by_name["shove"]["parameters"]["properties"]["to"]["enum"]
    check("manifest: shove aceita o chão (id do local)", "taverna-do-gancho" in shove_to)
    route_enum = by_name["enter_route"]["parameters"]["properties"]["route"]["enum"]
    check("manifest: rota da cena no enum", "portao-lateral" in route_enum)

    ctx_vazio = {"characters_present": [{"id": "a", "name": "A"}],
                 "objects_present": [], "items_present": [],
                 "self": {"id": "a", "inventory": [], "fisico": {}},
                 "location": {"id": "x", "name": "X"},
                 "routes": [], "in_transit": True}
    tools_vazio = {t["name"] for t in arbiter.build_tools(ctx_vazio)}
    check("manifest: sem itens não há verbos de item; em trânsito não há enter_route",
          not ({"take", "give", "stow", "drop", "shove", "equip", "unequip"}
               & tools_vazio)
          and "enter_route" not in tools_vazio)

    # --- tool consultiva: observe_entity com recorte de percepção ------------ #
    obs_bau = motor.observe_entity("torvin-ferreiro", "bau-trancado")
    check("observe: object presente na cena é observável (com descrição diegética)",
          obs_bau["kind"] == "object" and bool(obs_bau["description"].strip()))
    obs_self = motor.observe_entity("torvin-ferreiro", "torvin-ferreiro")
    check("observe: o próprio personagem é observável (traz o que faz agora)",
          obs_self["kind"] == "character" and obs_self["observer"] == obs_self["name"])
    check("observe: item aninhado no PRÓPRIO inventário é observável",
          motor.observe_entity("torvin-ferreiro", "frasco-de-oleo")["kind"] == "item")
    try:
        motor.observe_entity("torvin-ferreiro", "moeda-de-ouro")
        vazou = True
    except motor.MotorError:
        vazou = False
    check("observe: item dentro de contêiner fechado é NEGADO (anti-metagaming)",
          not vazou)
    try:
        motor.observe_entity("torvin-ferreiro", "placa-de-aviso")
        vazou2 = True
    except motor.MotorError:
        vazou2 = False
    check("observe: entidade de outro lugar (na rota) é NEGADA", not vazou2)

    # --- US1 + US3: correção no mesmo turno, com devlog capturado ------------ #
    logged = []
    _orig_log = devlog.log
    devlog.log = lambda label, content=None: logged.append((label, content))
    try:
        captured = []
        script = [
            ("shove", {"item": "moeda-de-ouro", "to": "chão da taverna"}),
            ("shove", {"item": "moeda-de-ouro", "to": "taverna-do-gancho"}),
            ("narrate", {"narrative_hint": "a moeda repousa no chão da taverna"}),
        ]
        resolution = arbiter.resolve_with_tools(
            INTENT, ctx, scripted_loop(script, captured), max_calls=8)
    finally:
        devlog.log = _orig_log

    check("US1: primeira chamada rejeitada com campo e validos",
          captured[0].get("ok") is False and captured[0].get("campo") == "to"
          and any(v["id"] == "taverna-do-gancho" for v in captured[0].get("validos", [])))
    check("US1: 'validos' traz nome junto do id (o 8b corrige pelo nome)",
          any(v.get("nome") for v in captured[0].get("validos", [])))
    check("US1: chamada corrigida aceita", captured[1].get("ok") is True)
    check("US1: resolução final com ids canônicos",
          resolution["item_transfers"] == [{"item": "moeda-de-ouro",
                                            "to": "taverna-do-gancho", "mode": "shove"}])
    check("US1: rejeição corrigida NÃO sobra em tool_rejections",
          resolution.get("tool_rejections") == [])
    check("US1: narrate encerrou com o hint",
          resolution["narrative_hint"] == "a moeda repousa no chão da taverna")

    labels = [lab for lab, _ in logged]
    check("US3: devlog registra manifest do turno", "MANIFEST DE TOOLS DO TURNO" in labels)
    check("US3: devlog registra as chamadas e validações na ordem",
          labels.count("TOOL CHAMADA PELO ÁRBITRO") == 3
          and labels.count("RETORNO DA VALIDAÇÃO") == 3
          and "OUTCOME (fase única)" in labels)  # spec 020: era "RESOLUÇÃO ACUMULADA"

    outcome = motor.apply_resolution("torvin-ferreiro", resolution)
    check("US1: aplicação atômica moveu a moeda para o chão da taverna",
          outcome["item_transfers_applied"] == [{"item": "moeda-de-ouro",
                                                 "to": "taverna-do-gancho"}]
          and (motor.WORLD_DIR / "taverna-do-gancho" / "moeda-de-ouro"
               / "item.md").exists())

    # --- conflito de fila: mesmo item duas vezes no turno --------------------- #
    captured2 = []
    script2 = [
        ("take", {"item": "moeda-de-ouro"}),
        ("give", {"item": "moeda-de-ouro", "to": "elga-taverneira"}),
        ("narrate", {"narrative_hint": "a moeda muda de mãos uma única vez"}),
    ]
    res2 = arbiter.resolve_with_tools(INTENT, ctx, scripted_loop(script2, captured2))
    check("conflito: segunda movimentação do mesmo item recusada",
          captured2[1].get("ok") is False
          and "já foi movimentado" in captured2[1].get("erro", ""))
    check("conflito: só a primeira entra na fila",
          res2["item_transfers"] == [{"item": "moeda-de-ouro", "to": "torvin-ferreiro"}])

    # --- item 31: posse/slot são AUTORIDADE do executor, não pré-voo da tool --- #
    # `espada-curta` está no CHÃO (torvin não a segura). Antes a tool recusava por
    # conta própria; agora quem recusa é `_apply_item_transfers` — e a recusa vem
    # CORRIGÍVEL (leva os validos, sem o "não refaça" do veredito do mundo).
    cap_np = []
    arbiter.resolve_with_tools(INTENT, ctx, scripted_loop(
        [("give", {"item": "espada-curta", "to": "elga-taverneira"})], cap_np))
    r_np = cap_np[0]
    check("item31: give de item não-possuído recusa com regra nao_possui_item",
          r_np.get("ok") is False and r_np.get("regra") == "nao_possui_item")
    check("item31: recusa corrigível leva validos e NÃO traz o 'não refaça' do veredito",
          bool(r_np.get("validos")) and "não refaça" not in r_np.get("erro", ""))
    cap_dp = []
    arbiter.resolve_with_tools(INTENT, ctx, scripted_loop(
        [("drop", {"item": "espada-curta"})], cap_dp))
    check("item31: drop de item não-possuído recusa pela MESMA autoridade",
          cap_dp[0].get("regra") == "nao_possui_item")
    # shove é o oposto: só o SOLTO se empurra. `bolsa-de-couro` está na mão do torvin.
    cap_sh = []
    arbiter.resolve_with_tools(INTENT, ctx, scripted_loop(
        [("shove", {"item": "bolsa-de-couro", "to": "taverna-do-gancho"})], cap_sh))
    r_sh = cap_sh[0]
    check("item31: shove de item carregado recusa item_carregado (corrigível, com validos)",
          r_sh.get("regra") == "item_carregado" and bool(r_sh.get("validos"))
          and "não refaça" not in r_sh.get("erro", ""))

    # --- US2: modelo responde texto (sem tools) → parse leniente no turno ---- #
    texto = json.dumps({
        "narrative_hint": "Torvin range os dentes",
        "movement": None,
        "mutations": [{"target": "torvin-ferreiro", "path": "status.mood",
                       "value": "irritado", "reason": "texto"}],
        "item_transfers": [], "memories": [],
    })

    def text_loop(system, user, tools, execute, max_calls):
        return {"stopped": "text", "text": texto, "calls": 0}

    res_texto = arbiter.resolve_with_tools(INTENT, ctx, text_loop)
    check("US2: texto sem tools vira resolução via parse leniente (mesmo turno)",
          res_texto["narrative_hint"] == "Torvin range os dentes"
          and res_texto["mutations"][0]["path"] == "status.mood")

    # --- US2b: modelo DESCREVE as tools em prosa (caso llama3.1:8b real) ------ #
    # dois JSONs cercados no meio do texto → executados pela MESMA guarda,
    # nunca um 5xx ("Extra data") nem um caminho de validação paralelo.
    prosa = (
        "Para resolver a ação, primeiro pegamos o seixo:\n\n"
        "```json\n"
        '{\n  "name": "take",\n  "parameters": {\n    "item": "seixo-branco"\n  }\n}\n'
        "```\n\n"
        "Depois encerramos o turno:\n\n"
        "```json\n"
        '{\n  "name": "narrate",\n  "parameters": {\n'
        '    "narrative_hint": "recolhe o seixo branco do chão"\n  }\n}\n'
        "```\n\nEssa é uma possível solução para a ação.\n"
    )

    def prose_loop(system, user, tools, execute, max_calls):
        return {"stopped": "text", "text": prosa, "calls": 0}

    res_prosa = arbiter.resolve_with_tools(INTENT, ctx, prose_loop)
    check("US2b: tools descritas em prosa são executadas pela guarda",
          res_prosa["item_transfers"] == [{"item": "seixo-branco",
                                           "to": "torvin-ferreiro"}]
          and res_prosa["narrative_hint"] == "recolhe o seixo branco do chão")
    check("US2b: nada sobra em tool_rejections quando a prosa era válida",
          res_prosa.get("tool_rejections") == [])

    # --- spec 020: runtime SEM tool-calling deixou de ser suportado (FR-011) -- #
    # Não há mais degradação para o modo clássico: resolve_action exige tools e
    # levanta erro claro se o runtime não as oferece.
    def unsupported_factory():
        def loop_fn(system, user, tools, execute, max_calls):
            raise llm.ToolsUnsupported("modelo de teste sem tools")
        return loop_fn

    def _unused_model_factory():
        return lambda system, user: ""

    try:
        server_app.resolve_action(INTENT, ctx, {"tool_calling": "auto"},
                                  unsupported_factory, _unused_model_factory)
        exigiu = False
    except llm.LLMError:
        exigiu = True
    check("spec 020: runtime sem tool-calling → erro claro (sem fallback clássico)",
          exigiu)

    # --- US4: insistência no erro até o limite — mundo intacto, sobra honesta - #
    # spec 020: o `take` do teste res2 aplicou por-op (fase única) — a moeda está na
    # mão do Torvin agora, não no chão. O proxy "um item segue existindo" aponta pra lá.
    moeda_antes = (motor.find_character_folder("torvin-ferreiro")
                   / "moeda-de-ouro" / "item.md")
    captured3 = []
    script3 = [("take", {"item": "machado-fantasma"})] * 5
    res3 = arbiter.resolve_with_tools(INTENT, ctx, scripted_loop(script3, captured3),
                                      max_calls=3)
    check("US4: loop parou no limite com todas as chamadas rejeitadas",
          len(captured3) == 3 and all(r.get("ok") is False for r in captured3))
    check("US4: sobra vira tool_rejections com o motivo",
          any(r.get("item") == "machado-fantasma" and r.get("why")
              for r in res3.get("tool_rejections", [])))
    check("US4: hint derivado não afirma sucesso",
          res3["narrative_hint"] == "tenta, mas não consegue completar o que pretendia")
    frases = server_app.inworld_failures(res3["tool_rejections"])
    check("US4: sobra vira frase de mundo para a narração (failed_effects)",
          any("machado-fantasma" in f for f in frases))
    outcome3 = motor.apply_resolution("torvin-ferreiro", res3)
    check("US4: mundo intacto — só a garantia de consequência (status.action)",
          outcome3["item_transfers_applied"] == [] and moeda_antes.exists()
          and all(a.get("path") == "status.action" for a in outcome3["applied"]))

    # --- resultado ----------------------------------------------------------- #
    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 6 (US1-US4) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
