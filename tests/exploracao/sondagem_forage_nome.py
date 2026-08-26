"""Diagnóstico RÁPIDO: a confusão `forage`→`forge_armor` medida em sondagem_forage.py
é colisão de NOME (token), não de description? Troca só o `name` exposto no tool-call
(mantém a description igual), na cena C1 (a que mais falhou), e mede se o erro some.

Uso:  python3 tests/exploracao/sondagem_forage_nome.py
"""
import json, urllib.request
from collections import Counter

PORTA, R, MODELO = 8789, 5, "qwen3:8b"

SYSTEM = """Você é A Mente de um personagem de RPG num mundo persistente. A instrução do jogador é uma sugestão de vontade — o personagem NÃO é um robô: tem índole e personalidade inegociáveis.

As ferramentas disponíveis são TUDO o que ele pode tentar aqui e agora; o mundo já filtrou pela cena.

ANTES DE AGIR, pense na SEQUÊNCIA de ações que ele quer realizar e escolha as ferramentas que cumprem essa sequência. Depois chame SOMENTE essas, na ordem pensada. A lista disponível não é um cardápio a percorrer: ferramenta que não faz parte da sequência não se chama.

- Toda chamada leva "prosa.acao": o que ele FAZ, in-world e concreto.
- Descreva a TENTATIVA, nunca o desfecho.
- Se nada couber exatamente, escolha a ferramenta MAIS PRÓXIMA do que ele quer e diga na prosa o que ele tenta."""

DESC = ("Colhe do alvo informado a matéria vegetal que houver nele, criando no lugar o que foi "
        "colhido. Em `onde` vai o lugar onde se está ou uma coisa presente e alcançável de onde se "
        "colhe. O mundo julga, pela descrição do alvo, se há o que colher ali e o quanto.")

NOMES = ["forage", "harvest", "colher"]

CID = "c1-uma"
INSTR = ("Você se cortou feio na queda e o sangue não estanca. Precisa de alguma coisa para "
         "tratar o ferimento, e agora.")

def post(path, payload):
    req = urllib.request.Request(f"http://localhost:{PORTA}{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())
def get(path):
    return json.loads(urllib.request.urlopen(f"http://localhost:{PORTA}{path}", timeout=60).read())
def chat(system, user, tools):
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.2}, "think": False,
            "messages":[{"role":"system","content":system},{"role":"user","content":user}],
            "tools": tools}
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    return (json.loads(urllib.request.urlopen(req, timeout=300).read()).get("message") or {})

tools_raw = (post("/api/mcp",{"jsonrpc":"2.0","id":1,"method":"tools/list",
             "params":{"character_id":CID}}).get("result") or {}).get("tools") or []
ctx = get(f"/api/context?character_id={CID}")
user = (f"O que ele faz?\n\nINSTRUÇÃO: {INSTR}\n\n" + json.dumps({
    "personalidade": (ctx.get("self") or {}).get("description"),
    "contexto": {"local": (ctx.get("location") or {}).get("name"),
        "descricao": (ctx.get("location") or {}).get("description"),
        "presentes": [c.get("name") for c in ctx.get("characters_present",[])],
        "objetos_presentes": ctx.get("objects_present"),
        "itens_presentes": ctx.get("items_present"),
        "inventario": (ctx.get("self") or {}).get("inventory")}}, ensure_ascii=False, indent=2))

placar = {}
for nome_teste in NOMES:
    nativas=[]
    for t in tools_raw:
        f=dict(t)
        if f["name"]=="forage":
            f["name"]=nome_teste
            f["description"]=DESC
        nativas.append({"type":"function","function":{"name":f["name"],
            "description":f.get("description",""),
            "parameters":f.get("inputSchema") or {"type":"object","properties":{}}}})
    chamou=0; mudo=0; outras=Counter()
    for _ in range(R):
        msg = chat(SYSTEM, user, nativas)
        tcs = msg.get("tool_calls") or []
        if not tcs: mudo += 1; continue
        viu=False
        for tc in tcs:
            f=tc.get("function") or {}; n=f.get("name")
            if n==nome_teste: viu=True
            else: outras[n]+=1
        if viu: chamou += 1
    placar[nome_teste]=(chamou,mudo,dict(outras))
    print(f"  name='{nome_teste:<8}'  chamou {chamou}/{R}  mudo {mudo}/{R}  outras={dict(outras)}")

print("\nSe 'harvest'/'colher' chamarem muito mais que 'forage', é colisão de NOME com forge_*.")
