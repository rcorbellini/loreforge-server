"""LABORATÓRIO DO SLOT MORTO — dá para CONSERTAR a primeira posição? (spec 066, Phase 0)

`sondagem_posicao_vinculo.py` achou que, no formato C, o vínculo da PRIMEIRA pessoa
listada morre: mesmo rótulo, mesma cena, 0/6 na posição 1 contra 6/6 nas posições 2 e 3.

A saída fácil seria ordenar o trecho pondo o menos importante em primeiro — desviar do
defeito. `nao-contornar-defeito-do-primitivo` diz o contrário: **conserte o mecanismo na
mesma spec.** Então a pergunta aqui é se a REDAÇÃO recupera o slot.

Hipótese do porquê: no formato C o primeiro item cola no preâmbulo ("Quem lhe diz alguma
coisa aqui: Renn, irmã. ...") e o modelo o lê como continuação do cabeçalho, não como
item da lista.

Três variantes, TODAS medindo só a posição 1, com o MESMO rótulo:

  C0  o formato C como está hoje (linha corrida depois de dois-pontos) — o controle
  C1  uma linha por pessoa (quebra a corrida; o item deixa de colar no preâmbulo)
  C2  sem preâmbulo: as frases começam direto, sem o "Quem lhe diz alguma coisa aqui:"

Uso:  python3 tests/exploracao/sondagem_slot1_vinculo.py   (exige só o Ollama de pé)
"""
import json
import re
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 6

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

NOMES = ["Renn", "Hulda", "Doncel", "Bram"]
ROTULO = "irmã"
NUCLEO = re.compile(r"irm[ãa]", re.I)
NEUTRO = "conhecido de vista"
ALVO = 0                                   # sempre a PRIMEIRA posição

ABERTURA = """\
Você é a mente de um personagem de RPG, numa cena real. Vai reagir ao que está à
sua volta. NUNCA invente relação, sentimento ou fato que não lhe foi dito."""

PERGUNTA = """\
Para CADA pessoa presente, escreva UMA frase curta (até 15 palavras) dizendo o que
você pensa ou sente ao vê-la. Baseie-se SOMENTE no que lhe foi informado."""

FECHO = """\
Responda SOMENTE com um objeto JSON, chaves = nomes exatamente como aparecem,
nada antes nem depois, EXATAMENTE assim:

{"Renn": "<frase>", "Hulda": "<frase>", "Doncel": "<frase>", "Bram": "<frase>"}"""

SYSTEM = ABERTURA + "\n\n" + PERGUNTA + "\n\n" + FECHO


def _frases():
    return [f"{nome}, {ROTULO if i == ALVO else NEUTRO}."
            for i, nome in enumerate(NOMES)]


def social_C0():
    return "Quem lhe diz alguma coisa aqui: " + " ".join(_frases())


def social_C1():
    return "Quem lhe diz alguma coisa aqui:\n" + "\n".join("- " + f for f in _frases())


def social_C2():
    return " ".join(_frases())


VARIANTES = [
    ("C0  linha corrida após dois-pontos (como está hoje)", social_C0),
    ("C1  uma linha por pessoa", social_C1),
    ("C2  sem preâmbulo", social_C2),
]


def ask(system, user):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return ((json.loads(urllib.request.urlopen(req, timeout=300).read())
             .get("message") or {}).get("content") or "")


def parse(raw):
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


print(f"modelo={MODELO} temp={TEMP} rodadas={R}")
print(f"Só a PRIMEIRA posição ({NOMES[ALVO]}, {ROTULO!r}) é medida. Só a redação muda.\n")

ask(SYSTEM, json.dumps({"lugar": LOCAL, "contexto_social": social_C0(),
                        "presentes": [{"nome": n} for n in NOMES]}, ensure_ascii=False))

for nome_v, montar in VARIANTES:
    acertos, validas = 0, 0
    for _ in range(R):
        user = json.dumps({
            "lugar": LOCAL,
            "contexto_social": montar(),
            "presentes": [{"nome": n, "fazendo": "circula entre as bancas"} for n in NOMES],
        }, ensure_ascii=False, indent=2)
        resp = parse(ask(SYSTEM, user))
        if not resp:
            continue
        validas += 1
        if NUCLEO.search(resp.get(NOMES[ALVO], "") or ""):
            acertos += 1
    print(f"{nome_v}: {acertos}/{validas}  {'#' * acertos}")

print("\nLeitura: se C1 ou C2 recuperam a posição 1, o slot morto era da REDAÇÃO e foi")
print("consertado. Se as três empatam em zero, o defeito é de ORDEM e a composição")
print("precisa tratá-lo — pondo em primeiro quem se pode perder.")
