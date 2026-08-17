"""Auto-teste da Fase 10 — Persuadir Personagem a Se Mover (spec 007).

Cobre, com rolagem forçada (motor._roll_d20 injetável):
  - unidades: DC monotônica (20 − 2×vontade), tendência (6–9 ir / 1–4 ficar /
    resto neutra), clamp da vontade
  - extremos deterministas SEM dado (SC-001): vontade 10 move; vontade 0 nega
  - quadrantes: virada quando a rolagem inverte a tendência; críticos naturais
    (20/1) informados mesmo sem virada; desfecho esperado sem crítico = silêncio
  - identidade com a movimentação própria (SC-005): mesmo travel_time
  - rota_indisponivel e personagem_inacessivel estruturados
  - guarda: enum sem o ator, redirecionamento alvo==ator, vontade 0 na guarda,
    repique "já foi movimentado"
  - segredo (FR-002): a vontade não aparece em failed_effects nem viradas

Cenário: Torvin CHA 8 (mod −1) e Elga CHA 13 (mod +1) na taverna; rota
portao-lateral → forja-de-ferro.

Uso:  python3 server/selftest_phase10.py
"""

from __future__ import annotations

import json
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
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
ROTA, TAVERNA_ID, FORJA_ID = "portao-lateral", "taverna-do-gancho", "forja-de-ferro"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(value):
    motor._roll_d20 = lambda: value


def forbid_roll():
    def _boom():
        raise AssertionError("rolagem não deveria acontecer aqui")
    motor._roll_d20 = _boom


def res(**parts):
    base = {"narrative_hint": "tenta convencer", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "memories": []}
    base.update(parts)
    return base


def persuade(actor, alvo, vontade, rota=ROTA):
    return motor.apply_resolution(actor, res(
        persuade_ops=[{"personagem": alvo, "rota": rota, "vontade": vontade}]))


def in_route(cid) -> bool:
    return (motor.WORLD_DIR / "routes" / ROTA / cid).is_dir()


def bring_back(cid) -> None:
    """Devolve um persuadido da rota à taverna (manutenção de cenário do teste)."""
    child = motor.WORLD_DIR / "routes" / ROTA / cid
    fm, body = motor.read_doc(child / "character.md")
    fm.pop("transit", None)
    motor.write_doc(child / "character.md", fm, body)
    os.replace(child, motor.WORLD_DIR / TAVERNA_ID / cid)


def scripted_loop(calls):
    def loop_fn(system, user, tools, execute, max_calls):
        for name, args in calls:
            execute(name, args)
        return {"stopped": "limit", "text": None, "calls": len(calls)}
    return loop_fn


try:
    # --- unidades: DC, tendência, régua ↔ matemática -------------------------- #
    check("DC monotônica: v5→10, v9→2, v1→18",
          motor.persuade_dc(5) == 10 and motor.persuade_dc(9) == 2
          and motor.persuade_dc(1) == 18)
    check("tendência: 6–9 'ir', 1–4 'ficar', 0/5/10 'neutra'",
          all(motor.persuade_tendencia(v) == "ir" for v in (6, 7, 8, 9))
          and all(motor.persuade_tendencia(v) == "ficar" for v in (1, 2, 3, 4))
          and all(motor.persuade_tendencia(v) == "neutra" for v in (0, 5, 10)))

    # --- extremos deterministas: NUNCA rolam (SC-001) ------------------------- #
    forbid_roll()
    out_10 = persuade(TORVIN, ELGA, 10)
    check("vontade 10: move sem rolagem — pasta na rota, transit gravado",
          out_10["persuade_ops_applied"]
          and out_10["persuade_ops_applied"][0]["destino"] == FORJA_ID
          and out_10["rolls"] == [] and in_route(ELGA))
    bring_back(ELGA)

    forbid_roll()
    out_0 = persuade(TORVIN, ELGA, 0)
    check("vontade 0: recusa_absoluta sem rolagem, ninguém se move",
          any(r.get("regra") == "recusa_absoluta" for r in out_0["rejected"])
          and out_0["rolls"] == [] and not in_route(ELGA))

    forbid_roll()
    out_clamp = persuade(TORVIN, ELGA, 15)
    check("clamp: vontade 15 vira 10 (move sem dado)",
          out_clamp["persuade_ops_applied"] and out_clamp["rolls"] == [])
    bring_back(ELGA)

    # --- quadrantes (Torvin CHA 8 → mod −1; Elga CHA 13 → mod +1) ------------- #
    # vontade 8 (tende IR), DC 4; d20=2 → total 1 < 4: falha COM virada, sem crítico
    force_roll(2)
    out_v = persuade(TORVIN, ELGA, 8)
    rej_v = [r for r in out_v["rejected"] if r.get("regra") == "persuasao_falhou"]
    check("tendia ir + rolagem ruim ⇒ fica; persuasao_falhou com virada, sem crítico",
          not in_route(ELGA) and rej_v
          and rej_v[0]["valores"]["virada"] is True
          and rej_v[0]["valores"]["critico"] is None
          and out_v["rolls"][0]["tendencia"] == "ir")
    twists_v = server_app.fate_twists(out_v["rolls"])
    check("virada negativa vira frase social ('estava quase indo')",
          twists_v and "quase indo" in twists_v[0]["o_que"])

    # vontade 2 (tende FICAR), DC 16; Elga persuade Torvin, d20=20 → 21 ≥ 16:
    # sucesso COM virada E crítico
    force_roll(20)
    out_q3 = persuade(ELGA, TORVIN, 2)
    check("tendia ficar + d20=20 ⇒ MOVE, virada + crítico de sucesso",
          in_route(TORVIN) and out_q3["persuade_ops_applied"]
          and out_q3["rolls"][0]["virada"] is True
          and out_q3["rolls"][0]["critico"] == "sucesso")
    check("virada positiva vira frase social ('algo nas palavras')",
          any("palavras" in t["o_que"]
              for t in server_app.fate_twists(out_q3["rolls"])))
    bring_back(TORVIN)

    # vontade 8, d20=10 → sucesso ESPERADO sem crítico: nenhum destaque
    force_roll(10)
    out_ok = persuade(TORVIN, ELGA, 8)
    check("desfecho esperado (sem virada, sem crítico) ⇒ fate_twists vazio",
          out_ok["persuade_ops_applied"]
          and out_ok["rolls"][0]["virada"] is False
          and out_ok["rolls"][0]["critico"] is None
          and server_app.fate_twists(out_ok["rolls"]) == [])
    bring_back(ELGA)

    # vontade 3 (tende ficar), d20=1 → falha esperada, MAS crítico informado
    force_roll(1)
    out_c1 = persuade(TORVIN, ELGA, 3)
    twists_c1 = server_app.fate_twists(out_c1["rolls"])
    check("falha crítica sem virada (d20=1) ⇒ informada ('a conversa azedou')",
          not in_route(ELGA) and out_c1["rolls"][0]["virada"] is False
          and out_c1["rolls"][0]["critico"] == "falha"
          and twists_c1 and "azedou" in twists_c1[0]["o_que"])

    # vontade 5 (neutra) nunca gera virada — d20 alto só marca o crítico
    force_roll(20)
    out_n = persuade(TORVIN, ELGA, 5)
    check("vontade 5 (neutra): sucesso sem virada (crítico à parte)",
          out_n["persuade_ops_applied"]
          and out_n["rolls"][0]["virada"] is False
          and out_n["rolls"][0]["tendencia"] == "neutra")
    bring_back(ELGA)

    # --- segredo da vontade (FR-002): nunca desce ao client ------------------- #
    force_roll(2)
    out_sec = persuade(TORVIN, ELGA, 8)
    payload = json.dumps({
        "failed_effects": server_app.inworld_failures(out_sec["rejected"]),
        "viradas": server_app.fate_twists(out_sec["rolls"]),
    }, ensure_ascii=False)
    check("segredo: 'vontade' não aparece em failed_effects nem viradas",
          "vontade" not in payload)
    check("falha estruturada narrável: frase com o alvo e o porquê",
          any(isinstance(f, dict)
              and "palavras não bastaram" in f.get("o_que_falhou", "")
              for f in server_app.inworld_failures(out_sec["rejected"])))

    # --- identidade com a movimentação própria (SC-005) ----------------------- #
    own = motor.apply_resolution(ELGA, res(movement={"enter_route": ROTA}))
    own_travel = own["movement"]["travel_time"]
    bring_back(ELGA)
    forbid_roll()
    out_same = persuade(TORVIN, ELGA, 10)
    check("persuadido viaja como se partisse sozinho: mesmo travel_time",
          out_same["persuade_ops_applied"][0]["travel_time"] == own_travel)
    bring_back(ELGA)

    # --- mundo nega o caminho / alvo ausente ---------------------------------- #
    forbid_roll()
    out_rota = persuade(TORVIN, ELGA, 10, rota="trilha-fantasma")
    check("rota inexistente ⇒ rota_indisponivel com motivo",
          any(r.get("regra") == "rota_indisponivel"
              and r.get("valores", {}).get("motivo")
              for r in out_rota["rejected"]))
    out_alvo = persuade(TORVIN, "nerissa-boticaria", 10)
    check("alvo fora da cena ⇒ personagem_inacessivel",
          any(r.get("regra") == "personagem_inacessivel"
              for r in out_alvo["rejected"]))

    # --- guarda do Árbitro -------------------------------------------------- #
    # spec 020: resolve_with_tools agora APLICA-E-REGISTRA por-op (fase única), então
    # um persuade de vontade 1-9 ROLA aqui — injeta-se um dado válido, e devolve-se
    # o alvo à cena entre os checks que o movem.
    force_roll(15)
    ctx = motor.get_context(TORVIN)
    idx = arbiter._scene_index(ctx)
    cand = arbiter._verb_candidates(idx)
    check("guarda: enum de persuade exclui o próprio ator",
          ELGA in cand["persuade"] and TORVIN not in cand["persuade"])
    tools = arbiter.build_tools(ctx)
    check("manifest: tool persuade presente (há rota e outro personagem)",
          any(t["name"] == "persuade" for t in tools))

    r_self = arbiter.resolve_with_tools(
        {"action": "convence a si mesmo a ir"}, ctx,
        scripted_loop([("persuade", {"personagem": TORVIN, "rota": ROTA,
                                     "vontade": 8})]))
    check("guarda: alvo==ator redireciona (nada enfileirado)",
          r_self.get("persuade_ops") == [])

    # spec 043: a nota é PEDIDA ao mundo (`ctx.ask`), não recebida em args — o ponto
    # de injeção do teste passa a ser esse, que é o caminho real.
    r_zero = arbiter.resolve_with_tools(
        {"action": "manda a taverneira embora"}, ctx,
        scripted_loop([("persuade", {"personagem": ELGA, "rota": ROTA,
                                     "vontade": 0})]), ask=lambda _s, _u: "0")
    check("guarda: vontade 0 nega já no turno com recusa_absoluta",
          r_zero.get("persuade_ops") == []
          and any(r.get("regra") == "recusa_absoluta"
                  for r in r_zero.get("tool_rejections", [])))

    # --- régua não se re-lê até o número agradar (Princípio X) ---------------- #
    # A recusa determinística NÃO se escapa insistindo com nota maior. Isto era
    # garantido pela TRAVA (`persuaded`) porque quem chamava preenchia a nota; desde
    # a spec 043 é garantido ANTES disso, por CONSTRUÇÃO: a nota não vem de quem
    # chama — a capacidade a pede ao mundo, com a régua que mora ao lado dela. Aqui
    # o "modelo" insiste mandando 0 e depois 8 em `args`, e os dois valores são
    # IGNORADOS: o mundo responde 0 nas duas vezes, e o veredito se mantém.
    _cap: list = []

    def _cap_loop(system, user, tools, execute, max_calls):
        _cap.append(execute("persuade", {"personagem": ELGA, "rota": ROTA,
                                          "vontade": 0}))
        _cap.append(execute("persuade", {"personagem": ELGA, "rota": ROTA,
                                          "vontade": 8}))
        return {"stopped": "limit", "text": None, "calls": 2}

    r_escape = arbiter.resolve_with_tools(
        {"action": "recua e insiste com mais lábia"}, ctx, _cap_loop,
        ask=lambda _s, _u: "0")   # o MUNDO diz 0, venha o que vier em args
    check("régua-escape: 1ª recusa (v0) carried_item_ids orientação a NÃO re-tentar",
          not _cap[0][0].get("ok")
          and "NÃO refaça a MESMA" in (_cap[0][0].get("erro") or ""),
          str(_cap[0][0].get("erro")))
    check("régua-escape: re-persuadir o MESMO alvo com nota maior é BARRADO",
          not _cap[1][0].get("ok")
          and "já aconteceu" in (_cap[1][0].get("erro") or ""),
          str(_cap[1][0].get("erro")))
    check("régua-escape: nada moveu — a recusa 0 valeu o turno inteiro",
          (r_escape.get("persuade_ops") or []) == [])

    r_dupla = arbiter.resolve_with_tools(
        {"action": "insiste duas vezes"}, ctx,
        scripted_loop([
            ("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 7}),
            ("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 9}),
        ]), ask=lambda _s, _u: "7")
    check("guarda: segundo persuade do mesmo alvo no turno é negado",
          len(r_dupla.get("persuade_ops") or []) == 1
          and r_dupla["persuade_ops"][0]["vontade"] == 7)
    bring_back(ELGA)  # r_dupla moveu ELGA (aplicou por-op); devolve-a à cena
    ctx = motor.get_context(TORVIN)

    # anti-loop genérico: chamada IDÊNTICA repetida não duplica efeito
    r_eco = arbiter.resolve_with_tools(
        {"action": "insiste na mesma coisa"}, ctx,
        scripted_loop([
            ("mutate", {"target": TORVIN, "path": "status.mood",
                        "value": "decidido"}),
            ("mutate", {"target": TORVIN, "path": "status.mood",
                        "value": "decidido"}),
            ("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 7}),
            ("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 7}),
        ]))
    check("anti-loop: chamada idêntica repetida é ignorada (1 mutation, 1 persuade)",
          len(r_eco.get("mutations") or []) == 1
          and len(r_eco.get("persuade_ops") or []) == 1)
    bring_back(ELGA)  # r_eco moveu ELGA (aplicou por-op)

    # --- item 31 §2: persuade migrada a apply_op_now ------------------------- #
    # O VEREDITO (recusa_absoluta/roll) é do executor agora, não pré-voo da tool. O
    # risco da migração era a VIRADA de uma persuasão que FALHA sumir (apply_op_now
    # descartava o `rolls` na recusa). Pela TOOL, a virada tem de subir em `rolls`.
    ctx = motor.get_context(TORVIN)
    force_roll(2)  # vontade 8 tende IR; d20=2 → falha COM virada, pela tool
    r_virada = arbiter.resolve_with_tools(
        {"action": "tenta convencer e falha"}, ctx,
        scripted_loop([("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 8})]), ask=lambda _s, _u: "8")
    check("item31: persuade migrada — virada de FALHA sobe em rolls pela tool",
          any(rr.get("virada") for rr in (r_virada.get("rolls") or []))
          and any(t.get("regra") == "persuasao_falhou"
                  for t in r_virada.get("tool_rejections", [])))
    # segredo (Princípio IX): a recusa que o MODELO lê NÃO leva o dado/DC/virada —
    # só o motivo. O número narra pelo client (rolls→fate_twists), nunca ao Árbitro.
    _capv: list = []
    force_roll(2)
    arbiter.resolve_with_tools(
        {"action": "tenta e falha"}, motor.get_context(TORVIN),
        lambda sy, u, t, execute, m: (_capv.append(
            execute("persuade", {"personagem": ELGA, "rota": ROTA, "vontade": 8})),
            {"stopped": "x", "text": None, "calls": 1})[1])
    check("item31: recusa de rolagem NÃO vaza o dado ao modelo (Princípio IX)",
          "rolagem" not in json.dumps(_capv[0][0], ensure_ascii=False)
          and "dc" not in (_capv[0][0].get("valores") or {}))

    # --- trava de regressão da spec 010 -------------------------------------- #
    # A spec 010 fez o persuade NEGAR alvo caído. Alvo DE PÉ não pode ter mudado:
    # este caso existe para acusar se aquela guarda vazar para quem está em pé.
    fm_elga, body_elga = motor.read_doc(
        motor.find_character_folder(ELGA) / "character.md")
    check("spec 010: Elga segue de pé (sem conditions de derrota)",
          not any(c in motor.DOWN_CONDITIONS
                  for c in ((fm_elga.get("status") or {}).get("conditions") or [])))
    force_roll(20)
    out_pe = persuade(TORVIN, ELGA, 8)
    check("spec 010 não regride a 007: persuadir alvo DE PÉ ainda move",
          out_pe["persuade_ops_applied"] and in_route(ELGA)
          and not any(r.get("regra") == "alvo_desacordado"
                      for r in out_pe["rejected"]))
    bring_back(ELGA)

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 10 (spec 007) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
