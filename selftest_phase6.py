"""Auto-teste da Fase 6 — Árbitro com Tool Calling (spec 003).

Cobre (tudo com transporte FAKE — nenhum teste chama LLM real):
  - build_tools: manifest com enums corretos da cena; tools omitidas sem candidato
  - US1: chamada com id errado recebe erro + "validos", corrige, e a resolução final
    aplica com ids canônicos (o mundo realmente muda)
  - conflito de fila: mesmo item duas vezes no turno é recusado
  - US3: devlog registra chamadas, validações e resolução final
  - US4: quem insiste no erro até o limite não muta o mundo, e a sobra vira
    tool_rejections → failed_effects (narrativa coerente com o estado)

spec 045: os casos que cobriam a DEGRADAÇÃO (texto em vez de tools com parse
leniente, ToolsUnsupported, tool_calling: off) saíram daqui — testavam
comportamento interno de `arbiter.resolve_with_tools`, removido junto com o
Fluxo B (prosa legado via /api/act). Não há mais segundo motor pra degradar
para; ver `selftest_helpers.resolve_scripted` e `loreforge-connector/laco.js`
(`_porQueNada`/`_fecharTurno`) para o caminho único que resta.

Roda sobre uma CÓPIA temporária do mundo de teste. Uso:  python3 server/selftest_phase6.py
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
os.environ["LOREFORGE_LOG"] = "0"  # silencia o devlog real; o teste captura via patch

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import devlog  # noqa: E402
import motor  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


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
        resolution = selftest_helpers.resolve_scripted(
            INTENT, ctx, script, captured=captured)
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

    # spec 045: "MANIFEST DE TOOLS DO TURNO" era logado só dentro de
    # `resolve_with_tools` (o laço do Fluxo B, removido) — o caminho único
    # (`resolver_proposta`) nunca monta um manifesto de turno, já que cada
    # chamada HTTP é UM `execute()` só; não há substituto a testar aqui.
    labels = [lab for lab, _ in logged]
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
    res2 = selftest_helpers.resolve_scripted(INTENT, ctx, script2, captured=captured2)
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
    selftest_helpers.resolve_scripted(INTENT, ctx, [
        ("give", {"item": "espada-curta", "to": "elga-taverneira"})], captured=cap_np)
    r_np = cap_np[0]
    check("item31: give de item não-possuído recusa com regra nao_possui_item",
          r_np.get("ok") is False and r_np.get("regra") == "nao_possui_item")
    check("item31: recusa corrigível leva validos e NÃO traz o 'não refaça' do veredito",
          bool(r_np.get("validos")) and "não refaça" not in r_np.get("erro", ""))
    cap_dp = []
    selftest_helpers.resolve_scripted(INTENT, ctx, [
        ("drop", {"item": "espada-curta"})], captured=cap_dp)
    check("item31: drop de item não-possuído recusa pela MESMA autoridade",
          cap_dp[0].get("regra") == "nao_possui_item")
    # shove é o oposto: só o SOLTO se empurra. `bolsa-de-couro` está na mão do torvin.
    cap_sh = []
    selftest_helpers.resolve_scripted(INTENT, ctx, [
        ("shove", {"item": "bolsa-de-couro", "to": "taverna-do-gancho"})], captured=cap_sh)
    r_sh = cap_sh[0]
    check("item31: shove de item carregado recusa item_carregado (corrigível, com validos)",
          r_sh.get("regra") == "item_carregado" and bool(r_sh.get("validos"))
          and "não refaça" not in r_sh.get("erro", ""))

    # --- spec 045: degradação por texto/ToolsUnsupported não existe mais ----- #
    # As US2/US2b (modelo respondendo em prosa em vez de tool_call, com parse
    # leniente) e o teste de ToolsUnsupported (spec 020/FR-011) testavam
    # comportamento interno de `arbiter.resolve_with_tools` — removido junto
    # com o Fluxo B (spec 045). Não há mais segundo motor pra degradar: o
    # caminho único (conector → MCP → guichê único) ou produz um tool_call ou
    # termina no recado honesto (`_porQueNada`/`_fecharTurno` em laco.js,
    # coberto por `loreforge-connector/test/laco.test.js`).

    # --- US4: insistência no erro não muta o mundo, sobra vira recado honesto - #
    # spec 020: o `take` do teste res2 aplicou por-op (fase única) — a moeda está na
    # mão do Torvin agora, não no chão. O proxy "um item segue existindo" aponta pra lá.
    # spec 045: o TETO de chamadas por turno era imposto pelo loop_fn do servidor
    # (max_calls); sem ele, quem limita rodadas é o conector (MAX_RODADAS em
    # mente.js). Aqui só resta provar que insistir no MESMO erro não corrompe o
    # mundo nem some com o motivo — não "parar em exatamente N chamadas".
    moeda_antes = (motor.find_character_folder("torvin-ferreiro")
                   / "moeda-de-ouro" / "item.md")
    captured3 = []
    script3 = [("take", {"item": "machado-fantasma"})] * 3
    res3 = selftest_helpers.resolve_scripted(INTENT, ctx, script3, captured=captured3)
    check("US4: toda insistência no mesmo erro é rejeitada (nada se corrompe)",
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
