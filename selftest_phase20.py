"""Auto-teste da Fase 20 — Boato e Reputação (spec 017).

Cobre:
  - GRAVAÇÃO: 1º→2º (nomeia), 2º→3º ("dizem por aí", anônimo); intensidade decai;
    valência copiada; sujeitos = todo o episódio
  - o SIGILO (SC-013): `ouvido_de` (a origem do 3º grau) NÃO sai em nada surfaçado
    ao Árbitro nem ao client; a cadeia é rastreável só no arquivo
  - o PORTÃO: extremos sem dado; nao_confiou com atitude; caído indisponível
  - a REPUTAÇÃO: quem ouviu pende menos que quem viveu; acumula; boato esfria antes
  - o ELO pelo Árbitro: ask_about → hear_about, citação conferida

Usa o WORLD REAL (11 personagens) copiado para tmpdir — o fixture só tem 2, e a
cadeia A→B→C exige mais. Memórias são limpas por personagem antes de cada bloco.

Uso:  python3 server/selftest_phase20.py
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

# spec 023: estas fases precisam de NPCs que só existem no SAVE. Para NUNCA testar
# contra world/ (regra do projeto), semeamos versões LIMPAS no tmp — isoladas, sem
# tocar o fixture compartilhado (que outras fases assertam).
def _seed_char(_loc, _cid, _name, _cha=12):
    _d = _tmp / "world" / _loc / _cid
    _d.mkdir(parents=True, exist_ok=True)
    (_d / "character.md").write_text(
        "---\ntype: character\nid: %s\nname: %s\ncontrolled_by: player_local\n"
        "weight_kg: 72\nattributes:\n  STR: 11\n  DEX: 11\n  CON: 11\n  INT: 12\n"
        "  WIS: 12\n  CHA: %d\nskills:\n  geral: 2\nstatus:\n  hp: 60\n  hp_max: 60\n"
        "  hunger: saciado\n  fatigue: leve\n  action: parado\n  mood: neutro\n"
        "  conditions: []\norigin: editorial\n---\n\n%s (fixture de apoio, spec 023).\n"
        % (_cid, _name, _cha, _name), encoding="utf-8")
_seed_char("taverna-do-gancho", "obadiah-mascate", "Obadiah, o Mascate", 13)
_seed_char("forja-de-ferro", "bram-pescador", "Bram, o Pescador", 12)
_seed_char("forja-de-ferro", "draven-vigia", "Draven, o Vigia", 10)
_seed_char("forja-de-ferro", "renn-trovador", "Renn, o Trovador", 12)
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app as server_app  # noqa: E402
import arbiter  # noqa: E402
import motor  # noqa: E402
import selftest_helpers  # noqa: E402

FAILS = []

A = "torvin-ferreiro"        # viveu
B = "bram-pescador"          # ouve de A (2º), conta a C
C = "obadiah-mascate"        # ouve de B (3º)
ALVO = "draven-vigia"        # o sujeito do episódio (ausente das conversas)
EPISODIO = "Draven roubou a bolsa no cais e sumiu na névoa"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def pasta(cid):
    return motor.find_character_folder(cid)


def limpar(*cids):
    for cid in cids:
        d = pasta(cid) / "memories"
        if d.is_dir():
            for p in d.glob("*.md"):
                p.unlink()


def dado(v):
    motor._roll_d20 = lambda: v


def ult_mem(cid):
    fm, body = motor.read_doc(sorted((pasta(cid) / "memories").glob("*.md"))[-1])
    return fm, body


def res(**parts):
    base = {"narrative_hint": "x", "movement": None, "mutations": [], "lido": [],
            "informes": [], "falas": [], "hearsay_ops": [], "item_transfers": [],
            "equip_ops": [], "lock_ops": [], "persuade_ops": [], "attack_ops": [],
            "carry_ops": [], "trade_ops": [], "learn_ops": [], "travel_ops": [],
            "memories": []}
    base.update(parts)
    return base


print("\n--- Gravação: 1º → 2º → 3º grau -------------------------------------")

limpar(A, B, C)
# A vive o episódio (1º grau, large, negativo por Draven)
motor._write_memory(pasta(A), f"Eu vi. {EPISODIO}.", intensity="large",
                    involved=[ALVO], valence={ALVO: motor.NEGATIVA})
fonteA, _ = ult_mem(A)
# A conta a B → 2º grau
motor._record_hearsay(pasta(B), fonteA, ALVO, EPISODIO, A)
memB, bodyB = ult_mem(B)
check("2º grau NOMEIA o narrador no corpo",
      motor.name_of(A).split(",")[0] in bodyB and "me contou" in bodyB, bodyB)
check("2º grau: narrador ENTRA em involved",
      A in motor.memory_involved(memB), str(motor.memory_involved(memB)))
check("2º grau: intensidade uma faixa abaixo (large→medium)",
      memB.get("intensity") == "medium", str(memB.get("intensity")))
check("2º grau: valência COPIADA (Draven negativo)",
      motor.memory_valence(memB).get(ALVO) == motor.NEGATIVA)
check("2º grau: ouvido_de = A", memB.get("ouvido_de") == A)

# B conta a C → 3º grau
motor._record_hearsay(pasta(C), memB, ALVO, EPISODIO, B)
memC, bodyC = ult_mem(C)
check("3º grau: corpo é ANÔNIMO ('dizem por aí')", "Dizem por aí" in bodyC, bodyC)
check("3º grau: narrador NÃO entra em involved (só o sujeito)",
      motor.memory_involved(memC) == [ALVO], str(motor.memory_involved(memC)))
check("3º grau: intensidade decaiu de novo (medium→small)",
      memC.get("intensity") == "small", str(memC.get("intensity")))
check("3º grau: ouvido_de = B (secreto, no arquivo)", memC.get("ouvido_de") == B)
check("o CONTEÚDO do episódio atravessa verbatim os três graus",
      EPISODIO in bodyB and EPISODIO in bodyC)


print("\n--- SIGILO (SC-013): a origem do 3º grau não sai do arquivo ----------")

ra = motor.remembered_about(C, ALVO)
check("remembered_about(C, alvo) NÃO tem a chave ouvido_de",
      ra and "ouvido_de" not in ra[0], str(list(ra[0].keys()) if ra else []))
check("e o id do narrador (B) não aparece em nada que ela devolve",
      not any(B in str(m) for m in ra))
prosa = motor.prose_of(C, memC.get("id")) or ""
check("prose_of do 3º grau não traz o nome de B (corpo anônimo)",
      B not in prosa and motor.name_of(B).split(",")[0] not in prosa, prosa[:80])
# o contexto de cena de C (o que vai ao Árbitro) não deve carregar ouvido_de
ctx = arbiter._context_for_prompt(motor.get_context(C))
check("o contexto do Árbitro para C não vaza ouvido_de/B",
      "ouvido_de" not in str(ctx) and B not in str(ctx.get("outros_presentes", "")))
check("MAS a cadeia é rastreável NO ARQUIVO: C.ouvido_de=B, B.ouvido_de=A",
      memC.get("ouvido_de") == B and memB.get("ouvido_de") == A)


print("\n--- Reputação: quem ouviu pende menos que quem viveu ----------------")

check("SC-005: afeto A(viveu) > B(2º) > C(3º) por Draven, mesmo sinal",
      motor.sentiment_toward(A, ALVO) < motor.sentiment_toward(B, ALVO)
      < motor.sentiment_toward(C, ALVO) < 0,
      f"A={motor.sentiment_toward(A,ALVO)} B={motor.sentiment_toward(B,ALVO)} "
      f"C={motor.sentiment_toward(C,ALVO)}")
# acumular: C ouve o mesmo de outra boca
_D = "renn-trovador"
limpar(_D)
motor._write_memory(pasta(_D), f"Eu vi. {EPISODIO}.", intensity="large",
                    involved=[ALVO], valence={ALVO: motor.NEGATIVA})
fonteD, _ = ult_mem(_D)
antes = motor.sentiment_toward(C, ALVO)
motor._record_hearsay(pasta(C), fonteD, ALVO, EPISODIO, _D)
check("SC-006: ouvir o mesmo de outra boca ACUMULA a reputação",
      motor.sentiment_toward(C, ALVO) < antes,
      f"{antes} -> {motor.sentiment_toward(C,ALVO)}")


print("\n--- O portão da confidência -----------------------------------------")

# reconstrói a memória-fonte de A para o elo pelo Árbitro
limpar(A, B)
motor._write_memory(pasta(A), f"Eu vi. {EPISODIO}.", intensity="large",
                    involved=[ALVO], valence={ALVO: motor.NEGATIVA})

# nota 0 recusa sem dado
dado(20)  # dado alto não salva o 0
out = motor.apply_resolution(B, res(
    lido=[f"Eu vi. {EPISODIO}."],
    hearsay_ops=[{"fonte": A, "sobre": ALVO, "trecho": EPISODIO,
                  "disposicao": 0, "atitude": "cerra os punhos e cala"}]))
regras = {r.get("regra") for r in out.get("rejected") or []}
check("nota 0 recusa (nao_confiou), sem gravar reconto",
      "nao_confiou" in regras and not out.get("hearsay_ops_applied"), str(regras))
check("nao_confiou carried_item_ids a atitude para A Mente narrar",
      any((r.get("valores") or {}).get("atitude")
          for r in out.get("rejected") or []))
# coerência da narração (passo 3 da review): a recusa chega ao client como falha
# de CONVERSA, com o MOTIVO na frase — nunca "'isso' não foi movido" sem causa
_fbol = server_app.inworld_failures(out.get("rejected") or [])
check("a recusa de boato vira falha de CONVERSA com a atitude (não silêncio)",
      any("não abriu o que sabe" in f.get("o_que_falhou", "")
          and "punhos" in f.get("o_que_falhou", "") for f in _fbol),
      str(_fbol))

# nota 10 conta sem dado
limpar(B)
# item 52: a op leva as FONTES (o lastro). É delas que a primitiva tira involved,
# valência, intensidade e grau — e uma op SEM elas é justamente a forjada, testada
# logo abaixo.
_fontes_A = [fm for fm in motor._iter_memories(A)
             if ALVO in motor.memory_involved(fm)]
out = motor.apply_resolution(B, res(
    lido=[f"Eu vi. {EPISODIO}."],
    hearsay_ops=[{"fonte": A, "sobre": ALVO, "trecho": EPISODIO,
                  "fontes_reconto": _fontes_A,
                  "disposicao": 10, "atitude": "fala baixo, olhando os lados"}]))
check("nota 10 conta: reconto gravado em B",
      bool(out.get("hearsay_ops_applied")) and
      any(motor.memory_ouvido_de(m) == A for m in motor._iter_memories(B)),
      str(out.get("rejected")))

# citação que a fonte não disse
limpar(B)
out = motor.apply_resolution(B, res(
    lido=[f"Eu vi. {EPISODIO}."],
    hearsay_ops=[{"fonte": A, "sobre": ALVO, "trecho": "Draven salvou uma criança",
                  "disposicao": 10, "atitude": "x"}]))
check("citação que a fonte não disse → citacao_nao_confere",
      any(r.get("regra") == "citacao_nao_confere" for r in out.get("rejected") or []))


print("\n--- Spec 034: ask_about resolve numa chamada só (sem hear_about) -----")

# o elo exige presença: A (torvin) e o ouvinte precisam estar no mesmo lugar.
# No world real, obadiah está na taverna com torvin — bram (B) está na forja.
OUVINTE = "obadiah-mascate"

_ctx0 = motor.get_context(OUVINTE)
_tools0 = {t["name"] for t in arbiter.build_tools(_ctx0)}
check("`hear_about` SAIU do manifest (spec 034: absorvida por ask_about)",
      "hear_about" not in _tools0, str(_tools0))
_aa = [t for t in arbiter.build_tools(_ctx0) if t["name"] == "ask_about"][0]
# spec 043: `disposicao` SAIU da face — é JUÍZO (ver selftest_phase18/44).
check("`ask_about` expõe só a ESCOLHA; `disposicao` (juízo) não desce",
      _aa["parameters"]["required"] == ["quem", "sobre"]
      and "disposicao" not in _aa["parameters"]["properties"],
      str(_aa["parameters"]))

limpar(A, OUVINTE)
motor._write_memory(pasta(A), f"Eu vi. {EPISODIO}.", intensity="large",
                    involved=[ALVO], valence={ALVO: motor.NEGATIVA})

# ITEM 52: o reconto agora pede ao mundo o Z (o que o informante DIZ), e isso passa
# pelo `ctx.ask`. A suíte roda SEM MODELO de propósito, então o Z é injetado — mesmo
# padrão do `loop_fn`, que também é um dublê. Sem injetar, `ask` devolve "" e o
# `ask_about` recusa, que é a degradação honesta (e ALTA, via `juizo_indisponivel`).
def _ask_z(_system, _user):
    return '{"conta": "Contei o que sei dele, do jeito que me lembro."}'

_visto_lista = []

dado(20)
_r = selftest_helpers.resolve_scripted(
    {"action": "pergunta de Draven"}, motor.get_context(OUVINTE),
    [("ask_about", {"quem": A, "sobre": ALVO, "disposicao": 8})],
    ask=_ask_z, captured=_visto_lista)
_visto = {"r": _visto_lista[0]}
check("ask_about surfacea episódios e põe a prosa em lido",
      _visto["r"].get("episodios") and _r.get("lido"))
check("ask_about NÃO surfacea ouvido_de nos episódios",
      all("ouvido_de" not in e for e in _visto["r"]["episodios"]))
check("o reconto JÁ foi gravado NA MESMA chamada — sem hear_about nenhum",
      any(motor.memory_ouvido_de(m) == A for m in motor._iter_memories(OUVINTE)),
      str(list(motor._iter_memories(OUVINTE))))
check("a resposta confirma o registro (`registrado`), sem número nenhum",
      _visto["r"].get("registrado") and "disposicao" not in str(_r.get("informes")),
      str(_visto["r"]))

# nota 0: recusa sem dado, nada registrado
limpar(OUVINTE)
_visto2_lista = []

# spec 043: a nota vem do MUNDO (`ctx.ask`), não de args.
_r2 = selftest_helpers.resolve_scripted(
    {"action": "pergunta"}, motor.get_context(OUVINTE),
    [("ask_about", {"quem": A, "sobre": ALVO, "disposicao": 0})],
    ask=lambda _s, _u: "0", captured=_visto2_lista)
_visto2 = {"r": _visto2_lista[0]}
check("disposicao 0 recusa SEM dado, nada registrado",
      _visto2["r"].get("erro")
      and not any(motor.memory_ouvido_de(m) == A
                  for m in motor._iter_memories(OUVINTE)),
      str(_visto2))
check("mesmo na recusa, o contexto (saldo/lembrança) chega ao Árbitro",
      "saldo_afeto" in _visto2["r"], str(_visto2["r"].keys()))


print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): " + ", ".join(FAILS))
    sys.exit(1)
print("todos os checks da Fase 20 (spec 017) passaram.")
