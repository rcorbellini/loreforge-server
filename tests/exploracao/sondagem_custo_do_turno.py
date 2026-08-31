"""CUSTO REAL: dois turnos de hoje x um turno com duas rodadas.
Mede `prompt_eval_count` / `eval_count` do Ollama — tokens de verdade, não estimativa."""
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

def tools_de(ctx):
    return [{"type":"function","function":{"name":c["nome"],"description":c.get("descricao") or "",
      "parameters":mcp_core.input_schema(c)}} for c in face.build(ctx)]

def call(msgs, tools=None):
    body={"model":"llama3.1:8b","stream":False,"options":{"temperature":0.4},"messages":msgs}
    if tools: body["tools"]=tools
    req=urllib.request.Request("http://localhost:11434/api/chat",data=json.dumps(body).encode(),
      headers={"Content-Type":"application/json"})
    r=json.loads(urllib.request.urlopen(req,timeout=600).read())
    return r, r.get("prompt_eval_count",0), r.get("eval_count",0)

ctx=motor.get_context("torvin-ferreiro")
tools=tools_de(ctx)
base="O que ele faz?\n\nINSTRUÇÃO: Pegue o frasco de óleo do chão e entregue ao Obadiah.\n\n"+json.dumps(payload(ctx),ensure_ascii=False,indent=2)

NARRAR_SYS="Você narra, em 2 ou 3 frases, o que o personagem fez e o que aconteceu. Nunca invente desfecho."
def narrar(o_que):
    return call([{"role":"system","content":NARRAR_SYS},
                 {"role":"user","content":json.dumps({"personagem":"Torvin","acontecido":o_que},ensure_ascii=False)}])

print("=== CENÁRIO A — HOJE: dois turnos, um passo cada ===")
tot_in=tot_out=chamadas=0
# turno 1: ESCOLHER + narrate
_,i,o=call([{"role":"system","content":SYS},{"role":"user","content":base}],tools)
print(f"  T1 ESCOLHER   entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
_,i,o=narrar("pegou o Frasco de Óleo")
print(f"  T1 narrate    entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
# turno 2: o jogador sussurra de novo, cena RECONSTRUÍDA do zero
base2="O que ele faz?\n\nINSTRUÇÃO: Agora entregue o frasco de óleo ao Obadiah.\n\n"+json.dumps(payload(ctx),ensure_ascii=False,indent=2)
_,i,o=call([{"role":"system","content":SYS},{"role":"user","content":base2}],tools)
print(f"  T2 ESCOLHER   entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
_,i,o=narrar("entregou o Frasco de Óleo a Obadiah")
print(f"  T2 narrate    entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
A=(tot_in,tot_out,chamadas)
print(f"  TOTAL A: {chamadas} chamadas · {tot_in} entrada · {tot_out} saída\n")

print("=== CENÁRIO B — PROPOSTO: um turno, duas rodadas ===")
tot_in=tot_out=chamadas=0
r,i,o=call([{"role":"system","content":SYS},{"role":"user","content":base}],tools)
print(f"  R1 ESCOLHER   entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
msg=r.get("message") or {}
msgs=[{"role":"system","content":SYS},{"role":"user","content":base},
      {"role":"assistant","content":msg.get("content") or "","tool_calls":msg.get("tool_calls") or []},
      {"role":"tool","content":"Frasco de Óleo passou para as mãos dele."}]
_,i,o=call(msgs,tools)
print(f"  R2 ESCOLHER   entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
_,i,o=narrar("pegou o Frasco de Óleo e entregou a Obadiah")
print(f"  narrate (UMA) entrada {i:>6}  saída {o:>4}"); tot_in+=i; tot_out+=o; chamadas+=1
B=(tot_in,tot_out,chamadas)
print(f"  TOTAL B: {chamadas} chamadas · {tot_in} entrada · {tot_out} saída\n")

print("=== COMPARAÇÃO ===")
print(f"  chamadas ao modelo : A={A[2]}   B={B[2]}   ({B[2]-A[2]:+d})")
print(f"  tokens de entrada  : A={A[0]}  B={B[0]}  ({B[0]-A[0]:+d}, {100*(B[0]-A[0])/A[0]:+.1f}%)")
print(f"  tokens de saída    : A={A[1]}  B={B[1]}  ({B[1]-A[1]:+d})")
