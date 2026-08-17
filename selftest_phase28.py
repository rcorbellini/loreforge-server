"""Auto-teste da Fase 28 — Intenções Persistentes (spec 026, US1).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`),
molde das fases 25-27: a validação AUTORITATIVA mora no handler auto-contido
(`_h_intentions`), não no pré-check do Árbitro, então testar no nível do Motor
é o que prova a garantia de verdade (o fallback de texto chega aqui do mesmo
jeito que o tool-calling). Cobre:

  - criar (sem intention_id) → arquivo novo, status ativa, aparece no contexto
  - atualizar (intention_id existente) → reescreve NO LUGAR (mesmo arquivo)
  - intention_id inexistente/de outro personagem → rejeição estruturada
  - content vazio / status inválido → rejeição estruturada
  - encerrar (concluida/abandonada) → some do contexto, mas o arquivo persiste
  - não reabre encerrada (intention_id de uma já concluída é rejeitado)
  - teto de exposição no contexto (as mais RECENTES ficam)
  - o manifest do Árbitro expõe `set_intention` com o enum de intenções ativas
  - FR-015: "origem" (manual/autônoma) é garantia ESTRUTURAL de observabilidade —
    `resolve_action` não tem (nem pode ganhar por acidente) esse parâmetro

Uso:  python3 server/selftest_phase28.py
"""

from __future__ import annotations

import inspect
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
import app as server_app  # noqa: E402

FAILS = []
TAVERNA = _tmp / "world" / "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str):
    d = TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: Sujeito de Teste\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: leve\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm sujeito de teste.\n", encoding="utf-8")


def _intentions_dir(char_id):
    return motor.find_character_folder(char_id) / "intentions"


def _files(char_id):
    d = _intentions_dir(char_id)
    return sorted(d.glob("*.md")) if d.exists() else []


# ---------------------------------------------------------------------------- #
# 1) criar — sem intention_id
out1 = motor.apply_resolution(TOR, {"intentions": [
    {"content": "Prometi a João que traria tomates da fazenda.", "status": "ativa"}]})
applied1 = out1.get("intentions_applied") or []
check("criar: uma op aplicada, com intention_id novo",
      len(applied1) == 1 and bool(applied1[0].get("intention_id")))
iid = applied1[0]["intention_id"] if applied1 else None
check("criar: exatamente um arquivo em intentions/", len(_files(TOR)) == 1)
if iid:
    fm, body = motor.read_doc(_intentions_dir(TOR) / f"{iid}.md")
    check("criar: frontmatter com type/status/timestamps corretos",
          fm.get("type") == "intention" and fm.get("status") == "ativa"
          and isinstance(fm.get("created_ts"), int) and isinstance(fm.get("updated_ts"), int))
    check("criar: corpo é o content em prosa",
          body.strip() == "Prometi a João que traria tomates da fazenda.")

# 2) aparece no contexto (get_active_intentions e get_context)
ativas = motor.get_active_intentions(motor.find_character_folder(TOR))
check("contexto: get_active_intentions lista a intenção ativa",
      any(i["id"] == iid for i in ativas))
ctx = motor.get_context(TOR)
check("contexto: get_context()['intentions'] traz {id, status, content}",
      any(i["id"] == iid and i["status"] == "ativa"
          and "tomates" in i["content"] for i in ctx.get("intentions") or []))

# 3) atualizar — intention_id existente reescreve NO LUGAR
out2 = motor.apply_resolution(TOR, {"intentions": [
    {"intention_id": iid, "content": "Já encontrei a plantação; agora vou colher.",
     "status": "ativa"}]})
check("atualizar: aplicado, mesmo intention_id",
      (out2.get("intentions_applied") or [{}])[0].get("intention_id") == iid)
check("atualizar: continua exatamente UM arquivo (reescreveu, não duplicou)",
      len(_files(TOR)) == 1)
fm2, body2 = motor.read_doc(_intentions_dir(TOR) / f"{iid}.md")
check("atualizar: corpo foi reescrito por inteiro", "colher" in body2 and "prometi" not in body2.lower())
check("atualizar: updated_ts >= created_ts", fm2["updated_ts"] >= fm2["created_ts"])

# 4) rejeições estruturadas
out3 = motor.apply_resolution(TOR, {"intentions": [
    {"intention_id": "int-nao-existe", "content": "x", "status": "ativa"}]})
check("rejeita: intention_id inexistente", bool(out3.get("rejected")))

out4 = motor.apply_resolution(TOR, {"intentions": [{"content": "", "status": "ativa"}]})
check("rejeita: content vazio", bool(out4.get("rejected")))

out5 = motor.apply_resolution(TOR, {"intentions": [
    {"content": "algo", "status": "concluida_com_erro_de_digitacao"}]})
check("rejeita: status fora do enum", bool(out5.get("rejected")))
check("rejeições não criam arquivo novo (segue 1 arquivo)", len(_files(TOR)) == 1)

# 5) encerrar — muda status, some do contexto, arquivo persiste
out6 = motor.apply_resolution(TOR, {"intentions": [
    {"intention_id": iid, "content": body2, "status": "concluida"}]})
check("encerrar: aplicado", bool(out6.get("intentions_applied")))
ativas2 = motor.get_active_intentions(motor.find_character_folder(TOR))
check("encerrar: some da lista de ATIVAS", not any(i["id"] == iid for i in ativas2))
check("encerrar: o ARQUIVO continua no disco (Princípio IV)", len(_files(TOR)) == 1)
fm3, _ = motor.read_doc(_intentions_dir(TOR) / f"{iid}.md")
check("encerrar: status gravado como concluida", fm3.get("status") == "concluida")

# 6) não reabre encerrada
out7 = motor.apply_resolution(TOR, {"intentions": [
    {"intention_id": iid, "content": "tentando reabrir", "status": "ativa"}]})
check("não reabre: update numa intenção concluída é rejeitado", bool(out7.get("rejected")))
fm4, _ = motor.read_doc(_intentions_dir(TOR) / f"{iid}.md")
check("não reabre: status permanece concluida (não voltou a ativa)",
      fm4.get("status") == "concluida")

# 7) isolamento entre personagens — id de OUTRO personagem não é achável aqui
_mk_char(ELGA)
out_elga = motor.apply_resolution(ELGA, {"intentions": [
    {"content": "Quero que a taverna prospere.", "status": "ativa"}]})
iid_elga = (out_elga.get("intentions_applied") or [{}])[0].get("intention_id")
out8 = motor.apply_resolution(TOR, {"intentions": [
    {"intention_id": iid_elga, "content": "x", "status": "ativa"}]})
check("isolamento: Torvin não atualiza intenção de Elga pelo id dela",
      bool(out8.get("rejected")))

# 8) teto de exposição — as mais RECENTES ficam
_mk_char("cheio-p28")
cap = motor._INTENTION_CONTEXT_CAP
for i in range(cap + 3):
    motor.apply_resolution("cheio-p28", {"intentions": [
        {"content": f"Intenção número {i}.", "status": "ativa"}]})
listadas = motor.get_active_intentions(motor.find_character_folder("cheio-p28"))
check(f"teto: contexto nunca excede o cap ({cap})", len(listadas) == cap)
check("teto: a intenção MAIS RECENTE (a última criada) está na lista",
      any(f"número {cap + 2}" in i["content"] for i in listadas))
check("teto: a MAIS ANTIGA (a primeira) foi excluída do contexto",
      not any("número 0." in i["content"] for i in listadas))
check("teto: nenhum arquivo foi apagado (todas continuam no disco)",
      len(_files("cheio-p28")) == cap + 3)

# 9) o manifest do Árbitro expõe a tool, com enum das intenções ATIVAS do ator
ctx_tor = motor.get_context(TOR)
tools = arbiter.build_tools(ctx_tor)
tool = next((t for t in tools if t["name"] == "set_intention"), None)
check("manifest: 'set_intention' está no manifest do Árbitro", tool is not None)
if tool:
    enum_ids = tool["parameters"]["properties"]["intention_id"]["enum"]
    check("manifest: enum de intention_id reflete as intenções ATIVAS do ator (sem a encerrada)",
          iid not in enum_ids)
    check("manifest: 'target' NÃO é parâmetro (Decisão 3 — só o próprio ator nesta spec)",
          "target" not in tool["parameters"]["properties"])


# 10) o CAMINHO VIVO do tool-calling — não só motor.apply_resolution direto.
# resolve_with_tools enfileira via execute() e aplica pelo MESMO _apply_queued_
# delta que mutations/attack_ops/etc. já usam — prova que a fiação de T010-T012
# (queue/_MUT_CH/build_tools/execute) funciona de ponta a ponta, não só o
# handler isolado (que a seção 1-8 já provou via motor.apply_resolution).
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


_mk_char("viva-p28")
ctx_viva = motor.get_context("viva-p28")
intent_viva = {"action": "reflete sobre um compromisso", "target": None,
              "utterance": None, "movement": None, "note": ""}
out_viva = arbiter.resolve_with_tools(intent_viva, ctx_viva, _scripted_loop([
    ("set_intention", {"content": "Vou ajudar a taverneira a encontrar o gato.",
                       "status": "ativa"}),
    ("narrate", {"narrative_hint": "resolve ajudar com o gato sumido"}),
]))
check("caminho vivo: o loop de tools aplicou a intenção (via execute→queue→"
      "_apply_queued_delta, não motor.apply_resolution direto)",
      len(_files("viva-p28")) == 1)
if _files("viva-p28"):
    fm_viva, body_viva = motor.read_doc(_files("viva-p28")[0])
    check("caminho vivo: conteúdo e status corretos", fm_viva.get("status") == "ativa"
          and "gato" in body_viva)
check("caminho vivo: nenhuma linha nova em app.inworld_effects (precedente "
      "create_memory — o relato mora no narrative_hint do turno, research.md D6)",
      not any("gato" in s.lower() for s in server_app.inworld_effects(out_viva)))

# 11) FR-015: "origem" é garantia ESTRUTURAL — resolve_action tem assinatura
# nomeada, sem **payload; acrescentar "origem" ali exigiria edição deliberada e
# visível no diff, nunca um repasse acidental do payload de /api/act.
_params = set(inspect.signature(server_app.resolve_action).parameters)
check("FR-015: 'origem' NÃO é (nem pode virar sem querer) parâmetro de resolve_action",
      "origem" not in _params, f"parâmetros={sorted(_params)}")

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 28 (Intenções Persistentes) OK.")
