"""Auto-teste da Fase 8 — Contêineres Abertos/Fechados e Travas (spec 005).

Cobre os cenários do quickstart da spec 005 (§1, 1–18), sem LLM real:
  - Validator: state.fechado, bloco locks (parcial/tipo/required; locks em item
    sem container)
  - Invisibilidade do fechado (contexto, inventário, observe, cadeia) com física
    intacta (peso/vagas contam o conteúdo)
  - open/close sem travas; no-ops; container_fechado em stow; mutate is_blocked
  - Travas de item: 0/1/2 chaves; deny_reason; chave em contêiner fechado não
    conta; chave DENTRO do alvo não satisfaz (anti-deadlock ao fechar)
  - Fallback JSON lock_ops: abre-e-pega no mesmo turno
  - Aviso autoral de deadlock em world_warnings(); legado permanece aberto

Roda sobre uma CÓPIA temporária do mundo de teste. Uso:  python3 server/selftest_phase8.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import arbiter  # noqa: E402
import motor  # noqa: E402
import validator  # noqa: E402

FAILS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def scripted_loop(script, captured):
    def loop_fn(system, user, tools, execute, max_calls):
        calls = 0
        for name, args in script:
            calls += 1
            result, done = execute(name, args)
            captured.append(result)
            if done:
                return {"stopped": "narrate", "text": None, "calls": calls}
        return {"stopped": "limit", "text": None, "calls": calls}
    return loop_fn


def res(**parts):
    base = {"narrative_hint": parts.pop("hint", "age sobre o que está por perto"),
            "movement": None, "mutations": [], "item_transfers": [],
            "equip_ops": [], "lock_ops": [], "memories": []}
    base.update(parts)
    return base


INTENT = {"action": "mexe nos contêineres da cena", "target": None,
          "utterance": None, "movement": None, "note": ""}

try:
    TAVERNA = motor.WORLD_DIR / "taverna-do-gancho"
    TORVIN = TAVERNA / "torvin-ferreiro"
    BAU = TAVERNA / "bau-lendario"
    CAIXA = TAVERNA / "caixa-de-pinho"

    # ===================== 1: Validator ===================================== #
    check("fixture íntegra no boot", motor.validate_world() == [],
          str(motor.validate_world()))
    check("1a: state.fechado não-bool rejeitado",
          any("state.fechado" in e for e in validator.validate(
              {"type": "object", "id": "x", "name": "X",
               "state": {"fechado": "sim"}})))
    check("1b: trava de item sem 'required' rejeitada",
          any("required" in e for e in validator.validate(
              {"type": "object", "id": "x", "name": "X",
               "locks": {"open": [{"type": "item"}]}})))
    check("1c: tipo de trava desconhecido rejeitado",
          any("desconhecido" in e for e in validator.validate(
              {"type": "object", "id": "x", "name": "X",
               "locks": {"open": [{"type": "magia", "required": "y"}]}})))
    check("1d: locks em item SEM container rejeitado",
          any("container" in e for e in validator.validate(
              {"type": "item", "id": "x", "name": "X",
               "locks": {"open": [{"type": "item", "required": "y"}]}})))
    check("1e: locks válido passa (item com container)",
          validator.validate(
              {"type": "item", "id": "x", "name": "X", "size": "P",
               "container": {"max_size": "PP", "max_items": 2},
               "locks": {"close": [{"type": "item", "required": "y"}]}}) == [])

    # ===================== 2/3/16: invisível, física intacta, legado ======== #
    ctx = motor.get_context("torvin-ferreiro")
    bau_ctx = next(o for o in ctx["objects_present"] if o["id"] == "bau-lendario")
    check("2a: baú fechado não expõe 'contains' (nem ao Árbitro-contexto)",
          bau_ctx["fechado"] is True and bau_ctx["contains"] == [])
    caixa_ctx = next(i for i in ctx["items_present"] if i["id"] == "caixa-de-pinho")
    check("2b: caixa fechada no chão sem conteúdo visível",
          caixa_ctx["container"]["fechado"] is True and caixa_ctx["contains"] == [])
    idx_items = arbiter._scene_index(ctx)["items"]
    check("2c: rubi e dado fora do índice da cena (invisíveis)",
          "rubi-antigo" not in idx_items and "dado-de-osso" not in idx_items)
    for oculto in ("rubi-antigo", "dado-de-osso"):
        try:
            motor.observe_entity("torvin-ferreiro", oculto)
            vazou = True
        except motor.MotorError:
            vazou = False
        check(f"2d: observar '{oculto}' (dentro de fechado) negado", not vazou)
    check("3: física intacta — peso efetivo da caixa fechada inclui o dado",
          abs(motor.effective_weight(CAIXA) - 0.41) < 1e-6)
    bau_legado = next(o for o in ctx["objects_present"] if o["id"] == "bau-trancado")
    check("16: legado sem campo = ABERTO (moeda do bau-trancado segue visível)",
          bau_legado["fechado"] is False
          and any(c["id"] == "moeda-de-ouro" for c in bau_legado["contains"]))
    check("sem deadlock autoral na fixture (chaves fora)",
          motor.deadlock_warnings() == [])

    # ===================== 11/12: fechado não recebe; sem bypass ============ #
    out11 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "moeda-de-cobre", "to": "caixa-de-pinho"}]))
    check("11: stow em contêiner fechado negado — container_fechado",
          any(r.get("regra") == "container_fechado" for r in out11["rejected"]))
    out12 = motor.apply_resolution("torvin-ferreiro", res(
        mutations=[{"target": "caixa-de-pinho", "path": "state.fechado",
                    "value": False, "reason": "hack"}]))
    check("12: mutate direto em state.fechado rejeitado (sem bypass das travas)",
          any("fecho" in (r.get("why") or "") for r in out12["rejected"]))
    caixa_fm, _ = motor.read_doc(CAIXA / "item.md")
    check("12: caixa segue fechada no arquivo", motor.is_closed(caixa_fm))

    # ===================== 4/5/15: abrir/fechar sem travas ================== #
    out4 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "caixa-de-pinho"}]))
    check("4: open sem travas aplicado",
          out4["lock_ops_applied"] == [{"op": "open", "target": "caixa-de-pinho"}])
    ctx4 = motor.get_context("torvin-ferreiro")
    caixa4 = next(i for i in ctx4["items_present"] if i["id"] == "caixa-de-pinho")
    check("4: dado reaparece na consulta após abrir",
          any(c["id"] == "dado-de-osso" for c in caixa4["contains"]))
    check("4: dado agora observável",
          motor.observe_entity("torvin-ferreiro", "dado-de-osso")["kind"] == "item")
    out_take = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "dado-de-osso", "to": "torvin-ferreiro"}]))
    check("4: item revelado é reachable_entities (take do dado)",
          out_take["item_transfers_applied"] == [{"item": "dado-de-osso",
                                                  "to": "torvin-ferreiro"}])
    out5 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "caixa-de-pinho"}]))
    ctx5 = motor.get_context("torvin-ferreiro")
    caixa5 = next(i for i in ctx5["items_present"] if i["id"] == "caixa-de-pinho")
    check("5: close aplicado e conteúdo some de novo",
          out5["lock_ops_applied"] == [{"op": "close", "target": "caixa-de-pinho"}]
          and caixa5["contains"] == [] and caixa5["container"]["fechado"] is True)
    out15 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "caixa-de-pinho"}]))
    check("15: close em já fechado = no-op aplicado (nunca erro)",
          out15["lock_ops_applied"] == [{"op": "close", "target": "caixa-de-pinho",
                                         "noop": True}])
    ctx15 = motor.get_context("torvin-ferreiro")
    cap15 = []
    arbiter.resolve_with_tools(INTENT, ctx15, scripted_loop(
        [("open", {"target": "caixa-de-pinho"}),
         ("open", {"target": "caixa-de-pinho"}),
         ("narrate", {"narrative_hint": "abre a caixinha de pinho"})], cap15))
    # o 2º open idêntico é interceptado pelo anti-loop genérico (spec 007) — o
    # importante é: ok neutro, nota de "já feito", e UM único lock_op na fila.
    check("15: guarda — 1º open ok; 2º open no turno vira nota de repetição",
          cap15[0].get("ok") is True and cap15[1].get("ok") is True
          and ("já está aberto" in (cap15[1].get("nota") or "")
               or "repetição ignorada" in (cap15[1].get("nota") or "")))

    # ===================== 14/13: mover fechado; cadeia ===================== #
    out14 = motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "caixa-de-pinho", "to": "torvin-ferreiro"}]))
    check("14: pegar contêiner fechado segue as regras 004 (mão + state.slot)",
          out14["item_transfers_applied"] == [{"item": "caixa-de-pinho",
                                               "to": "torvin-ferreiro"}])
    motor.apply_resolution("torvin-ferreiro", res(
        equip_ops=[{"op": "equip", "item": "mochila-de-couro"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "caixa-de-pinho"}],
        item_transfers=[{"item": "dado-de-osso", "to": "caixa-de-pinho"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "caixa-de-pinho"}],
        item_transfers=[{"item": "caixa-de-pinho", "to": "mochila-de-couro"}]))
    inv = {i["id"]: i for i in motor.get_context("torvin-ferreiro")["self"]["inventory"]}
    check("13: cadeia — caixa fechada DENTRO da mochila aberta: dado oculto do dono",
          "caixa-de-pinho" in inv and "dado-de-osso" not in inv)

    # ===================== 6/7/8: travas por chave ========================== #
    out6a = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "bau-lendario"}]))
    rej6a = [r for r in out6a["rejected"] if r.get("regra") == "trava_nao_satisfeita"]
    check("6: abrir sem nenhuma chave nega na 1ª camada (chave-de-ferro)",
          rej6a and rej6a[0]["valores"]["item_requerido"] == "chave-de-ferro")
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-ferro", "to": "torvin-ferreiro"}]))
    out6b = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "bau-lendario"}]))
    rej6b = [r for r in out6b["rejected"] if r.get("regra") == "trava_nao_satisfeita"]
    check("6: com 1 chave nega na 2ª camada, com deny_reason in-world",
          rej6b and rej6b[0]["valores"]["item_requerido"] == "chave-de-prata"
          and "prateada" in rej6b[0]["valores"].get("motivo", ""))
    # 8: a outra chave GUARDADA em contêiner fechado não conta
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-prata", "to": "torvin-ferreiro"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "caixa-de-pinho"}],
        item_transfers=[{"item": "chave-de-prata", "to": "caixa-de-pinho"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "caixa-de-pinho"}]))
    out8 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "bau-lendario"}]))
    check("8: chave dentro de contêiner FECHADO não conta como tê-la",
          any(r.get("regra") == "trava_nao_satisfeita"
              and r["valores"]["item_requerido"] == "chave-de-prata"
              for r in out8["rejected"]))
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "caixa-de-pinho"}],
        item_transfers=[{"item": "chave-de-prata", "to": "torvin-ferreiro"}]))
    out7 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "bau-lendario"}]))
    check("7: com as DUAS chaves acessíveis o baú abre",
          out7["lock_ops_applied"] == [{"op": "open", "target": "bau-lendario"}])
    ctx7 = motor.get_context("torvin-ferreiro")
    bau7 = next(o for o in ctx7["objects_present"] if o["id"] == "bau-lendario")
    inv7 = {i["id"] for i in ctx7["self"]["inventory"]}
    check("7: rubi revelado; chaves permanecem com o ator (não consumidas)",
          any(c["id"] == "rubi-antigo" for c in bau7["contains"])
          and {"chave-de-ferro", "chave-de-prata"} <= inv7)

    # ===================== 18: fallback — fecha, e abre-e-pega num turno ==== #
    motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "bau-lendario"}]))
    # libera uma mão (prata → mochila aberta; continua acessível para a trava)
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-prata", "to": "mochila-de-couro"}]))
    out18 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "open", "target": "bau-lendario"}],
        item_transfers=[{"item": "rubi-antigo", "to": "torvin-ferreiro"}]))
    check("18: abrir E pegar no MESMO turno (open antes das transferências)",
          out18["lock_ops_applied"] == [{"op": "open", "target": "bau-lendario"}]
          and out18["item_transfers_applied"] == [{"item": "rubi-antigo",
                                                   "to": "torvin-ferreiro"}])

    # ===================== 9/10/17: anti-deadlock e aviso autoral =========== #
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-ferro", "to": "bau-lendario"}]))
    out9 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "bau-lendario"}]))
    check("9: fechar exigindo chave que está DENTRO do alvo nega (anti-deadlock)",
          any(r.get("regra") == "trava_nao_satisfeita"
              and r["valores"]["acao"] == "close"
              and r["valores"]["item_requerido"] == "chave-de-ferro"
              for r in out9["rejected"]))
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-ferro", "to": "torvin-ferreiro"}]))
    motor.apply_resolution("torvin-ferreiro", res(
        item_transfers=[{"item": "chave-de-prata", "to": "bau-lendario"}]))
    out10 = motor.apply_resolution("torvin-ferreiro", res(
        lock_ops=[{"op": "close", "target": "bau-lendario"}]))
    check("10: com a chave na mão o baú fecha (prata ficou dentro)",
          out10["lock_ops_applied"] == [{"op": "close", "target": "bau-lendario"}])
    warns17 = motor.deadlock_warnings()
    check("17: deadlock (prata trancada dentro do baú que a exige) vira AVISO",
          any(w["id"] == "bau-lendario" and "chave-de-prata" in w["aviso"]
              for w in warns17))
    check("17: aviso não é erro — mundo segue íntegro", motor.validate_world() == [])

    # ===================== manifest e encerramento ========================== #
    tools = {t["name"] for t in arbiter.build_tools(motor.get_context("torvin-ferreiro"))}
    check("manifest: open presente (baú fechado na cena) e close ausível conforme estado",
          "open" in tools)
    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 8 (spec 005) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
