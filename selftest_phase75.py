"""Auto-teste da Fase 75 — o desejo: o world GUARDA, o harness DECIDE (contrato 03).

Pelo FIO, com o servidor HTTP de verdade (a mesma porta que o harness do conector e o
client usam). O que se prova:

  1. o harness CRIA, ATUALIZA e FECHA o desejo pelas portas do dono (`/api/intention/*`);
  2. o `close` aceita `concluida` (novo, spec 075) além de `abandonada` — e o padrão
     continua `abandonada`, para o client de antes não mudar;
  3. `status` fora do vocabulário é recusado com motivo (400);
  4. `lembrar: true` faz a desistência VIRAR MEMÓRIA (spec 073, FR-015) — é o que o
     harness pede quando o personagem larga o desejo;
  5. o contexto não desce mais `parada` nem `passos_cumpridos`, na ida e volta JSON.

Uso:  python3 selftest_phase75.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test75-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
os.environ["LOREFORGE_REGISTRO_DIR"] = str(_tmp / "registro")
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import app as server_app  # noqa: E402

FAILS = []
LUGAR = "mirante-do-corvo"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, nome: str) -> Path:
    d = motor.WORLD_DIR / LUGAR / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {nome}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"status:\n  hp: 10\n  hp_max: 10\n  action: espera\n  mood: calmo\n  conditions: []\n"
        f"---\nAlguém.\n", encoding="utf-8")
    return d


def post(port, rota, corpo):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{rota}", json.dumps(corpo).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


try:
    pasta = _mk_char("desejante", "Desejante")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server_app.Handler)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()

    print("\n--- o harness cria, atualiza e fecha pelas portas do dono ---")
    st, r = post(port, "/api/intention/create",
                 {"character_id": "desejante",
                  "content": "Matar a sede.\n- Beber do cantil\nPronto quando: sede saciada."})
    check("create responde 200 com o id", st == 200 and r.get("id"), str(r))
    iid = r.get("id")
    st, r = post(port, "/api/intention/update",
                 {"character_id": "desejante", "intention_id": iid,
                  "content": "Matar a sede.\n- Pedir água à Elga\nPronto quando: sede saciada."})
    check("update responde 200", st == 200, str(r))
    fm, body = motor.read_doc(pasta / "intentions" / f"{iid}.md")
    check("o plano novo está no disco, em prosa", "Pedir água à Elga" in body, body)

    print("\n--- o close com `concluida` (spec 075) ---")
    st, r = post(port, "/api/intention/close",
                 {"character_id": "desejante", "intention_id": iid, "status": "concluida"})
    check("close concluida responde 200", st == 200, str(r))
    fm, _ = motor.read_doc(pasta / "intentions" / f"{iid}.md")
    check("o disco registra `concluida`", fm.get("status") == "concluida", str(fm.get("status")))

    st, r = post(port, "/api/intention/create", {"character_id": "desejante", "content": "Outra coisa."})
    i2 = r.get("id")
    st, r = post(port, "/api/intention/close",
                 {"character_id": "desejante", "intention_id": i2, "status": "inventado"})
    check("status fora do vocabulário é recusado com motivo (400)", st == 400 and "status" in r.get("error", ""), str(r))
    st, r = post(port, "/api/intention/close", {"character_id": "desejante", "intention_id": i2})
    fm, _ = motor.read_doc(pasta / "intentions" / f"{i2}.md")
    check("sem `status`, o padrão continua `abandonada` (o client de antes não muda)",
          st == 200 and fm.get("status") == "abandonada", str(fm.get("status")))

    print("\n--- `lembrar`: a desistência vira memória ---")
    mems_antes = len(list((pasta / "memories").glob("*.md"))) if (pasta / "memories").exists() else 0
    st, r = post(port, "/api/intention/create", {"character_id": "desejante", "content": "Achar o mapa perdido."})
    i3 = r.get("id")
    st, r = post(port, "/api/intention/close",
                 {"character_id": "desejante", "intention_id": i3, "status": "abandonada", "lembrar": True})
    mems_depois = len(list((pasta / "memories").glob("*.md"))) if (pasta / "memories").exists() else 0
    check("abandonar com `lembrar` cria a memória da desistência", st == 200 and mems_depois == mems_antes + 1,
          f"{mems_antes} -> {mems_depois}")

    print("\n--- o contexto não desce o relógio nem a contagem ---")
    st, r = post(port, "/api/intention/create",
                 {"character_id": "desejante", "content": "Matar a fome.\n- Comer o pão"})
    fio = json.loads(json.dumps(motor.get_context("desejante")))
    ints = fio["self"]["intentions"]
    check("a intenção ativa desce", any(i["id"] == r.get("id") for i in ints), str(ints))
    check("sem `parada` nem `passos_cumpridos` em nenhuma",
          all("parada" not in i and "passos_cumpridos" not in i for i in ints), str(ints))
    httpd.shutdown()
finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("fase 75: todos os checks passaram.")
