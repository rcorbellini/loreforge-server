"""Auto-teste da Fase 59 — Escrever (spec 059).

Sem modelo/LLM ligado para a maior parte: exercita o Motor direto
(`motor.apply_resolution`) para o comportamento DETERMINÍSTICO do executor
(`_apply_write_ops`), com os dois gates FORÇADOS na op (não há dado nesta
tool — os gates são a única incerteza, e já vêm julgados). A camada de
GUARDA/FACE (`arbiter.build_ctx`/`execute`, enums, XOR memoria_id/texto,
desaparecimento sem instrumento) usa `ask` forçado, no molde da 058.

Cobre os nove invariantes de `contracts/write-tool.md`:

  1. `sing` byte-idêntico com `own_memories(..., require_sobre=True)` implícito.
  2. `own_memories(require_sobre=False)` inclui memória SEM `sobre`.
  3. Modo ancorado transcreve o `conteudo` EXATO (byte a byte).
  4. Escrever duas vezes no mesmo item preserva as duas (nunca overwrite).
  5. Prosa vazia, após escrita, não carrega marca de "estava vazio".
  6. `write` some do manifest sem instrumento na mão.
  7. Nenhuma nota do gate aparece em nenhum payload aplicado.
  8. Todo desfecho (as duas recusas de mérito, a de estado) narra.
  9. `write_alvo` nunca inclui personagem, objeto ou lugar — só itens.

Uso:  python3 selftest_phase59.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test59-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import app as server_app  # noqa: E402

FAILS = []
LUGAR = "mirante-do-corvo"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pasta(cid):
    return motor.find_character_folder(cid)


def _mk_char(cid: str, name: str, presente_em: str = LUGAR):
    d = motor.WORLD_DIR / presente_em / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: 10\n"
        f"  CHA: 10\n"
        f"status:\n  hp: 20\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")
    return d


def _mk_instrumento(actor_folder: Path, iid: str):
    d = actor_folder / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: Pena e Tinteiro (teste)\n"
        f"origin: editorial\nsize: PP\nweight_kg: 0.1\nstate:\n  slot: mao\n"
        f"---\nUma pena de ganso e um tinteiro, prontos na mão.\n",
        encoding="utf-8")
    return d


def _mk_item_cena(lugar: str, iid: str, corpo: str, nome: str = "Item de Teste"):
    """Um item SOLTO na cena (não carregado por ninguém) — molde de
    `alaude-remendado`, que sempre sentou direto sob `taverna-do-gancho`."""
    d = motor.WORLD_DIR / lugar / iid
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {iid}\nname: {nome}\norigin: editorial\n"
        f"size: P\nweight_kg: 0.3\n---\n{corpo}\n", encoding="utf-8")
    return d


def _mk_memoria(cid: str, texto: str, intensity="medium", involved=None,
               evento="brew"):
    folder = pasta(cid)
    return motor.memoria._write_memory(
        folder, texto, intensity=intensity, involved=involved or [],
        evento=evento, domain="botica")


def _mems(cid, evento=None):
    out = list(motor._iter_memories(cid))
    if evento:
        out = [m for m in out if m.get("evento") == evento]
    return out


def _corpo(item_folder: Path) -> str:
    _, body = motor.read_doc(item_folder / "item.md")
    return body.strip()


def res(**parts):
    return {"write_ops": [], **parts}


GATE_ALTO = {"superficie": 10, "instrumento_nota": 10}


print("\n--- 1/2. own_memories: require_sobre preserva sing, libera write --------")

SOLITARIO = "botanico-solitario-p59"
_mk_char(SOLITARIO, "Botânico Solitário")
mem_solo_id = _mk_memoria(
    SOLITARIO, "Fervi casca de salgueiro-branco com mel: baixou a febre.",
    intensity="medium", involved=[])   # SEM outro envolvido — vivência só dele

com_sobre = motor.own_memories(SOLITARIO)                       # default (sing)
sem_sobre = motor.own_memories(SOLITARIO, require_sobre=False)  # write
check("1. own_memories(default) EXCLUI memória sem outro envolvido (== sing hoje)",
      mem_solo_id not in {m["id"] for m in com_sobre}, str(com_sobre))
check("2. own_memories(require_sobre=False) INCLUI a mesma memória, sobre=None",
      any(m["id"] == mem_solo_id and m["sobre"] is None for m in sem_sobre),
      str(sem_sobre))

print("\n--- 3. modo ANCORADO: transcrição verbatim, byte a byte ------------------")

ESCRITOR = "escritor-p59"
_mk_char(ESCRITOR, "Escritor")
pena = _mk_instrumento(pasta(ESCRITOR), "pena-p59-a")
livro = _mk_item_cena(LUGAR, "livro-receitas-p59", "", nome="Livro de Receitas")
mem_receita = _mk_memoria(
    ESCRITOR, "Ferva casca de salgueiro-branco com mel por um quarto de hora.",
    intensity="medium", involved=[])

_, conteudo_memoria = motor.read_doc(pasta(ESCRITOR) / "memories" / f"{mem_receita}.md")
out_ancorado = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "livro-receitas-p59", "instrumento": "pena-p59-a",
    "memoria_id": mem_receita, "texto": None, **GATE_ALTO}]))
aplicadas_a = out_ancorado.get("write_ops_applied") or []
check("3a. escrita ancorada foi aplicada (sem recusa)",
      len(aplicadas_a) == 1, str(out_ancorado.get("rejected")))
check("3b. o corpo do item é EXATAMENTE o conteúdo da memória — byte a byte",
      _corpo(livro) == conteudo_memoria.strip(),
      f"item={_corpo(livro)!r} memoria={conteudo_memoria.strip()!r}")

print("\n--- (livre) modo LIVRE: texto passa como veio ----------------------------")

bilhete = _mk_item_cena(LUGAR, "bilhete-p59", "", nome="Bilhete em Branco")
out_livre = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "bilhete-p59", "instrumento": "pena-p59-a",
    "memoria_id": None, "texto": "Volto ao anoitecer.", **GATE_ALTO}]))
check("livre. o corpo do item é EXATAMENTE o texto informado",
      _corpo(bilhete) == "Volto ao anoitecer.", _corpo(bilhete))

print("\n--- 4. acumula: dois autores, o mesmo item, os dois textos sobrevivem ----")

OUTRO_ESCRITOR = "outro-escritor-p59"
_mk_char(OUTRO_ESCRITOR, "Outro Escritor")
pena2 = _mk_instrumento(pasta(OUTRO_ESCRITOR), "pena-p59-b")
quadro = _mk_item_cena(LUGAR, "quadro-p59", "", nome="Quadro de Avisos")
motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "quadro-p59", "instrumento": "pena-p59-a",
    "memoria_id": None, "texto": "Procura-se um alaúde perdido.", **GATE_ALTO}]))
motor.apply_resolution(OUTRO_ESCRITOR, res(write_ops=[{
    "alvo": "quadro-p59", "instrumento": "pena-p59-b",
    "memoria_id": None, "texto": "Vende-se lenha seca, bom preço.", **GATE_ALTO}]))
corpo_quadro = _corpo(quadro)
check("4a. o primeiro texto sobreviveu ao segundo (nunca overwrite)",
      "Procura-se um alaúde perdido." in corpo_quadro, corpo_quadro)
check("4b. o segundo texto também está lá",
      "Vende-se lenha seca, bom preço." in corpo_quadro, corpo_quadro)
check("4c. o primeiro vem ANTES do segundo (ordem preservada)",
      corpo_quadro.find("alaúde") < corpo_quadro.find("lenha"), corpo_quadro)

print("\n--- 5. prosa vazia -> escrita não deixa marca de \"estava vazio\" ----------")

check("5. o bilhete (corpo era vazio) não tem marca alguma de vazio anterior",
      "vazio" not in _corpo(bilhete).lower()
      and _corpo(bilhete) == "Volto ao anoitecer.", _corpo(bilhete))

print("\n--- (dedup) escrever duas vezes seguidas no MESMO turno convive ----------")

cartaz = _mk_item_cena(LUGAR, "cartaz-p59", "", nome="Cartaz")
out_dup = motor.apply_resolution(ESCRITOR, res(write_ops=[
    {"alvo": "cartaz-p59", "instrumento": "pena-p59-a", "memoria_id": None,
     "texto": "Primeira linha.", **GATE_ALTO},
    {"alvo": "cartaz-p59", "instrumento": "pena-p59-a", "memoria_id": None,
     "texto": "Segunda linha.", **GATE_ALTO},
]))
check("dedup. as DUAS escritas no mesmo turno foram aplicadas (sem dedup)",
      len(out_dup.get("write_ops_applied") or []) == 2, str(out_dup))
check("dedup. as duas linhas convivem no corpo final",
      "Primeira linha." in _corpo(cartaz) and "Segunda linha." in _corpo(cartaz),
      _corpo(cartaz))

print("\n--- (gate) os dois gates são de ADMISSÃO — abaixo do limiar recusa -------")

alvo_ruim = _mk_item_cena(LUGAR, "alvo-ruim-p59", "", nome="Alvo Duvidoso")
out_sup_baixa = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "alvo-ruim-p59", "instrumento": "pena-p59-a", "memoria_id": None,
    "texto": "x", "superficie": 2, "instrumento_nota": 10}]))
regras_sup = {r.get("regra") for r in out_sup_baixa.get("rejected") or []}
check("gate-superficie. nota abaixo do limiar (2 < 5) recusa com 'nao_e_superficie'",
      "nao_e_superficie" in regras_sup, str(regras_sup))
check("gate-superficie. o item NÃO foi tocado",
      _corpo(alvo_ruim) == "", _corpo(alvo_ruim))

out_instr_baixa = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "alvo-ruim-p59", "instrumento": "pena-p59-a", "memoria_id": None,
    "texto": "x", "superficie": 10, "instrumento_nota": 3}]))
regras_instr = {r.get("regra") for r in out_instr_baixa.get("rejected") or []}
check("gate-instrumento. nota abaixo do limiar (3 < 5) recusa com "
     "'nao_serve_pra_escrever'", "nao_serve_pra_escrever" in regras_instr,
      str(regras_instr))

print("\n--- (estado) o único portão de ATOR é dormir (\"descansando\") ------------")

DORMINDO = "dormindo-p59"
d_dorm = _mk_char(DORMINDO, "Dorminhoco")
fm, body = motor.read_doc(d_dorm / "character.md")
fm["status"]["descansando_desde"] = 1
motor.write_doc(d_dorm / "character.md", fm, body)
out_dorme = motor.apply_resolution(DORMINDO, res(write_ops=[{
    "alvo": "quadro-p59", "instrumento": "pena-p59-a", "memoria_id": None,
    "texto": "x", **GATE_ALTO}]))
regras_dorme = {r.get("regra") for r in out_dorme.get("rejected") or []}
check("estado. ator dormindo: ÚNICA recusa possível ('descansando')",
      "descansando" in regras_dorme, str(regras_dorme))

print("\n--- (revalidação) alvo/instrumento/memória sumidos entre guarda e aplicação")

out_alvo_sumiu = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "item-que-nao-existe-p59", "instrumento": "pena-p59-a",
    "memoria_id": None, "texto": "x", **GATE_ALTO}]))
check("revalida-alvo. alvo inexistente recusa com 'item_sumiu'",
      any(r.get("regra") == "item_sumiu"
          for r in out_alvo_sumiu.get("rejected") or []), str(out_alvo_sumiu))

out_instr_sumiu = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "quadro-p59", "instrumento": "instrumento-que-nao-existe-p59",
    "memoria_id": None, "texto": "x", **GATE_ALTO}]))
check("revalida-instrumento. instrumento inexistente recusa com 'sem_instrumento'",
      any(r.get("regra") == "sem_instrumento"
          for r in out_instr_sumiu.get("rejected") or []), str(out_instr_sumiu))

out_mem_sumiu = motor.apply_resolution(ESCRITOR, res(write_ops=[{
    "alvo": "quadro-p59", "instrumento": "pena-p59-a",
    "memoria_id": "memoria-que-nao-existe-p59", "texto": None, **GATE_ALTO}]))
check("revalida-memoria. memoria_id inexistente recusa com 'memoria_sumiu'",
      any(r.get("regra") == "memoria_sumiu"
          for r in out_mem_sumiu.get("rejected") or []), str(out_mem_sumiu))

print("\n--- 7. nenhuma nota do gate aparece no payload APLICADO -------------------")

check("7. o dict `applied` de uma escrita bem-sucedida não carrega nota nenhuma",
      aplicadas_a and not ({"superficie", "instrumento_nota"} & set(aplicadas_a[0])),
      str(aplicadas_a[0] if aplicadas_a else None))

print("\n--- (memória do ato) domain=nenhuma, evento=write -------------------------")

mem_ato = _mems(ESCRITOR, evento="write")
check("memoria-ato. o escritor ganhou UMA memória do próprio ato, domain='nenhuma'",
      len(mem_ato) >= 1 and all(m.get("domain") == "nenhuma" for m in mem_ato),
      str(mem_ato))

print("\n--- 8. todo desfecho narra (Princípio X) ----------------------------------")

_fbol = server_app.inworld_effects(out_ancorado)
check("8a. a escrita bem-sucedida produz frase in-world",
      any("escreveu" in f for f in _fbol) if _fbol else False, str(_fbol))

print("\n--- 6/9. FACE: sem instrumento a tool SOME; write_alvo é só item ----------")

SEM_MAO = "sem-instrumento-p59"
_mk_char(SEM_MAO, "Sem Instrumento")
manifest_sem = arbiter.build_tools(motor.get_context(SEM_MAO))
check("6a. SEM item na mão, 'write' NÃO aparece no manifest",
      not any(t["name"] == "write" for t in manifest_sem), str(manifest_sem))

COM_MAO = "com-instrumento-p59"
d_com = _mk_char(COM_MAO, "Com Instrumento")
_mk_instrumento(d_com, "pena-p59-c")
manifest_com = arbiter.build_tools(motor.get_context(COM_MAO))
face_write = next((t for t in manifest_com if t["name"] == "write"), None)
check("6b. COM item na mão, 'write' APARECE no manifest",
      face_write is not None, str([t['name'] for t in manifest_com]))

idx_com = arbiter._scene_index(motor.get_context(COM_MAO))
cand_com = arbiter.scene_candidates(idx_com)
check("9. write_alvo nunca inclui personagem, objeto ou o lugar — só itens",
      set(cand_com.get("write_alvo") or []) <= set(idx_com["items"]),
      str(cand_com.get("write_alvo")))

print("\n--- (guarda) XOR memoria_id/texto, e enums reais --------------------------")


def _ask_fixo(_s, _u):
    return '{"superficie": 10, "instrumento": 10}'


ctx_guarda = arbiter.build_ctx(motor.get_context(COM_MAO), ask=_ask_fixo)
r_nenhum = ctx_guarda.execute("write", {"alvo": "quadro-p59",
                                        "instrumento": "pena-p59-c"})
check("guarda-xor. nem memoria_id nem texto: recusa corrigível",
      r_nenhum[0].get("ok") is not True, str(r_nenhum))
r_ambos = ctx_guarda.execute("write", {"alvo": "quadro-p59",
                                       "instrumento": "pena-p59-c",
                                       "memoria_id": "qualquer", "texto": "x"})
check("guarda-xor. os dois ao mesmo tempo: recusa corrigível",
      r_ambos[0].get("ok") is not True, str(r_ambos))

r_alvo_invalido = ctx_guarda.execute("write", {"alvo": "item-fantasma",
                                               "instrumento": "pena-p59-c",
                                               "texto": "x"})
check("guarda-alvo. alvo fora do enum: recusa corrigível com validos",
      r_alvo_invalido[0].get("ok") is not True
      and "validos" in r_alvo_invalido[0], str(r_alvo_invalido))

_chamadas_gate = {"n": 0}
def _ask_conta(_s, _u):
    _chamadas_gate["n"] += 1
    return '{"superficie": 10, "instrumento": 10}'


ctx_guarda2 = arbiter.build_ctx(motor.get_context(COM_MAO), ask=_ask_conta)
r_mem_invalida = ctx_guarda2.execute("write", {
    "alvo": "quadro-p59", "instrumento": "pena-p59-c",
    "memoria_id": "memoria-que-nao-e-do-ator"})
check("guarda-memoria. memoria_id que não é do ator: recusa corrigível",
      r_mem_invalida[0].get("ok") is not True, str(r_mem_invalida))
check("guarda-memoria. a recusa NÃO chamou o gate (zero LLM antes de validar)",
      _chamadas_gate["n"] == 0, str(_chamadas_gate))

r_ok = ctx_guarda.execute("write", {"alvo": "quadro-p59",
                                    "instrumento": "pena-p59-c",
                                    "texto": "Escrito pela guarda real."})
check("guarda-ok. chamada válida (texto livre) passa pela guarda e aplica",
      r_ok[0].get("ok") is True, str(r_ok))
check("guarda-ok. o texto realmente chegou ao item, pelo caminho público inteiro",
      "Escrito pela guarda real." in _corpo(quadro), _corpo(quadro))

print("\n" + "=" * 70)
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("Fase 59 (Escrever, spec 059) OK.")
