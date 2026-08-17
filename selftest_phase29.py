"""Auto-teste da Fase 29 — Compromisso Lembrado (spec 027).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`),
molde das fases 25-28: a validação AUTORITATIVA mora nos handlers
auto-contidos (`compromisso._h_promise`, `itens._h_transfer`,
`comercio._h_trade`), não no pré-check do Árbitro. Cobre:

  - `prometer`: puramente verbal — memória nos dois lados + intenção só no
    ator, NUNCA move item (spec 036: item saiu do escopo de `prometer` de
    vez — quem quiser reforçar um empréstimo mecânico usa `give` com
    `emprestimo=true`, separadamente)
  - `prometer` nunca rola dado (FR-004)
  - `give`/`trade` com `intention_id` válido e da própria pasta: fecha junto
  - `give`/`trade` com `intention_id` inválido/alheio/já encerrado: a
    TRANSFERÊNCIA continua de pé, só o fechamento fica marcado como não
    realizado (nunca vira `rejected` — FR-007)
  - `give` sem `intention_id`: comportamento IDÊNTICO ao de sempre (zero
    regressão)
  - o CAMINHO VIVO do tool-calling (`resolve_with_tools`): `prometer` no
    manifest (sem `item` em properties), dispatch via `execute()`, e o
    outcome expõe `promise_ops_applied` E `intentions_applied` (o achado do
    `_ACC_CH` corrigido junto desta spec)
  - US3: encadear emprestar (give+emprestimo, física) → prometer (verbal,
    separado) → devolver, e confirmar que o credor tem, no contexto, a
    intenção ativa e a memória nova lado a lado

Uso:  python3 server/selftest_phase29.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"
MOEDA1, MOEDA2 = "moeda-de-prata-1", "moeda-de-prata-2"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def ifolder(item_id) -> Path:
    return motor.find_entity(item_id)[0].parent


def dono(item_id) -> str | None:
    """Sobe a cadeia de pastas até achar um character.md (molde de selftest_phase14)."""
    p = ifolder(item_id).parent
    world = motor.WORLD_DIR
    while p != world and p != p.parent:
        if (p / "character.md").exists():
            return motor.read_doc(p / "character.md")[0].get("id")
        p = p.parent
    return None


def dar(cid: str, item_id: str):
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm["state"] = {**(fm.get("state") or {}), "slot": motor.HAND_SLOT}
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.find_character_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def memories(cid: str) -> list[tuple[dict, str]]:
    d = motor.find_character_folder(cid) / "memories"
    if not d.exists():
        return []
    return [motor.read_doc(p) for p in sorted(d.glob("*.md"))]


def intentions(cid: str) -> list[tuple[dict, str]]:
    d = motor.find_character_folder(cid) / "intentions"
    if not d.exists():
        return []
    return [motor.read_doc(p) for p in sorted(d.glob("*.md"))]


def forbid_roll():
    def _boom():
        raise AssertionError("rolagem não deveria acontecer em `prometer`")
    motor._roll_d20 = _boom


def allow_roll():
    import random
    motor._roll_d20 = lambda: random.randint(1, 20)


# --------------------------------------------------------------------------- #
# 1) prometer — puramente verbal: memória nos dois lados + intenção só no
#    ator, zero física (spec 036: `item` saiu do escopo de `prometer`)
forbid_roll()
n_mem_tor0, n_mem_elga0 = len(memories(TOR)), len(memories(ELGA))
out1 = motor.apply_resolution(TOR, {"promise_ops": [
    {"para": ELGA, "expectativa": "que ela devolva na próxima vez que nos virmos"}]})
allow_roll()
applied1 = out1.get("promise_ops_applied") or []
check("prometer: uma op aplicada, com intention_id",
      len(applied1) == 1 and bool(applied1[0].get("intention_id")))
check("prometer: memória nova em quem prometeu (Torvin)",
      len(memories(TOR)) == n_mem_tor0 + 1)
check("prometer: memória nova em quem recebeu (Elga)",
      len(memories(ELGA)) == n_mem_elga0 + 1)
_, corpo_tor = memories(TOR)[-1]
_, corpo_elga = memories(ELGA)[-1]
check("prometer: conteúdo da memória do promitente carried_item_ids a expectativa",
      "devolva" in corpo_tor)
check("prometer: conteúdo da memória do alvo menciona o promitente",
      "Torvin" in corpo_elga or "prometeu" in corpo_elga.lower())
ativas_tor = motor.get_active_intentions(motor.find_character_folder(TOR))
iid1 = applied1[0]["intention_id"]
check("prometer: intenção ATIVA existe em quem prometeu",
      any(i["id"] == iid1 for i in ativas_tor))
check("prometer: NENHUMA intenção nasce no alvo (FR-008)",
      not motor.get_active_intentions(motor.find_character_folder(ELGA)))

# 2) segundo juramento — confirma que memória+intenção acumulam normalmente
n_mem_tor1, n_mem_elga1 = len(memories(TOR)), len(memories(ELGA))
out2 = motor.apply_resolution(TOR, {"promise_ops": [
    {"para": ELGA, "expectativa": "que eu não vou contar o que vi na forja"}]})
applied2 = out2.get("promise_ops_applied") or []
check("juramento: aplicado", len(applied2) == 1)
check("juramento: memória nova nos dois lados",
      len(memories(TOR)) == n_mem_tor1 + 1 and len(memories(ELGA)) == n_mem_elga1 + 1)
check("juramento: intenção nova (segunda) em quem prometeu",
      len(motor.get_active_intentions(motor.find_character_folder(TOR))) == 2)

# 3) prometer nunca rola dado — já garantido pelo forbid_roll() ativo em 1
#    (se tivesse rolado, o AssertionError já teria estourado o teste inteiro)
check("prometer: FR-004 (sem rolagem) — nenhum boom do forbid_roll() disparou",
      True)

# --------------------------------------------------------------------------- #
# 5) give com intention_id VÁLIDO e da própria pasta — fecha junto. `iid1`
#    pertence a TORVIN (nasceu do prometer dele em 1), então é ELE quem tem
#    que ser o ator aqui — só a própria pasta fecha a própria intenção.
dar(TOR, MOEDA2)
out5 = motor.apply_resolution(TOR, {"item_transfers": [
    {"item": MOEDA2, "to": ELGA, "intention_id": iid1}]})
check("give+intention_id válido: item mudou de mão", dono(MOEDA2) == ELGA)
applied5 = out5.get("item_transfers_applied") or []
check("give+intention_id válido: applied marca intention_closed=True",
      len(applied5) == 1 and applied5[0].get("intention_closed") is True)
fm_iid1, _ = motor.read_doc(
    motor.find_character_folder(TOR) / "intentions" / f"{iid1}.md")
check("give+intention_id válido: a intenção realmente fechou no disco",
      fm_iid1.get("status") == "concluida")
check("give+intention_id válido: NENHUMA rejeição — não é isso que sinaliza sucesso/falha",
      not out5.get("rejected"))

# 6) give com intention_id INVÁLIDO — transferência PERMANECE, só o fechamento falha
dar(TOR, MOEDA2)  # devolve pra Torvin poder tentar de novo
out6 = motor.apply_resolution(TOR, {"item_transfers": [
    {"item": MOEDA2, "to": ELGA, "intention_id": "int-nao-existe"}]})
check("give+intention_id inválido: a transferência acontece MESMO ASSIM",
      dono(MOEDA2) == ELGA)
applied6 = out6.get("item_transfers_applied") or []
check("give+intention_id inválido: applied marca intention_closed=False",
      len(applied6) == 1 and applied6[0].get("intention_closed") is False)
check("give+intention_id inválido: NUNCA vira `rejected` (FR-007) — "
      "senão _apply_op_now trataria a op inteira como negada",
      not out6.get("rejected"))

# 7) give SEM intention_id — comportamento idêntico ao de sempre (zero regressão)
dar(ELGA, MOEDA2)
out7 = motor.apply_resolution(ELGA, {"item_transfers": [{"item": MOEDA2, "to": TOR}]})
applied7 = out7.get("item_transfers_applied") or []
check("give sem intention_id: aplica normalmente", dono(MOEDA2) == TOR)
check("give sem intention_id: applied NÃO ganha a chave intention_closed",
      len(applied7) == 1 and "intention_closed" not in applied7[0])

# --------------------------------------------------------------------------- #
# 8) o CAMINHO VIVO do tool-calling — prometer no manifest + dispatch real +
#    o achado do _ACC_CH (promise_ops_applied E intentions_applied aparecem)
def _scripted_loop(script):
    def loop_fn(system, user, tools, execute, max_calls):
        calls = 0
        for name, args in script:
            calls += 1
            result, done = execute(name, args)
            if done or calls >= max_calls:
                return {"stopped": "narrate", "text": None, "calls": calls}
        return {"stopped": "limit", "text": None, "calls": calls}
    return loop_fn


ctx_tor = motor.get_context(TOR)
tools = arbiter.build_tools(ctx_tor)
tool_prometer = next((t for t in tools if t["name"] == "promise"), None)
check("manifest: 'prometer' está no manifest (há alvo presente)", tool_prometer is not None)
if tool_prometer:
    props = tool_prometer["parameters"]["properties"]
    check("manifest: prometer tem para/expectativa",
          {"para", "expectativa"} <= set(props))
    check("manifest: 'item' NÃO existe mais em prometer (spec 036 — item é "
          "exclusividade de give+emprestimo)",
          "item" not in props)
tool_give = next((t for t in tools if t["name"] == "give"), None)
check("manifest: 'give' ganhou intention_id opcional",
      tool_give is not None and "intention_id" in tool_give["parameters"]["properties"]
      and "intention_id" not in tool_give["parameters"]["required"])
check("manifest: 'give' ganhou 'emprestimo' opcional (spec 036)",
      tool_give is not None and "emprestimo" in tool_give["parameters"]["properties"]
      and "emprestimo" not in tool_give["parameters"]["required"])

intent_viva = {"action": "promete algo a Elga", "target": ELGA,
              "utterance": None, "movement": None, "note": ""}
out_viva = arbiter.resolve_with_tools(intent_viva, ctx_tor, _scripted_loop([
    ("promise", {"para": ELGA,
                  "expectativa": "que vou ajudar na forja amanhã"}),
    ("narrate", {"narrative_hint": "promete ajudar Elga"}),
]))
check("caminho vivo: outcome expõe 'promise_ops_applied' (o canal novo)",
      bool(out_viva.get("promise_ops_applied")))

intent_si = {"action": "reflete sobre um compromisso", "target": None,
            "utterance": None, "movement": None, "note": ""}
out_si = arbiter.resolve_with_tools(intent_si, motor.get_context(TOR),
                                    _scripted_loop([
    ("set_intention", {"content": "Vou visitar o ferreiro amanhã.",
                       "status": "ativa"}),
    ("narrate", {"narrative_hint": "decide visitar o ferreiro"}),
]))
check("achado do _ACC_CH: outcome de set_intention expõe 'intentions_applied' "
      "no caminho VIVO de tool-calling (antes desta spec, _ACC_CH não listava "
      "o canal e o outcome nunca carregava isto, mesmo com o arquivo escrito certo)",
      bool(out_si.get("intentions_applied")))

# --------------------------------------------------------------------------- #
# 9) US3 — dois canais decompostos e compostos: emprestar (give+emprestimo,
#    física — spec 036) É SEPARADO de prometer (verbal, cobrança — spec 027).
#    O credor percebe o pagamento e tem tudo para fechar sozinho, sem tool
#    nova: emprestar → prometer (verbal, sem item) → devolver SEM referenciar
#    nenhuma intenção (caminho comum, US2 cenário 2) → o credor vê, no
#    contexto seguinte, a intenção ainda ativa e a memória nova do pagamento
#    lado a lado.
dar(TOR, "moeda-de-prata-3")
out_emprestimo = motor.apply_resolution(TOR, {"item_transfers": [
    {"item": "moeda-de-prata-3", "to": ELGA, "emprestimo": True}]})
check("US3: emprestar (give+emprestimo) move a moeda fisicamente pra Elga",
      dono("moeda-de-prata-3") == ELGA)
check("US3: emprestar aplicado sem rejeição",
      bool(out_emprestimo.get("item_transfers_applied")) and not out_emprestimo.get("rejected"))
out_p = motor.apply_resolution(TOR, {"promise_ops": [
    {"para": ELGA,
     "expectativa": "que ela devolva a moeda na próxima vez que a encontrar"}]})
iid_cobranca = out_p["promise_ops_applied"][0]["intention_id"]
motor.apply_resolution(ELGA, {"item_transfers": [
    {"item": "moeda-de-prata-3", "to": TOR}]})
ctx_tor_depois = motor.get_context(TOR)
check("US3: Torvin ainda tem a intenção ativa de cobrar (ninguém a fechou por ele)",
      any(i["id"] == iid_cobranca for i in ctx_tor_depois.get("intentions") or []))
_, ultimo_corpo = memories(TOR)[-1]
check("US3: a memória mais recente de Torvin é a do pagamento recebido de Elga",
      "Elga" in ultimo_corpo and "prometi" not in ultimo_corpo.lower())
tools_tor_depois = arbiter.build_tools(ctx_tor_depois)
si_tool = next((t for t in tools_tor_depois if t["name"] == "set_intention"), None)
check("US3: 'set_intention' no manifest já oferece o id certo para fechar, "
      "sem nenhuma ferramenta nova desta spec ser chamada de novo",
      si_tool is not None
      and iid_cobranca in si_tool["parameters"]["properties"]["intention_id"]["enum"])

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 29 (Compromisso Lembrado, spec 027) OK.")
