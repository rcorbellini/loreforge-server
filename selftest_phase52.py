"""Auto-teste da Fase 52 — Esquartejar (spec 050, US1+US2+US3).

Sem modelo/LLM ligado — exercita o Motor direto (`motor.apply_resolution`) para o
comportamento DETERMINÍSTICO do executor, e `arbiter.build_ctx`/`execute` (com `ask`
forçado, ou contado) para o comportamento da GUARDA (enum de mortos, zero-LLM
estrutural). Cobre:

  - US1: corpo válido -> uma ou mais porções de carne nascem NO ATO (síncrono, sem
    materialização preguiçosa); o corpo permanece intocado, só ganha
    `status.esquartejado`
  - US2: alvo vivo/incapacitado -> recusa estrutural, ZERO chamada ao Árbitro;
    esquartejabilidade/rendimento 0 -> recusa de mérito, com memória; corpo já
    esquartejado -> recusa estrutural na 2ª tentativa, mesmo sem sucesso na 1ª
  - US3: proficiência em "acougue" soma DIRETO na rolagem de rendimento (decide a
    banda, não só a quantidade depois) — mesmo mecanismo assintótico de "cozinha"

Uso:  python3 selftest_phase52.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test52-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402

FAILS = []
TAVERNA = "taverna-do-gancho"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _mk_char(cid: str, name: str, dex: int = 10, weight_kg: float = 70,
            conditions=None, hp=20):
    d = motor.WORLD_DIR / TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    cond_yaml = str(list(conditions or []))
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {name}\n"
        f"controlled_by: player_local\nweight_kg: {weight_kg}\n"
        f"attributes:\n  STR: 10\n  DEX: {dex}\n  CON: 10\n  INT: 10\n  WIS: 10\n  CHA: 10\n"
        f"skills:\n  geral: 1\n"
        f"status:\n  hp: {hp}\n  hp_max: 20\n  hunger: sem fome\n  fatigue: 0\n"
        f"  action: parado\n  mood: neutro\n  conditions: {cond_yaml}\n"
        f"origin: editorial\n---\nUm presente qualquer, feito de carne de verdade.\n",
        encoding="utf-8")
    return d


def esquartejado_de(cid: str) -> bool:
    fm, _ = motor.read_doc(motor.find_character_folder(cid) / "character.md")
    return bool((fm.get("status") or {}).get("esquartejado"))


def memorias_evento(cid: str, evento: str) -> list:
    return [fm for fm in motor.memoria._iter_memories(cid) if fm.get("evento") == evento]


def esquartejar_op(alvo, esquartejabilidade=7, rendimento=7,
                   nome="Carne de Teste", descricao="pedaços de carne crua"):
    return {"alvo": alvo, "esquartejabilidade": esquartejabilidade,
            "rendimento": rendimento, "nome": nome, "descricao": descricao}


def _planta_memoria_acougue(cid: str, intensity: str = "giant"):
    folder = motor.find_character_folder(cid)
    motor.memoria._write_memory(folder, "uma sessão e tanto esquartejando",
                                intensity=intensity, domain="acougue", involved=[cid])


def carnes_da(location_folder: Path) -> list[Path]:
    return sorted(location_folder.glob("carne-*"))


force = motor._roll_d20

# =========================================================================== #
# US1 — esquartejar de verdade: uma ou mais porções de carne nascem NO ATO,
# o corpo continua existindo, só marcado
# =========================================================================== #

_mk_char("acougueiro-p52", "Açougueiro de Teste")
ACG = "acougueiro-p52"
acg_folder = motor.find_character_folder(ACG)
taverna_folder = acg_folder.parent

_mk_char("coelho-p52", "Coelho Morto", weight_kg=2, conditions=["morto"], hp=0)
COELHO = "coelho-p52"

motor._roll_d20 = lambda: 20  # banda farto garantida (rendimento=8, dc<=4)
motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op(COELHO, esquartejabilidade=9, rendimento=8,
                  nome="Carne de Coelho", descricao="pedaços de carne magra e fresca")]})
motor._roll_d20 = force

carnes_farto = carnes_da(taverna_folder)
check("US1: uma ou mais porções de carne nascem NO ATO (síncrono, sem materialização "
     "preguiçosa)", len(carnes_farto) >= 1, str(carnes_farto))
if carnes_farto:
    fm0, body0 = motor.read_doc(carnes_farto[0] / "item.md")
    check("US1: nome/description vêm do que o Árbitro escreveu, iguais em todas as porções",
          all(motor.read_doc(c / "item.md")[0].get("name") == "Carne de Coelho"
             and motor.read_doc(c / "item.md")[1].strip() ==
             "pedaços de carne magra e fresca" for c in carnes_farto))
check("US1: o corpo CONTINUA existindo, identidade intacta",
      (taverna_folder / COELHO / "character.md").exists())
check("US1: o corpo é marcado status.esquartejado = true", esquartejado_de(COELHO))
mem_farto = memorias_evento(ACG, "butcher_farto")
check("US1: memória 'medium' positiva já gravada NO ATO (domain='acougue')",
      len(mem_farto) == 1 and mem_farto[0].get("intensity") == "medium"
      and mem_farto[0].get("domain") == "acougue", str(mem_farto))

# banda FRACO: item(ns) ainda nasce(m), peso TOTAL menor (FR-010/FR-011)
_mk_char("gafanhoto-p52", "Gafanhoto Morto", weight_kg=0.02, conditions=["morto"], hp=0)
GAFANHOTO = "gafanhoto-p52"
motor._roll_d20 = lambda: 1  # banda fraco garantida
motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op(GAFANHOTO, esquartejabilidade=6, rendimento=3,
                  nome="Carne de Gafanhoto", descricao="uma lasca ínfima de carne")]})
motor._roll_d20 = force
peso_farto = sum(motor.read_doc(c / "item.md")[0].get("weight_kg", 0) for c in carnes_farto)
carnes_totais = carnes_da(taverna_folder)
carnes_gafanhoto = [c for c in carnes_totais if c not in carnes_farto]
peso_fraco = sum(motor.read_doc(c / "item.md")[0].get("weight_kg", 0) for c in carnes_gafanhoto)
check("US1: banda FRACO ainda produz item(ns) (nunca falha total)",
      len(carnes_gafanhoto) >= 1, str(carnes_gafanhoto))
check("US1: peso TOTAL de banda fraco (corpo pequeno) é MENOR que o de banda farto "
     "(corpo maior) — a banda/porte modula quantidade, nunca o texto",
      peso_fraco < peso_farto, f"{peso_fraco} vs {peso_farto}")

# dar uma porção a um segundo presente, guardar a outra (SC-006)
if len(carnes_farto) >= 1:
    _mk_char("ajudante-p52", "Ajudante de Teste")
    AJUD = "ajudante-p52"
    porcao_id = carnes_farto[0].name
    motor.apply_resolution(ACG, {"item_transfers": [
        {"item": porcao_id, "to": AJUD}]})
    encontrado = motor.find_entity(porcao_id)
    check("US1: uma porção pode ser entregue a outro presente, a outra fica com quem "
         "esquartejou — cada porção é entidade independente",
          encontrado is not None and encontrado[0].parent.parent.name == AJUD,
          str(encontrado[0]) if encontrado else "None")

# segredo: nenhuma das duas notas aparece no manifest da tool
import types as _types_mod
import arbiter_tools.base as _face_mod
face_butcher = _face_mod.build_face(motor.registro.get_spec("butcher"), "butcher",
                                    _types_mod.SimpleNamespace(
                                        cand={"butcher_alvo": []}, actor_id=ACG))
props_butcher = (face_butcher or {}).get("parameters", {}).get("properties", {})
check("US1: nenhuma das duas notas (nem nome/descricao) aparece na FACE",
      not ({"esquartejabilidade", "rendimento", "nome", "descricao"} & set(props_butcher)),
      str(sorted(props_butcher)))

# =========================================================================== #
# US2 — alvo vivo/incapacitado: recusa ESTRUTURAL, zero LLM; esquartejabilidade/
# rendimento 0: recusa de MÉRITO, com memória; corpo já esquartejado: recusa
# permanente, mesmo sem sucesso na 1ª tentativa; erro corrigível: sem memória
# =========================================================================== #

_mk_char("vivo-p52", "Personagem Vivo", conditions=[])
VIVO = "vivo-p52"
_mk_char("caido-p52", "Personagem Caído", conditions=["incapacitado"])
CAIDO = "caido-p52"

_chamadas = {"n": 0}


def _ask_conta(system, user):
    _chamadas["n"] += 1
    return ('{"esquartejabilidade": 8, "rendimento": 8, "nome": "Carne", '
           '"descricao": "carne crua"}')


ctx_vivo = arbiter.build_ctx(motor.get_context(ACG), ask=_ask_conta,
                             prosa={"acao": "tenta esquartejar quem está de pé"})
res_vivo = ctx_vivo.execute("butcher", {"alvo": VIVO})
check("US2: alvo VIVO não está no enum de butcher_alvo — recusa estrutural, "
     "ZERO chamada ao Árbitro", not res_vivo[0].get("ok") and _chamadas["n"] == 0,
      str(res_vivo[0]))

_chamadas["n"] = 0
ctx_caido = arbiter.build_ctx(motor.get_context(ACG), ask=_ask_conta,
                              prosa={"acao": "tenta esquartejar quem está caído"})
res_caido = ctx_caido.execute("butcher", {"alvo": CAIDO})
check("US2: alvo só INCAPACITADO (não morto) — mesma recusa estrutural, ZERO LLM",
      not res_caido[0].get("ok") and _chamadas["n"] == 0, str(res_caido[0]))

# gate ESQUARTEJABILIDADE 0 (nível de executor, autoritativo)
_mk_char("golem-p52", "Golem de Pedra", conditions=["morto"], hp=0)
GOLEM = "golem-p52"
out_sem_carne = motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op(GOLEM, esquartejabilidade=0, rendimento=5)]})
check("US2: esquartejabilidade 0 -> recusa 'sem_carne', RENDIMENTO nunca chega a "
     "importar, nenhum item criado", any(r.get("regra") == "sem_carne"
                                        for r in out_sem_carne["rejected"]),
      str(out_sem_carne["rejected"]))
check("US2: mesmo recusado, o corpo é marcado esquartejado (recurso finito consumido "
     "pela tentativa)", esquartejado_de(GOLEM))
mem_sem_carne = memorias_evento(ACG, "butcher_refused_esquartejabilidade")
check("US2: recusa por esquartejabilidade gera memória 'small' negativa, domain='nenhuma'",
      len(mem_sem_carne) == 1 and mem_sem_carne[0].get("intensity") == "small"
      and mem_sem_carne[0].get("domain") in (None, "nenhuma"), str(mem_sem_carne))

# corpo já esquartejado (do gate acima) -> 2ª tentativa recusa ESTRUTURALMENTE
out_2a_tentativa = motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op(GOLEM, esquartejabilidade=9, rendimento=9)]})
check("US2: corpo já esquartejado (mesmo com rendimento 0 na 1ª tentativa) recusa "
     "de novo, sem reconsultar réguas — carne não regenera",
      any(r.get("regra") == "ja_esquartejado" for r in out_2a_tentativa["rejected"]),
      str(out_2a_tentativa["rejected"]))

# gate RENDIMENTO 0
_mk_char("carbonizado-p52", "Corpo Carbonizado", conditions=["morto"], hp=0)
CARBONIZADO = "carbonizado-p52"
out_sem_rendimento = motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op(CARBONIZADO, esquartejabilidade=8, rendimento=0)]})
check("US2: rendimento 0 (esquartejabilidade > 0) -> recusa 'nada_a_aproveitar'",
      any(r.get("regra") == "nada_a_aproveitar" for r in out_sem_rendimento["rejected"]),
      str(out_sem_rendimento["rejected"]))
check("US2: corpo marcado esquartejado mesmo com rendimento 0",
      esquartejado_de(CARBONIZADO))

# erro corrigível: alvo inexistente na cena -> sem memória (distinção dos dois acima)
out_corrigivel = motor.apply_resolution(ACG, {"esquartejar_ops": [
    esquartejar_op("nao-existe-p52")]})
check("US2: alvo inexistente na cena -> recusa 'alvo_inacessivel', corrigível",
      any(r.get("regra") == "alvo_inacessivel" for r in out_corrigivel["rejected"]),
      str(out_corrigivel["rejected"]))
check("US2: erro corrigível (id inexistente) NÃO gera memória nenhuma — distinto das "
     "recusas de mérito acima", "memory" not in (out_corrigivel["rejected"][0] or {}))

# =========================================================================== #
# US3 — proficiência em "acougue" soma DIRETO na rolagem de rendimento
# =========================================================================== #

_mk_char("novato-p52", "Novato de Teste")
NOVATO = "novato-p52"
_mk_char("experiente-p52", "Experiente de Teste")
EXPERIENTE = "experiente-p52"
_planta_memoria_acougue(EXPERIENTE, "giant")

_mk_char("corpo-novato-p52", "Corpo A", conditions=["morto"], hp=0)
_mk_char("corpo-exp-p52", "Corpo B", conditions=["morto"], hp=0)

nivel_novato_antes = motor.memoria.proficiencies_for(NOVATO).get("acougue", -1)
check("US3: ator SEM nenhuma memória domain='acougue' -> nivel_acougue = 0.0 (bônus "
     "zero, nunca erro)", nivel_novato_antes == 0.0, str(nivel_novato_antes))

# MESMO d20 (9), rendimento=5 -> dc=persuade_dc(5)=10 (mesma curva de `cook`):
# novato (nivel=0) -> total=9 < dc(10) -> fraco. experiente (nivel~3.33, giant) ->
# total=12.33, margem 2.33<=5 -> medio. A MESMA tirada produzindo bandas
# diferentes, só pela perícia (FR-008) — molde EXATO do teste equivalente de `cook`.
motor._roll_d20 = lambda: 9
motor.apply_resolution(NOVATO, {"esquartejar_ops": [
    esquartejar_op("corpo-novato-p52", esquartejabilidade=7, rendimento=5)]})
motor.apply_resolution(EXPERIENTE, {"esquartejar_ops": [
    esquartejar_op("corpo-exp-p52", esquartejabilidade=7, rendimento=5)]})
motor._roll_d20 = force

mem_novato = (memorias_evento(NOVATO, "butcher_farto")
             + memorias_evento(NOVATO, "butcher_medio")
             + memorias_evento(NOVATO, "butcher_fraco"))
mem_exp = (memorias_evento(EXPERIENTE, "butcher_farto")
          + memorias_evento(EXPERIENTE, "butcher_medio")
          + memorias_evento(EXPERIENTE, "butcher_fraco"))
check("US3: com o MESMO d20 (9), novato cai em banda FRACO e experiente cruza pra "
     "MÉDIO (a proficiência soma direto na tirada, FR-008)",
      len(mem_novato) == 1 and len(mem_exp) == 1
      and mem_novato[0].get("evento") == "butcher_fraco"
      and mem_exp[0].get("evento") == "butcher_medio",
      f"novato={mem_novato[0].get('evento') if mem_novato else None} "
      f"exp={mem_exp[0].get('evento') if mem_exp else None}")

mem_dominio_recusa = [fm for fm in motor.memoria._iter_memories(ACG)
                      if fm.get("evento") in ("butcher_refused_esquartejabilidade",
                                              "butcher_refused_rendimento")
                      and fm.get("domain") == "acougue"]
check("US3: recusas de mérito NÃO carregam domain='acougue' — só carne criada "
     "alimenta a proficiência", len(mem_dominio_recusa) == 0, str(mem_dominio_recusa))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 52 (Esquartejar, spec 050) OK.")
