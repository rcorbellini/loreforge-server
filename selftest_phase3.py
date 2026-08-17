"""Auto-teste da Fase 3 — consciência temporal: memórias (US3).

Cobre:
  - criação de memória de 1ª classe ancorada ao personagem afetado (FR-025)
  - só personagens PRESENTES recebem memória; alvo ausente é ignorado
  - intensity inválida cai para 'medium'; ttl inválido cai para o padrão
  - contexto traz memórias ativas ORDENADAS por intensidade e sem expiradas (FR-028)
  - expiração preguiçosa marca 'expired' mas PRESERVA o arquivo (US3 #3)
  - resolução reativa: idle afetado ganha mutação de status + memória no mesmo turno (FR-024)

Roda sobre uma CÓPIA temporária do mundo. Uso:  python3 server/selftest_phase3.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent
REPO_ROOT = SERVER_DIR.parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")

sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def mem_files(char_id):
    folder = motor.find_character_folder(char_id)
    return sorted((folder / "memories").glob("*.md"))


try:
    # --- resolução reativa: idle (elga) afetado ganha status + memória (FR-024/025) --- #
    resolution = {
        "narrative_hint": "Torvin derruba a panela de Elga; o ensopado se espalha no chão.",
        "mutations": [
            {"target": "elga-taverneira", "path": "status.mood", "value": "furiosa",
             "reason": "teve o trabalho destruído"},
        ],
        "memories": [
            {"target": "elga-taverneira",
             "content": "Ele derrubou minha panela e estragou o jantar de toda a casa. Não esqueço.",
             "intensity": "large", "ttl_seconds": 86400},
            # alvo ausente: deve ser ignorado
            {"target": "fantasma", "content": "irrelevante", "intensity": "giant", "ttl_seconds": 10},
        ],
    }
    out = motor.apply_resolution("torvin-ferreiro", resolution)
    created = out.get("memories_created", [])
    # o mundo TAMBÉM registra sozinho agora (spec 013), então a lista traz mais
    # que a memória pedida pelo Árbitro. O que continua valendo: o alvo presente
    # ganhou a dele, e o ausente ("fantasma") foi ignorado.
    alvos = [m["target"] for m in created]
    check("cria memória para o presente", "elga-taverneira" in alvos, str(created))
    check("ignora memória de alvo ausente da cena", "fantasma" not in alvos,
          str(created))
    check("memória ancorada na pasta de elga", len(mem_files("elga-taverneira")) >= 1)
    check("idle recebeu mutação de status no mesmo turno (FR-024)",
          any(m["target"] == "elga-taverneira" and m.get("path") == "status.mood"
              for m in out["applied"]))

    # o conteúdo é gravado na perspectiva do afetado (body do arquivo)
    latest = max(mem_files("elga-taverneira"), key=lambda p: p.stat().st_mtime)
    fm_latest, body_latest = motor.read_doc(latest)
    check("memória em 1ª pessoa (perspectiva)", "minha panela" in body_latest, body_latest[:60])
    check("memória nasce ativa com prazo", fm_latest.get("state") == "active"
          and fm_latest.get("timestamp_end") > fm_latest.get("timestamp_start"))

    # --- clamp de intensity/ttl inválidos ---------------------------------- #
    res_bad = {
        "narrative_hint": "x",
        "mutations": [],
        "memories": [{"target": "torvin-ferreiro", "content": "algo",
                      "intensity": "colossal", "ttl_seconds": "muito"}],
    }
    out_bad = motor.apply_resolution("torvin-ferreiro", res_bad)
    tid = out_bad["memories_created"][0]["id"]
    tfile = next(p for p in mem_files("torvin-ferreiro") if p.stem == tid)
    fm_bad, _ = motor.read_doc(tfile)
    check("intensity inválida vira 'medium'", fm_bad.get("intensity") == "medium")
    check("ttl inválido vira padrão", fm_bad.get("timestamp_end") - fm_bad.get("timestamp_start")
          == motor._DEFAULT_TTL_SECONDS)

    # --- contexto: ativas ordenadas por intensidade, sem expiradas (FR-028) --- #
    # cria manualmente memórias de várias intensidades para elga
    elga_folder = motor.find_character_folder("elga-taverneira")
    now = int(time.time())
    seeds = [("small", "detalhe pequeno"), ("giant", "trauma enorme"), ("medium", "algo medio")]
    for i, (inten, txt) in enumerate(seeds):
        fm = {"type": "memory", "id": f"mem-ord-{i}", "timestamp_start": now,
              "timestamp_end": now + 9999, "intensity": inten, "state": "active"}
        motor.write_doc(elga_folder / "memories" / f"mem-ord-{i}.md", fm, txt)
    # e uma já vencida por prazo (state ainda 'active', mas timestamp_end no passado)
    fm_exp = {"type": "memory", "id": "mem-vencida", "timestamp_start": now - 100,
              "timestamp_end": now - 10, "intensity": "giant", "state": "active"}
    motor.write_doc(elga_folder / "memories" / "mem-vencida.md", fm_exp, "já passou")

    ctx = motor.get_context("elga-taverneira")  # dispara lazy: expira a vencida
    intensities = [m["intensity"] for m in ctx["memories"]]
    order = {"giant": 0, "large": 1, "medium": 2, "small": 3}
    check("memórias ordenadas por intensidade",
          intensities == sorted(intensities, key=lambda x: order.get(x, 9)), str(intensities))
    check("giant vem antes de small", intensities and intensities[0] == "giant")
    contents = [m["content"] for m in ctx["memories"]]
    check("memória vencida excluída do contexto", "já passou" not in contents)

    # --- saliência: recente e/ou forte = vívida; antiga = latente ---------- #
    salient_now = int(time.time())
    fm_recente = {"type": "memory", "id": "mem-recente", "timestamp_start": salient_now,
                  "timestamp_end": salient_now + 10 ** 9, "intensity": "giant", "state": "active"}
    motor.write_doc(elga_folder / "memories" / "mem-recente.md", fm_recente, "trauma desta semana")
    # giant antiga (2 anos): fora da janela vívida (180 dias) -> latente
    fm_antiga = {"type": "memory", "id": "mem-antiga",
                 "timestamp_start": salient_now - 730 * 86400,
                 "timestamp_end": salient_now + 10 ** 9, "intensity": "giant", "state": "active"}
    motor.write_doc(elga_folder / "memories" / "mem-antiga.md", fm_antiga, "luto de anos atrás")

    # o CONTEXTO passa por evocação (spec 013): latente que a cena não evoca não
    # desce. A saliência em si se lê da pasta, sem o filtro.
    ctx_ids = {m["id"] for m in motor.get_context("elga-taverneira")["memories"]}
    check("evocação: vívida desce sempre", "mem-recente" in ctx_ids)
    check("evocação: latente que ninguém evoca NÃO desce", "mem-antiga" not in ctx_ids)

    by_id = {m["id"]: m for m in motor.get_active_memories(elga_folder)}
    check("saliência: memória recente é vívida", by_id["mem-recente"]["salience"] == "vivida")
    check("saliência: memória giant antiga é latente", by_id["mem-antiga"]["salience"] == "latente")
    check("recência: antiga rotulada 'há anos'", by_id["mem-antiga"]["recency"] == "há anos")

    # --- expiração preguiçosa marca 'expired' mas preserva o arquivo (US3 #3) --- #
    vfile = elga_folder / "memories" / "mem-vencida.md"
    check("arquivo da memória vencida ainda existe", vfile.exists())
    fm_v, _ = motor.read_doc(vfile)
    check("memória vencida foi marcada 'expired'", fm_v.get("state") == "expired")

finally:
    shutil.rmtree(_tmp, ignore_errors=True)

print()
if FAILS:
    print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
    sys.exit(1)
print("todos os checks da Fase 3 passaram.")
