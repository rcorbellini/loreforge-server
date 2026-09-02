"""Auto-teste da Fase 42 — Tools de Consulta da Mente (spec 040).

(Número de FASE ≠ número de SPEC: phase40/41 já eram de outras specs.)

Rede DETERMINÍSTICA (sem LLM) da lane paralela de consulta:
  - o registro `consult_specs()` tem as duas tools auto-declaradas
  - `recall` casa por SUJEITO (id/nome citado em `sobre`) e por TEMA (domínio/evento)
  - `recall` respeita a PERSPECTIVA: só a memória do próprio personagem (não vaza)
  - ausência é reportada como ausência, nunca inventada
  - `current_moment` devolve PROSA de período — sem número/hora
  - nenhum payload vaza `intensity`/`valence`/`timestamp` (Princípios V/IX)
  - despacho: `consult_specs()[nome].query` é o MESMO corpo da fachada `motor`

Não toca o caminho de mutação (restrição não-negociável) — só lê.

Uso:  python3 server/selftest_phase42.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test42-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import app  # noqa: E402  (o funil real da proposta/consulta — `resolver_proposta`)
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _seed_memory():
    """Uma memória de FURTO de Torvin envolvendo Elga (fixture determinística)."""
    folder = motor.find_character_folder("torvin-ferreiro")
    mem_dir = folder / "memories"
    mem_dir.mkdir(exist_ok=True)
    now = int(time.time())
    fm = {
        "type": "memory", "id": f"mem-{now}-teste42", "kind": "acontecimento",
        "involved": ["elga-taverneira", "taverna-do-gancho"],
        "timestamp_start": now, "timestamp_end": now + 10 ** 7,
        "intensity": "medium", "state": "active",
        "summary": "Vi Elga surrupiar uma moeda do balcão",
        "domain": "crime", "evento": "witness_theft",
        "valence": {"elga-taverneira": "negativa"},
    }
    motor.write_doc(mem_dir / f"{fm['id']}.md", fm,
                    "Vi Elga surrupiar uma moeda do balcão da taverna.")


def run() -> int:
    FAILS.clear()
    _seed_memory()

    specs = motor.consult_specs()
    check("registro tem consultar_memoria e consultar_momento",
          {"consultar_memoria", "consultar_momento"} <= set(specs.keys()),
          f"tem: {sorted(specs.keys())}")

    r_tema = motor.recall("torvin-ferreiro", {"sobre": "houve furto por aqui?"})
    check("recall casa por TEMA (furto)", "Elga" in r_tema["lembra"], r_tema["lembra"][:80])

    r_suj = motor.recall("torvin-ferreiro", {"sobre": "o que sei de Elga?"})
    check("recall casa por SUJEITO (Elga)", "Elga" in r_suj["lembra"], r_suj["lembra"][:80])

    r_aus = motor.recall("torvin-ferreiro", {"sobre": "dragões alados"})
    check("recall reporta AUSÊNCIA sem inventar",
          "não guarda" in r_aus["lembra"].lower(), r_aus["lembra"][:80])

    r_persp = motor.recall("elga-taverneira", {"sobre": "houve furto por aqui?"})
    check("recall respeita a PERSPECTIVA (não vaza memória de terceiro)",
          "não guarda" in r_persp["lembra"].lower(), r_persp["lembra"][:80])

    # --- O DONO É A SESSÃO, NUNCA UM ARGUMENTO -------------------------------- #
    # A consulta passou a DESCER à Mente como tool (a Mente escreve os argumentos),
    # e isso muda a superfície: antes só a bancada chamava `/api/consult`. Ler a
    # memória de outro personagem seria metagaming absoluto — o que se sabe do que
    # o outro guarda só se obtém por `ask_about`, que ele pode negar. Então o dono
    # tem de vir do character_id da SESSÃO, e nenhum argumento pode movê-lo.
    #
    # Duas camadas, testadas separadamente porque falham por motivos diferentes:
    # (1) `recall` só olha `find_character_folder(character_id)`; (2) o funil
    # `resolver_proposta` retira `character_id` dos args, e `Mundo.propor` o
    # sobrescreve com o da sessão (escrito DEPOIS do `**corpo`).
    limpo = motor.recall("torvin-ferreiro", {"sobre": "Elga"})
    injetado = motor.recall("torvin-ferreiro", {
        "sobre": "Elga",
        "character_id": "elga-taverneira", "quem": "elga-taverneira",
        "personagem": "elga-taverneira", "alvo": "elga-taverneira",
        "dono": "elga-taverneira", "folder": "elga-taverneira",
    })
    check("recall IGNORA qualquer dono vindo nos args", injetado == limpo,
          f"injetado={str(injetado)[:120]}")

    # E o universo dos dois é de fato DIFERENTE — senão o teste acima passaria
    # por coincidência, comparando duas respostas vazias.
    check("as duas memórias são universos distintos (o teste discrimina)",
          motor.recall("torvin-ferreiro", {"sobre": "houve furto por aqui?"})
          != motor.recall("elga-taverneira", {"sobre": "houve furto por aqui?"}))

    class _H:
        def resolver_proposta(self, nome, payload):
            return app.Handler.resolver_proposta(self, nome, payload)
        def _refuse_if_down(self, *a):
            return None
        # spec 056: `resolver_proposta` passou a autenticar antes de tudo — este
        # dublê de Handler não tem `self.server` (não é um socket de verdade),
        # então cai direto no modo legado (mesmo retorno de `_authenticate` sem
        # `auth_enabled`), sem tentar ler nada de rede.
        def _authenticate(self):
            return {"sub": "local", "email": "", "name": "local"}
        def _authorize_character(self, *a):
            return True

    via_funil = _H().resolver_proposta("consultar_memoria", {
        "character_id": "torvin-ferreiro", "sobre": "Elga",
        # o que uma Mente maliciosa (ou só confusa) escreveria nos argumentos
        "quem": "elga-taverneira", "personagem": "elga-taverneira",
    })
    check("funil: a consulta pelo caminho real fica no dono da sessão",
          via_funil.get("lembra") == limpo["lembra"],
          f"{str(via_funil.get('lembra'))[:120]}")
    check("funil: `character_id` não chega aos args da consulta",
          "character_id" not in str(via_funil.get("sobre", "")))

    blob = str(r_tema)
    check("recall não vaza intensity/valence/timestamp",
          not any(k in blob for k in ("intensity", "valence", "timestamp",
                                      "medium", "negativa")), blob[:100])

    mom = motor.current_moment()
    check("current_moment devolve prosa de período",
          isinstance(mom.get("momento"), str) and mom["momento"] != "", str(mom))
    check("current_moment não vaza hora/número",
          not any(c.isdigit() for c in mom.get("momento", "")), str(mom))

    check("despacho: consult_specs['consultar_momento'].query == current_moment",
          specs["consultar_momento"].query(None, {}) == motor.current_moment())
    check("despacho: consult_specs['consultar_memoria'].query == recall",
          specs["consultar_memoria"].query("torvin-ferreiro", {"sobre": "Elga"})
          == motor.recall("torvin-ferreiro", {"sobre": "Elga"}))

    # US4 (sussurro player-facing): consultar não CRIA memória e não toca o caminho de
    # mutação. (spec 064: a lane passou a escrever UMA coisa — o PRAZO do que foi
    # evocado, via o handler `_consultar_memoria`. Não cria entidade, não muda posse,
    # não toca `status`; é o relógio de uma lembrança, da mesma família do que
    # `_expire_memories` já faz na leitura. A contagem abaixo segue valendo, e passa a
    # valer por um motivo mais forte: mesmo escrevendo, a consulta não FABRICA memória.)
    folder = motor.find_character_folder("torvin-ferreiro")
    antes = len(list((folder / "memories").glob("*.md")))
    motor.recall("torvin-ferreiro", {"sobre": "Elga"})
    motor.current_moment()
    depois = len(list((folder / "memories").glob("*.md")))
    check("US4: consultar NÃO cria memória (read-only)", antes == depois,
          f"antes={antes} depois={depois}")
    check("US4: retorno de recall não traz chaves de mutação",
          not any(k in r_tema for k in ("applied", "aconteceu", "created", "memories_created")))

    # US3 (dois gatilhos): a MESMA consulta serve ao Árbitro (fachada motor.*) e ao
    # client (consult_specs) — uma fonte, sem reimplementação (arbiter-boundary R4).
    check("US3: reúso Árbitro×client — mesmo resultado das duas vias",
          motor.current_moment() == specs["consultar_momento"].query(None, {}))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S) na Fase 42: {', '.join(FAILS)}")
        return 1
    print("Fase 42 (Tools de Consulta da Mente, spec 040) OK.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
