"""Sondagem: o Árbitro conta boato sem inventar e cita o EPISÓDIO? (spec 017)

NÃO É TESTE DE REGRESSÃO. Modelo real, imprime, NUNCA falha.

Dois alvos (riscos do plano):
  1. Ao recontar, o Árbitro cita o EPISÓDIO ("Draven roubou...") e NÃO a moldura
     ("Fulano me contou...")? Se citar a moldura, a origem vaza no corpo do 3º grau.
  2. A régua ancorada BAIXO trava demais? Distribuição das notas de confidência.

Uso:  python3 server/tests/exploracao/sondagem_boato.py [repeticoes]
"""
import os, re, shutil, sys, tempfile
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-"))
shutil.copytree(RAIZ.parent / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
_log = _tmp / "devlog.log"
os.environ["LOREFORGE_LOG"] = "1"; os.environ["LOREFORGE_LOG_FILE"] = str(_log)
sys.path.insert(0, str(RAIZ))
import app as server_app, arbiter, motor  # noqa: E402

FONTE = "torvin-ferreiro"       # tem a memória, presente na taverna
OUVINTE = "obadiah-mascate"     # co-localizado
ALVO = "draven-vigia"           # o sujeito, ausente
EP = "Draven roubou uma bolsa no cais e sumiu na névoa antes que o vissem"
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

def pasta(c): return motor.find_character_folder(c)
def limpar(c):
    d = pasta(c)/"memories"
    [p.unlink() for p in d.glob("*.md")] if d.is_dir() else None

def rodar():
    limpar(FONTE); limpar(OUVINTE)
    motor._write_memory(pasta(FONTE), f"Eu vi com estes olhos. {EP}.",
                        intensity="large", involved=[ALVO], valence={ALVO: "negativa"})
    marca = _log.stat().st_size if _log.exists() else 0
    intent = {"action": f"pergunta a Torvin o que ele sabe de Draven",
              "target": ALVO, "utterance": "O que você sabe do vigia Draven?",
              "movement": None}
    loop = server_app.build_loop_fn(server_app.CONFIG["arbiter"])
    r = arbiter.resolve_with_tools(intent, motor.get_context(OUVINTE), loop)
    trecho = ""
    if _log.exists():
        with _log.open(encoding="utf-8") as fh:
            fh.seek(marca); trecho = fh.read()
    ops = r.get("hearsay_ops") or []
    return {
        "perguntou": "ask_about" in trecho,
        "contou": bool(ops),
        "notas": [o.get("disposicao") for o in ops],
        "trechos": [o.get("trecho") for o in ops],
    }

print(f"\nSondagem do boato — {REPS} repetições | modelo: {server_app.CONFIG['arbiter'].get('model')}")
print("caso: Obadiah pergunta a Torvin (testemunha) o que ele sabe de Draven\n")
notas = []
for i in range(REPS):
    try:
        o = rodar()
    except Exception as e:
        print(f"  {i+1}: (erro: {type(e).__name__}: {e})", flush=True); continue
    notas += [n for n in o["notas"] if n is not None]
    moldura = any(t and ("contou" in t.lower() or "disse" in t.lower()) for t in o["trechos"])
    print(f"  {i+1}: perguntou={o['perguntou']} contou={o['contou']} "
          f"notas={o['notas']} | cita moldura(RUIM)={moldura}", flush=True)
    for t in o["trechos"]:
        if t: print(f"       trecho: “{t[:90]}”", flush=True)
if notas:
    print(f"\n  notas de confidência: {sorted(notas)} (média {sum(notas)/len(notas):.1f})")
    print(f"  distribuição: {dict(Counter(notas))}")
print("""
Leitura:
  - cita moldura=RUIM em algum → a origem vaza no corpo do 3º grau; endurecer a
    instrução da tool (não o código)
  - notas baixas/médias e variadas = régua viva; todas altas = afrouxou demais""")
shutil.rmtree(_tmp, ignore_errors=True)
