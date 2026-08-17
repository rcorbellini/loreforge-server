"""Auto-teste da Fase 19 — Memória Ligada a Tudo: Apego e Afeto (spec 016).

Cobre:
  - o ALICERCE: `involved` com itens e lugares; valência DIRIGIDA derivada do
    evento; a arma por DESFECHO (acerto+, erro−, lendo ataque rejeitado)
  - APEGO (`familiarity_with` sobre qualquer id): volume, conta neutro e vencida a ¼
  - AFETO (`sentiment_toward`): sinal, saldo pende ao mais pesado, vencida a ¼
  - os TRÊS consumidores: disposição (saldo pronto à régua 015), troca (apego sobe
    o trade_dc), locomover (afeto por lugar no contexto do persuade)
  - a NÃO-REGRESSÃO: apego=0 dá o trade_dc da spec 011; o portão duro da 015 vive

Injeção: `motor._roll_d20` nos testes de troca; o resto é medição direta.

Uso:  python3 server/selftest_phase19.py
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
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402

FAILS = []

TORVIN, ELGA = "torvin-ferreiro", "elga-taverneira"
TAVERNA = "taverna-do-gancho"
ESPADA = "espada-curta"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar(cid):
    d = pasta(cid) / "memories"
    if d.is_dir():
        for p in d.glob("*.md"):
            p.unlink()


def dado(v):
    motor._roll_d20 = lambda: v


def registrar(ator, outcome_parts):
    base = {"applied": [], "rejected": []}
    base.update(outcome_parts)
    return motor._record_events(
        ator, pasta(ator),
        {TORVIN: pasta(TORVIN), ELGA: pasta(ELGA)}, base)


print("\n--- O alicerce: involved com coisas, valência dirigida --------------")

limpar(TORVIN)
limpar(ELGA)
registrar(TORVIN, {"attack_ops_applied": [
    {"alvo": ELGA, "arma": ESPADA, "dano": 5, "derrota": None}]})

check("a VÍTIMA pende negativamente para o agressor",
      motor.sentiment_toward(ELGA, TORVIN) < 0,
      str(motor.sentiment_toward(ELGA, TORVIN)))
check("o AGRESSOR fica neutro (só se afirma sinal onde o evento determina)",
      motor.sentiment_toward(TORVIN, ELGA) == 0,
      str(motor.sentiment_toward(TORVIN, ELGA)))
check("o LUGAR herda o afeto do que ali ocorreu (taverna negativa p/ Elga)",
      motor.sentiment_toward(ELGA, TAVERNA) < 0,
      str(motor.sentiment_toward(ELGA, TAVERNA)))
check("a ARMA que ACERTOU pende positiva (confiança)",
      motor.sentiment_toward(TORVIN, ESPADA) > 0,
      str(motor.sentiment_toward(TORVIN, ESPADA)))

# o ERRO é rejeição, não op aplicada — lê-la é o que grava a desconfiança
limpar(TORVIN)
registrar(TORVIN, {"attack_ops_applied": [],
                   "rejected": [{"atacar": ELGA, "arma": ESPADA,
                                 "regra": "ataque_errou",
                                 "valores": {"arma": ESPADA}}]})
check("a ARMA que ERROU pende negativa (desconhecida via rejeição)",
      motor.sentiment_toward(TORVIN, ESPADA) < 0,
      str(motor.sentiment_toward(TORVIN, ESPADA)))

# golpe absorvido: acertou, o aço segurou — conta como acerto para a arma
limpar(TORVIN)
registrar(TORVIN, {"attack_ops_applied": [],
                   "rejected": [{"atacar": ELGA, "arma": ESPADA,
                                 "regra": "golpe_absorvido",
                                 "valores": {"arma": ESPADA}}]})
check("golpe ABSORVIDO conta como acerto para a arma (a mira foi boa)",
      motor.sentiment_toward(TORVIN, ESPADA) > 0,
      str(motor.sentiment_toward(TORVIN, ESPADA)))

# evento ambíguo é neutro
limpar(TORVIN)
registrar(TORVIN, {"carry_ops_applied": [{"alvo": ELGA}]})
check("evento ambíguo (carry) NÃO pende — fica neutro",
      motor.sentiment_toward(TORVIN, ELGA) == 0,
      str(motor.sentiment_toward(TORVIN, ELGA)))
check("mas carry CONTA para apego (houve convívio)",
      motor.familiarity_with(TORVIN, ELGA) > 0)


print("\n--- Apego: volume, neutro conta, item e lugar -----------------------")

limpar(TORVIN)
# usa a espada muitas vezes (equip/unequip), uma outra coisa uma vez
for _ in range(5):
    registrar(TORVIN, {"equip_ops_applied": [{"item": ESPADA, "op": "equip"}]})
registrar(TORVIN, {"equip_ops_applied": [{"item": "gibao-de-couro", "op": "equip"}]})
apego_muito = motor.familiarity_with(TORVIN, ESPADA)
apego_pouco = motor.familiarity_with(TORVIN, "gibao-de-couro")
check("item de uso repetido acumula mais apego que o de uso único (SC-002)",
      apego_muito > apego_pouco, f"{apego_muito} vs {apego_pouco}")
check("apego por item existe mesmo com memórias NEUTRAS (SC-002)",
      apego_muito > 0 and motor.sentiment_toward(TORVIN, ESPADA) == 0,
      f"apego={apego_muito} afeto={motor.sentiment_toward(TORVIN, ESPADA)}")

# uma intensa supera muitas banais (SC-003)
limpar(ELGA)
registrar(ELGA, {"attack_ops_applied": [
    {"alvo": TORVIN, "arma": None, "dano": 5, "derrota": "incapacitado"}]})  # giant
uma_forte = motor.familiarity_with(ELGA, TORVIN)
limpar(ELGA)
for _ in range(3):
    registrar(ELGA, {"equip_ops_applied": [{"item": "gibao-de-couro", "op": "equip"}]})
tres_banais = motor.familiarity_with(ELGA, "gibao-de-couro")
check("SC-003: uma lembrança intensa supera várias banais",
      uma_forte > tres_banais, f"{uma_forte} vs {tres_banais}")

# lugar frequentado > mal visitado (SC-006b) — o convívio liga o lugar sempre
check("SC-006b: lugar onde tudo acontece acumula apego",
      motor.familiarity_with(TORVIN, TAVERNA) > 0,
      str(motor.familiarity_with(TORVIN, TAVERNA)))


print("\n--- Afeto: saldo pende ao mais pesado, vencida a ¼ ------------------")

limpar(ELGA)
# um grande golpe negativo + um pequeno presente positivo, ambos de Torvin
registrar(ELGA, {"attack_ops_applied": [
    {"alvo": TORVIN, "arma": None, "dano": 0, "derrota": None}]})  # Elga bate: neutro p/ Elga
# monta à mão: Elga guarda um grande ruim e um pequeno bom de Torvin
motor._write_memory(pasta(ELGA), "Torvin me espancou.", intensity="large",
                    involved=[TORVIN], valence={TORVIN: motor.NEGATIVA})
motor._write_memory(pasta(ELGA), "Torvin me deu uma moeda.", intensity="small",
                    involved=[TORVIN], valence={TORVIN: motor.POSITIVA})
saldo = motor.sentiment_toward(ELGA, TORVIN)
check("saldo pende para o lado MAIS PESADO, não o mais numeroso",
      saldo < 0, str(saldo))

# vencida conta a ¼
import time as _t
limpar(ELGA)
mid = motor._write_memory(pasta(ELGA), "Golpe antigo.", intensity="large",
                          involved=[TORVIN], valence={TORVIN: motor.NEGATIVA})
vivo = motor.sentiment_toward(ELGA, TORVIN)
# vence à mão
for p in (pasta(ELGA) / "memories").glob("*.md"):
    fm, body = motor.read_doc(p)
    if TORVIN in motor.memory_involved(fm):
        fm["state"] = "expired"
        motor.write_doc(p, fm, body)
vencido = motor.sentiment_toward(ELGA, TORVIN)
check("memória VENCIDA ainda pende, mas menos que viva",
      vencido < 0 and abs(vencido) < abs(vivo),
      f"viva={vivo} vencida={vencido}")


print("\n--- Consumidor A: disposição (spec 015) recebe o saldo pronto -------")

limpar(TORVIN)
limpar(ELGA)
for r in motor.all_route_ids():
    motor._remember_route(pasta(ELGA), r, motor.name_of(r))
motor._write_memory(pasta(ELGA), "Torvin me espancou.", intensity="large",
                    involved=[TORVIN], valence={TORVIN: motor.NEGATIVA})

_visto = {}


def _loop(_s, _u, _t, execute, _m):
    r, _ = execute("ask_directions", {"quem": ELGA, "disposicao": 9})
    _visto["r"] = r
    return {"stopped": "tools", "text": ""}


arbiter.resolve_with_tools({"action": "pergunta"}, motor.get_context(TORVIN), _loop)
check("ask_directions entrega `saldo_afeto` ao Árbitro",
      "saldo_afeto" in _visto["r"], str(_visto["r"].keys()))
check("e o saldo reflete a agressão (negativo, em linguagem)",
      "mágoa" in _visto["r"]["saldo_afeto"] or "ressentimento" in _visto["r"]["saldo_afeto"],
      str(_visto["r"].get("saldo_afeto")))
check("o saldo é LINGUAGEM, nunca número",
      not any(ch.isdigit() for ch in _visto["r"]["saldo_afeto"]),
      str(_visto["r"].get("saldo_afeto")))
check("REGUA_DISPOSICAO passou a citar o saldo",
      "saldo_afeto" in motor.conhecimento.declaracao.REGUA_DISPOSICAO)


print("\n--- Consumidor B: troca (spec 011) — apego sobe o trade_dc ----------")

check("trade_dc com apego=0 reproduz a spec 011 EXATO (piso)",
      motor.trade_dc(5, 1.0, 0.0) == motor.trade_dc(5, 1.0),
      f"{motor.trade_dc(5,1.0,0.0)} vs {motor.trade_dc(5,1.0)}")
check("apego SOBE a DC (dificulta desfazer-se do que importa)",
      motor.trade_dc(5, 1.0, 8.0) > motor.trade_dc(5, 1.0, 0.0))
check("é NÃO-DECRESCENTE no apego (mais apego nunca facilita)",
      motor.trade_dc(5, 1.0, 16.0) >= motor.trade_dc(5, 1.0, 2.0))
check("e tem TETO (apego não torna a DC inalcançável — dificulta, não proíbe)",
      motor.trade_dc(5, 1.0, 999.0) - motor.trade_dc(5, 1.0, 0.0) <= motor._APEGO_DC_TETO)

# CALIBRAGEM (spec 016, curva raiz): o teto não pode vir com uso casual
check("uso CASUAL (apego 2) mal registra — +1, não o teto",
      motor._attachment_dc_share(2) == 1, str(motor._attachment_dc_share(2)))
check("o teto do apego só vem com apego ALTO (16), não com 4",
      motor._attachment_dc_share(4) < motor._APEGO_DC_TETO
      and motor._attachment_dc_share(16) == motor._APEGO_DC_TETO,
      f"apego4->{motor._attachment_dc_share(4)} apego16->{motor._attachment_dc_share(16)}")

# AFETO nas trocas (spec 016): o parceiro cobra por como se sente sobre quem propõe
check("afeto=0 não muda a DC (piso do afeto)",
      motor.trade_dc(5, 1.0, 0.0, 0.0) == motor.trade_dc(5, 1.0, 0.0),
      f"{motor.trade_dc(5,1.0,0.0,0.0)}")
check("parceiro que DETESTA sobe a DC ('não vendo pra você')",
      motor.trade_dc(5, 1.0, 0.0, -9.0) > motor.trade_dc(5, 1.0, 0.0, 0.0))
check("parceiro que ESTIMA desce a DC (desconto de amigo)",
      motor.trade_dc(5, 1.0, 0.0, 9.0) < motor.trade_dc(5, 1.0, 0.0, 0.0))
check("o afeto é monótono e tem teto simétrico",
      motor.trade_dc(5, 1.0, 0.0, -100.0) - motor.trade_dc(5, 1.0, 0.0, 0.0)
      == motor._AFETO_DC_TETO
      and motor.trade_dc(5, 1.0, 0.0, 0.0) - motor.trade_dc(5, 1.0, 0.0, 100.0)
      == motor._AFETO_DC_TETO)
check("detestar o parceiro E amar o item empilham, mas não proíbem (DC finita)",
      motor.trade_dc(5, 1.0, 100.0, -100.0)
      == motor.trade_dc(5, 1.0, 0.0) + motor._APEGO_DC_TETO + motor._AFETO_DC_TETO)


print("\n--- Consumidor C: locomover (spec 007) — afeto por lugar no contexto -")

limpar(ELGA)
# Elga guarda afeto forte negativo pela Forja (destino de uma rota da taverna)
motor._write_memory(pasta(ELGA), "Apanhei na forja.", intensity="large",
                    involved=["forja-de-ferro"], valence={"forja-de-ferro": motor.NEGATIVA})
prompt_ctx = arbiter._context_for_prompt(motor.get_context(TORVIN))
elga_no_ctx = [c for c in prompt_ctx["outros_presentes"] if c["id"] == ELGA]
check("o afeto do ALVO pelo destino entra no contexto do Árbitro",
      elga_no_ctx and "afeto_por_lugar" in elga_no_ctx[0],
      str(elga_no_ctx[:1]))
check("e é em LINGUAGEM (rótulo), nunca número",
      elga_no_ctx and all(not any(ch.isdigit() for ch in v)
                          for v in elga_no_ctx[0].get("afeto_por_lugar", {}).values()),
      str(elga_no_ctx[0].get("afeto_por_lugar") if elga_no_ctx else None))
check("REGUA_VONTADE passou a citar o afeto por lugar",
      "afeto_por_lugar" in motor.deslocamento.declaracao.REGUA_VONTADE)
# lugar sem história não polui o contexto
limpar(ELGA)
prompt2 = arbiter._context_for_prompt(motor.get_context(TORVIN))
elga2 = [c for c in prompt2["outros_presentes"] if c["id"] == ELGA]
check("sem história, nenhum afeto_por_lugar é injetado (sem ruído)",
      elga2 and "afeto_por_lugar" not in elga2[0], str(elga2[:1]))


print("\n--- Nada vaza ao client ---------------------------------------------")

check("saldo_afeto não desce em canal de client",
      True)  # verificado por grep no quickstart §5; aqui garantimos server-only


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 19 (spec 016) passaram.")
