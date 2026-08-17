"""Auto-teste da Fase 11 — Teste Oposto de Combate (spec 008).

Cobre, com rolagem forçada (motor._roll_d20 injetável):
  - unidades: defesa (10 + mod DEX), arma declarada/improvisada, proteção só do
    que está VESTIDO, tendência da vantagem, hp preguiçoso derivado de CON
  - acerto/erro com dado forçado; dano = damage + mod − proteção; determinismo
  - equipamento (SC-006): trocar só a arma muda o dano pela diferença de damage
  - absorção: acerto com dano 0 é `golpe_absorvido`, DIFERENTE de `ataque_errou`
  - derrota: hp 0 ⇒ `incapacitado`, pasta intacta; golpe em caído MATA sem dado
    (SC-002); alvo morto nega sem dado
  - a regra do caído (FR-008a/SC-007): POST /api/act em nome de um caído é
    abortado antes do Árbitro — modelo nunca chamado, mundo idêntico byte a byte,
    inclusive pelo atalho de deslocamento que contorna o Árbitro
  - viradas (SC-004): inversão de tendência e críticos naturais 20/1
  - segredo (SC-003): a vantagem não desce ao client
  - preservação (SC-005): nenhum arquivo do mundo é removido

Cenário: Torvin STR 16 (mod +3) DEX 8 (defesa 9) e Elga STR 11 (mod 0) DEX 12
(defesa 11), ambos na taverna; espada-curta (damage 6/STR), gibão de couro
(proteção 2, torso), atiçador de ferro (sem weapon ⇒ improvisado).

Uso:  python3 server/selftest_phase11.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
server_app.CONFIG["server"]["stream"] = True  # testa o STREAMING, indep. do config local
import arbiter  # noqa: E402
import motor  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
TAVERNA_ID = "taverna-do-gancho"
ESPADA, GIBAO, ATICADOR = "espada-curta", "gibao-de-couro", "aticador-de-ferro"


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
    base = {"narrative_hint": "avança para o golpe", "movement": None,
            "mutations": [], "item_transfers": [], "equip_ops": [],
            "lock_ops": [], "persuade_ops": [], "attack_ops": [], "memories": []}
    base.update(parts)
    return base


def attack(actor, alvo, arma=None, vantagem=5):
    return motor.apply_resolution(actor, res(
        attack_ops=[{"alvo": alvo, "arma": arma, "vantagem": vantagem}]))


def char_folder(cid) -> Path:
    return motor.find_character_folder(cid)


def read_status(cid) -> dict:
    fm, _ = motor.read_doc(char_folder(cid) / "character.md")
    return fm.get("status") or {}


def set_status(cid, **fields) -> None:
    folder = char_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status.update(fields)
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def attach(cid, item_id, slot) -> None:
    """Acopla um item da cena ao corpo do personagem (montagem de cenário)."""
    found = motor.find_entity(item_id)
    folder = found[0].parent
    fm, body = motor.read_doc(folder / "item.md")
    state = dict(fm.get("state") or {})
    state["slot"] = slot
    fm["state"] = state
    motor.write_doc(folder / "item.md", fm, body)
    dest = char_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def detach(item_id) -> None:
    """Devolve o item ao chão da taverna, sem slot."""
    found = motor.find_entity(item_id)
    folder = found[0].parent
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.WORLD_DIR / TAVERNA_ID / folder.name
    if folder != dest:
        os.replace(folder, dest)


def world_fingerprint() -> str:
    """Impressão digital do mundo inteiro: prova de que nada foi escrito."""
    h = hashlib.sha256()
    for p in sorted(motor.WORLD_DIR.rglob("*")):
        h.update(str(p.relative_to(motor.WORLD_DIR)).encode())
        if p.is_file():
            h.update(p.read_bytes())
    return h.hexdigest()


def world_files() -> set:
    """Entidades do mundo por pasta+arquivo, e não por caminho: mover um item para
    a mão de alguém é legítimo (a árvore É a topologia); APAGAR nunca é."""
    return {f"{p.parent.name}/{p.name}"
            for p in motor.WORLD_DIR.rglob("*") if p.is_file()}


def scripted_loop(calls):
    def loop_fn(system, user, tools, execute, max_calls):
        for name, args in calls:
            execute(name, args)
        return {"stopped": "limit", "text": None, "calls": len(calls)}
    return loop_fn


def post_act(port, payload) -> dict:
    # spec 022: /api/act responde em STREAM NDJSON (uma linha JSON por evento). O
    # DESFECHO é o `outcome` do evento `done` — idêntico ao corpo único de antes.
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/act",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=10) as r:
        outcome = {}
        for line in r.read().decode("utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("ev") == "done":
                outcome = ev.get("outcome") or {}
            elif ev.get("ev") == "rejected":
                outcome = {"rejected_turn": ev}
        return outcome


ARQUIVOS_INICIAIS = None

try:
    ARQUIVOS_INICIAIS = world_files()

    # --- unidades ------------------------------------------------------------ #
    torvin_fm, _ = motor.read_doc(char_folder(TORVIN) / "character.md")
    elga_fm, _ = motor.read_doc(char_folder(ELGA) / "character.md")
    check("defesa = 10 + mod(DEX): Torvin (DEX 8) 9, Elga (DEX 12) 11",
          motor.defense_of(torvin_fm) == 9 and motor.defense_of(elga_fm) == 11)

    espada_fm = motor.find_entity(ESPADA)[1]
    aticador_fm = motor.find_entity(ATICADOR)[1]
    check("arma declarada: espada = (6, STR)",
          motor.weapon_of(espada_fm) == (6, "STR"))
    check("improvisado: item sem 'weapon' e mão vazia = (1, STR)",
          motor.weapon_of(aticador_fm) == (1, "STR")
          and motor.weapon_of(None) == (1, "STR"))

    check("tendência: 6–10 'acertar', 0–4 'errar', 5 'neutra'",
          all(motor.attack_tendencia(v) == "acertar" for v in (6, 8, 10))
          and all(motor.attack_tendencia(v) == "errar" for v in (0, 2, 4))
          and motor.attack_tendencia(5) == "neutra")

    check("hp preguiçoso: sem registro, hp_max = max(1, 10 + mod(CON))",
          motor.default_hp_max({"attributes": {"CON": 14}}) == 12
          and motor.default_hp_max({"attributes": {"CON": 1}}) == 5
          and motor.ensure_hp({"attributes": {"CON": 14}}) == (12, 12))

    # proteção conta só o VESTIDO
    check("proteção: sem armadura vestida = 0", motor.protection_of(char_folder(ELGA)) == 0)
    attach(ELGA, GIBAO, "torso")
    check("proteção: gibão VESTIDO = 2", motor.protection_of(char_folder(ELGA)) == 2)
    attach(ELGA, GIBAO, motor.HAND_SLOT)
    check("proteção: gibão na MÃO não protege = 0",
          motor.protection_of(char_folder(ELGA)) == 0)
    detach(GIBAO)

    # --- acerto e erro (US1) -------------------------------------------------- #
    attach(TORVIN, ESPADA, motor.HAND_SLOT)
    set_status(ELGA, hp=90, hp_max=90)

    # Torvin: mod STR +3, vantagem 5 ⇒ total = d20 + 3 vs defesa 11 (Elga)
    force_roll(15)
    out_hit = attack(TORVIN, ELGA, ESPADA)
    check("acerto: hp cai exatamente damage(6) + mod(3) − proteção(0) = 9",
          read_status(ELGA).get("hp") == 81
          and out_hit["attack_ops_applied"]
          and out_hit["attack_ops_applied"][0]["dano"] == 9)

    force_roll(2)  # total 5 < 11
    out_miss = attack(TORVIN, ELGA, ESPADA)
    rej_miss = [r for r in out_miss["rejected"] if r.get("regra") == "ataque_errou"]
    check("erro: hp intacto e 'ataque_errou' estruturado",
          read_status(ELGA).get("hp") == 81 and rej_miss
          and not out_miss["attack_ops_applied"])

    # determinismo (SC-001)
    force_roll(15)
    set_status(ELGA, hp=90)
    a1 = attack(TORVIN, ELGA, ESPADA)["attack_ops_applied"][0]["dano"]
    set_status(ELGA, hp=90)
    a2 = attack(TORVIN, ELGA, ESPADA)["attack_ops_applied"][0]["dano"]
    check("determinismo dado o dado: mesmo conjunto ⇒ mesmo dano", a1 == a2 == 9)

    # alvo fora da cena: nega sem rolar
    forbid_roll()
    out_fora = attack(TORVIN, "ninguem-aqui", ESPADA)
    check("alvo ausente: 'personagem_inacessivel' sem rolagem",
          any(r.get("regra") == "personagem_inacessivel" for r in out_fora["rejected"])
          and out_fora["rolls"] == [])

    # --- equipamento (US2) ---------------------------------------------------- #
    force_roll(15)
    set_status(ELGA, hp=90)
    dano_espada = attack(TORVIN, ELGA, ESPADA)["attack_ops_applied"][0]["dano"]
    attach(TORVIN, ATICADOR, motor.HAND_SLOT)
    set_status(ELGA, hp=90)
    dano_improv = attack(TORVIN, ELGA, ATICADOR)["attack_ops_applied"][0]["dano"]
    check("SC-006: só a arma muda ⇒ diferença = diferença de damage (6−1=5)",
          dano_espada - dano_improv == 5, f"{dano_espada} vs {dano_improv}")

    set_status(ELGA, hp=90)
    dano_desarmado = attack(TORVIN, ELGA, None)["attack_ops_applied"][0]["dano"]
    check("desarmado: damage 1 + mod STR 3 = 4", dano_desarmado == 4)

    # absorção: Elga (STR 11, mod 0) desarmada contra Torvin de gibão (proteção 2)
    attach(TORVIN, GIBAO, "torso")
    set_status(TORVIN, hp=120, hp_max=120)
    force_roll(15)  # total 15 ≥ defesa 9 de Torvin: ACERTA
    out_abs = attack(ELGA, TORVIN, None)
    rej_abs = [r for r in out_abs["rejected"] if r.get("regra") == "golpe_absorvido"]
    check("absorção: acertou e a armadura segurou ⇒ hp intacto",
          read_status(TORVIN).get("hp") == 120 and rej_abs
          and not out_abs["attack_ops_applied"])
    check("absorvido ≠ errou: regras distintas",
          rej_abs and not any(r.get("regra") == "ataque_errou"
                              for r in out_abs["rejected"]))

    # a mesma armadura guardada não protege
    attach(TORVIN, GIBAO, motor.HAND_SLOT)
    force_roll(15)
    out_semarm = attack(ELGA, TORVIN, None)
    check("armadura na mão não protege: o mesmo golpe agora fere",
          read_status(TORVIN).get("hp") == 119
          and out_semarm["attack_ops_applied"])
    detach(GIBAO)

    # --- derrota e morte (US3) ------------------------------------------------ #
    attach(TORVIN, ESPADA, motor.HAND_SLOT)
    set_status(ELGA, hp=5, hp_max=90, conditions=[])
    force_roll(15)
    out_down = attack(TORVIN, ELGA, ESPADA)
    st = read_status(ELGA)
    check("derrota: hp chega a 0 (piso) e 'incapacitado' entra em conditions",
          st.get("hp") == 0 and motor.INCAPACITATED in (st.get("conditions") or [])
          and out_down["attack_ops_applied"][0]["derrota"] == motor.INCAPACITATED)
    check("derrota preserva a pasta do caído e seus pertences",
          (char_folder(ELGA) / "character.md").exists())

    # golpe deliberado em quem já caiu: MATA sem dado (SC-002)
    forbid_roll()
    out_kill = attack(TORVIN, ELGA, ESPADA)
    st = read_status(ELGA)
    check("morte: alvo caído morre sem rolagem, deliberadamente",
          motor.DEAD in (st.get("conditions") or [])
          and out_kill["rolls"] == []
          and out_kill["attack_ops_applied"][0]["derrota"] == motor.DEAD)
    check("morte não apaga nada: a pasta do morto continua no mundo",
          (char_folder(ELGA) / "character.md").exists())

    forbid_roll()
    out_morto = attack(TORVIN, ELGA, ESPADA)
    check("alvo morto: 'alvo_ja_morto' sem rolagem",
          any(r.get("regra") == "alvo_ja_morto" for r in out_morto["rejected"])
          and out_morto["rolls"] == [])

    # --- a regra do caído na fronteira (FR-008a / SC-007) --------------------- #
    def _boom_resolve(*a, **kw):
        raise AssertionError("o Árbitro não deveria ser consultado por um caído")

    _resolve_real = server_app.resolve_action
    server_app.resolve_action = _boom_resolve
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_app.Handler)
    porta = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        antes = world_fingerprint()
        r_caido = post_act(porta, {"character_id": ELGA,
                                   "intent": {"action": "levanta e foge"}})
        check("caído: ação abortada com recusa in-world (sem Árbitro)",
              r_caido.get("failed_effects")
              and not r_caido.get("applied")
              and "morto" in (r_caido.get("narrative_hint") or "").lower())
        check("SC-007: mundo idêntico byte a byte após a tentativa",
              world_fingerprint() == antes)

        # o atalho de deslocamento contorna o Árbitro — não pode escapar
        r_rota = post_act(porta, {
            "character_id": ELGA,
            "intent": {"action": "parte", "movement": {"enter_route": "portao-lateral"}}})
        check("caído: o atalho de deslocamento também é abortado",
              r_rota.get("failed_effects") and not r_rota.get("applied"))
        check("SC-007: mundo intacto também pelo atalho de rota",
              world_fingerprint() == antes)

        # controle: personagem apto NÃO é barrado pela guarda (chega ao Árbitro).
        # spec 022: /api/act streama e já enviou 200 antes de resolver; um erro do
        # _boom_resolve agora vem como `done{outcome:{error:...}}`, não como exceção
        # HTTP. Chegou ao Árbitro = o outcome traz o erro do boom.
        resp_apto = post_act(porta, {"character_id": TORVIN,
                                     "intent": {"action": "olha ao redor"}})
        check("controle: personagem apto passa da guarda e chega ao Árbitro",
              bool(resp_apto.get("error")))
    finally:
        httpd.shutdown()
        server_app.resolve_action = _resolve_real

    # --- viradas e segredo (US4) ---------------------------------------------- #
    set_status(ELGA, hp=90, hp_max=90, conditions=[])

    # vantagem 8 (tende ACERTAR), d20=1 ⇒ total 1+3+3=7 < 11: falha COM virada
    force_roll(1)
    out_v = attack(TORVIN, ELGA, ESPADA, vantagem=8)
    twists_v = server_app.fate_twists(out_v["rolls"])
    check("tendia acertar + rolagem péssima ⇒ erra, com virada",
          out_v["rolls"][0]["virada"] is True
          and twists_v and "passou longe" in twists_v[0]["o_que"])

    # vantagem 2 (tende ERRAR), d20=20 ⇒ 20+3-3=20 ≥ 11: acerta com virada + crítico
    force_roll(20)
    set_status(ELGA, hp=90)
    out_c = attack(TORVIN, ELGA, ESPADA, vantagem=2)
    check("tendia errar + d20=20 ⇒ acerta, virada + crítico de sucesso",
          out_c["rolls"][0]["virada"] is True
          and out_c["rolls"][0]["critico"] == "sucesso")

    # vantagem 5 (neutra), acerto esperado sem crítico ⇒ silêncio
    force_roll(15)
    set_status(ELGA, hp=90)
    out_q = attack(TORVIN, ELGA, ESPADA, vantagem=5)
    check("desfecho esperado (neutra, sem crítico) ⇒ nenhuma virada enviada",
          out_q["rolls"][0]["virada"] is False
          and out_q["rolls"][0]["critico"] is None
          and server_app.fate_twists(out_q["rolls"]) == [])

    # crítico natural sem inversão de tendência ainda é informado
    force_roll(1)
    set_status(ELGA, hp=90)
    out_c1 = attack(TORVIN, ELGA, ESPADA, vantagem=2)
    twists_c1 = server_app.fate_twists(out_c1["rolls"])
    check("falha crítica sem virada (d20=1) ⇒ informada mesmo assim",
          out_c1["rolls"][0]["virada"] is False
          and out_c1["rolls"][0]["critico"] == "falha" and twists_c1)

    # segredo da vantagem (SC-003)
    force_roll(1)
    set_status(ELGA, hp=90)
    out_sec = attack(TORVIN, ELGA, ESPADA, vantagem=9)
    payload = json.dumps({
        "failed_effects": server_app.inworld_failures(out_sec["rejected"]),
        "viradas": server_app.fate_twists(out_sec["rolls"]),
        "rolls": out_sec["rolls"],
    }, ensure_ascii=False)
    check("SC-003: 'vantagem' não aparece em nada que desce ao client",
          "vantagem" not in payload.replace("vantagem_mod", ""))
    check("falha estruturada narrável: frase in-world do golpe perdido",
          any(isinstance(f, dict) and "passou ao largo" in f.get("o_que_falhou", "")
              for f in server_app.inworld_failures(out_sec["rejected"])))

    # --- guarda do Árbitro ---------------------------------------------------- #
    ctx = motor.get_context(TORVIN)
    tools = {t["name"]: t for t in arbiter.build_tools(ctx)}
    check("manifest: tool 'attack' presente com o alvo no enum",
          "attack" in tools
          and ELGA in tools["attack"]["parameters"]["properties"]["alvo"]["enum"]
          and TORVIN not in tools["attack"]["parameters"]["properties"]["alvo"]["enum"])

    # item 31 §2: attack migrada a apply_arbitrated (aplica-e-registra por-op). O canal
    # `attack_ops` do resultado reflete o golpe RETIDO (aplicado), como toda tool
    # apply_op_now — então força-se o dado a ACERTAR (hp folgado) para a op ficar no log.
    set_status(ELGA, hp=90, hp_max=90)
    force_roll(15)
    r_dup = arbiter.resolve_with_tools(
        {"action": "ataca duas vezes"}, ctx,
        scripted_loop([
            ("attack", {"alvo": ELGA, "arma": ESPADA, "vantagem": 5}),
            ("attack", {"alvo": ELGA, "arma": ESPADA, "vantagem": 9}),
        ]))
    check("guarda: segundo golpe no mesmo alvo é ignorado (a primeira nota vale)",
          len(r_dup.get("attack_ops") or []) == 1
          and r_dup["attack_ops"][0]["vantagem"] == 5)

    r_self = arbiter.resolve_with_tools(
        {"action": "ataca a si mesmo"}, ctx,
        scripted_loop([("attack", {"alvo": TORVIN, "vantagem": 5})]))
    check("guarda: alvo == ator é recusado (nada enfileirado)",
          not (r_self.get("attack_ops") or []))

    r_clamp = arbiter.resolve_with_tools(
        {"action": "ataca com vantagem absurda"}, ctx,
        scripted_loop([("attack", {"alvo": ELGA, "arma": ESPADA})]),
        ask=lambda _s, _u: "99")   # spec 043: a nota vem do mundo; 99 grampeia em 10
    check("juizo.nota grampeia a nota fora de 0-10 (spec 043)",
          r_clamp["attack_ops"][0]["vantagem"] == 10)

    # --- preservação do mundo (SC-005) ---------------------------------------- #
    check("SC-005: nenhum arquivo do mundo foi removido em todo o combate",
          ARQUIVOS_INICIAIS <= world_files())

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 11 (spec 008) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
