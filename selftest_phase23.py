"""Auto-teste da Fase 23 — Turno de fase única (spec 020).

Dirige `selftest_helpers.resolve_scripted` com roteiros e prova o que a fase única
entrega: a ORDEM das chamadas é a sequência do mundo, e a próxima tool lê o que a
anterior mudou. Cobre:
  - atacar→pedir vs pedir→atacar: a ordem muda o que o informante lembra (US1)
  - presente→persuadir: a persuasão lê o afeto que a entrega gravou (US1, benigno)
  - resposta coerente com a mistura sucesso+falha (US2, FR-013)
  - turno de uma tool só: idêntico ao esperado (SC-004)
  - o feito É o aplicado: a tool aplica no ato, contra os arquivos (US2)

Roda sobre cópia do fixture. Uso:  python3 server/selftest_phase23.py
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
import selftest_helpers  # noqa: E402

FAILS = []
TOR = "torvin-ferreiro"
ELGA = "elga-taverneira"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def limpa_memorias(cid):
    d = motor.find_character_folder(cid) / "memories"
    if d.is_dir():
        for p in d.glob("*.md"):
            p.unlink()


def rodar(action, script):
    """Roda o roteiro via selftest_helpers e devolve (outcome, por_nome), onde
    por_nome[nome] é a lista de retornos daquele nome, na ordem — mesma forma
    que o antigo `loop(script).capt` oferecia, para inspecionar o que uma tool
    seguinte enxergou do que a anterior mudou."""
    captured = []
    outcome = selftest_helpers.resolve_scripted(
        {"action": action}, motor.get_context(TOR), script, captured=captured)
    por_nome = {}
    for (n, _a), r in zip(script, captured):
        por_nome.setdefault(n, []).append(r)
    return outcome, por_nome


motor._roll_d20 = lambda: 18  # golpes/rolagens fortes por padrão

print("--- US1: a ORDEM das chamadas é a sequência do mundo --------------------")

# atacar → pedir: o pedido vê o golpe do MESMO turno
limpa_memorias(ELGA)
_, por_nome = rodar("golpeia e pergunta", [
    ("attack", {"alvo": ELGA, "vantagem": 5}),
    ("ask_directions", {"quem": ELGA, "disposicao": 9}),
    ("narrate", {"narrative_hint": "golpeia e pergunta"})])
ask_ret = (por_nome.get("ask_directions") or [{}])[0]
lembra = ask_ret.get("lembra_de_voce") or []
check("atacar→pedir: o informante JÁ lembra do golpe no mesmo turno",
      any("golpeou" in (m.get("content") or "").lower() for m in lembra), str(lembra)[:120])
check("atacar→pedir: o afeto do informante já pesa contra quem golpeou",
      ask_ret.get("saldo_afeto") == "guarda mágoa", str(ask_ret.get("saldo_afeto")))

# pedir → atacar: no momento do pedido NÃO havia golpe (a ordem inverte o efeito)
limpa_memorias(ELGA)
_, por_nome2 = rodar("pergunta e golpeia", [
    ("ask_directions", {"quem": ELGA}),
    ("attack", {"alvo": ELGA, "vantagem": 5}),
    ("narrate", {"narrative_hint": "pergunta e golpeia"})])
ask_ret2 = (por_nome2.get("ask_directions") or [{}])[0]
check("pedir→atacar: no pedido NÃO havia golpe (a ordem decidiu)",
      not (ask_ret2.get("lembra_de_voce") or [])
      and ask_ret2.get("saldo_afeto") != "guarda mágoa",
      str(ask_ret2.get("lembra_de_voce")))

print("\n--- T013: portão DETERMINÍSTICO de violência (não confia na nota do modelo) --")

limpa_memorias(ELGA)
motor.apply_resolution(TOR, {"attack_ops": [{"alvo": ELGA, "vantagem": 8}],
                             "narrative_hint": "golpeia a Elga"})
check("após o golpe, has_trauma_from(Elga, Torvin) = True",
      motor.has_trauma_from(ELGA, TOR))
_tor_fm, _ = motor.read_doc(motor.find_character_folder(TOR) / "character.md")
_passou, _ = motor.roll_disposicao(TOR, _tor_fm, ELGA, nota=9)  # Árbitro deu nota ALTA
check("mesmo com nota 9 do Árbitro, o Motor FORÇA a recusa (quem apanhou não indica)",
      not _passou)
check("sem violência, o portão NÃO fecha por si (nota alta ainda passa)",
      motor.roll_disposicao(TOR, _tor_fm, "obadiah-mascate", nota=9)[0])

print("\n--- US1: presente aplicado por-op cria afeto no mesmo turno (benigno) ---")

# Torvin entrega a bolsa (que ele já tem) à Elga; o afeto dela por ele sobe NO ATO
# — é isto que uma persuasão seguinte no mesmo turno leria (spec 016 via 020).
limpa_memorias(ELGA)
rodar("entrega a bolsa à Elga", [
    ("give", {"item": "bolsa-de-couro", "to": ELGA}),
    ("narrate", {"narrative_hint": "entrega a bolsa"})])
check("presente aplicado por-op: o afeto da Elga por Torvin já é positivo no turno",
      motor.sentiment_toward(ELGA, TOR) > 0, f"{motor.sentiment_toward(ELGA, TOR):+.2f}")

print("\n--- US2: o feito É o aplicado (a tool muta no ato) ----------------------")

tav = motor.WORLD_DIR / "taverna-do-gancho"
out4, _ = rodar("pega a calça", [
    ("take", {"item": "calca-de-linho"}),
    ("narrate", {"narrative_hint": "pega a calça"})])
check("a tool aplicou nos ARQUIVOS no ato (calça saiu do chão para o Torvin)",
      not (tav / "calca-de-linho").exists()
      and (motor.find_character_folder(TOR) / "calca-de-linho").exists())
check("o outcome já vem aplicado (item_transfers_applied), não uma fila a aplicar",
      out4.get("item_transfers_applied") == [{"item": "calca-de-linho", "to": TOR}]
      and out4.get("_applied_in_loop") is True)

print("\n--- US2: resposta coerente com a mistura sucesso+falha (FR-013) ---------")

# 1ª tool aplica (mutate mood), 2ª falha (item inexistente) — a resposta reflete AMBOS
out5, _ = rodar("muta e erra", [
    ("mutate", {"target": TOR, "path": "status.mood", "value": "alerta"}),
    ("take", {"item": "machado-fantasma"}),
    ("narrate", {"narrative_hint": "fica alerta, erra o machado"})])
tor5, _ = motor.read_doc(motor.find_character_folder(TOR) / "character.md")
sucesso = (tor5.get("status") or {}).get("mood") == "alerta"
falha = any(r.get("item") == "machado-fantasma"
            for r in out5.get("tool_rejections") or [])
check("mistura: o sucesso ficou no mundo (mood=alerta) E a falha está relatada",
      sucesso and falha, f"sucesso={sucesso} falha={falha}")
check("a falha NÃO desfez o sucesso (o mundo ficou coerente com a mistura, FR-013)",
      sucesso and any("machado" in f for f in
                      __import__("app").inworld_failures(out5.get("tool_rejections") or [])))

print("\n--- SC-004: turno de uma tool só — desfecho esperado --------------------")

rodar("respira", [
    ("mutate", {"target": TOR, "path": "status.mood", "value": "sereno"}),
    ("narrate", {"narrative_hint": "respira fundo"})])
tor_fm, _ = motor.read_doc(motor.find_character_folder(TOR) / "character.md")
check("mutate de uma tool aplicou (mood=sereno) e nada mais mudou de sujeito",
      (tor_fm.get("status") or {}).get("mood") == "sereno")
# ---- item 53.5: ELE SE DÁ CONTA DE QUE JÁ SABE, e nem pergunta --------------
# O Irmão Tobias passou TRÊS HORAS pedindo à Nerissa o caminho do Beco das
# Sombras. A memória dele dizia "Sei o caminho: Beco das Sombras. Já o percorri, e
# os pés lembram por onde vai", e o beco estava aberto na cena — ele nunca tentou
# entrar. A pergunta não tinha o que render, e nada dizia isso a ele.
#
# A recusa é GRATUITA de propósito: ninguém se cansa de NÃO perguntar, e a decisão
# é anterior à conversa — nem chega a pedir juízo ao Árbitro.
# a Elga da fixture não conhece caminho nenhum: primeiro ELA precisa ter o que
# ensinar, senão o ramo testado (`ele já sabe TUDO que esse aí ensinaria`) nunca
# dispara — cairia no `nada_a_ensinar`, que é outro caso.
for _r in ("rua-do-mercador", "portao-lateral"):
    motor._remember_route(motor.find_character_folder(ELGA), _r, _r)
_ensinaveis = motor.directions_from(ELGA)["caminhos"]
# `directions_from` descarta caminho sem PROSA no `.md` (não haveria o que citar),
# e na fixture só um dos dois tem — um basta para o ramo testado.
check("53.5 (setup): a informante tem caminho a ensinar",
      len(_ensinaveis) >= 1, str(_ensinaveis))
_antes_fad = (motor.read_doc(motor.find_character_folder(TOR) / "character.md")[0]
              .get("status") or {}).get("fatigue")
for _c in _ensinaveis:
    motor._remember_route(motor.find_character_folder(TOR), _c["rota"], _c["nome"])
_, _por_nome53 = rodar("pergunta o caminho", [
    ("ask_directions", {"quem": ELGA, "disposicao": 9}),
    ("narrate", {"narrative_hint": "ia perguntar"})])
_r53 = (_por_nome53.get("ask_directions") or [{}])[0]
check("53.5: sabendo TODOS os caminhos dele, a pergunta não acontece",
      _r53.get("ok") is False and "já sabe" in (_r53.get("erro") or ""), str(_r53)[:150])
_depois_fad = (motor.read_doc(motor.find_character_folder(TOR) / "character.md")[0]
               .get("status") or {}).get("fatigue")
check("53.5: e é GRATUITA — não cobra fadiga de quem não perguntou",
      _antes_fad == _depois_fad, f"{_antes_fad} → {_depois_fad}")
# e continua perguntando quando há o que aprender
_folder = motor.find_character_folder(TOR) / "memories"
for _p in _folder.glob("*.md"):
    _fm, _b = motor.read_doc(_p)
    if motor.memory_kind(_fm) == motor.ROTA:
        _p.unlink()
_, _por_nome53b = rodar("pergunta", [
    ("ask_directions", {"quem": ELGA, "disposicao": 9}),
    ("narrate", {"narrative_hint": "pergunta"})])
_r53b = (_por_nome53b.get("ask_directions") or [{}])[0]
check("53.5: sem saber os caminhos, a pergunta acontece normalmente",
      _r53b.get("ok") is True, str(_r53b)[:150])


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 23 (spec 020) passaram.")
