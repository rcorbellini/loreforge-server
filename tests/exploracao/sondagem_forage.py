"""LABORATÓRIO DE DESCRIPTION — `forage` (spec 054), molde exato de
`lab_descriptions.py` (kindle_fire, 2026-08-25). Mesma disciplina: mede FALSO
NEGATIVO (situação clara de colher, e não chamou — silêncio conta) e FALSO
POSITIVO (chamou sem motivo), contra a lista de tools REAL e o prompt de
escolha REAL do conector.

Uso:  python3 tests/exploracao/sondagem_forage.py
      (exige o server de laboratório de pé em :8789 sobre /tmp/lab-forage, e o
       Ollama de pé — ver docs/validacao-de-descriptions.md)
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

VARIANTES = [
 ("VA atual (código)",
  "Colhe do alvo informado a matéria vegetal que houver nele, criando no lugar o que foi "
  "colhido. Em `onde` vai o lugar onde se está ou uma coisa presente e alcançável de onde se "
  "colhe. O mundo julga, pela descrição do alvo, se há o que colher ali e o quanto."),
 ("VB efeito concreto + falha explícita",
  "Colhe matéria vegetal do alvo informado, e o que for colhido aparece ali, pronto para "
  "pegar. Em `onde` vai o lugar onde está agora, ou uma coisa presente e alcançável. O mundo "
  "julga, pela descrição do alvo, se há o que colher — um alvo sem nada de verde não rende "
  "nada."),
 ("VC mínimo imperativo",
  "Colhe o que houver de vegetal no alvo informado, deixando o resultado ali. Em `onde` vai o "
  "lugar atual ou algo presente e alcançável. O que não tem vegetação não rende nada."),
]

CENAS = [
 ("C1 ferido, sem remédio, clareira farta em ervas ", "c1-uma", True,
  "Você se cortou feio na queda e o sangue não estanca. Precisa de alguma coisa para tratar "
  "o ferimento, e agora."),
 ("C2 convés, NENHUMA vegetação, sem necessidade   ", "c2-dois", False,
  "O convés balança com a maré. Você está de bom humor e só quer aproveitar a viagem."),
 ("C3 clareira farta, MAS já colheu, só descansando", "c3-tres", False,
  "Você já colheu o que precisava faz pouco. Agora quer é sentar e descansar um instante "
  "à sombra."),
 ("C4 praça, conversa, nada a ver com plantas       ", "c4-quatro", False,
  "Um velho sentado no banco da praça acena para você. Puxe conversa com ele."),
 ("C5 intenção ATIVA de colher pro ferimento, encosta", "c5-cinco", True,
  "Você decidiu que vai colher alguma planta nesta encosta para tratar o corte no braço, "
  "e ainda não fez."),
]

def post(path, payload):
    req = urllib.request.Request(f"http://localhost:{PORTA}{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())
def get(path):
    return json.loads(urllib.request.urlopen(f"http://localhost:{PORTA}{path}", timeout=60).read())
def chat(system, user, tools):
    # think:false — mesma config do Árbitro real (config.server.json): qwen3 entra
    # em raciocínio estendido por padrão via /api/chat (medido: 1m34s numa chamada
    # trivial de "diga ok"), e a Mente precisa CHAMAR tools, não escrever raciocínio.
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.2},
            "think": False,
            "messages":[{"role":"system","content":system},{"role":"user","content":user}],
            "tools": tools}
    req = urllib.request.Request("http://localhost:11434/api/chat",
        data=json.dumps(body).encode(), headers={"Content-Type":"application/json"})
    return (json.loads(urllib.request.urlopen(req, timeout=300).read()).get("message") or {})

placar = {}
for vnome, vdesc in VARIANTES:
    fn = fp = 0
    print(f"\n{'='*76}\n### {vnome}\n{'='*76}")
    for cnome, cid, deve, instr in CENAS:
        tools = (post("/api/mcp",{"jsonrpc":"2.0","id":1,"method":"tools/list",
                 "params":{"character_id":cid}}).get("result") or {}).get("tools") or []
        nativas=[]
        for t in tools:
            f=dict(t)
            if f["name"]=="forage": f["description"]=vdesc
            nativas.append({"type":"function","function":{"name":f["name"],
                "description":f.get("description",""),
                "parameters":f.get("inputSchema") or {"type":"object","properties":{}}}})
        ctx = get(f"/api/context?character_id={cid}")
        user = (f"O que ele faz?\n\nINSTRUÇÃO: {instr}\n\n" + json.dumps({
            "personalidade": (ctx.get("self") or {}).get("description"),
            "necessidade": {"fome": (ctx.get("self") or {}).get("status",{}).get("hunger")},
            "contexto": {"local": (ctx.get("location") or {}).get("name"),
                "descricao": (ctx.get("location") or {}).get("description"),
                "presentes": [c.get("name") for c in ctx.get("characters_present",[])],
                "objetos_presentes": ctx.get("objects_present"),
                "itens_presentes": ctx.get("items_present"),
                "inventario": (ctx.get("self") or {}).get("inventory")}}, ensure_ascii=False, indent=2))
        chamou=0; mudo=0; outras=Counter(); ondes=[]
        for _ in range(R):
            try: msg = chat(SYSTEM, user, nativas)
            except Exception as e: outras[f"ERRO"]+=1; continue
            tcs = msg.get("tool_calls") or []
            if not tcs: mudo += 1; continue
            viu_forage=False
            for tc in tcs:
                f=tc.get("function") or {}; n=f.get("name")
                args=f.get("arguments") or {}
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except Exception: args={}
                if n=="forage":
                    viu_forage=True
                    onde=args.get("onde")
                    if onde: ondes.append(onde)
                else: outras[n]+=1
            if viu_forage: chamou += 1
        erro = (R-chamou) if deve else chamou
        if deve: fn += erro
        else: fp += erro
        rot = "FN" if deve else "FP"
        print(f"  {cnome}  {'DEVE' if deve else 'NÃO'}  chamou {chamou}/{R}  mudo {mudo}/{R}  {rot}={erro}")
        print(f"      onde={ondes}  outras={dict(outras)}")
    placar[vnome]=(fn,fp)
    print(f"  >>> {vnome}: FN={fn}  FP={fp}  TOTAL DE ERROS={fn+fp}")

print(f"\n{'='*76}\nPLACAR (menor é melhor)\n{'='*76}")
for k,(fn,fp) in sorted(placar.items(), key=lambda x: x[1][0]+x[1][1]):
    print(f"  {k:<42} FN={fn:>2}  FP={fp:>2}  total={fn+fp:>2}")
