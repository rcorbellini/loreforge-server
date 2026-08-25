"""LABORATÓRIO DE DESCRIPTION — a redação de uma tool melhora ou piora a escolha?

A `description` de uma tool não é texto de enfeite: é a única coisa que a LLM
cliente lê para decidir se aquela capacidade serve à situação. Este arnês mede
essa decisão, variante por variante, contra a lista de tools REAL e o prompt de
escolha REAL do conector.

MEDE DUAS COISAS, E SÓ ELAS:
  FALSO NEGATIVO — situação clara de chamar, e não chamou. Ficar MUDO conta como
                   erro: no jogo, silêncio é um turno perdido.
  FALSO POSITIVO — chamou sem motivo (o efeito já existe na cena, ou a cena não
                   tem nada a ver com a tool).

REGRAS DE DESENHO, aprendidas errando (2026-08-25):

  · A INSTRUÇÃO PRECISA TORNAR A SITUAÇÃO CLARA. A primeira versão deste
    laboratório usava "faça o que fizer sentido" e mediu, na prática, silêncio:
    o modelo ficava mudo em até 3 de 3 rodadas e nenhuma variante se distinguia.
  · A TOOL PRECISA ESTAR DISPONÍVEL TAMBÉM NAS CENAS QUE NÃO DEVEM CHAMÁ-LA.
    Sem isso o falso positivo é impossível de medir.
  · INTENÇÃO ATIVA CONTA COMO MOTIVO LEGÍTIMO. Se o personagem decidiu fazer
    algo, chamar a tool correspondente está certo — mesmo que a intenção em si
    esteja mal regulada (isso é problema do mecanismo de intenção, não da
    description).
  · NENHUMA VARIANTE ENUMERA CASO DE USO. Listar "serve para X, Y e Z" congela a
    tool nos usos que hoje imaginamos e mata o que ninguém previu — e, medido,
    nem ajuda a escolher.

Uso:  python3 tests/exploracao/lab_descriptions.py
      (exige um server sobre um mundo de laboratório e o Ollama de pé — ver
       docs/validacao-de-descriptions.md para o passo a passo)
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
 ("V1 atual (player-facing, lista usos)",
  "Tenta acender fogo com o que estiver ao alcance. O mundo decide, lendo as descrições, se "
  "aquilo realmente pode queimar e o quanto a tentativa é favorável — o que você tem em mãos "
  "conta. Dá para se aquecer, cozinhar e, se a chama e o lugar permitirem, trabalhar metal. "
  "Um fogo aceso não prende quem o acendeu: ele queima sozinho e, em algum momento, se apaga. "
  "Coisas que não queimam são recusadas, e uma tentativa pode simplesmente não pegar."),
 ("V2 efeito + contrato (com DESTRUÍDOS)",
  "Queima os materiais informados. Eles são DESTRUÍDOS; se de fato pegarem fogo, nasce no "
  "lugar uma fonte de calor acesa, que dura um tempo e depois se apaga sozinha. Em `materiais` "
  "vai só o que deve virar combustível — a ferramenta de fazer faísca não entra na lista, o "
  "mundo já considera sozinho o que está em mãos. O mundo julga se aquilo queima: o que não "
  "queima é recusado sem destruir nada."),
 ("V4 mínimo imperativo",
  "Queima os materiais informados para criar uma fonte de calor acesa no lugar. Os materiais "
  "são destruídos. Passe apenas o que deve virar combustível; a ferramenta de acender não "
  "entra. O que não queima é recusado sem consumo."),
 ("V5 efeito, sem alarde de destruição",
  "Acende uma fonte de calor no lugar, queimando os materiais informados. Em `materiais` vão "
  "as coisas que devem virar combustível; a ferramenta de fazer faísca não entra — o mundo já "
  "considera sozinho o que está em mãos. O mundo julga, pela descrição, se aquilo pega fogo."),
]

CENAS = [
 ("C1 noite fria, lenha seca, pederneira na mão", "c1-alma", True,
  "A noite caiu de vez e o frio está insuportável aqui em cima."),
 ("C2 carne crua, NENHUMA fonte de calor, gravetos", "c2-bento", True,
  "Você está faminto e só tem essa carne crua."),
 ("C3 fogueira JÁ ACESA, carne crua, com fome    ", "c3-cira", False,
  "Você está faminta e só tem essa carne crua."),
 ("C4 conversa na praça, nada a ver com fogo     ", "c4-dora", False,
  "O velho sentado no poço reparou em você. Puxe conversa com ele."),
 ("C5 intenção ATIVA de fazer fogo + mato seco   ", "c5-vidal", True,
  "Você decidiu que vai fazer uma fogueira nesta parada, e ainda não fez."),
]

def post(path, payload):
    req = urllib.request.Request(f"http://localhost:{PORTA}{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())
def get(path):
    return json.loads(urllib.request.urlopen(f"http://localhost:{PORTA}{path}", timeout=60).read())
def chat(system, user, tools):
    body = {"model": MODELO, "stream": False, "options": {"temperature": 0.2},
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
            if f["name"]=="kindle_fire": f["description"]=vdesc
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
        chamou=0; mudo=0; outras=Counter(); mats=[]
        for _ in range(R):
            try: msg = chat(SYSTEM, user, nativas)
            except Exception as e: outras[f"ERRO"]+=1; continue
            tcs = msg.get("tool_calls") or []
            if not tcs: mudo += 1; continue
            viu_kindle=False
            for tc in tcs:
                f=tc.get("function") or {}; n=f.get("name")
                args=f.get("arguments") or {}
                if isinstance(args,str):
                    try: args=json.loads(args)
                    except Exception: args={}
                if n=="kindle_fire":
                    viu_kindle=True
                    m=args.get("materiais"); mats += (m if isinstance(m,list) else [m] if m else [])
                else: outras[n]+=1
            if viu_kindle: chamou += 1
        erro = (R-chamou) if deve else chamou
        if deve: fn += erro
        else: fp += erro
        rot = "FN" if deve else "FP"
        print(f"  {cnome}  {'DEVE' if deve else 'NÃO'}  chamou {chamou}/{R}  mudo {mudo}/{R}  {rot}={erro}")
        print(f"      materiais={mats}  outras={dict(outras)}")
    placar[vnome]=(fn,fp)
    print(f"  >>> {vnome}: FN={fn}  FP={fp}  TOTAL DE ERROS={fn+fp}")

print(f"\n{'='*76}\nPLACAR (menor é melhor)\n{'='*76}")
for k,(fn,fp) in sorted(placar.items(), key=lambda x: x[1][0]+x[1][1]):
    print(f"  {k:<42} FN={fn:>2}  FP={fp:>2}  total={fn+fp:>2}")
