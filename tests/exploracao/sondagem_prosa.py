"""Sondagem: até onde vai o canal de prosa (spec 014, Phase 6).

NÃO É TESTE DE REGRESSÃO. Depende do modelo real e é intermitente por natureza:
imprime o que o Árbitro fez e NUNCA falha. Misturar isto à suíte a tornaria não
confiável — a fase 15 já custou caro nessa lição.

O que se mede: com `examine` entregando prosa, o modelo alcança efeitos que
NENHUM campo declara e NENHUMA instrução pede? Nenhuma tool nova é criada aqui —
o ponto é justamente medir o alcance do que já existe.

Uso:  python3 server/tests/exploracao/sondagem_prosa.py [repeticoes]
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import re as _re
from collections import Counter
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-sonda-"))
shutil.copytree(RAIZ.parent / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
# o devlog é a única forma de ver as tools CONSULTIVAS: `examine` não entra na
# fila, então sem isto não dá para saber se o modelo chegou a LER
_log = _tmp / "devlog.log"
os.environ["LOREFORGE_LOG"] = "1"
os.environ["LOREFORGE_LOG_FILE"] = str(_log)
sys.path.insert(0, str(RAIZ))

import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

ATOR = "sarga-contrabandista"
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 3


def por(item_id, nome, corpo, **extra):
    """Põe um item novo junto do ator, com o texto que se quer sondar."""
    fm = {"type": "item", "id": item_id, "name": nome,
          "size": "PP", "weight_kg": 0.1}
    fm.update(extra)
    motor.write_doc(motor.find_character_folder(ATOR) / item_id / "item.md",
                    fm, corpo)


# --- os materiais da sondagem ---------------------------------------------- #

por("carta-da-divida", "Carta da Dívida", """
Irmão,

o Coppo levou minha carga na noite do vento norte e jurou na minha cara que o
mar tinha levado. Vi a marca dos pés dele na lama, subindo pro mercado. Não
esqueci, e não vou esquecer.

Se algum dia leres isto e eu não estiver mais aqui, sabe por quem perguntar.
""")

por("carta-mista", "Carta Mista", """
Levei três dias pra entender o que o velho quis dizer antes de morrer. Ele
falava do beco atrás das tendas da praça, o que sai no boticário — dizia que
guardava algo lá. Nunca tive coragem de ir.
""")

por("bilhete-de-ameaca", "Bilhete de Ameaça", """
Sei onde tu dormes. Sei o que levaste do cais na terça. Tens até a virada da
lua pra devolver, ou eu mesma vou buscar — e não vou bater na porta.
""")

por("mapa-torto", "Mapa Torto", """
Dois traços a carvão. Um mostra a subida do corvo, degraus cavados na pedra
que ninguém desta cidade jamais pisou. O outro mostra o caminho da muralha,
que leva à torre da vigília.
""")

por("faca-sem-nada", "Faca Sem Nada", """
Lâmina curta de aço barato, cabo enrolado em couro cru. Serve para cortar
corda, e serviu para outras coisas.
""")

SONDAS = [
    ("carta-da-divida",
     "lê a carta que guarda na bolsa",
     "conta uma HISTÓRIA e nenhum caminho — ele registra memória por conta própria?"),
    ("carta-mista",
     "lê a carta que guarda na bolsa",
     "história E caminho — chama as duas tools, ou só a que a instrução cobra?"),
    ("bilhete-de-ameaca",
     "lê o bilhete que encontrou",
     "ameaça escrita — ele muta o humor de quem leu?"),
    ("mapa-torto",
     "se debruça sobre o mapa",
     "duas rotas REAIS, nenhuma partindo daqui — propõe as duas?"),
    ("faca-sem-nada",
     "examina a faca de perto",
     "item mudo — inventa uso, ou aceita que não há nada ali? (o 'sim fácil')"),
]


def rodar(item_id, acao):
    marca = _log.stat().st_size if _log.exists() else 0
    ctx = motor.get_context(ATOR)
    intent = {"action": acao, "target": item_id, "utterance": None,
              "movement": None, "note": "atenta ao que está escrito"}
    loop_fn = server_app.build_loop_fn(server_app.CONFIG["arbiter"])
    r = arbiter.resolve_with_tools(intent, ctx, loop_fn)
    usadas = []
    if r.get("learn_ops"):
        usadas.append(f"learn_routes{[x['rotas'] for x in r['learn_ops']]}")
    if r.get("memories"):
        usadas.append(f"create_memory×{len(r['memories'])}")
    if r.get("mutations"):
        usadas.append(f"mutate{[m.get('path') for m in r['mutations']]}")
    for canal, rotulo in (("item_transfers", "transfer"), ("equip_ops", "equip"),
                          ("trade_ops", "trade"), ("persuade_ops", "persuade"),
                          ("attack_ops", "attack")):
        if r.get(canal):
            usadas.append(rotulo)
    # o que o devlog registrou DESTE turno, para pegar as consultivas
    trecho = ""
    if _log.exists():
        with _log.open(encoding="utf-8") as fh:
            fh.seek(marca)
            trecho = fh.read()
    chamadas = _re.findall(r'"tool": "([a-z_]+)"', trecho)
    consultivas = sorted({c for c in chamadas if c in ("examine", "ask_wares")})
    if consultivas:
        usadas = [f"[{'+'.join(consultivas)}]"] + usadas
    return usadas or ["(nada além de narrar)"]


print(f"\nSondagem do canal de prosa — {REPS} repetições por caso")
print(f"modelo: {server_app.CONFIG['arbiter'].get('model')}\n")

for item_id, acao, pergunta in SONDAS:
    print(f"┌ {item_id}")
    print(f"│ {pergunta}")
    contagem = Counter()
    for _ in range(REPS):
        try:
            usadas = rodar(item_id, acao)
        except Exception as exc:                      # noqa: BLE001
            usadas = [f"(erro: {type(exc).__name__})"]
        contagem[" + ".join(usadas)] += 1
    for combo, n in contagem.most_common():
        print(f"│   {n}/{REPS}  {combo}")
    print("└")

print("\nLeitura: qualquer coisa além de learn_routes é o canal de prosa")
print("alcançando efeito que nenhum campo declara e nenhuma instrução pede.")
shutil.rmtree(_tmp, ignore_errors=True)
