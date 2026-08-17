"""Auto-teste da Fase 24 — Streaming do turno + trava de turno-em-andamento (spec 022).

Cobre, sem Ollama (loop_fn falso e lento):
  - o /api/act responde em STREAM NDJSON: primeiro evento `turn_start`, ao menos um
    `heartbeat` durante a espera do modelo, e um `done{outcome}` por último (FR-001/002/003)
  - equivalência: o `outcome` do `done` é uma resolução válida (o streaming não muda o
    desfecho — SC-003; a igualdade byte-a-byte com o não-streaming é coberta pela suíte
    inteira, que roda com emit=None)
  - trava de turno-em-andamento (FR-005b): dois /api/act concorrentes do MESMO
    personagem → exatamente um resolve (`done`) e o outro é REJEITADO (`turn_in_flight`),
    sem intercalar
  - unidade da trava: _claim_turn/_release_turn

Uso:  python3 server/selftest_phase24.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import time
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

FAILS = []
TORVIN = "torvin-ferreiro"


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "ok  " if cond else "FALHA"
    print(f"[{status}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def read_events(port, payload) -> list[dict]:
    """Consome o stream NDJSON e devolve a lista de eventos {"ev":...}."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/act",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        evs = []
        for line in r.read().decode("utf-8").splitlines():
            line = line.strip()
            if line:
                evs.append(json.loads(line))
        return evs


# --- loop_fn FALSO e LENTO: dorme (força ≥1 batimento) e não chama nenhuma tool ----- #
def _slow_loop(system, user, tools, execute, max_calls):
    time.sleep(0.35)
    return {"stopped": "limit", "text": None, "calls": 0}


# --- loop_fn que aplica DOIS efeitos em sequência (para os beats op_applied, Fase 2) - #
def _beat_loop(system, user, tools, execute, max_calls):
    execute("take", {"item": "aticador-de-ferro"})
    execute("take", {"item": "agulha-de-ferro"})
    return {"stopped": "limit", "text": None, "calls": 2}


def main() -> None:
    server_app.build_loop_fn = lambda arb: _slow_loop   # injeta o loop lento
    server_app.HEARTBEAT_SECS = 0.1                      # batimento rápido para o teste

    # --- unidade da trava --------------------------------------------------- #
    check("trava: _claim_turn marca e o 2º do mesmo id é negado",
          server_app._claim_turn("x") and not server_app._claim_turn("x"))
    server_app._release_turn("x")
    check("trava: após _release_turn, _claim_turn volta a valer",
          server_app._claim_turn("x"))
    server_app._release_turn("x")

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_app.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    try:
        # --- ordem dos eventos + batimento ---------------------------------- #
        evs = read_events(port, {"character_id": TORVIN,
                                 "intent": {"action": "olha ao redor"}})
        tipos = [e.get("ev") for e in evs]
        check("stream: primeiro evento é turn_start", tipos and tipos[0] == "turn_start",
              str(tipos))
        check("stream: ao menos um heartbeat durante a espera", "heartbeat" in tipos,
              str(tipos))
        check("stream: último evento é done", tipos and tipos[-1] == "done", str(tipos))
        done = next((e for e in evs if e.get("ev") == "done"), None)
        check("stream: done carried_item_ids um outcome válido (narrative_hint presente)",
              bool(done) and isinstance(done.get("outcome"), dict)
              and "narrative_hint" in done["outcome"])

        # --- trava de turno concorrente do MESMO personagem ----------------- #
        results: dict[str, list] = {}

        def fire(tag):
            results[tag] = read_events(port, {"character_id": TORVIN,
                                              "intent": {"action": "olha"}})

        a = threading.Thread(target=fire, args=("a",))
        b = threading.Thread(target=fire, args=("b",))
        a.start()
        time.sleep(0.05)   # garante sobreposição: 'a' já está no turno lento
        b.start()
        a.join(); b.join()
        tipos_a = [e.get("ev") for e in results["a"]]
        tipos_b = [e.get("ev") for e in results["b"]]
        rejeitou = ("rejected" in tipos_a) ^ ("rejected" in tipos_b)
        resolveu = ("done" in tipos_a) ^ ("done" in tipos_b)
        check("trava concorrente: exatamente um foi rejeitado (turn_in_flight)", rejeitou,
              f"a={tipos_a} b={tipos_b}")
        check("trava concorrente: exatamente um resolveu (done)", resolveu,
              f"a={tipos_a} b={tipos_b}")
        rej_ev = next((e for grp in results.values() for e in grp
                       if e.get("ev") == "rejected"), None)
        check("trava concorrente: a rejeição diz o motivo turn_in_flight",
              bool(rej_ev) and rej_ev.get("reason") == "turn_in_flight")

        # --- Fase 2: narração por beats (op_applied na ordem de execução) ----- #
        server_app.build_loop_fn = lambda arb: _beat_loop
        evs2 = read_events(port, {"character_id": TORVIN,
                                  "intent": {"action": "pega o atiçador e a agulha"}})
        tipos2 = [e.get("ev") for e in evs2]
        beats = [e for e in evs2 if e.get("ev") == "op_applied"]
        check("beats: dois op_applied desceram (um por efeito aplicado)",
              len(beats) == 2, str(tipos2))
        check("beats: são da família item_transfers, na ordem de execução",
              all(b.get("kind") == "item_transfers_applied" for b in beats)
              and beats == sorted(beats, key=lambda b: evs2.index(b)))
        check("beats: cada op_applied vem ANTES do done", "done" in tipos2
              and all(tipos2.index("op_applied") < tipos2.index("done")
                      for _ in beats))
        check("beats: o done ainda traz o outcome completo",
              bool(next((e for e in evs2 if e["ev"] == "done"), {}).get("outcome")))

        # --- US3: o envelope {"ev":...} é uniforme e comporta o feed futuro ---- #
        todos = evs + evs2 + results["a"] + results["b"]
        check("US3: todo evento do stream tem o envelope {\"ev\":...}",
              all(isinstance(e, dict) and "ev" in e for e in todos))
        # um evento de feed hipotético (Modelo B) encaixa na MESMA forma, sem campo novo
        notice = json.loads(json.dumps({"ev": "notice", "about": "elga-taverneira",
                                        "kind": "attacked_by", "by": "torvin-ferreiro"}))
        check("US3: um evento de feed (notice) usa o mesmo envelope, sem campo novo",
              notice.get("ev") == "notice" and "about" in notice and "kind" in notice)

        # --- modo NÃO-STREAMADO (server.stream = false): JSON único, sem eventos --- #
        server_app.CONFIG["server"]["stream"] = False
        server_app.build_loop_fn = lambda arb: _slow_loop
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/act",
            data=json.dumps({"character_id": TORVIN,
                             "intent": {"action": "olha"}}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            ctype = r.headers.get("Content-Type", "")
            plain = json.loads(r.read().decode("utf-8"))  # JSON ÚNICO (não NDJSON)
        check("plain: Content-Type é application/json (não x-ndjson)",
              "json" in ctype and "ndjson" not in ctype, ctype)
        check("plain: a resposta é o OUTCOME (narrative_hint), não eventos {ev}",
              "narrative_hint" in plain and "ev" not in plain, str(list(plain)[:5]))
        server_app.CONFIG["server"]["stream"] = True  # restaura
    finally:
        httpd.shutdown()

    print()
    if FAILS:
        print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS))
        sys.exit(1)
    print("Fase 24 (streaming do turno) OK.")


if __name__ == "__main__":
    main()
