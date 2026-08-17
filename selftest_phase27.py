"""Auto-teste da Fase 27 — memória de testemunha: a cena tem plateia (spec 024).

Rolagem forçada (motor._roll_d20), tudo OFFLINE (zero LLM — a prova do SC-001 é
rodar sem Ollama). Cobre:

  US1 (furto):
  - FLAGRADO: a testemunha ATENTA (WIS alta) grava memória factual de PRIMEIRA MÃO;
    a DISTRAÍDA (WIS baixa) NÃO — a percepção é rolagem d20+WIS vs. exposição (G_perc)
  - a testemunha do furto ganha valência− LEVE ao ladrão, mas NÃO cai no portão de
    trauma (`has_trauma_from`=False): quem só viu não é vítima (G7)
  - LIMPO: ninguém testemunha, nem a mais atenta (SC-002/G3)
  - CAÍDO não testemunha (G2)
  - PARIDADE: a vítima segue ganhando o trauma; o desfecho do ator é intacto (G6)
  - SEGREDO: nada da testemunha desce ao client em inworld_effects (G8)

  US2 (público):
  - TRANSFERÊNCIA (banal, público): quem tem VÍNCULO com um envolvido RETÉM; o
    ESTRANHO percebe (público não rola) mas o piso de saliência descarta (G4/SC-003)
  - GOLPE (carregado, público): a testemunha SEM vínculo ainda assim grava (memorável
    a todos), com valência− ao agressor e SEM trauma (FR-007)

Uso:  python3 server/selftest_phase27.py
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
import app as server_app  # noqa: E402

FAILS = []
TAVERNA = _tmp / "world" / "taverna-do-gancho"
ELGA = "elga-taverneira"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force(v):
    motor._roll_d20 = lambda: v


def _mk_char(cid, wis=10, dex=10, conditions="[]"):
    d = TAVERNA / cid
    d.mkdir(parents=True, exist_ok=True)
    (d / "character.md").write_text(
        f"---\ntype: character\nid: {cid}\nname: {cid.replace('-', ' ').title()}\n"
        f"controlled_by: player_local\nweight_kg: 70\n"
        f"attributes:\n  STR: 10\n  DEX: {dex}\n  CON: 10\n  INT: 10\n  WIS: {wis}\n  CHA: 10\n"
        f"skills:\n  atencao: 1\n"
        f"status:\n  hp: 50\n  hp_max: 50\n  hunger: saciado\n  fatigue: leve\n"
        f"  action: parado\n  mood: neutro\n  conditions: {conditions}\n"
        f"origin: editorial\n---\nPersonagem de teste.\n", encoding="utf-8")


def _mk_item(dono_folder, item_id):
    d = dono_folder / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: Bugiganga\nvalue: 1\nsize: P\n"
        f"weight_kg: 0.2\norigin: editorial\n---\nUma bugiganga.\n", encoding="utf-8")


def _mems(cid):
    md = motor.find_character_folder(cid) / "memories"
    return list(md.glob("*.md")) if md.exists() else []


def _viu(cid, trecho):
    """cid guarda memória de testemunha contendo `trecho`?"""
    for p in _mems(cid):
        _fm, body = motor.read_doc(p)
        if trecho.lower() in (body or "").lower():
            return True
    return False


# ---- montagem da plateia ---------------------------------------------------- #
_mk_char("ladrao-p27", dex=10)          # ladrão: DEX 10 → mod 0
_mk_char("atento-p27", wis=18)          # +4: percebe o furto exposição 5
_mk_char("distraido-p27", wis=6)        # -2: não percebe
_mk_char("caido-p27", wis=18, conditions="[incapacitado]")   # atento, mas caído

# ============================ US1 — FURTO ==================================== #
# FLAGRADO: exposição 5 (steal DC 10 / percepção DC 10). force(9): ladrão total 9
# → flagrado_levou; atento 9+4=13≥10 vê; distraído 9-2=7<10 não; caído fora.
_mk_item(TAVERNA / ELGA, "bug-w1")
force(9)
out1 = motor.apply_resolution("ladrao-p27", {"steal_ops": [
    {"alvo": ELGA, "item": "bug-w1", "exposicao": 5}]})

check("US1 FLAGRADO: a testemunha ATENTA grava o furto (primeira mão)",
      _viu("atento-p27", "furtar"))
check("US1 FLAGRADO: a DISTRAÍDA não percebe (rolagem+WIS < exposição)",
      not _viu("distraido-p27", "furtar"))
check("US1 G2: o CAÍDO não testemunha", not _viu("caido-p27", "furtar"))
check("US1 G7: a testemunha ganha valência− ao ladrão…",
      motor.sentiment_toward("atento-p27", "ladrao-p27") < 0,
      f"afeto={motor.sentiment_toward('atento-p27', 'ladrao-p27')}")
check("US1 G7: …mas NÃO cai no portão de trauma (só viu, não sofreu)",
      not motor.has_trauma_from("atento-p27", "ladrao-p27"))
check("US1 G6 paridade: a VÍTIMA segue ganhando o trauma (participante intacto)",
      motor.has_trauma_from(ELGA, "ladrao-p27"))
check("US1 primeira mão: a memória da testemunha não tem 'ouvido_de'",
      all("ouvido_de" not in (motor.read_doc(p)[0] or {})
          for p in _mems("atento-p27")))

# G8 segredo: nada da testemunha (exposição/nome/‘Vi’) desce ao client
blob = " ".join(server_app.inworld_effects(out1))
check("US1 G8: o que desce ao client não expõe a testemunha nem a exposição",
      "atento" not in blob.lower() and "5" not in blob and "vi " not in blob.lower(),
      blob)

# LIMPO: exposição 5, force(20) → ladrão total 20 ≥ 10 → LIMPO; ninguém vê.
_mk_char("atento2-p27", wis=18)
_mk_item(TAVERNA / ELGA, "bug-w2")
force(20)
motor.apply_resolution("ladrao-p27", {"steal_ops": [
    {"alvo": ELGA, "item": "bug-w2", "exposicao": 5}]})
check("US1 SC-002: furto LIMPO não deixa NENHUMA testemunha (nem a mais atenta)",
      not _viu("atento2-p27", "furtar"))

# ============================ US2 — PÚBLICO ================================== #
# TRANSFERÊNCIA (banal, público): amigo (vínculo com Elga) retém; estranho não.
_mk_char("doador-p27", dex=10)
_mk_item(TAVERNA / "doador-p27", "bug-give")
_mk_char("amigo-p27", wis=6)     # WIS baixa DE PROPÓSITO: público não rola percepção
_mk_char("estranho-p27", wis=6)
# semeia vínculo do amigo com Elga (algumas convivências → familiaridade > piso)
for i in range(3):
    motor.record_event("amigo-p27", f"Bebi com Elga, noite {i}.", "trade",
                       ["amigo-p27", ELGA])
force(10)
motor.apply_resolution("doador-p27", {"item_transfers": [
    {"item": "bug-give", "to": ELGA}]})
check("US2 G4: a testemunha COM vínculo retém o ato banal (público)",
      _viu("amigo-p27", "entregar"))
check("US2 G4/SC-003: o ESTRANHO percebe mas o piso descarta (não retém o banal)",
      not _viu("estranho-p27", "entregar"))

# GOLPE (carregado, público): o estranho SEM vínculo ainda grava (memorável a todos).
_mk_char("atacante-p27", dex=10)
_mk_char("vitima-p27", wis=10)
_mk_char("olheiro-p27", wis=6)   # sem vínculo com ninguém
force(20)                        # crítico → acerta (op aplicada)
motor.apply_resolution("atacante-p27", {"attack_ops": [
    {"alvo": "vitima-p27", "arma": None, "vantagem": 5}]})
check("US2 FR-007: a testemunha SEM vínculo grava o GOLPE (carregado é memorável a todos)",
      _viu("olheiro-p27", "golpear"))
check("US2 golpe que só FERE: valência− ao agressor, mas medium → sem trauma (só de pé-atrás)",
      motor.sentiment_toward("olheiro-p27", "atacante-p27") < 0
      and not motor.has_trauma_from("olheiro-p27", "atacante-p27"))

# DERROTA (refino do mantenedor 2026-07-23): derrubar é memória de IMPACTO (large) —
# a testemunha CRUZA o portão de trauma. Golpe deliberado em quem já está caído = derrota.
_mk_char("carrasco-p27", dex=10)
_mk_char("condenado-p27", conditions="[incapacitado]")
_mk_char("plateia-p27", wis=6)   # sem vínculo com ninguém
force(20)
motor.apply_resolution("carrasco-p27", {"attack_ops": [
    {"alvo": "condenado-p27", "arma": None, "vantagem": 0}]})
check("US2 DERROTA: a testemunha grava o derrube como memória de IMPACTO",
      _viu("plateia-p27", "derrubar"))
check("US2 DERROTA: a testemunha CRUZA o portão de trauma (teme quem derrubou)",
      motor.has_trauma_from("plateia-p27", "carrasco-p27"))

# E8 (refino do mantenedor): quem AMA a vítima leva o furto UM DEGRAU acima —
# medium→large → cruza o portão de trauma. O estranho fica em medium (só de pé-atrás).
_mk_char("ladrao-e8", dex=10)
_mk_char("amado-e8", wis=18)     # ama Elga
_mk_char("qualquer-e8", wis=18)  # não conhece Elga
for i in range(6):               # semeia AFETO+ forte por Elga (memórias positivas)
    motor.record_event("amado-e8", f"Elga cuidou de mim, {i}", "gift_received",
                       ["amado-e8", ELGA], valence={ELGA: "positiva"})
saldo = motor.sentiment_toward("amado-e8", ELGA)
_mk_item(TAVERNA / ELGA, "bug-e8"); force(9)
motor.apply_resolution("ladrao-e8", {"steal_ops": [
    {"alvo": ELGA, "item": "bug-e8", "exposicao": 5}]})
check(f"E8 pré-condição: amado-e8 nutre forte afeto por Elga (saldo={saldo:.1f}≥{4.0})",
      saldo >= 4.0)
check("E8: quem AMA a vítima leva o furto a mal de verdade → CRUZA o portão de trauma",
      motor.has_trauma_from("amado-e8", "ladrao-e8"))
check("E8: o ESTRANHO que viu o mesmo furto fica em medium (sem trauma — só de pé-atrás)",
      _viu("qualquer-e8", "furtar") and not motor.has_trauma_from("qualquer-e8", "ladrao-e8"))

print()
if FAILS:
    print(f"FALHOU ({len(FAILS)}): " + "; ".join(FAILS)); sys.exit(1)
print("Fase 27 (memória de testemunha) OK.")
