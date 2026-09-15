#!/usr/bin/env python3
"""FASE 73 — o ciclo do compromisso, fatia 1: a fome.

Estes testes vêm ANTES da implementação de propósito. Três dos requisitos desta fatia
são invisíveis a olho nu e permanentes se vazarem:

  · o número de `parada_desde` chegando ao client (Princípio V);
  · o passo sendo riscado por quem não devia (Princípio IX);
  · o abandono que não vira memória — a lição da spec 013: evento sem valência
    declarada não vira memória de NINGUÉM, e some sem erro nenhum.

Nenhum deles quebra um teste que não os procure. Por isso eles existem.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("LOREFORGE_LOG", "0")

_falhas: list[str] = []


def ok(cond, msg):
    print(f"[{'ok  ' if cond else 'FALHA'}] {msg}")
    if not cond:
        _falhas.append(msg)


def _mundo_temporario():
    """Um mundo só para este teste — `LOREFORGE_WORLD` existe para isto."""
    tmp = tempfile.mkdtemp(prefix="phase73-")
    os.environ["LOREFORGE_WORLD"] = tmp
    return Path(tmp)


RAIZ = _mundo_temporario()
import motor  # noqa: E402  (depois de LOREFORGE_WORLD)
from motor.intencoes import primitivas as P  # noqa: E402
import app as server_app  # noqa: E402
import arbiter  # noqa: E402

PASTA = RAIZ / "lugar" / "fulano"
(PASTA / "intentions").mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# T010 — o critério fecha quando deixa de apertar, e NÃO antes
# --------------------------------------------------------------------------- #

print("\n--- o critério de fim (FR-002, FR-013a) ---")

ok(P.criterio_cumprido({"hunger": "faminto"}, "hunger") is False,
   "faminto NÃO cumpre o critério de fome")
ok(P.criterio_cumprido({"hunger": "com fome"}, "hunger") is False,
   "com fome NÃO cumpre — o rótulo intermediário também aperta")
ok(P.criterio_cumprido({"hunger": "sem fome"}, "hunger") is True,
   "sem fome CUMPRE o critério")
ok(P.criterio_cumprido({"thirst": "sedento"}, "thirst") is False,
   "sedento NÃO cumpre o critério de sede")
ok(P.criterio_cumprido({"fatigue": "descansado"}, "sleep") is True,
   "descansado CUMPRE o critério de sono (o campo é `fatigue`, a Mente diz `sleep`)")
ok(P.criterio_cumprido({"hunger": "sem fome"}, "inventado") is False,
   "critério fora do vocabulário NUNCA cumpre — não se fecha por engano")
ok(P.criterio_cumprido(None, "hunger") is False,
   "sem `needs` não cumpre — ausência não é satisfação")


# --------------------------------------------------------------------------- #
# T011 — `parada_desde` zera ao riscar, e SÓ nisso
# --------------------------------------------------------------------------- #

print("\n--- o relógio da estagnação (FR-012) ---")

iid = P.create_intention(PASTA, "Matar minha fome.\n- take Maçã\n- eat Maçã",
                         pronto_quando="hunger")
fm, _ = motor.read_doc(PASTA / "intentions" / f"{iid}.md")
ok(fm.get("pronto_quando") == "hunger", "a intenção nasce com o critério gravado")
ok(isinstance(fm.get("parada_desde"), int),
   "o relógio NASCE PARADO — um compromisso recém-firmado ainda não andou")

nascimento = fm["parada_desde"]
time.sleep(1.1)
ok(P.riscar_passo(PASTA, iid) is True, "riscar um passo funciona")
fm, _ = motor.read_doc(PASTA / "intentions" / f"{iid}.md")
ok(fm.get("passos_cumpridos") == 1, "o passo riscado conta +1")
ok(fm["parada_desde"] > nascimento,
   "riscar ZERA o relógio — é o refresh, e é o coração do mecanismo")

depois = fm["parada_desde"]
time.sleep(1.1)
fm2, _ = motor.read_doc(PASTA / "intentions" / f"{iid}.md")
ok(fm2["parada_desde"] == depois,
   "o mero PASSAR DO TEMPO não zera — o relógio conta estagnação, não idade")

ok(P.rotulo_de_parada(int(time.time())) is None,
   "acabou de andar: rótulo AUSENTE, nunca 'agora mesmo'")
agora = int(time.time())
ok(P.rotulo_de_parada(agora - 30 * 60, agora) is not None,
   "parada há muito: o rótulo aparece")
ok("voltas" in (P.rotulo_de_parada(agora - 30 * 60, agora) or ""),
   "o rótulo fala em VOLTAS, a unidade do jogo")


# --------------------------------------------------------------------------- #
# T013 — NENHUM número de `parada_desde` desce ao client (Princípio V)
# --------------------------------------------------------------------------- #

print("\n--- o segredo do relógio (Princípio V) ---")

# força a intenção a estar parada há muito, para o rótulo aparecer
fm, body = motor.read_doc(PASTA / "intentions" / f"{iid}.md")
fm["parada_desde"] = int(time.time()) - 40 * 60
motor.write_doc(PASTA / "intentions" / f"{iid}.md", fm, body)

expostas = P.get_active_intentions(PASTA)
ok(len(expostas) == 1, "a intenção ativa desce ao contexto")
entrada = expostas[0]
ok("parada" in entrada, "o RÓTULO de parada desce")
ok("parada_desde" not in entrada,
   "o NÚMERO não desce — Princípio V, e é o vazamento que nenhum outro teste pegaria")
ok(isinstance(entrada.get("parada"), str), "a parada é texto, não número")
bruto = json.dumps(entrada, ensure_ascii=False)
ok(str(fm["parada_desde"]) not in bruto,
   "o timestamp cru não aparece em lugar nenhum do que desce")
ok(entrada.get("passos_cumpridos") == 1,
   "a CONTAGEM de passos desce — é o que o prompt de executar lê")
ok(entrada.get("pronto_quando") == "hunger",
   "o critério desce (é vocabulário fechado, não id de cena)")

# e a chave some quando acabou de andar (spec 067: ausente, nunca `null`)
P.riscar_passo(PASTA, iid)
ok("parada" not in P.get_active_intentions(PASTA)[0],
   "acabou de andar: a chave é AUSENTE, nunca `null` (spec 067)")


# --------------------------------------------------------------------------- #
# T009 — as travas do nascimento (FR-003)
# --------------------------------------------------------------------------- #

print("\n--- as travas do nascimento (FR-003) ---")

T = P.travas_do_nascimento
_regra = lambda *a: (T(*a) or (None,))[0]

# Cada trava nasce de uma intenção REAL e podre, gravada no mundo (§2).
ok(_regra("Análise o contexto e decida o que achar melhor, pensando em como se "
          "manter a longo prazo", "hunger", None) == "intencao_meta",
   "META-INSTRUÇÃO barrada — o caso do Draven, ativo há semanas")
ok(_regra("Fazer um trabalho de forja, sem pressa e com cuidado", None, None)
   == "intencao_sem_criterio",
   "SEM CRITÉRIO barrada — o caso do Pip")
ok(_regra("Matar minha fome.", "inventado", None)
   == "intencao_criterio_desconhecido",
   "critério fora do vocabulário barrado")
ok(_regra("Vou aprender o caminho de Beco das Sombras com Nerissa, a Boticária",
          "hunger", "Nerissa, a Boticária") == "intencao_aponta_pra_si",
   "APONTA PARA SI barrada — o caso da Nerissa, que nasceu torta")
ok(_regra("", "hunger", None) == "intencao_vazia", "conteúdo vazio barrado")

# E O QUE TEM DE PASSAR — inclusive o compromisso desta fatia.
ok(T("Matar minha fome.", "hunger", "Draven, o Vigia") is None,
   "'matar minha fome' PASSA — não nomeia entidade externa, e é a US1 inteira. "
   "O FR-003 como escrito ('não nomeie sujeito concreto') a rejeitaria")
ok(T("Levar três maçãs a Elga, a Taverneira.", "hunger", "Draven, o Vigia") is None,
   "compromisso com outro PASSA")
ok(T("Matar minha fome comendo o que Nerissa me der.", "hunger",
     "Draven, o Vigia") is None,
   "citar OUTRO personagem pelo nome passa — só o PRÓPRIO nome barra")

# cada regra tem frase in-world, copiada de `_WHY_BY_REGRA`
from motor.io import _WHY_BY_REGRA  # noqa: E402
for regra in ("intencao_vazia", "intencao_meta", "intencao_sem_criterio",
              "intencao_criterio_desconhecido", "intencao_aponta_pra_si",
              "intencao_ja_cumprida"):
    frase = _WHY_BY_REGRA.get(regra, "")
    ok(bool(frase) and frase != regra,
       f"`{regra}` tem frase in-world — recusa nunca é silenciosa (Princípio X)")
    ok("não pode" not in frase,
       f"`{regra}` não soa como proibição de sistema — 'não pode' convida a insistir")


# --------------------------------------------------------------------------- #
# T010b — `fechar_por_criterio` fecha, e só o que devia
# --------------------------------------------------------------------------- #

print("\n--- o fechamento pelo mundo (FR-013) ---")

outra = P.create_intention(PASTA, "Aprender a forjar.", pronto_quando="thirst")
fechadas = P.fechar_por_criterio(PASTA, {"hunger": "faminto", "thirst": "sedento"})
ok(fechadas == [], "com fome e sede, nada fecha")

fechadas = P.fechar_por_criterio(PASTA, {"hunger": "sem fome", "thirst": "sedento"})
ok(len(fechadas) == 1, "a fome passou: UMA intenção fecha")
ok(fechadas[0]["id"] == iid, "fecha a CERTA — a de fome, não a de sede")
fm, _ = motor.read_doc(PASTA / "intentions" / f"{iid}.md")
ok(fm["status"] == "concluida", "o status vai para `concluida` no disco")
ok(fechadas[0].get("content"),
   "o que fechou volta COM o texto — a narração precisa dele para RELATAR "
   "(Princípio X, obrigação 2: fechamento silencioso é incompleto)")

restantes = P.get_active_intentions(PASTA)
ok(len(restantes) == 1 and restantes[0]["id"] == outra,
   "a concluída sai do contexto; a de sede continua")

# uma intenção SEM critério nunca é fechada por este caminho
velha = P.create_intention(PASTA, "Um compromisso do mundo antigo, sem critério.")
fechadas = P.fechar_por_criterio(PASTA, {"hunger": "sem fome"})
ok(all(f["id"] != velha for f in fechadas),
   "intenção sem `pronto_quando` NUNCA fecha sozinha — compatibilidade com o que "
   "já está gravado no mundo")


# --------------------------------------------------------------------------- #
# riscar respeita o estado
# --------------------------------------------------------------------------- #

print("\n--- riscar é do mundo, e respeita o estado ---")

ok(P.riscar_passo(PASTA, iid) is False,
   "não se risca passo de intenção já concluída")
ok(P.riscar_passo(PASTA, "int-que-nao-existe") is False,
   "não se risca passo de intenção inexistente")


# --------------------------------------------------------------------------- #
# T012 — o abandono VIRA MEMÓRIA (FR-015, e a lição da spec 013)
# --------------------------------------------------------------------------- #

print("\n--- o abandono vira memória (FR-015) ---")

ok(hasattr(P, "abandonar"), "existe a primitiva de abandonar")
larga = P.create_intention(PASTA, "Um plano que não anda.", pronto_quando="sleep")
antes = len(list((PASTA / "memories").glob("*.md"))) if (PASTA / "memories").exists() else 0
# `abandonar` grava memória via `remember`, que resolve a pasta pelo id do
# personagem — neste mundo de teste não há personagem registrado, então o que se
# afere aqui é o ESTADO; a memória em si é coberta pelo teste de campo (T032).
res = P.abandonar(PASTA, larga, "fulano")
ok(res is not None and res["id"] == larga, "abandonar devolve o que foi largado")
fm, _ = motor.read_doc(PASTA / "intentions" / f"{larga}.md")
ok(fm["status"] == "abandonada", "o status vai para `abandonada` no disco")
ok(P.abandonar(PASTA, larga, "fulano") is None,
   "não se abandona duas vezes — a segunda é no-op, não erro")
ok(all(i["id"] != larga for i in P.get_active_intentions(PASTA)),
   "a abandonada sai do contexto")

# a valência/intensidade viajam COM o ato (spec 038 matou as tabelas centrais)
import inspect  # noqa: E402
fonte = inspect.getsource(P.abandonar)
ok('valence=' in fonte and 'negativa' in fonte,
   "a valência viaja COM o ato — as tabelas centrais morreram na spec 038")
ok('intensity="medium"' in fonte,
   "intensidade `medium`: desistir pesa, mas não é trauma — `large`/`giant` "
   "dispararia o portão de `sofreu_trauma_de`, e largar um plano não é agressão")


# --------------------------------------------------------------------------- #
# T021 — a carência do corpo desce assumível
# --------------------------------------------------------------------------- #

print("\n--- a carência do corpo (FR-004) ---")

from motor.percepcao.consultas import _carencias_do_corpo  # noqa: E402

faminto = _carencias_do_corpo({"status": {"hunger": "faminto",
                                          "thirst": "sedento"}})
ok(any(c["pronto_quando"] == "hunger" for c in faminto),
   "quem tem fome recebe a carência de matá-la")
# `saciado` e não `"sem fome"` de propósito: `hunger_label` lê "sem fome" COMO
# "com fome" (o casamento é por substring e "fome" casa dentro). É o item 81 do
# backlog, achado implementando esta fatia, e está FORA do escopo dela.
ok(_carencias_do_corpo({"status": {"hunger": "saciado", "thirst": "hidratado",
                                   "fatigue": "descansado"}}) == [],
   "quem não tem carência nenhuma recebe lista VAZIA — a chave desce vazia, não some "
   "(spec 067: o contrato é completo por decisão, quem filtra é o conector)")
ok(all("pronto_quando" in c for c in faminto),
   "toda carência vem COM o critério que a encerraria — é o que `set_intention` pede")
ok(all(isinstance(c.get("porque"), str) for c in faminto),
   "a carência diz o PORQUÊ em rótulo, nunca em número (Princípio V)")
bruto = json.dumps(faminto, ensure_ascii=False)
ok(not any(ch.isdigit() for ch in bruto),
   "NENHUM dígito na carência — o número da fome é segredo do mundo")


# --------------------------------------------------------------------------- #
# T027 — o CASAMENTO do passo: quem risca é o mundo, e risca rígido
# --------------------------------------------------------------------------- #

print("\n--- o casamento do passo (FR-011) ---")

ok(P.passos_do_plano("Matar minha fome.\n- ir ao Cais Velho\n- comer") ==
   ["ir ao Cais Velho", "comer"],
   "o plano sai do corpo: a 1a linha e o COMPROMISSO, as de traco sao os PASSOS")
ok(P.passos_do_plano("So o compromisso, sem plano.") == [],
   "intencao sem plano nao tem passo nenhum")

cid = P.create_intention(
    PASTA, "Matar minha fome.\n- ir ao Cais Velho\n- comer o pao de centeio",
    pronto_quando="hunger")

# o ato ACEITO que casa: a viagem resolveu para `cais-velho`, e o passo pendente
# cita as duas metades do id.
r = P.casar_e_riscar(PASTA, [{"target": 'fulano', "path": "status.location",
                              "value": "cais-velho"}], 'fulano')
ok(r is not None and r["passo"] == "ir ao Cais Velho",
   "viajar para `cais-velho` risca 'ir ao Cais Velho'")
fm, _ = motor.read_doc(PASTA / "intentions" / f"{cid}.md")
ok(fm.get("passos_cumpridos") == 1, "o casamento conta +1 no plano")

# RIGIDEZ: meia referencia NAO risca. E o falso negativo aceito de proposito —
# um passo riscado a toa mantem viva para sempre a intencao que nao anda.
ok(P.casar_e_riscar(PASTA, [{"value": "forno-velho"}], 'fulano') is None,
   "`forno-velho` NAO risca 'comer o pao de centeio' — falta o alvo inteiro")
ok(P.casar_e_riscar(PASTA, [{"value": "pao-de-centeio-mofado"}], 'fulano') is None,
   "id com pedaco que o passo nao cita ('mofado') NAO risca")
ok(P.casar_e_riscar(PASTA, [{"value": "pao-de-centeio"}], 'fulano') is not None,
   "o id inteiro citado no passo RISCA — o rigor nao e cegueira")

# o ATOR nunca e alvo de casamento: ele esta em toda op.
P.create_intention(PASTA, "Nada.\n- falar com " + 'fulano', pronto_quando="hunger")
ok(P.casar_e_riscar(PASTA, [{"target": 'fulano', "path": "status.action",
                             "value": "reagiu a situacao"}], 'fulano') is None,
   "o id do PROPRIO ator nunca risca — ele e alvo de toda op")

# A PROSA NUNCA E REFERENCIA. O `value` de `status.action` e a acao escrita, e o
# `reason` e frase de mundo — casar por eles seria riscar por coincidencia de
# vocabulario, que e o falso positivo mais barato de cometer.
P.create_intention(PASTA, "Nada.\n- comer o pao", pronto_quando="hunger")
ok(P.casar_e_riscar(PASTA, [{"target": "outro", "path": "status.action",
                             "value": "comer"}], 'fulano') is None,
   "o `value` de `status.action` e PROSA, nunca referencia")
ok(P.casar_e_riscar(PASTA, [{"target": "outro", "reason": "comer"}],
                    'fulano') is None,
   "`reason` e frase de mundo, nunca referencia")

# o plano todo riscado para de consumir atos
fm, _ = motor.read_doc(PASTA / "intentions" / f"{cid}.md")
ok(fm.get("passos_cumpridos") == 2, "os dois passos do plano estao riscados")
ok(P.casar_e_riscar(PASTA, [{"value": "cais-velho"}], 'fulano') is None,
   "plano esgotado nao risca mais — nao ha passo pendente")


# --------------------------------------------------------------------------- #
# T027 (fio inteiro) — o risca acontece DE VERDADE no caminho do turno
# --------------------------------------------------------------------------- #
#
# O teste acima prova a PRIMITIVA. Este prova a LIGAÇÃO, que é onde o defeito
# caro mora: uma primitiva certa que ninguém chama é exatamente o registro
# paralelo que morre com a suíte verde. Por isso ele entra por `apply_resolution`
# — a mesma porta do jogo — e não pela função direto.

print("\n--- o fio inteiro: apply_resolution risca (FR-011) ---")

motor.write_doc(RAIZ / "lugar" / "location.md",
                {"type": "location", "id": "lugar", "name": "Lugar",
                 "size": "P", "entry_point": None, "origin": "editorial"},
                "Um lugar.")
VIZINHO = RAIZ / "lugar" / "beltrano"
VIZINHO.mkdir(parents=True, exist_ok=True)
motor.write_doc(RAIZ / "lugar" / "fulano" / "character.md",
                {"type": "character", "id": "fulano", "name": "Fulano",
                 "controlled_by": "player_local",
                 "attributes": {"STR": 10, "DEX": 10, "CON": 10,
                                "INT": 10, "WIS": 10, "CHA": 10},
                 "status": {"hp": 10, "hp_max": 10, "hunger": 20,
                            "fatigue": 20, "action": "espera",
                            "mood": "calmo", "conditions": []}},
                "O dono das intencoes de cima.")
motor.write_doc(VIZINHO / "character.md",
                {"type": "character", "id": "beltrano", "name": "Beltrano",
                 "controlled_by": "player_local",
                 "attributes": {"STR": 10, "DEX": 10, "CON": 10,
                                "INT": 10, "WIS": 10, "CHA": 10},
                 "status": {"hp": 10, "hp_max": 10, "hunger": 20,
                            "fatigue": 20, "action": "espera",
                            "mood": "calmo", "conditions": []}},
                "Um vizinho.")
fio = P.create_intention(VIZINHO, "Matar minha fome.\n- falar com Fulano",
                         pronto_quando="hunger")
out = motor.apply_resolution(
    "beltrano", {"mutations": [{"target": "fulano", "path": "status.mood",
                                "value": "surpreso"}]})
fm, _ = motor.read_doc(VIZINHO / "intentions" / f"{fio}.md")
ok(fm.get("passos_cumpridos") == 1,
   "o turno inteiro risca: `apply_resolution` chama o casamento, nao so o teste")
ok(isinstance(out.get("passo_riscado"), dict),
   "o que foi riscado volta no outcome — o mundo relata o que fez")


# --------------------------------------------------------------------------- #
# T020 (fio inteiro) — desistir pela PORTA REAL deixa memoria
# --------------------------------------------------------------------------- #
#
# `abandonar` existir nao basta: antes desta trava ela estava exportada e NINGUEM
# a chamava — A Mente encerrava por `update_intention`, o compromisso morria em
# silencio, e a suite ficava verde. Uma primitiva certa que ninguem chama e um
# registro paralelo: morto no jogo.

print("\n--- desistir pela porta real (FR-015) ---")

largar = P.create_intention(VIZINHO, "Achar o mapa perdido.\n- procurar no porao",
                            pronto_quando="hunger")
antes_mem = len(list((VIZINHO / "memories").glob("*.md"))) \
    if (VIZINHO / "memories").exists() else 0
motor.apply_resolution("beltrano", {"intentions": [
    {"intention_id": largar, "content": "Achar o mapa perdido.",
     "status": "abandonada"}]})
fm, _ = motor.read_doc(VIZINHO / "intentions" / f"{largar}.md")
ok(fm.get("status") == "abandonada", "o compromisso foi encerrado pela porta real")
depois_mem = len(list((VIZINHO / "memories").glob("*.md"))) \
    if (VIZINHO / "memories").exists() else 0
ok(depois_mem > antes_mem,
   "desistir NAO deixou memoria — o `set_intention(status=abandonada)` passou por "
   "fora de `abandonar`, e o compromisso morreu em silencio")


# --------------------------------------------------------------------------- #
# Item 81 — o rotulo canonico tem de ser lido de volta como ELE MESMO
# --------------------------------------------------------------------------- #
#
# Achado dirigindo o mundo real, nao pela suite: quatro personagens (draven,
# nerissa, vranna, torvin-britador) tinham `hunger: sem fome` gravado, e
# `hunger_label` devolvia "com fome" — a marca solta "fome" casa dentro de
# "sem fome". Nao era cosmetico: o criterio desta fatia confere JUSTAMENTE esse
# rotulo, entao o compromisso de matar a fome nunca fecharia para eles, e a
# SC-001 seria medida contra um mundo que nao pode passar.
#
# A invariante que fecha o buraco de vez, e que vale para toda tabela de rotulo:
# a SAIDA e uma entrada valida, e cai no mesmo balde.

print("\n--- a idempotencia do rotulo (item 81) ---")

from motor.fisica.primitivas import hunger_label, thirst_label  # noqa: E402

for bruto in ("faminto", "com fome", "sem fome", "saciado", "extremo",
              "morrendo de fome", "com muita fome", ""):
    lab = hunger_label({"status": {"hunger": bruto}})
    ok(hunger_label({"status": {"hunger": lab}}) == lab,
       f"fome {bruto!r} -> {lab!r} e lido de volta como ele mesmo")

for bruto in ("sedento", "com sede", "sem sede", "hidratado", "desidratado", ""):
    lab = thirst_label({"status": {"thirst": bruto}})
    ok(thirst_label({"status": {"thirst": lab}}) == lab,
       f"sede {bruto!r} -> {lab!r} e lido de volta como ele mesmo")

ok(hunger_label({"status": {"hunger": "sem fome"}}) == "sem fome",
   "quem o mundo disse que NAO tem fome nao volta a ter — o caso dos quatro")
ok(criterio_cumprido_de := P.criterio_cumprido(
       {"hunger": hunger_label({"status": {"hunger": "sem fome"}})}, "hunger"),
   "e com o rotulo certo o compromisso de fome FECHA (SC-001 deixa de ser inmedivel)")


# --------------------------------------------------------------------------- #
# FR-007 — o passo que nao nomeia ato nenhum
# --------------------------------------------------------------------------- #
#
# O caso do Tobias, literal e ativo no mundo: "fazer um inventario completo dos
# frascos de vidro". Nasceu impossivel e nada percebeu.

print("\n--- o passo sem verbo (FR-007) ---")

VERBOS = ["take", "eat", "travel_to", "forge_weapon", "examine"]

ok(P.passos_sem_verbo("Matar minha fome.\n- take o pao\n- eat o pao", VERBOS) == [],
   "plano feito de verbos do mundo passa inteiro")
ok(P.passos_sem_verbo(
       "Inventario.\n- fazer um inventario completo dos frascos de vidro",
       VERBOS) == ["fazer um inventario completo dos frascos de vidro"],
   "o passo do Tobias e reprovado: nao ha ato nenhum ali")

# A CORRECAO AO FR-007: a regua e o VOCABULARIO DO MUNDO, nao a face da cena. Um
# plano que atravessa cenas e bom, e validar contra a face rejeitaria justamente os
# melhores — `forge_weapon` nao esta na face de quem ainda esta na praca.
ok(P.passos_sem_verbo(
       "Forjar a lamina.\n- travel_to Forja de Ferro\n- forge_weapon lamina",
       VERBOS) == [],
   "plano que ATRAVESSA cenas passa — a regua e o mundo, nao a face de agora")

ok(P.passos_sem_verbo("So o compromisso, sem plano.", VERBOS) == [],
   "compromisso sem plano nao tem passo a reprovar")
ok(P.passos_sem_verbo("Qualquer coisa.\n- inventar", []) == [],
   "sem vocabulario nao se reprova no escuro — regua ausente nao e regua zero")
ok(P.passos_sem_verbo("Comer.\n- Take a maca", VERBOS) == [],
   "o casamento e por palavra, insensivel a caixa")
ok(P.passos_sem_verbo("Comer.\n- retaken o pao", VERBOS) ==
   ["retaken o pao"],
   "`take` DENTRO de outra palavra nao conta como verbo")


# --------------------------------------------------------------------------- #
# US4 / FR-004 e FR-005 — a carencia do MUNDO desce pela MESMA vista
# --------------------------------------------------------------------------- #

print("\n--- a carencia do mundo (US4) ---")

from motor.percepcao.consultas import (_carencias_do_corpo, _pecas_paradas,  # noqa: E402
                                       _rotulo_da_peca)
from motor import trabalho  # noqa: E402

# uma peca DELE, no meio do caminho, no lugar onde ele esta
PECA = RAIZ / "lugar" / "peca-de-teste"
PECA.mkdir(parents=True, exist_ok=True)
motor.write_doc(PECA / "object.md",
                {"type": "object", "id": "peca-de-teste",
                 "name": "Martelo de Teste (em processo)", "origin": "emergente",
                 trabalho.BLOCO: {"tool": "craft", "tipo": "object",
                                  "tempo_necessario_s": 1800,
                                  "tempo_trabalhado_s": 200,
                                  "ator": "beltrano"}},
                "Um martelo pela metade.")

paradas = _pecas_paradas("beltrano", VIZINHO)
ok(len(paradas) == 1 and paradas[0]["id"] == "peca-de-teste",
   "a peca parada DELE e vista")
ok(_pecas_paradas("fulano", RAIZ / "lugar" / "fulano") == [],
   "a peca de OUTRO nao vira carencia sua — um compromisso sobre ela e ajudar "
   "alguem, que e outra coisa com outro dono")

# FR-004: a MESMA vista, o corpo e o mundo juntos
faminto_fm = {"status": {"hunger": "faminto"}}
vista = _carencias_do_corpo(faminto_fm, paradas)
criterios = [c["pronto_quando"] for c in vista]
ok("hunger" in criterios and "peca" in criterios,
   "corpo e mundo descem pela MESMA lista (FR-004) — separa-los faria a Mente "
   "tratar uma como urgencia e a outra como enfeite")
ok(all("porque" in c and "o_que" in c and "pronto_quando" in c for c in vista),
   "toda carencia, do corpo ou do mundo, tem a mesma forma")
peca_v = [c for c in vista if c["pronto_quando"] == "peca"][0]
ok("Martelo de Teste" in peca_v["o_que"],
   "a carencia do mundo NOMEIA a peca — sem o nome o plano nao teria alvo")
bruto = json.dumps(vista, ensure_ascii=False)
ok(not any(ch.isdigit() for ch in bruto),
   "NENHUM digito: '200 de 1800 segundos' e medida interna (Principio V)")

# FR-005: a vista e DERIVADA — some quando a carencia e atendida, e nada a apaga
trabalho.atualizar(PECA, tempo_trabalhado_s=1800)
ok(_pecas_paradas("beltrano", VIZINHO) == [],
   "peca terminada SOME da vista — ela e derivada, nao entidade no world/")
ok(_rotulo_da_peca([]) == "nenhuma parada"
   and P.criterio_cumprido({"peca": _rotulo_da_peca([])}, "peca") is True,
   "e o compromisso sobre a peca FECHA pelo mesmo criterio de leitura de campo")
ok(P.criterio_cumprido({"peca": "parada no meio"}, "peca") is False,
   "peca ainda no meio NAO fecha")


# --------------------------------------------------------------------------- #
# US6 / FR-017, FR-018 — COBRAR, a acao arbitrada que fecha o laco economico
# --------------------------------------------------------------------------- #
#
# Rolagem FORCADA. O que se prende aqui e o molde inteiro da
# `loreforge-arbitrated-action`: onde o dado SOME, os tres desfechos por distancia
# a DC, a virada, a falha nao-silenciosa, o segredo da nota, a memoria dos dois
# lados, e o veredito unico no turno.
#
# CADA CASO USA UM PAR NOVO, e isso nao e higiene: a primeira versao deste bloco
# reusava o mesmo credor e devedor, e a partir do primeiro CALOTE tudo passou a dar
# "nega". Nao era bug — era o portao de trauma funcionando: a memoria `large`
# negativa do calote envenena a relacao dali em diante, que e exatamente o que esta
# tool veio fazer. O teste e que estava errado. Fica travado abaixo, de proposito.

print("\n--- cobrar (US6) ---")

CENA = RAIZ / "porto"
CENA.mkdir(parents=True, exist_ok=True)
motor.write_doc(CENA / "location.md",
                {"type": "location", "id": "porto", "name": "Porto",
                 "size": "M", "entry_point": None, "origin": "editorial"},
                "Um cais.")
_n_par = [0]


def _gente(cid, nome, cha=10):
    d = CENA / cid
    d.mkdir(parents=True, exist_ok=True)
    motor.write_doc(d / "character.md",
                    {"type": "character", "id": cid, "name": nome,
                     "controlled_by": "player_local", "weight_kg": 70,
                     "attributes": {"STR": 10, "DEX": 10, "CON": 10,
                                    "INT": 10, "WIS": 10, "CHA": cha},
                     "status": {"hp": 50, "hp_max": 50, "hunger": "saciado",
                                "fatigue": 10, "action": "parado",
                                "mood": "neutro", "conditions": []}},
                    f"{nome}, de teste.")
    return d


def _par(com_promessa=True):
    """Um credor e um devedor NOVOS, sem historia entre eles."""
    _n_par[0] += 1
    n = _n_par[0]
    cr, dv = f"credor{n}-p73", f"devedor{n}-p73"
    # NOME SEM DIGITO: a trava do Principio V varre digito por digito na narracao,
    # e "Credor 3" reprovaria por causa do teste, nao do codigo.
    letra = chr(ord("A") + (n - 1) % 26)
    _gente(cr, f"Credor {letra}")
    _gente(dv, f"Devedor {letra}")
    if com_promessa:
        # o `promise` DE VERDADE — a lembranca dos dois lados nasce dele, nao a mao.
        motor.apply_resolution(dv, {"promise_ops": [
            {"para": cr, "expectativa": "devolver as tres moedas"}]})
    return cr, dv


def _force(v):
    motor._roll_d20 = lambda: v


def _cobra(cr, dv, nota, item=None):
    op = {"de_quem": dv, "cumprimento": nota}
    if item:
        op["item"] = item
    return motor.apply_resolution(cr, {"cobranca_ops": [op]})


# --- PORTAO 1: sem promessa, recusa SEM ROLAR -------------------------------
cr, dv = _par(com_promessa=False)
_force(20)   # dado que passaria em qualquer DC
out = _cobra(cr, dv, 9)
ok(any(r.get("regra") == "sem_promessa" for r in (out.get("rejected") or [])),
   "sem promessa na memoria: recusa, e a regra e `sem_promessa`")
ok(not (out.get("rolls") or []),
   "sem promessa NAO ROLA DADO — e o portao que torna a tool barata")

cr, dv = _par()
ok(motor.memoria.promessa_viva_de(cr, dv) is not None,
   "o `promise` deixou a lembranca nos dois lados — o fato ja existia (spec 027)")
ok(motor.memoria.promessa_viva_de(dv, cr) is not None,
   "e dos DOIS lados mesmo: quem prometeu tambem lembra")

# --- PORTAO 2 e 3: os extremos da regua, sem dado ---------------------------
cr, dv = _par()
out = _cobra(cr, dv, 0)
ok(any(r.get("regra") == "nao_pagou" for r in (out.get("rejected") or [])),
   "nota 0: nao paga")
ok(all(r.get("rolagem") is None for r in (out.get("rolls") or [])),
   "nota 0 nao rola o dado — o extremo da regua e deterministico")

cr, dv = _par()
out = _cobra(cr, dv, 10)
ap = out.get("cobranca_ops_applied") or []
ok(len(ap) == 1 and ap[0]["desfecho"] == "paga", "nota 10: paga")
ok(all(r.get("rolagem") is None for r in (out.get("rolls") or [])),
   "nota 10 tambem nao rola")

# --- A FAIXA DO MEIO: uma rolagem, tres desfechos por distancia -------------
# nota 5 -> DC 10. mod(CHA 10) = 0.
cr, dv = _par()
_force(20)
out = _cobra(cr, dv, 5)
ap = out.get("cobranca_ops_applied") or []
ok(len(ap) == 1 and ap[0]["desfecho"] == "paga", "passou a DC: PAGA")
rolls = [r for r in (out.get("rolls") or []) if r.get("tipo") == "cobranca"]
ok(len(rolls) == 1 and rolls[0].get("rolagem"),
   "UMA rolagem, e so uma — o dado e unico no ato")

cr, dv = _par()
_force(7)    # total 7 vs DC 10: falhou por 3 (<=5)
out = _cobra(cr, dv, 5)
ap = out.get("cobranca_ops_applied") or []
ok(len(ap) == 1 and ap[0]["desfecho"] == "regateia",
   "falhou por <=5: REGATEIA — o meio-termo que a faixa preve")

cr, dv = _par()
_force(1)    # total 1 vs DC 10: falhou por 9
out = _cobra(cr, dv, 5)
ok(any(r.get("regra") == "nao_pagou" for r in (out.get("rejected") or [])),
   "falhou por mais de 5: NEGA")
ok(any("não paga" in (r.get("why") or "") for r in (out.get("rejected") or [])),
   "e a recusa NAO E SILENCIOSA: volta com a frase de mundo (Principio X)")

# --- O CALOTE ENVENENA A RELACAO: o portao de trauma ------------------------
#
# E AQUI QUE ESTA TOOL PAGA O JOGO. O calote deixa memoria `large` negativa nos
# dois, e `large` e justamente o que `sofreu_trauma_de` procura: dali em diante
# eles nao cooperam. Punicao por reputacao, num mundo sem Estado.
ok(motor.memoria.has_trauma_from(dv, cr) is True,
   "depois do calote, o devedor guarda TRAUMA de quem o cobrou")
_force(20)   # dado maximo, nota maxima
out = _cobra(cr, dv, 10)
ap = out.get("cobranca_ops_applied") or []
ok(ap and ap[0]["desfecho"] == "nega",
   "e nem nota 10 com dado 20 o faz pagar — o portao forca a nota a 0 ANTES do dado")

# --- A VIRADA, e o que NAO e virada -----------------------------------------
cr, dv = _par()
_force(20)
out = _cobra(cr, dv, 3)   # a cena nao prometia pagamento, e o dado virou
ap = out.get("cobranca_ops_applied") or []
ok(ap and ap[0]["desfecho"] == "paga" and ap[0].get("virada") is True,
   "nota baixa + dado otimo = VIRADA, e ela sobe para a narracao")

# A VIRADA SO EXISTE NUM SENTIDO, e isso e propriedade da CURVA, nao esquecimento.
#
# Medido aqui: com nota >= 8 a DC cai para <= 4, e "falhar por mais de 5" exigiria
# um total NEGATIVO — impossivel com d20 >= 1. Entao uma cobranca JUSTA nunca e
# NEGADA pelo acaso; o pior que o dado faz e rebaixa-la a regateio.
#
# Isso e o certo, e vale escrito: o acaso pode dar a quem nao merecia, mas nao pode
# roubar por completo de quem cumpriu. Se um dia se quiser o contrario, e a curva
# que muda — nao este teste.
cr, dv = _par()
_force(1)
out = _cobra(cr, dv, 9)
ap = out.get("cobranca_ops_applied") or []
ok(ap and ap[0]["desfecho"] == "regateia",
   "nota alta com o pior dado NAO vira calote: o piso de quem cumpriu e o regateio")

cr, dv = _par()
_force(7)
out = _cobra(cr, dv, 5)
ap = out.get("cobranca_ops_applied") or []
ok(ap and ap[0].get("virada") is False,
   "regatear NAO e virada — e o meio-termo previsto, nao uma surpresa")

# --- A MEMORIA DOS DOIS LADOS, cada uma na sua perspectiva ------------------
cr, dv = _par()
_force(20)
out = _cobra(cr, dv, 6)
alvos = {m["target"] for m in (out.get("memories_created") or [])
         if m.get("event") == "cobranca"}
ok(alvos == {cr, dv},
   "um ato, DUAS lembrancas — o fato marca os dois (e a via generica da 038 "
   "aprendeu a fazer isso para toda tool futura)")
textos = {}
for cid in (cr, dv):
    for m in motor.memoria._iter_memories(cid):
        if m.get("evento") == "cobranca":
            textos[cid] = motor.read_doc(
                motor.find_character_folder(cid) / "memories" / f"{m['id']}.md")[1]
ok("Cobrei" in textos.get(cr, "") and "me cobrou" in textos.get(dv, ""),
   "cada lado lembra o que ELE viveu — a mesma frase nos dois faria a memoria "
   "mentir sobre quem fez o que")
ok(motor.sentiment_toward(cr, dv) > 0,
   "a divida quitada APROXIMA: o afeto de quem cobrou pelo que pagou sobe")

# --- O VEREDITO E UNICO NO TURNO -------------------------------------------
#
# Numa acao arbitrada quem escolhe a nota e o MODELO, e isso abre um buraco que
# toda tool deste molde tem: recusado o desfecho, ele re-chama a MESMA acao com uma
# nota MAIOR e escapa do veredito. Um modelo fraco entra em loop nisso (mediu-se um
# turno de 129 s no caso do `persuade`).
#
# A cena se le UMA VEZ por turno. E a marca vale TAMBEM na recusa deterministica
# (sem promessa, nota 0), nao so no sucesso — senao o buraco fica aberto justamente
# onde ele e mais barato de explorar.
cr, dv = _par(com_promessa=False)
ctx_escape = arbiter.build_ctx(motor.get_context(cr), ask=lambda _s, _u: "0",
                               prosa={"acao": "cobra, e insiste"})
r1 = ctx_escape.execute("cobrar", {"de_quem": dv})
r2 = ctx_escape.execute("cobrar", {"de_quem": dv})
ok(not r1[0].get("ok") and "NÃO refaça a MESMA" in (r1[0].get("erro") or ""),
   "a 1a recusa (sem promessa) ja ORIENTA a nao re-tentar mudando a regua")
ok(not r2[0].get("ok") and "já aconteceu" in (r2[0].get("erro") or ""),
   "re-cobrar o MESMO alvo no turno e BARRADO — inclusive depois da recusa "
   "deterministica, que e onde o buraco era mais barato")

# COBRAR OUTRA PESSOA no mesmo turno PASSA: e trabalho novo, nao re-tentativa. A
# fronteira importa — barrar a ferramenta inteira seria proibir o legitimo.
cr2, dv2 = _par()
ctx_outro = arbiter.build_ctx(motor.get_context(cr2), ask=lambda _s, _u: "6",
                              prosa={"acao": "cobra de um, depois de outro"})
_force(20)
ra = ctx_outro.execute("cobrar", {"de_quem": dv2})
ok(ra[0].get("ok"), "a primeira cobranca do turno passa")
ok("de_quem" in str(ra[0]), "e devolve o alvo, sem nota nenhuma")


# --- O SEGREDO DO MUNDO (Principio V/IX) ------------------------------------
cr, dv = _par()
_force(12)
out = _cobra(cr, dv, 6)
visivel = json.dumps({k: v for k, v in out.items() if k != "rolls"},
                     ensure_ascii=False, default=str)
ok("cumprimento" not in visivel and '"dc"' not in visivel,
   "a NOTA e a DC nao aparecem em nada que desca ao client")
frases = server_app.inworld_effects(out)
ok(frases and not any(ch.isdigit() for f in frases for ch in f),
   "a narracao do desfecho nao tem NENHUM numero")
ok(any("cobrou" in f for f in frases),
   "e o desfecho VIRA NARRACAO — cobrar em silencio seria incompleto (Principio X)")


# --------------------------------------------------------------------------- #
# §15 — a recusa de VOCABULARIO tem de convidar o retry
# --------------------------------------------------------------------------- #
#
# Medido em jogo (medicoes.md §15): a Nerissa montou um plano BOM de oito passos e
# mandou `pronto_quando: "odila-aguadeira"` — o id de uma PESSOA. O mundo recusou
# com uma frase solta, apontando o campo ERRADO e engolindo a lista de criterios
# validos. Ela nao tinha como corrigir, e nao tentou de novo: UM `set_intention` em
# duas horas de jogo, e o ciclo inteiro da spec nunca disparou.
#
# Erro corrigivel NAO e recusa de merito. Quem nomeou errado um vocabulario precisa
# receber o vocabulario de volta.

print("\n--- a recusa que convida o retry (§15) ---")

class _CtxFalso:
    """So o bastante para ver o que `ctx.err` recebeu."""
    INTENTION_STATUSES = ["ativa", "concluida", "abandonada"]

    def __init__(self, needs=None, nome="Fulano"):
        self.context = {"self": {"name": nome, "needs": needs or {},
                                 "intentions": []}}
        self.ultimo = None

    def err(self, erro, campo=None, validos=None):
        self.ultimo = {"erro": erro, "campo": campo, "validos": validos}
        return {"ok": False, **self.ultimo}


from motor.intencoes.declaracao import _set_intention  # noqa: E402

ctx = _CtxFalso(needs={"hunger": "faminto"})
_set_intention("set_intention",
               {"content": "Fazer um remedio.\n- forage raiz", "status": "ativa",
                "pronto_quando": "odila-aguadeira"}, ctx)
ok(ctx.ultimo["campo"] == "pronto_quando",
   "o criterio desconhecido aponta o CAMPO certo, nao `content`")
nomes = {v["id"] for v in (ctx.ultimo["validos"] or [])}
ok(nomes and nomes == set(P._CRITERIO_POR_CAMPO),
   "e devolve o VOCABULARIO inteiro — sem ele a Mente nao tem como corrigir")

ctx2 = _CtxFalso(needs={"hunger": "faminto"})
_set_intention("set_intention",
               {"content": "Fazer um remedio.\n- forage raiz", "status": "ativa"}, ctx2)
ok(ctx2.ultimo["campo"] == "pronto_quando" and ctx2.ultimo["validos"],
   "sem criterio nenhum tambem convida o retry, com a lista")

# A RECUSA DE MERITO SEGUE SEM LISTA: nao ha o que corrigir num "isso ja e verdade".
ctx3 = _CtxFalso(needs={"hunger": "sem fome"})
_set_intention("set_intention",
               {"content": "Matar minha fome.\n- eat pao", "status": "ativa",
                "pronto_quando": "hunger"}, ctx3)
ok(ctx3.ultimo["validos"] is None,
   "recusa de MERITO nao devolve lista — ela nao e um erro a corrigir")


# --------------------------------------------------------------------------- #
# A FAMILIA POSSE (research.md §R2) — a quinta, e a primeira com ALVO
# --------------------------------------------------------------------------- #
#
# Entrou depois da corrida de 14/09 (§15.6): sem ela, um compromisso de FAZER um
# remedio recebia `pronto_quando: hunger` — 3/3 — porque nenhum criterio servia e o
# modelo escolhe o primeiro que nao e absurdo. O compromisso fecharia no instante em
# que o personagem comesse: um FALSO FECHAMENTO que o SC-002 contaria como acerto.
# Vocabulario pequeno demais nao recusa: ele VAZA.

print("\n--- a familia POSSE (R2) ---")

INV = ["Remedio de Raiz Torta", "Moeda de Cobre"]
ok(P.criterio_cumprido(None, "posse", "raiz torta", INV) is True,
   "carregar 'Remedio de Raiz Torta' cumpre 'raiz torta'")
ok(P.criterio_cumprido(None, "posse", "garra de lobo", INV) is False,
   "o que nao se carrega NAO cumpre")
ok(P.criterio_cumprido(None, "posse", "raiz seca", INV) is False,
   "meia coincidencia nao basta: todo pedaco do alvo tem de aparecer")
ok(P.criterio_cumprido(None, "posse", None, INV) is False,
   "posse SEM alvo nunca cumpre — e por isso a trava existe")
ok(P.criterio_cumprido(None, "posse", "raiz torta", []) is False,
   "de maos vazias, nao cumpre")

# A TRAVA: prometer TER sem dizer o que
ok(P.travas_do_nascimento("Fazer um remedio.\n- brew raiz", "posse", None, None)
   == ("intencao_posse_sem_alvo", {}),
   "posse sem alvo e barrada no nascimento")
ok(P.travas_do_nascimento("Fazer um remedio.\n- brew raiz", "posse", None,
                          "remedio de raiz torta") is None,
   "com o alvo, nasce")

# O ALVO SOBREVIVE ao arquivo, e desce no contexto
pid = P.create_intention(VIZINHO, "Fazer o remedio.\n- brew raiz torta",
                         pronto_quando="posse",
                         pronto_quando_alvo="remedio de raiz torta")
fm, _ = motor.read_doc(VIZINHO / "intentions" / f"{pid}.md")
ok(fm.get("pronto_quando_alvo") == "remedio de raiz torta",
   "o alvo e gravado no arquivo da intencao")
ctx_int = [i for i in P.get_active_intentions(VIZINHO) if i["id"] == pid]
ok(ctx_int and ctx_int[0].get("pronto_quando_alvo") == "remedio de raiz torta",
   "e DESCE no contexto — sem ele a Mente nao sabe o que estava perseguindo")

# so a POSSE ganha a chave: guardar `alvo` numa intencao de fome convidaria a
# proxima leitura a perguntar "alvo de que?"
fid = P.create_intention(VIZINHO, "Matar a fome.\n- eat pao", pronto_quando="hunger")
fm2, _ = motor.read_doc(VIZINHO / "intentions" / f"{fid}.md")
ok("pronto_quando_alvo" not in fm2,
   "intencao sem alvo nao ganha a chave vazia")

# O FIO INTEIRO: o compromisso de posse fecha quando a coisa chega — inclusive por
# um caminho que ninguem planejou.
ok(P.fechar_por_criterio(VIZINHO, {"hunger": "faminto"}, []) == [],
   "de maos vazias, o compromisso de posse NAO fecha")
fechadas = P.fechar_por_criterio(VIZINHO, {"hunger": "faminto"},
                                 ["Remedio de Raiz Torta"])
ok([f for f in fechadas if f["id"] == pid],
   "com a coisa em maos, FECHA — e fecha por leitura de campo, como as outras")
fm3, _ = motor.read_doc(VIZINHO / "intentions" / f"{pid}.md")
ok(fm3.get("status") == "concluida", "e o arquivo registra `concluida`")

# E A GUARDA DO JA-CUMPRIDO vale para a posse: quem ja tem nao promete conseguir.
ok(P.criterio_cumprido(None, "posse", "remedio de raiz torta",
                       ["Remedio de Raiz Torta"]) is True,
   "quem ja carrega a coisa ja cumpriu — a guarda do FR-013b barra o nascimento")


# O FIO REAL DA POSSE: pela tool, nao pela primitiva.
#
# `apply_resolution` -> `_h_intentions` -> `create_intention`. Se o
# `pronto_quando_alvo` cair em qualquer emenda desse caminho, a intencao nasce com
# um criterio que nunca vira verdade — e nada grita, porque o arquivo existe e a
# suite da primitiva fica verde. Ja aconteceu duas vezes nesta spec.
motor.apply_resolution("beltrano", {"intentions": [
    {"content": "Conseguir a garra.\n- take garra de lobo",
     "status": "ativa", "pronto_quando": "posse",
     "pronto_quando_alvo": "garra de lobo"}]})
nascidas = [i for i in P.get_active_intentions(VIZINHO)
            if "garra" in i["content"].lower()]
ok(nascidas and nascidas[0].get("pronto_quando_alvo") == "garra de lobo",
   "o alvo atravessa o TURNO INTEIRO — nao so a primitiva")


# A PECA INACABADA NA MAO NAO CUMPRE "ter o martelo".
#
# Achado pela sondagem depois da posse: a Mente escolheu `posse(martelo)` para
# "terminar o martelo que deixei no meio". Sem filtro, o proprio "Martelo de Sucata
# (em processo)" na mao satisfaz — e o compromisso de TERMINAR fecharia por carregar
# a coisa inacabada. Falso fechamento, o mesmo defeito que a posse veio consertar.
from motor.percepcao.consultas import _carregados_prontos  # noqa: E402

MAO = VIZINHO / "martelo-no-meio"
MAO.mkdir(parents=True, exist_ok=True)
motor.write_doc(MAO / "item.md",
                {"type": "item", "id": "martelo-no-meio",
                 "name": "Martelo de Sucata (em processo)", "origin": "emergente",
                 "weight_kg": 1.0,
                 trabalho.BLOCO: {"tool": "craft", "tipo": "object",
                                  "tempo_necessario_s": 1800,
                                  "tempo_trabalhado_s": 200,
                                  "ator": "beltrano"}},
                "Um martelo pela metade, na mao.")
prontos = _carregados_prontos("beltrano", VIZINHO)
ok(not any("Martelo" in n for n in prontos),
   "a peca INACABADA na mao nao conta como posse — ter nao e ter pronto")
ok(P.criterio_cumprido(None, "posse", "martelo", prontos) is False,
   "e por isso 'ter o martelo' NAO fecha enquanto ele esta no meio")

# terminada, passa a contar
bloco_ok = dict(motor.read_doc(MAO / "item.md")[0][trabalho.BLOCO])
bloco_ok["tempo_trabalhado_s"] = 1800
fm_m, corpo_m = motor.read_doc(MAO / "item.md")
fm_m[trabalho.BLOCO] = bloco_ok
motor.write_doc(MAO / "item.md", fm_m, corpo_m)
prontos2 = _carregados_prontos("beltrano", VIZINHO)
ok(any("Martelo" in n for n in prontos2),
   "terminada, a peca passa a contar como posse")


# --------------------------------------------------------------------------- #
# A FAMILIA LUGAR (research.md §R2) — a mais barata das cinco
# --------------------------------------------------------------------------- #
#
# "Chegar la" e metade do que a Mente escreve: o FR-007 foi corrigido justamente
# porque um plano de mais de um passo atravessa cenas de proposito. Sem `lugar`, um
# compromisso de ir a algum lugar nao tinha como fechar, e vazava para a familia mais
# proxima — o mesmo defeito que a §15.6 mediu com o remedio caindo em `hunger`.

print("\n--- a familia LUGAR (R2) ---")

ONDE = {"lugar": "forja-de-ferro Forja de Ferro"}
ok(P.criterio_cumprido(ONDE, "lugar", "Forja de Ferro") is True,
   "estar la cumpre, pelo NOME")
ok(P.criterio_cumprido(ONDE, "lugar", "forja-de-ferro") is True,
   "e pelo ID — a Mente escreve ora um, ora outro")
ok(P.criterio_cumprido(ONDE, "lugar", "Praca do Mercado") is False,
   "estar em OUTRO lugar nao cumpre")
ok(P.criterio_cumprido(ONDE, "lugar", None) is False,
   "lugar sem alvo nunca cumpre")
ok(P.criterio_cumprido({"lugar": ""}, "lugar", "Forja de Ferro") is False,
   "sem saber onde ele esta, nao se fecha por engano")

ok(P.travas_do_nascimento("Chegar la.\n- travel_to forja", "lugar", None, None)
   == ("intencao_posse_sem_alvo", {}),
   "lugar sem alvo e barrado no nascimento, como a posse")
ok(P.travas_do_nascimento("Chegar la.\n- travel_to forja", "lugar", None,
                          "Forja de Ferro") is None,
   "com o alvo, nasce")

# O FIO REAL: nasce pela tool, e FECHA quando ele chega.
motor.apply_resolution("beltrano", {"intentions": [
    {"content": "Chegar a Forja de Ferro.\n- travel_to Forja de Ferro",
     "status": "ativa", "pronto_quando": "lugar",
     "pronto_quando_alvo": "Forja de Ferro"}]})
viagem = [i for i in P.get_active_intentions(VIZINHO)
          if "Forja" in i["content"]]
ok(viagem and viagem[0].get("pronto_quando_alvo") == "Forja de Ferro",
   "o compromisso de chegar nasce com o alvo, pelo turno inteiro")
ok(P.fechar_por_criterio(VIZINHO, {"lugar": "porto Porto"}, []) == []
   or not any("Forja" in f["content"] for f in
              P.fechar_por_criterio(VIZINHO, {"lugar": "porto Porto"}, [])),
   "longe dali, NAO fecha")
chegou = P.fechar_por_criterio(VIZINHO, {"lugar": "forja-de-ferro Forja de Ferro"}, [])
ok(any("Forja" in f["content"] for f in chegou),
   "chegando, FECHA — e fecha por leitura de campo, como as outras quatro")


# E O LUGAR SAI DA PASTA, nao de `status.location`.
#
# A arvore e a verdade sobre onde alguem esta; `status.location` e texto que pode
# envelhecer, e ja envelheceu no jogo. Esta trava prende a LEITURA real — sem ela, o
# `needs["lugar"]` acima e fixture minha confirmando a si mesma
# (`[[fixture-de-teste-certifica-o-bug]]`).
from motor.turno import _onde_esta  # noqa: E402

lido = _onde_esta(VIZINHO)      # o Beltrano mora em RAIZ/lugar/, id `lugar`
ok(lido.split()[0] == "lugar" and "Lugar" in lido,
   f"o lugar real sai da pasta, com id E nome: {lido!r}")
ok(P.criterio_cumprido({"lugar": lido}, "lugar", "Lugar") is True,
   "e o que a leitura real devolve CASA com o criterio — a ponta que a fixture "
   "sozinha nao prova")


upd = P.create_intention(VIZINHO, "Fazer o remedio.\n- brew raiz torta",
                         pronto_quando="posse",
                         pronto_quando_alvo="remedio de raiz torta")

# ATUALIZAR NAO PODE APAGAR O CRITERIO.
#
# A Mente reescreve o `content` inteiro ao atualizar (e a tool manda fazer assim), e
# nao reenvia o `pronto_quando` — o conector nem o desce ao prompt. Se `update`
# perdesse o criterio, a intencao viraria uma que NUNCA fecha, em silencio: o
# arquivo existe, o status e `ativa`, e `fechar_por_criterio` simplesmente a ignora
# para sempre. E o unico jeito de perceber seria estranhar que ela nunca acaba.
antes_fm, _ = motor.read_doc(VIZINHO / "intentions" / f"{upd}.md")
P.update_intention(VIZINHO, upd, "Fazer o remedio, com calma.\n- brew raiz torta",
                   "ativa")
depois_fm, _ = motor.read_doc(VIZINHO / "intentions" / f"{upd}.md")
ok(depois_fm.get("pronto_quando") == antes_fm.get("pronto_quando")
   and depois_fm.get("pronto_quando_alvo") == antes_fm.get("pronto_quando_alvo"),
   "atualizar o compromisso PRESERVA o criterio e o alvo")


print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S):")
    for f in _falhas:
        print(f"  · {f}")
    sys.exit(1)
print("fase 73: todos os checks passaram.")
