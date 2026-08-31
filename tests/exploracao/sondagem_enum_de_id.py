"""ENUM DE ID x TEXTO LIVRE: pesa menos? erra mais?
Variante B tira TODO enum e descreve o parâmetro; o acerto é medido com o
`_match_scene_ref` que o Motor JÁ usa para casar nome->id."""
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
ctx=motor.get_context("torvin-ferreiro")
s,l=ctx["self"],ctx["location"]

# o universo de referências da cena: (id, nome) — o que o `_match_scene_ref` recebe
ENTRIES=[]
for c in ctx["characters_present"]:
    if c.get("state")!="self": ENTRIES.append((c["id"], c.get("name") or ""))
for i in ctx["items_present"]: ENTRIES.append((i["id"], i.get("name") or ""))
for i in s["inventory"]: ENTRIES.append((i["id"], i.get("name") or ""))
for o in ctx["objects_present"]: ENTRIES.append((o["id"], o.get("name") or ""))
for r in ctx["routes"]: ENTRIES.append((r["id"], r.get("name") or ""))

payload={"personalidade":s.get("body"),"necessidade":s.get("necessidade"),
 "contexto":{"local":l.get("name"),"descricao":l.get("narrative"),
   "presentes":[{"id":c.get("id"),"nome":c.get("name"),"fazendo":c.get("action")} for c in ctx["characters_present"] if c.get("state")!="self"],
   "objetos_presentes":[{"id":o.get("id"),"nome":o.get("name")} for o in ctx["objects_present"]],
   "itens_presentes":[{"id":i.get("id"),"nome":i.get("name")} for i in ctx["items_present"]],
   "inventario":[{"id":i.get("id"),"nome":i.get("name")} for i in s["inventory"]]},
 "memorias":[m.get("summary") or m.get("content") for m in (ctx.get("memories") or [])][:20],
 "rotas_disponiveis":[{"id":r.get("id"),"nome":r.get("name"),"para":r.get("destination_name")} for r in ctx["routes"]]}

caps=face.build(ctx)
COM=[{"type":"function","function":{"name":c["nome"],"description":c.get("descricao") or "",
  "parameters":mcp_core.input_schema(c)}} for c in caps]
SEM=json.loads(json.dumps(COM))
for t in SEM:
    for k,v in (t["function"]["parameters"].get("properties") or {}).items():
        if isinstance(v,dict) and "enum" in v:
            v.pop("enum")
            v["description"]="o NOME ou o id daquilo, exatamente como aparece na cena"

print(f"peso do bloco tools: COM enum {len(json.dumps(COM,ensure_ascii=False))//4} tokens · "
      f"SEM enum {len(json.dumps(SEM,ensure_ascii=False))//4} tokens "
      f"({100*(len(json.dumps(SEM,ensure_ascii=False))-len(json.dumps(COM,ensure_ascii=False)))/len(json.dumps(COM,ensure_ascii=False)):+.0f}%)\n")

def call(user, tools):
    body={"model":"llama3.1:8b","stream":False,"options":{"temperature":0.4},
      "messages":[{"role":"system","content":SYS},{"role":"user","content":user}],"tools":tools}
    req=urllib.request.Request("http://localhost:11434/api/chat",data=json.dumps(body).encode(),
      headers={"Content-Type":"application/json"})
    r=json.loads(urllib.request.urlopen(req,timeout=600).read())
    return (r.get("message") or {}), r.get("prompt_eval_count",0)

CASOS=[("Pegue o frasco de óleo do chão.","take","item","frasco-de-oleo"),
       ("Entregue a moeda-cobre-038 ao Obadiah.","give","to","obadiah-mascate"),
       ("Repare bem no cantil de água que está no chão.","examine","alvo","cantil-de-agua-fresca"),
       ("Pergunte à Odila por onde se vai daqui.","ask_directions","quem","odila-aguadeira")]
R=5
for vnome, tools in (("COM enum (hoje)",COM),("SEM enum (texto livre)",SEM)):
    tool_ok=alvo_ok=alvo_resolvido=0; total=0; toks=0
    print(f"--- {vnome} ---")
    for instr, esperada, param, alvo_certo in CASOS:
        user="O que ele faz?\n\nINSTRUÇÃO: "+instr+"\n\n"+json.dumps(payload,ensure_ascii=False,indent=2)
        amostras=[]
        for _ in range(R):
            m,tk=call(user,tools); toks+=tk; total+=1
            calls=m.get("tool_calls") or []
            achou=next((c for c in calls if c.get("function",{}).get("name")==esperada), None)
            if not achou: amostras.append("(tool errada/mudo)"); continue
            tool_ok+=1
            bruto=(achou["function"].get("arguments") or {}).get(param)
            bruto=bruto if isinstance(bruto,str) else json.dumps(bruto,ensure_ascii=False)
            amostras.append(bruto)
            if bruto==alvo_certo: alvo_ok+=1; alvo_resolvido+=1
            elif motor._match_scene_ref(bruto or "", ENTRIES)==alvo_certo: alvo_resolvido+=1
        print(f"   {esperada:15} {param:6} -> {amostras}")
    print(f"   => tool certa {tool_ok}/{total} · alvo id EXATO {alvo_ok}/{total} · "
          f"alvo RESOLVÍVEL {alvo_resolvido}/{total} · média entrada {toks//total} tokens\n")
