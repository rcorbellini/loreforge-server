"""Auto-teste da Fase 32 — Fadiga como recurso + réguas moduladas (spec 030,
US1+US2).

Sem nenhum modelo/LLM — exercita o Motor direto (`motor.apply_resolution`).
Cobre:

  - `fatigue_max` deriva de CON (fisica.default_hp_max) quando não declarado
  - cada executor com esforço físico chama `fisica.spend_fatigue` na
    categoria certa (attack=alto, steal=medio, travel=alto)
  - a exceção central: `persuade_ops`/`persuade_give_ops` cobram do ALVO
    (quem fisicamente viaja/entrega), NUNCA de quem persuadiu
  - `dormir` recupera fadiga por completo numa noite inteira (`_dormir_
    noite_inteira`, simulando >= 8h reais — spec 031 tornou `dormir` um
    alternador iniciar/acordar; esta fase testa só o caso "noite cheia",
    o caso de duração parcial mora em `selftest_phase33.py`); fadiga
    nunca ultrapassa o teto
  - as três rolagens moduladas (aprender, percepção de testemunha,
    resistência à persuasão) pioram com fadiga alta; persuasão SEM custo
    de fadiga associado (roll_disposicao) nunca é modulada (FR-009)

ORDEM IMPORTA: `persuade_ops`/`travel_ops` bem-sucedidos MOVEM o
personagem pra fora da cena (a viagem é física, imediata) — por isso os
dois ficam por ÚLTIMO entre os testes que precisam de Torvin e Elga juntos
na taverna.

Uso:  python3 server/selftest_phase32.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"
TOR, ELGA = "torvin-ferreiro", "elga-taverneira"
MOEDA1 = "moeda-de-prata-1"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def fadiga_de(cid: str) -> tuple[int, int]:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return motor.ensure_fatigue(fm)


def ifolder(item_id) -> Path:
    return motor.find_entity(item_id)[0].parent


def dar(cid: str, item_id: str):
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm["state"] = {**(fm.get("state") or {}), "slot": motor.HAND_SLOT}
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.find_character_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def _mk_char(cid: str, name: str, wis: int = 10):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: 10\n  CON: 10\n  INT: 10\n  WIS: {wis}\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: baixo\n"
        f"  action: parado\n  mood: neutro\n  conditions: []\n"
        f"origin: editorial\n---\nUm presente qualquer.\n", encoding="utf-8")


def _memories(cid: str):
    d = motor.find_character_folder(cid) / "memories"
    if not d.exists():
        return []
    return [motor.read_doc(p) for p in sorted(d.glob("*.md"))]


def _com_fadiga_no_arquivo(cid: str, fadiga: int):
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    teto = motor.fatigue_max(fm)
    fm["status"] = {**(fm.get("status") or {}), "fatigue": fadiga, "fatigue_max": teto}
    motor.write_doc(folder / "character.md", fm, body)


def _seq_mock(primeiro, resto):
    fila = [primeiro]
    def _mock():
        return fila.pop(0) if fila else resto
    return _mock


def _descansando_desde_p32(cid: str):
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return (fm.get("status") or {}).get("descansando_desde")


def _backdate_p32(cid: str, segundos_atras: float):
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status["descansando_desde"] = time.time() - segundos_atras
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)


def _dormir_noite_inteira(cid: str):
    """spec 031: `dormir` virou alternador (iniciar/acordar) — os testes
    desta fase (herdados da spec 030) assumiam reset pleno numa chamada
    só. Este helper simula uma noite INTEIRA (>= 8h reais, sem esperar de
    verdade) pra preservar a intenção original de cada asserção: iniciar,
    "adiantar o relógio" backdatando o timestamp gravado, acordar."""
    motor.apply_resolution(cid, {"rest_ops": [{"op": "sleep"}]})
    folder = motor.find_character_folder(cid)
    fm, body = motor.read_doc(folder / "character.md")
    status = dict(fm.get("status") or {})
    status["descansando_desde"] = time.time() - (8 * 3600 + 60)
    fm["status"] = status
    motor.write_doc(folder / "character.md", fm, body)
    motor.apply_resolution(cid, {"rest_ops": [{"op": "wake_up"}]})


def _fm_com_fadiga(base_fm: dict, fadiga: int) -> dict:
    fm = dict(base_fm)
    fm["status"] = {**(base_fm.get("status") or {}), "fatigue": fadiga,
                    "fatigue_max": motor.fatigue_max(base_fm)}
    return fm


# =========================================================================== #
# US1 — fadiga como recurso (Frente A)
# =========================================================================== #

# 1) fatigue_max deriva de CON — Torvin (CON 14, mod +2) => 100+10*2 = 120
tor_fm, _ = motor.read_doc(motor.find_character_folder(TOR) / "character.md")
check("fatigue_max deriva de CON (Torvin, CON 14 -> 120)",
      motor.fatigue_max(tor_fm) == 120, str(motor.fatigue_max(tor_fm)))

fadiga0, teto0 = fadiga_de(TOR)
check("fadiga inicial é 0 (personagem nunca tocado)", fadiga0 == 0)

# 2) attack_ops custa 'alto' (0.08 * 120 = 9.6 -> 10)
force_hit = motor._roll_d20
motor._roll_d20 = lambda: 20  # garante acerto
motor.apply_resolution(TOR, {"attack_ops": [{"alvo": ELGA, "vantagem": 5}]})
motor._roll_d20 = force_hit
fadiga1, _ = fadiga_de(TOR)
check("attack_ops custa fadiga 'alto' (~10) no ATACANTE",
      fadiga1 == 10, f"obtido: {fadiga1}")

# 3) steal_ops custa 'medio' (0.05 * 120 = 6)
dar(ELGA, MOEDA1)
force_roll = motor._roll_d20
motor._roll_d20 = lambda: 8  # furto flagrado+levou: DEX -1, dc=10, 8-1=7, falha por 3
motor.apply_resolution(TOR, {"steal_ops": [{"alvo": ELGA, "item": MOEDA1, "exposicao": 5}]})
motor._roll_d20 = force_roll
fadiga2, _ = fadiga_de(TOR)
check("steal_ops soma fadiga 'medio' (~6) no LADRÃO",
      fadiga2 == fadiga1 + 6, f"obtido: {fadiga2}, esperado {fadiga1 + 6}")

# 4) dormir (uma noite inteira, spec 031) recupera fadiga por completo
check("fadiga de Torvin > 0 antes de dormir (precondição)", fadiga2 > 0)
_dormir_noite_inteira(TOR)
fadiga_depois_dormir, _ = fadiga_de(TOR)
check("dormir (noite inteira) zera a fadiga", fadiga_depois_dormir == 0, str(fadiga_depois_dormir))

# 5) fadiga nunca ultrapassa fatigue_max (clamp) — várias ações seguidas
for _ in range(20):
    force = motor._roll_d20
    motor._roll_d20 = lambda: 20
    motor.apply_resolution(TOR, {"attack_ops": [{"alvo": ELGA, "vantagem": 5}]})
    motor._roll_d20 = force
fadiga_max_atingida, teto_tor = fadiga_de(TOR)
check("fadiga nunca ultrapassa fatigue_max (clamp)",
      fadiga_max_atingida == teto_tor, f"{fadiga_max_atingida} vs teto {teto_tor}")
_dormir_noite_inteira(TOR)  # zera antes dos próximos testes (noite inteira, spec 031)

# =========================================================================== #
# US2 (parte 1) — percepção de testemunha modulada por fadiga. AINDA com
# Torvin e Elga juntos na taverna — precisa ser ANTES de persuade/travel,
# que os movem pra fora.
# =========================================================================== #

# Sequência de dado: a PRIMEIRA chamada (o roll do FURTO em si) recebe 8 —
# Torvin (DEX 8, mod -1), exposicao=5 (dc=10): 8-1=7, falha por 3 (<=5) =>
# flagrado_levou. Chamadas SEGUINTES (percepção de CADA testemunha) recebem
# 10. Testemunha WIS 10 (mod 0), exposicao=5 => dc_percepcao=10:
# descansada (penalidade 0): 10+0-0=10 >= 10, PERCEBE.
# exausta (penalidade 4, 100% do teto): 10+0-4=6 < 10, NÃO PERCEBE.
_mk_char("testemunha-descansada-p32", "Testemunha Descansada")
_com_fadiga_no_arquivo("testemunha-descansada-p32", 0)
dar(ELGA, "moeda-de-prata-2")
motor._roll_d20 = _seq_mock(8, 10)
motor.apply_resolution(TOR, {"steal_ops": [
    {"alvo": ELGA, "item": "moeda-de-prata-2", "exposicao": 5}]})
motor._roll_d20 = force
check("testemunha DESCANSADA percebe o furto furtivo",
      any(fm.get("evento") == "witness_theft"
          for fm, _ in _memories("testemunha-descansada-p32")))

_mk_char("testemunha-exausta-p32", "Testemunha Exausta")
_com_fadiga_no_arquivo("testemunha-exausta-p32",
                       motor.fatigue_max({"attributes": {"CON": 10}}))
dar(ELGA, "moeda-de-prata-3")
motor._roll_d20 = _seq_mock(8, 10)
motor.apply_resolution(TOR, {"steal_ops": [
    {"alvo": ELGA, "item": "moeda-de-prata-3", "exposicao": 5}]})
motor._roll_d20 = force
check("testemunha EXAUSTA NÃO percebe o MESMO furto (fadiga desconta de WIS)",
      not any(fm.get("evento") == "witness_theft"
              for fm, _ in _memories("testemunha-exausta-p32")))

# =========================================================================== #
# US1 (continuação) — persuade_ops/travel_ops, por ÚLTIMO entre os testes
# "os dois presentes": sucesso MOVE o alvo/ator pra fora da taverna.
# =========================================================================== #

# 6) persuade_ops — a EXCEÇÃO central: quem gasta é o ALVO, não o persuasor.
elga_fm, _ = motor.read_doc(motor.find_character_folder(ELGA) / "character.md")
custo_elga = round(0.08 * motor.fatigue_max(elga_fm))  # CON 13 -> mod 1 -> teto 110
motor.memoria._remember_route(
    motor.find_character_folder(ELGA), "portao-lateral", "Portão Lateral")
fadiga_persuasor_antes, _ = fadiga_de(TOR)
fadiga_alvo_antes, _ = fadiga_de(ELGA)
force_persuade = motor._roll_d20
motor._roll_d20 = lambda: 20  # garante sucesso da persuasão
out_pers = motor.apply_resolution(TOR, {"persuade_ops": [
    {"personagem": ELGA, "rota": "portao-lateral", "vontade": 8}]})
motor._roll_d20 = force_persuade
fadiga_persuasor_depois, _ = fadiga_de(TOR)
fadiga_alvo_depois, _ = fadiga_de(ELGA)
check("persuade_ops aconteceu (precondição do teste)",
      bool(out_pers.get("persuade_ops_applied")), str(out_pers))
check("persuade_ops: quem PERSUADIU (Torvin) NÃO gasta fadiga",
      fadiga_persuasor_depois == fadiga_persuasor_antes,
      f"antes={fadiga_persuasor_antes} depois={fadiga_persuasor_depois}")
check("persuade_ops: quem foi PERSUADIDO (Elga) gasta fadiga 'alto'",
      fadiga_alvo_depois == fadiga_alvo_antes + custo_elga,
      f"antes={fadiga_alvo_antes} depois={fadiga_alvo_depois} custo_esperado={custo_elga}")

# 7) travel_ops custa 'alto' — MOVE Torvin pra fora da taverna.
motor.memoria._remember_route(
    motor.find_character_folder(TOR), "portao-lateral", "Portão Lateral")
fadiga_antes_travel, _ = fadiga_de(TOR)
out_travel = motor.apply_resolution(TOR, {"travel_ops": [{"destino": "forja-de-ferro"}]})
fadiga3, _ = fadiga_de(TOR)
check("travel_ops aconteceu (precondição do teste)",
      bool(out_travel.get("travel_ops_applied")), str(out_travel.get("travel_ops_applied")))
check("travel_ops soma fadiga 'alto' (~10) em quem viaja",
      fadiga3 == fadiga_antes_travel + 10, f"obtido: {fadiga3}")

# 8) o caminho VIVO do tool-calling: 'dormir' aparece no manifest e funciona
ctx_tor = motor.get_context(TOR)
tools_ctx = arbiter.build_tools(ctx_tor)
tool_dormir = next((t for t in tools_ctx if t["name"] == "sleep"), None)
check("manifest: 'dormir' está sempre disponível, sem parâmetros",
      tool_dormir is not None and tool_dormir["parameters"]["properties"] == {})


intent_dormir = {"action": "descansa", "target": None, "utterance": None,
                 "movement": None, "note": ""}
selftest_helpers.resolve_scripted(intent_dormir, ctx_tor, [
    ("sleep", {}),
    ("narrate", {"narrative_hint": "descansa"}),
])
check("caminho vivo: 'dormir' via tool-calling inicia o descanso (spec 031)",
      _descansando_desde_p32(TOR) is not None)
_backdate_p32(TOR, 8 * 3600 + 60)
ctx_tor2 = motor.get_context(TOR)
# item 50: acordar é `wake_up`, capacidade própria — não mais a 2ª chamada de
# `sleep`. Chamar `sleep` aqui passaria a ser RECUSADO (`ja_dormindo`).
selftest_helpers.resolve_scripted(intent_dormir, ctx_tor2, [
    ("wake_up", {}),
    ("narrate", {"narrative_hint": "acorda"}),
])
check("caminho vivo: 'wake_up' via tool-calling acorda e zera a fadiga de verdade",
      fadiga_de(TOR)[0] == 0, str(fadiga_de(TOR)))

# =========================================================================== #
# US2 (parte 2) — as demais rolagens moduladas: chamadas diretas às funções
# de rolagem (puras, sem dependência de localização/cena).
# =========================================================================== #

tor_fresh_fm, _ = motor.read_doc(motor.find_character_folder(TOR) / "character.md")
teto_tor2 = motor.fatigue_max(tor_fresh_fm)
descansado = _fm_com_fadiga(tor_fresh_fm, 0)
exausto = _fm_com_fadiga(tor_fresh_fm, teto_tor2)

# 9) roll_learn_check: DC piora com fadiga alta — d20=13, INT=10 (mod 0),
# LEARN_ROUTE_DC=12: descansado passa (13>=12); exausto (penalidade +2,
# dc=14) falha (13<14).
motor._roll_d20 = lambda: 13
passou_descansado, _ = motor.conhecimento.roll_learn_check(TOR, descansado, "subida-do-corvo")
motor._roll_d20 = lambda: 13
passou_exausto, _ = motor.conhecimento.roll_learn_check(TOR, exausto, "subida-do-corvo")
motor._roll_d20 = force
check("roll_learn_check: descansado passa com d20=13 (DC 12)", passou_descansado)
check("roll_learn_check: exausto FALHA no MESMO d20=13 (DC piora pra 14)",
      not passou_exausto)

# 10) roll_persuasion_check: DC piora com fadiga do ALVO — vontade=3 =>
# persuade_dc(3)=14 (descansado) vs 14+2=16 (exausto).
elga_fresh_fm, _ = motor.read_doc(motor.find_character_folder(ELGA) / "character.md")
teto_elga = motor.fatigue_max(elga_fresh_fm)
elga_descansada = _fm_com_fadiga(elga_fresh_fm, 0)
elga_exausta = _fm_com_fadiga(elga_fresh_fm, teto_elga)

motor._roll_d20 = lambda: 13
_, info_d = motor.deslocamento.roll_persuasion_check(
    tor_fresh_fm, TOR, ELGA, "portao-lateral", 3, alvo_fm=elga_descansada)
motor._roll_d20 = lambda: 13
_, info_e = motor.deslocamento.roll_persuasion_check(
    tor_fresh_fm, TOR, ELGA, "portao-lateral", 3, alvo_fm=elga_exausta)
motor._roll_d20 = force
check("roll_persuasion_check: DC sobe quando o ALVO está exausto",
      info_e["rolagem"]["dc"] > info_d["rolagem"]["dc"],
      f"descansado dc={info_d['rolagem']['dc']} exausto dc={info_e['rolagem']['dc']}")

# 11) roll_persuade_give_check: mesmo tratamento, mesma curva. Usa um
# alvo_id FICTÍCIO (sem histórico) — Torvin já traumatizou Elga de verdade
# nas seções de combate acima, e o portão de trauma (spec 023) forçaria
# disposicao=0 se usássemos o id real dela aqui (rolagem None, fora do que
# este teste quer medir).
motor._roll_d20 = lambda: 13
_, gd = motor.comercio.roll_persuade_give_check(
    tor_fresh_fm, TOR, "alvo-neutro-p32", TOR, MOEDA1, 3, alvo_fm=elga_descansada)
motor._roll_d20 = lambda: 13
_, ge = motor.comercio.roll_persuade_give_check(
    tor_fresh_fm, TOR, "alvo-neutro-p32", TOR, MOEDA1, 3, alvo_fm=elga_exausta)
motor._roll_d20 = force
check("roll_persuade_give_check: DC sobe quando o ALVO está exausto",
      ge["rolagem"]["dc"] > gd["rolagem"]["dc"],
      f"descansado dc={gd['rolagem']['dc']} exausto dc={ge['rolagem']['dc']}")

# 12) FR-009 — persuasão SEM custo de fadiga associado (roll_disposicao, o
# portão de hear_about/ask_about) NUNCA é modulada pela fadiga de quem
# responde — nem recebe o parâmetro. Mesma nota, mesmo resultado, sempre.
# Id fictício (sem histórico com Torvin) pelo mesmo motivo da seção 11.
motor._roll_d20 = lambda: 11
passou_disp1, info_disp1 = motor.conhecimento.roll_disposicao(
    TOR, tor_fresh_fm, "informante-neutro-p32", 5)
motor._roll_d20 = lambda: 11
passou_disp2, info_disp2 = motor.conhecimento.roll_disposicao(
    TOR, tor_fresh_fm, "informante-neutro-p32", 5)
motor._roll_d20 = force
check("FR-009: roll_disposicao (sem custo de fadiga) é idêntico entre chamadas",
      info_disp1["rolagem"]["dc"] == info_disp2["rolagem"]["dc"]
      and passou_disp1 == passou_disp2)

# =========================================================================== #
# US3 — renovação de memória por proximidade, generalizada (Frente C)
# =========================================================================== #

_mk_char("renov-p32", "Testador de Renovação")
RENOV = "renov-p32"
renov_folder = motor.find_character_folder(RENOV)

# 13) extensão fracionária proporcional à intensidade: 'giant' estende MUITO
# mais que 'small' — metade do TTL-base de cada uma.
mid_giant = motor.memoria._write_memory(
    renov_folder, "um evento e tanto", intensity="giant", involved=[RENOV, "sujeito-p32"])
mid_small = motor.memoria._write_memory(
    renov_folder, "um evento qualquer", intensity="small", involved=[RENOV, "sujeito-p32"])
fm_giant_antes, _ = motor.read_doc(renov_folder / "memories" / f"{mid_giant}.md")
fm_small_antes, _ = motor.read_doc(renov_folder / "memories" / f"{mid_small}.md")
ttl_giant_antes = fm_giant_antes["timestamp_end"]
ttl_small_antes = fm_small_antes["timestamp_end"]

motor.memoria._renew_memory(renov_folder, entity_id="sujeito-p32", modo="prazo")
fm_giant_depois, _ = motor.read_doc(renov_folder / "memories" / f"{mid_giant}.md")
fm_small_depois, _ = motor.read_doc(renov_folder / "memories" / f"{mid_small}.md")
extensao_giant = fm_giant_depois["timestamp_end"] - ttl_giant_antes
extensao_small = fm_small_depois["timestamp_end"] - ttl_small_antes
check("renovação: memória 'giant' estende BEM mais que 'small'",
      extensao_giant > extensao_small,
      f"giant={extensao_giant}s small={extensao_small}s")
check("renovação NÃO é reset pleno (extensão < TTL-base cheio de giant)",
      extensao_giant < motor.memoria._TTL_BY_INTENSITY["giant"],
      f"extensao={extensao_giant}, ttl_cheio={motor.memoria._TTL_BY_INTENSITY['giant']}")

# 14) memória VENCIDA revive (mesmo espírito de rota)
mid_vencida = motor.memoria._write_memory(
    renov_folder, "algo já esquecido", intensity="medium",
    involved=[RENOV, "sujeito-vencido-p32"])
vpath = renov_folder / "memories" / f"{mid_vencida}.md"
vfm, vbody = motor.read_doc(vpath)
vfm["timestamp_end"] = int(__import__("time").time()) - 10
vfm["state"] = "expired"
motor.write_doc(vpath, vfm, vbody)
motor.memoria._renew_memory(renov_folder, entity_id="sujeito-vencido-p32", modo="prazo")
vfm_depois, _ = motor.read_doc(vpath)
check("renovação REVIVE memória vencida (state volta a active, prazo no futuro)",
      vfm_depois["state"] == "active"
      and vfm_depois["timestamp_end"] > int(__import__("time").time()))

# 15) agnóstico ao tipo de entidade — funciona igual pra pessoa/lugar/item
mid_lugar = motor.memoria._write_memory(
    renov_folder, "um lugar marcante", intensity="medium",
    involved=[RENOV, "taverna-do-gancho"])
ttl_lugar_antes = motor.read_doc(renov_folder / "memories" / f"{mid_lugar}.md")[0]["timestamp_end"]
motor.memoria._renew_memory(renov_folder, entity_id="taverna-do-gancho", modo="prazo")
ttl_lugar_depois = motor.read_doc(renov_folder / "memories" / f"{mid_lugar}.md")[0]["timestamp_end"]
check("renovação agnóstica a tipo: funciona pra LUGAR igual funciona pra pessoa",
      ttl_lugar_depois > ttl_lugar_antes)

# =========================================================================== #
# US4 — compromisso não cumprido intensifica ao dormir (Frente D)
# =========================================================================== #

_mk_char("credor-p32", "Credor")
_mk_char("devedor-p32", "Devedor")
CREDOR, DEVEDOR = "credor-p32", "devedor-p32"

out_prom = motor.apply_resolution(DEVEDOR, {"promise_ops": [
    {"para": CREDOR, "expectativa": "que eu pague o que devo"}]})
check("prometer aconteceu (precondição do teste)",
      bool(out_prom.get("promise_ops_applied")), str(out_prom))

devedor_folder = motor.find_character_folder(DEVEDOR)
int_path = sorted((devedor_folder / "intentions").glob("*.md"))[0]
int_fm, _ = motor.read_doc(int_path)
mem_id_compromisso = int_fm.get("memoria_id")
check("a intenção do compromisso guarda o memoria_id (spec 030)",
      bool(mem_id_compromisso), str(int_fm))

mem_path = devedor_folder / "memories" / f"{mem_id_compromisso}.md"


def _intensidade_atual():
    fm, _ = motor.read_doc(mem_path)
    return fm.get("intensity")


intensidade_inicial = _intensidade_atual()  # "medium" (evento "promise")
check("memória do compromisso nasce 'medium' (precondição do teste)",
      intensidade_inicial == "medium", str(intensidade_inicial))

# dormir 1x (noite inteira, spec 031): sem carência, intensifica já na
# primeira noite (medium -> large) — só descanso de QUALIDADE (>=50%
# recuperado) intensifica; _dormir_noite_inteira sempre é uma noite cheia.
_dormir_noite_inteira(DEVEDOR)
check("1ª noite com o compromisso pendente: medium -> large (sem carência)",
      _intensidade_atual() == "large", str(_intensidade_atual()))

# dormir 2x: large -> giant
_dormir_noite_inteira(DEVEDOR)
check("2ª noite: large -> giant", _intensidade_atual() == "giant",
      str(_intensidade_atual()))

# dormir 3x: já no teto, permanece giant (nunca estoura a escala)
_dormir_noite_inteira(DEVEDOR)
check("3ª noite: permanece 'giant' (teto, nunca ultrapassa)",
      _intensidade_atual() == "giant", str(_intensidade_atual()))

# cumpre o compromisso (fecha a intenção) — dormir de novo NÃO intensifica mais
motor.intencoes.close_intention(devedor_folder, int_fm["id"], status="concluida")
intensidade_apos_cumprir = _intensidade_atual()
_dormir_noite_inteira(DEVEDOR)
check("compromisso CUMPRIDO: dormir de novo não intensifica mais",
      _intensidade_atual() == intensidade_apos_cumprir,
      f"antes={intensidade_apos_cumprir} depois={_intensidade_atual()}")

# ---- item 51 (fatia 1): a NECESSIDADE em RÓTULO ------------------------------
# A segunda bússola do tick autônomo estava desligada: o prompt de autonomia lia
# `status_sobrevivencia` numa "escala de 0 a 10" e o conector a alimentava com
# `status.survival_level || 0` — campo que NUNCA existiu no mundo. Constante zero
# para todo personagem, e o modelo lia o zero como urgência ("com o status de
# sobrevivência em 0, ele está focado em resolver problemas imediatos, como
# encontrar comida"). Pior: `hunger`/`fatigue` não chegavam à Mente por nenhuma
# outra via — o personagem não tinha como SABER que estava com fome.
#
# RÓTULO, nunca escala: "fato vai em rótulo, não número; o número é segredo do
# mundo". Um personagem sabe que está faminto, não que está em 7 de 10.
_fome = lambda h: motor.fisica.hunger_label({"status": {"hunger": h}})
check("51.1: o vocabulário LIVRE do mundo normaliza em rótulo canônico",
      _fome("saciado") == "sem fome" and _fome("satisfeita") == "sem fome"
      and _fome("faminta") == "faminto" and _fome("extremo") == "faminto"
      and _fome("com fome") == "com fome",
      f'{_fome("saciado")}/{_fome("satisfeita")}/{_fome("faminta")}/{_fome("extremo")}')
check("51.1: ficha SEM `hunger` não inventa fome (ausência não é urgência)",
      motor.fisica.hunger_label({}) == "sem fome"
      and _fome("") == "sem fome" and _fome("coisa que ninguém escreveu") == "sem fome")

_cans = lambda f, teto: motor.fisica.fatigue_label(
    {"status": {"fatigue": f, "fatigue_max": teto}})
# o MESMO número, dois corpos: 70 num teto de 100 é 70%; num de 120 é 58%. O teto
# varia por corpo, então rótulo absoluto mentiria para metade do mundo.
check("51.1: o cansaço é faixa do PRÓPRIO teto, não número absoluto",
      _cans(70, 100) == "muito cansado" and _cans(70, 120) == "cansado",
      f"70/100={_cans(70, 100)} · 70/120={_cans(70, 120)}")
check("51.1: exausto no topo, descansado no fundo",
      _cans(100, 100) == "exausto" and _cans(0, 100) == "descansado",
      f"{_cans(100, 100)} / {_cans(0, 100)}")
# a DÍVIDA que a spec 030 (FR-001) criou e que este rótulo torna visível: metade
# das fichas do mundo tem `fatigue` como PALAVRA, e palavra lê como 0
check("51.1: `fatigue` texto legado lê como descansado (dívida do item 51, visível)",
      _cans("alto", 100) == "descansado", _cans("alto", 100))

# e chega ao CONTEXTO, que é a única porta da Mente
_ctx51 = motor.get_context(TORVIN_ID if "TORVIN_ID" in dir() else "torvin-ferreiro")
check("51.1: a necessidade DESCE no contexto, ao lado do status cru",
      isinstance((_ctx51.get("self") or {}).get("necessidade"), dict)
      and "fome" in _ctx51["self"]["necessidade"]
      and "cansaco" in _ctx51["self"]["necessidade"],
      str((_ctx51.get("self") or {}).get("necessidade")))
check("51.1: e o status CRU segue lá — a régua do Motor precisa do número",
      "fatigue" in (_ctx51["self"].get("status") or {}))


print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 32 (Fadiga como recurso, spec 030) OK.")
