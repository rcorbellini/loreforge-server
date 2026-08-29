"""LABORATÓRIO DE DESCRIPTION — `sing` (spec 058), a FACE que desce à Mente.

Molde de `sondagem_brew.py`, com uma divergência deliberada: `sing` ainda NÃO existe
no código, então não há manifest real a buscar num server de laboratório. A tool é
declarada aqui, sinteticamente, ao lado de quatro vizinhas plausíveis — e só a
`description` varia entre as variantes, que é o invariante que o método exige.

A pergunta desta sondagem é ESPECÍFICA e não é a de sempre (FN/FP genérico). O
`memoria_id` sai de um enum de ids OPACOS (`mem-4b2a`...), e isso abre um fork que
nenhuma tool anterior tinha:

  FA (contrato puro)  — a Mente escolhe um id sem saber o que cada um contém.
                        Erra a lembrança?
  FC (com a listagem) — o molde de `accuse`: as lembranças entram na description com
                        resumo. Resolve a escolha do id, mas INDUZ a cantar?

Mede, por variante: (a) chamou quando devia, (b) escolheu o id CERTO, (c) chamou
quando não devia (falso positivo — é aqui que a indução da listagem apareceria).

Uso:  python3 tests/exploracao/sondagem_sing_face.py   (exige só o Ollama de pé)
"""
import json
import urllib.request
from collections import Counter

# o modelo da MENTE (o conector), não o do Árbitro — é ela quem lê a description.
MODELO, TEMP, R = "llama3.1:8b", 0.2, 5

SYSTEM = """Você é A Mente de um personagem de RPG num mundo persistente. A instrução do jogador é uma sugestão de vontade — o personagem NÃO é um robô: tem índole e personalidade inegociáveis.

As ferramentas disponíveis são TUDO o que ele pode tentar aqui e agora; o mundo já filtrou pela cena.

ANTES DE AGIR, pense na SEQUÊNCIA de ações que ele quer realizar e escolha as ferramentas que cumprem essa sequência. Depois chame SOMENTE essas, na ordem pensada. A lista disponível não é um cardápio a percorrer: ferramenta que não faz parte da sequência não se chama.

- Toda chamada leva "prosa.acao": o que ele FAZ, in-world e concreto.
- Descreva a TENTATIVA, nunca o desfecho.
- Se nada couber exatamente, escolha a ferramenta MAIS PRÓXIMA do que ele quer e diga na prosa o que ele tenta."""

MEMORIAS = ["mem-4b2a", "mem-91c7", "mem-33f0"]
LISTAGEM = ("Lembranças disponíveis: mem-4b2a (sobre Torvin: 'Vi Torvin derrubar o que "
            "saiu do poço'); mem-91c7 (sobre Elga: 'Elga me deu abrigo na noite da "
            "tempestade'); mem-33f0 (sobre Bram: 'Dizem por aí que Bram afundou um bote "
            "de propósito').")

_BASE = ("Canta, para quem estiver aqui, uma lembrança sua. Quem ouvir passa a saber do "
         "que aconteceu, mesmo sem ter estado lá. Em `memoria_id` vai a lembrança a "
         "cantar; em `instrumento`, algo que você já tenha na mão.")

VARIANTES = [
    ("FA contrato puro          ", _BASE),
    ("FB contrato + a restrição ", _BASE + " Só se canta o que você lembra."),
    ("FC contrato + listagem    ", _BASE + " " + LISTAGEM),
]


def tools(desc):
    return [
        {"type": "function", "function": {
            "name": "sing", "description": desc,
            "parameters": {"type": "object", "properties": {
                "memoria_id": {"type": "string", "enum": MEMORIAS},
                "instrumento": {"type": "string", "enum": ["alaude-remendado"]},
                "prosa": {"type": "object", "properties": {"acao": {"type": "string"}}}},
                "required": ["memoria_id", "prosa"]}}},
        {"type": "function", "function": {
            "name": "ask_about", "description":
            "Pergunta a outro presente o que ele sabe de alguém ou de um lugar.",
            "parameters": {"type": "object", "properties": {
                "quem": {"type": "string", "enum": ["elga-taverneira", "bram-pescador"]},
                "sobre": {"type": "string"},
                "prosa": {"type": "object", "properties": {"acao": {"type": "string"}}}},
                "required": ["quem", "sobre", "prosa"]}}},
        {"type": "function", "function": {
            "name": "examine", "description":
            "Olha de perto uma coisa presente e lê o que ela mostra.",
            "parameters": {"type": "object", "properties": {
                "alvo": {"type": "string", "enum": ["alaude-remendado", "lareira"]},
                "prosa": {"type": "object", "properties": {"acao": {"type": "string"}}}},
                "required": ["alvo", "prosa"]}}},
        {"type": "function", "function": {
            "name": "take", "description": "Pega para a mão algo ao alcance.",
            "parameters": {"type": "object", "properties": {
                "item": {"type": "string", "enum": ["alaude-remendado"]},
                "prosa": {"type": "object", "properties": {"acao": {"type": "string"}}}},
                "required": ["item", "prosa"]}}},
        {"type": "function", "function": {
            "name": "sleep", "description": "Deita e dorme, recuperando o corpo.",
            "parameters": {"type": "object", "properties": {
                "prosa": {"type": "object", "properties": {"acao": {"type": "string"}}}},
                "required": ["prosa"]}}},
    ]


CENA = ("Você está na Taverna do Gancho, salão cheio, a lareira acesa. Elga seca canecas "
        "atrás do balcão; Bram conta moedas; Doncel cochila sobre a mesa. Um alaúde "
        "remendado está encostado no banco ao seu lado. ")

CASOS = [
    # (rótulo, instrução, deve chamar?, id esperado ou None)
    ("C1 quer que a mesa saiba do feito de Torvin", CENA
     + "Você quer que essa gente toda saiba do que Torvin fez naquele poço.",
     True, "mem-4b2a"),
    ("C2 quer honrar a bondade de Elga          ", CENA
     + "Você quer que fique registrado, para todo mundo aqui, o quanto Elga foi "
       "generosa com você naquela noite de tempestade.", True, "mem-91c7"),
    ("C3 só quer descansar (falso positivo)     ", CENA
     + "Você está exausto da estrada e só quer sentar num canto e descansar.",
     False, None),
    ("C4 intenção ATIVA de cantar               ", CENA
     + "Você decidiu que vai cantar para essa mesa a história do poço, e ainda não "
       "cantou.", True, "mem-4b2a"),
    ("C5 quer saber o que Elga sabe de Bram     ", CENA
     + "Você quer descobrir o que Elga sabe sobre o Bram e aquele bote.", False, None),
]


def chat(system, user, tls):
    body = {"model": MODELO, "stream": False, "think": False,
            "options": {"temperature": TEMP},
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "tools": tls}
    req = urllib.request.Request("http://localhost:11434/api/chat",
                                 data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    return (json.loads(urllib.request.urlopen(req, timeout=300).read())
            .get("message") or {})


print(f"modelo={MODELO} temp={TEMP} rodadas={R}\n")
placar = {}
for nome_v, desc in VARIANTES:
    tls = tools(desc)
    fn = fp = id_errado = 0
    print(f"--- {nome_v} ---")
    for rot, instr, deve, id_ok in CASOS:
        chamou, ids, outras = 0, Counter(), Counter()
        for _ in range(R):
            msg = chat(SYSTEM, instr, tls)
            calls = msg.get("tool_calls") or []
            nomes = [c["function"]["name"] for c in calls]
            if "sing" in nomes:
                chamou += 1
                for c in calls:
                    if c["function"]["name"] == "sing":
                        ids[(c["function"].get("arguments") or {}).get("memoria_id")] += 1
            for n in nomes:
                if n != "sing":
                    outras[n] += 1
            if not calls:
                outras["<mudo>"] += 1
        if deve:
            fn += R - chamou
            id_errado += sum(v for k, v in ids.items() if k != id_ok)
        else:
            fp += chamou
        print(f"   {rot} sing={chamou}/{R} ids={dict(ids)} outras={dict(outras)}")
    placar[nome_v] = (fn, fp, id_errado)
    print(f"   >> FN={fn}  FP={fp}  id_errado={id_errado}\n")

print("=" * 70)
print(f"{'variante':28s} {'FN':>4} {'FP':>4} {'id_errado':>10} {'total':>6}")
for k, (fn, fp, ie) in placar.items():
    print(f"{k:28s} {fn:>4} {fp:>4} {ie:>10} {fn+fp+ie:>6}")
