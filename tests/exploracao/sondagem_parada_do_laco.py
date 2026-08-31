"""O laço PARA sozinho? Simula continuar-no-sucesso até a Mente não pedir mais nada."""
import json, sys, os, urllib.request
from pathlib import Path
sys.path.insert(0,"/home/rcorbellini/loreforge/loreforge-server")
os.environ.setdefault("LOREFORGE_LOG","0")
import motor, face, mcp_core
# o ESCOLHER_SYSTEM é lido do PRÓPRIO mente.js — nunca uma cópia que
# envelhece em silêncio (foi o que aconteceu com o lab_descriptions).
_M = (Path(__file__).resolve().parents[3] / "loreforge-connector" / "mente.js").read_text(encoding="utf-8")
_i = _M.index("const ESCOLHER_SYSTEM = `") + 25
SYS = _M[_i:_M.index("`;", _i)]
def payload(ctx):
    s,l=ctx["self"],ctx["location"]
    return {"personalidade":s.get("body"),"necessidade":s.get("necessidade"),
      "contexto":{"local":l.get("name"),"descricao":l.get("narrative"),
        "presentes":[{"id":c.get("id"),"nome":c.get("name"),"fazendo":c.get("action")} for c in ctx["characters_present"] if c.get("state")!="self"],
        "objetos_presentes":[{"id":o.get("id"),"nome":o.get("name")} for o in ctx["objects_present"]],
        "itens_presentes":[{"id":i.get("id"),"nome":i.get("name")} for i in ctx["items_present"]],
        "inventario":[{"id":i.get("id"),"nome":i.get("name")} for i in s["inventory"]]},
      "memorias":[m.get("summary") or m.get("content") for m in (ctx.get("memories") or [])][:20],
      "rotas_disponiveis":[{"id":r.get("id"),"nome":r.get("name"),"para":r.get("destination_name")} for r in ctx["routes"]]}
ctx=motor.get_context("torvin-ferreiro")
tools=[{"type":"function","function":{"name":c["nome"],"description":c.get("descricao") or "",
  "parameters":mcp_core.input_schema(c)}} for c in face.build(ctx)]
def call(msgs):
    body={"model":"llama3.1:8b","stream":False,"options":{"temperature":0.4},"messages":msgs,"tools":tools}
    req=urllib.request.Request("http://localhost:11434/api/chat",data=json.dumps(body).encode(),
      headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req,timeout=600).read())

SUSSURROS=[
 ("cadeia de 2", "Pegue o frasco de óleo do chão e entregue ao Obadiah."),
 ("cadeia de 3", "Pegue o frasco de óleo do chão, guarde na sua bolsa de couro, e depois pergunte à Odila por onde se vai daqui."),
 ("aberto/vago", "Faça o que achar melhor aqui na praça."),
 ("uma coisa só", "Entregue uma das suas moedas de cobre ao Obadiah."),
]
TETO=8
for nome, instr in SUSSURROS:
    print(f"\n### {nome}: \"{instr}\"")
    base="O que ele faz?\n\nINSTRUÇÃO: "+instr+"\n\n"+json.dumps(payload(ctx),ensure_ascii=False,indent=2)
    msgs=[{"role":"system","content":SYS},{"role":"user","content":base}]
    entrada=0
    for r in range(1,TETO+1):
        resp=call(msgs); entrada+=resp.get("prompt_eval_count",0)
        m=resp.get("message") or {}
        calls=m.get("tool_calls") or []
        nomes=[c.get("function",{}).get("name") for c in calls]
        if not calls:
            txt=(m.get("content") or "").strip().replace("\n"," ")[:90]
            print(f"   r{r}: PAROU SOZINHA (sem tool call) — \"{txt}\"")
            break
        print(f"   r{r}: {nomes}   (entrada acumulada {entrada})")
        msgs=msgs+[{"role":"assistant","content":m.get("content") or "","tool_calls":calls},
                   {"role":"tool","content":"Feito. O mundo registrou a ação."}]
    else:
        print(f"   >>> NÃO PAROU em {TETO} rodadas (entrada acumulada {entrada})")
