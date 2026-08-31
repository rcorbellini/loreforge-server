"""O CASO DIFÍCIL: alvo ambíguo, alvo AUSENTE e id de runtime sem nome bom.
É contra isto que o enum foi posto (item 52.5)."""
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
ctx=motor.get_context("elga-taverneira")   # tem 5 moedas iguais e uma `peca-...`
s,l=ctx["self"],ctx["location"]
IDS=set()
for c in ctx["characters_present"]: IDS.add(c["id"])
for i in ctx["items_present"]: IDS.add(i["id"])
for i in s["inventory"]: IDS.add(i["id"])
for o in ctx["objects_present"]: IDS.add(o["id"])
ENTRIES=[(c["id"],c.get("name") or "") for c in ctx["characters_present"]] \
      + [(i["id"],i.get("name") or "") for i in ctx["items_present"]] \
      + [(i["id"],i.get("name") or "") for i in s["inventory"]] \
      + [(o["id"],o.get("name") or "") for o in ctx["objects_present"]]
payload={"personalidade":s.get("body"),
 "contexto":{"local":l.get("name"),"descricao":l.get("narrative"),
   "presentes":[{"id":c.get("id"),"nome":c.get("name")} for c in ctx["characters_present"] if c.get("state")!="self"],
   "objetos_presentes":[{"id":o.get("id"),"nome":o.get("name")} for o in ctx["objects_present"]],
   "itens_presentes":[{"id":i.get("id"),"nome":i.get("name")} for i in ctx["items_present"]],
   "inventario":[{"id":i.get("id"),"nome":i.get("name")} for i in s["inventory"]]}}
caps=face.build(ctx)
COM=[{"type":"function","function":{"name":c["nome"],"description":c.get("descricao") or "",
  "parameters":mcp_core.input_schema(c)}} for c in caps]
SEM=json.loads(json.dumps(COM))
for t in SEM:
    for k,v in (t["function"]["parameters"].get("properties") or {}).items():
        if isinstance(v,dict) and "enum" in v:
            v.pop("enum"); v["description"]="o NOME ou o id daquilo, exatamente como aparece na cena"
def call(user,tools):
    body={"model":"llama3.1:8b","stream":False,"options":{"temperature":0.4},
      "messages":[{"role":"system","content":SYS},{"role":"user","content":user}],"tools":tools}
    req=urllib.request.Request("http://localhost:11434/api/chat",data=json.dumps(body).encode(),
      headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req,timeout=600).read()).get("message") or {}

# alvo AUSENTE de propósito: nada disso existe na cena da Elga
CASOS=[("AMBÍGUO  ","Entregue uma moeda de cobre ao Bram.","give","to"),
       ("AMBÍGUO  ","Guarde uma das suas moedas de prata.","stow","item"),
       ("AUSENTE  ","Examine o destilador que está aqui.","examine","alvo"),
       ("AUSENTE  ","Entregue o pingente de estanho ao Bram.","give","item")]
R=5
for vnome,tools in (("COM enum",COM),("SEM enum",SEM)):
    real=fantasma=0; tot=0
    print(f"--- {vnome} ---")
    for tipo,instr,tool,param in CASOS:
        saidas=[]
        for _ in range(R):
            m=call("O que ele faz?\n\nINSTRUÇÃO: "+instr+"\n\n"+json.dumps(payload,ensure_ascii=False,indent=2),tools)
            c=next((x for x in (m.get("tool_calls") or []) if x.get("function",{}).get("name")==tool),None)
            if not c: saidas.append("—"); continue
            v=(c["function"].get("arguments") or {}).get(param)
            v=v if isinstance(v,str) else json.dumps(v,ensure_ascii=False)
            tot+=1
            if v in IDS or motor._match_scene_ref(v or "",ENTRIES): real+=1; saidas.append(f"OK:{v}")
            else: fantasma+=1; saidas.append(f"FANTASMA:{v}")
        print(f"   {tipo} {tool:9} {saidas}")
    print(f"   => alvo REAL {real}/{tot} · alvo FANTASMA {fantasma}/{tot}\n")
