"""A Mente CORRIGE o `pronto_quando` quando a recusa traz a lista? (spec 073, §15)

Medido em jogo: a Nerissa mandou `pronto_quando: "odila-aguadeira"` — o id de uma
PESSOA —, o mundo recusou sem dizer quais critérios existem, e ela NÃO tentou de novo.
Um `set_intention` em duas horas, e o ciclo inteiro da spec morreu ali.

O conserto foi devolver campo + `validos`. Esta sondagem mede se isso basta: dada a
mesma cena e a recusa COM a lista, ela escolhe um critério do vocabulário?

Quatro cenas, cada uma com um critério claramente certo — mas o gabarito não é meu:
o que se mede é se a resposta CAI NO VOCABULÁRIO, não se bate com o que eu acho.
Sair do vocabulário é a falha; qual dos quatro ela escolhe é agência dela.

Uso:  python3 tests/exploracao/sondagem_criterio.py [rodadas]
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("LOREFORGE_LOG", "0")

from motor.intencoes.declaracao import SET_INTENTION  # noqa: E402
from motor.intencoes.primitivas import _CRITERIO_POR_CAMPO  # noqa: E402

MODELO = os.environ.get("LOREFORGE_MODELO", "llama3.1:8b")
RODADAS = int(sys.argv[1]) if len(sys.argv) > 1 else 3
VOCAB = sorted(_CRITERIO_POR_CAMPO)

# A DESCRIÇÃO REAL da tool — não uma paráfrase. É ela que o jogo manda.
DESC = SET_INTENTION.description

SYSTEM = (
    "Você é um personagem decidindo um compromisso. A ferramenta `set_intention` "
    "pede `content` (o compromisso) e `pronto_quando` (o fato que o encerra).\n\n"
    f"{DESC}\n\n"
    "O mundo RECUSOU sua primeira tentativa, e disse o que falta:\n"
    '  erro: "você não saberia dizer quando isso estaria cumprido"\n'
    f'  campo: "pronto_quando"\n'
    f'  validos: {json.dumps(VOCAB)}\n\n'
    "Se o que encerra é TER algo em mãos, use \"posse\" e diga em "
    "`pronto_quando_alvo` o NOME da coisa (vale o que ainda não existe: o remédio "
    "que você vai preparar).\n\n"
    "Responda APENAS um objeto JSON, sem texto antes ou depois:\n"
    '{"pronto_quando": "<um dos validos>", "pronto_quando_alvo": "<o nome, ou null>"}'
)

CENAS = [
    ("faminto", "Você está faminto. Firmou: 'Matar minha fome antes do anoitecer.'"),
    ("sedento", "Você está sedento. Firmou: 'Achar água boa e beber.'"),
    ("exausto", "Você está exausto, de pé há muitas horas. Firmou: 'Dormir.'"),
    ("peça parada", "Você deixou um martelo pela metade na forja. "
                    "Firmou: 'Terminar o martelo que deixei no meio.'"),
    ("ter a garra", "Você firmou: 'Conseguir a garra de lobo que o Verro guarda.'"),
    # e a cena que CAUSOU o defeito, literal
    ("o caso da Nerissa", "Você firmou: 'Fazer um remédio de raiz torta para ajudar "
                          "os outros, com Odila, a Aguadeira.' Sua primeira resposta "
                          "foi 'odila-aguadeira', e o mundo recusou."),
]


def ask(user: str) -> str:
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": 0.2},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=300).read())
        return (r.get("message") or {}).get("content") or ""
    except Exception:
        return ""


def escolha(texto: str):
    """Devolve (criterio, alvo) — o alvo importa: `posse` sem ele é inútil."""
    try:
        i, f = texto.index("{"), texto.rindex("}") + 1
        d = json.loads(texto[i:f])
        v = d.get("pronto_quando")
        a = d.get("pronto_quando_alvo")
        return (str(v).strip() if v else None,
                str(a).strip() if a and str(a).lower() != "null" else None)
    except Exception:
        return (None, None)


print("=" * 74)
print(f"A MENTE CORRIGE O CRITÉRIO? — modelo {MODELO}, {RODADAS} rodada(s)")
print(f"vocabulário: {VOCAB}")
print("=" * 74)

dentro = fora = mudo = 0
for rot, cena in CENAS:
    obtidas = []
    for _ in range(RODADAS):
        e, alvo = escolha(ask(cena))
        if e is None:
            mudo += 1
        elif e in VOCAB:
            dentro += 1
            # `posse` SEM alvo é o mesmo que critério nenhum: a trava o barra, e
            # contar como acerto esconderia o buraco.
            obtidas.append(f"{e}({alvo})" if e == "posse" else e)
        else:
            fora += 1
            obtidas.append(f"!{e}")
    print(f"  {rot:22} {Counter(obtidas).most_common()}")

total = dentro + fora + mudo
print("-" * 74)
print(f"  no vocabulário: {dentro}/{total}   fora: {fora}   sem resposta: {mudo}")
if fora or mudo:
    print("  A recusa COM a lista ainda não basta — o conserto da §15.3 é necessário")
    print("  mas não suficiente, e a próxima corrida vai medir nada de novo.")
else:
    print("  A lista basta: a Mente escolhe do vocabulário. A corrida pode ser refeita.")
