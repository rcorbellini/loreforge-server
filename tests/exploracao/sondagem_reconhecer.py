"""Sondagem: o Árbitro dispara recognize sem NARRAR a impressão? (spec 018)

NÃO É TESTE DE REGRESSÃO. Modelo real, imprime, NUNCA falha.

O alvo crítico é a FRONTEIRA (skill loreforge-arbiter-boundary): um sussurro
"observe/analise o X" — o Árbitro chama `recognize`? E ao fazê-lo, o
narrative_hint dele NÃO descreve a impressão (que é do personagem)? Se o hint
narrar a impressão, é o anti-padrão: endurecer a instrução da tool, não o código.

Uso:  python3 server/tests/exploracao/sondagem_reconhecer.py [repeticoes]
"""
import os, re, shutil, sys, tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-"))
shutil.copytree(RAIZ.parent / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
_log = _tmp / "devlog.log"
os.environ["LOREFORGE_LOG"] = "1"; os.environ["LOREFORGE_LOG_FILE"] = str(_log)
sys.path.insert(0, str(RAIZ))
import app as server_app, arbiter, motor  # noqa: E402

ATOR = "torvin-ferreiro"        # na taverna
ALVO = "elga-taverneira"        # co-localizada; Torvin terá história com ela
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3

def prep():
    d = motor.find_character_folder(ATOR)/"memories"
    [p.unlink() for p in d.glob("*.md")] if d.is_dir() else None
    motor._write_memory(motor.find_character_folder(ATOR),
        "Elga me serviu ensopado quando eu não tinha um cobre, e nunca cobrou.",
        intensity="large", involved=[ALVO], valence={ALVO: "positiva"})

def rodar():
    prep()
    marca = _log.stat().st_size if _log.exists() else 0
    intent = {"action": "observa e analisa Elga com atenção",
              "target": ALVO, "utterance": "Quem é essa mulher para mim?",
              "movement": None}
    loop = server_app.build_loop_fn(server_app.CONFIG["arbiter"])
    r = arbiter.resolve_with_tools(intent, motor.get_context(ATOR), loop)
    trecho = ""
    if _log.exists():
        with _log.open(encoding="utf-8") as fh:
            fh.seek(marca); trecho = fh.read()
    chamou = "recognize" in trecho
    hint = (r.get("narrative_hint") or "")
    # sinais de que o hint NARROU a impressão (ruim): menção a ensopado/dívida/gratidão
    vazou = any(w in hint.lower() for w in ("ensopado", "cobre", "gratid", "dívida", "lembra"))
    return {"chamou_recognize": chamou, "hint": hint[:120], "hint_narrou_impressao": vazou,
            "desceu_pacote": bool(r.get("reconhecimentos"))}

print(f"\nSondagem do reconhecer — {REPS} reps | modelo: {server_app.CONFIG['arbiter'].get('model')}")
print("caso: 'observa e analisa Elga' (Torvin tem história viva com ela)\n")
for i in range(REPS):
    try:
        o = rodar()
    except Exception as e:
        print(f"  {i+1}: (erro: {type(e).__name__}: {e})", flush=True); continue
    print(f"  {i+1}: chamou_recognize={o['chamou_recognize']} "
          f"desceu_pacote={o['desceu_pacote']} | hint_narrou_impressao(RUIM)={o['hint_narrou_impressao']}", flush=True)
    print(f"       hint: “{o['hint']}”", flush=True)
print("""
Leitura:
  - chamou_recognize=True e hint_narrou_impressao=False = a fronteira se sustenta
    (o Árbitro buscou, o personagem narra)
  - hint_narrou_impressao=True em algum = o Árbitro roubou a interpretação;
    endurecer a instrução da tool (não o código)""")
shutil.rmtree(_tmp, ignore_errors=True)
