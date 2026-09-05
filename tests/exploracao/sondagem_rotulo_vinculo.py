"""LABORATÓRIO DE RÓTULO — quantas palavras o vínculo sobrevive? (spec 066, Phase 0)

A sondagem irmã (`sondagem_vinculo_afeto.py`) mediu o FORMATO e deixou um buraco: ela
comparou rótulo de UMA palavra ("primo", sobreviveu 7/8 na narração) contra TRÊS com
aposto ("irmã de criação", 1/8). **Duas palavras nunca foi testado** — e é exatamente onde
caem "meia-irmã", "terra natal" e "irmão de criação", que o próprio schema da spec usa de
exemplo.

A pergunta é estreita e decide o contrato do campo `bonds.label`:

  o rótulo deve ser livre, orientado, ou validado como forma curta?

MEDE UMA COISA: dado um rótulo de N palavras, ele SOBREVIVE na frase que A Mente escreve,
ou o modelo o poda? Sobreviver = o núcleo do rótulo aparece na resposta.

NÃO mede qualidade da frase — isso é outra pergunta, e misturá-las foi o erro que o
`lab_descriptions.py` já registra no cabeçalho dele.

Uso:  python3 tests/exploracao/sondagem_rotulo_vinculo.py   (exige só o Ollama de pé)
"""
import json
import re
import sys
import urllib.request

MODELO, TEMP, R = "llama3.1:8b", 0.4, 8

LOCAL = {"nome": "Praça do Mercado",
         "descricao": ("Bancas de pano puxado, cheiro de peixe seco e especiaria. "
                       "O sol já está alto e o movimento é grande.")}

# (nome, rótulo, regex do NÚCLEO que precisa sobreviver, nº de palavras)
# O núcleo é a parte que carrega o fato — se ela some, o vínculo se perdeu.
CASOS = [
    ("Renn",   "primo",             re.compile(r"prim[ao]", re.I),                 1),
    ("Hulda",  "meia-irmã",         re.compile(r"meia[- ]irm[ãa]", re.I),          2),
    ("Doncel", "irmão de criação",  re.compile(r"irm[ãa]o de cria", re.I),         3),
]
# controle: o mesmo núcleo SEM qualificação, para separar "o modelo poda o aposto" de
# "o modelo simplesmente não repete o rótulo"
CONTROLE = ("Bram", "irmão", re.compile(r"irm[ãa]o", re.I), 1)

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


def montar_user():
    """Formato C (o vencedor da sondagem irmã): parágrafo antes da lista, sujeito e
    objeto por extenso, sem possessivo ambíguo."""
    todos = CASOS + [CONTROLE]
    frases = [f"{nome}, {rotulo}." for nome, rotulo, _, _ in todos]
    presentes = [{"nome": n, "fazendo": "circula entre as bancas"} for n, _, _, _ in todos]
    return json.dumps({
        "lugar": LOCAL,
        "contexto_social": "Quem lhe diz alguma coisa aqui: " + " ".join(frases),
        "presentes": presentes,
    }, ensure_ascii=False, indent=2)


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
print("A MESMA cena e o MESMO formato nas quatro linhas — só o TAMANHO do rótulo muda.\n")

todos = CASOS + [CONTROLE]
sobreviveu = {nome: 0 for nome, _, _, _ in todos}
validas = 0

# aquecimento: a sondagem anterior mostrou que a 1ª chamada de uma sessão costuma
# voltar vazia. Ela não conta.
ask(SYSTEM, montar_user())

for i in range(R):
    resp = parse(ask(SYSTEM, montar_user()))
    if not resp:
        print(f"   [{i+1}] (resposta ilegível — descartada)")
        continue
    validas += 1
    for nome, rotulo, nucleo, _ in todos:
        frase = resp.get(nome, "") or ""
        ok = bool(nucleo.search(frase))
        if ok:
            sobreviveu[nome] += 1
    print(f"   [{i+1}] " + " | ".join(
        f"{nome}:{'OK' if todos[j][2].search(resp.get(nome,'') or '') else '--'}"
        for j, (nome, _, _, _) in enumerate(todos)))

print(f"\n=== RESULTADO ({validas} rodadas válidas) ===")
for nome, rotulo, _, palavras in todos:
    marca = "  <- CONTROLE" if nome == CONTROLE[0] else ""
    print(f"{palavras} palavra(s)  {rotulo!r:22} sobreviveu {sobreviveu[nome]}/{validas}{marca}")

print("\nLeitura: se 2 palavras acompanha 1 palavra, o bound pode ser 2 e 'meia-irmã'/")
print("'terra natal' cabem. Se 2 acompanha 3, o bound é 1 e o schema fica mais restrito.")
print("O CONTROLE separa 'o modelo poda o aposto' de 'o modelo não repete rótulo nenhum'.")
