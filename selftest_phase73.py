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


print()
if _falhas:
    print(f"{len(_falhas)} FALHA(S):")
    for f in _falhas:
        print(f"  · {f}")
    sys.exit(1)
print("fase 73: todos os checks passaram.")
