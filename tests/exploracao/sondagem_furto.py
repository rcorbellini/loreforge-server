"""Sondagem exploratória (spec 023): a EXPOSIÇÃO que o Árbitro dá a um furto
responde à DESCRIÇÃO do item? (SC-005 — a vistosidade é lida da prosa, não de campo).

Comportamento do MODELO, não determinístico — precisa do Ollama no ar. Não entra na
suíte; roda à mão para calibrar a REGUA_FURTO e confirmar que a prosa foi lida.

Ideia: dois itens de MESMO peso/valor na posse da Elga, um descrito "à vista"
(uma carne fumegante no balcão) e outro "escondido" (um anel preso por dentro do
punho da manga). Pede-se ao Árbitro que furte cada um e compara-se a nota de
EXPOSIÇÃO (`steal_ops[].exposicao`) que ele propõe: o escondido deve puxar nota
MENOR (mais difícil). Rodar N vezes e olhar a média.

Uso:  python3 server/tests/exploracao/sondagem_furto.py   (com Ollama em :11434)
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent.parent.parent
_tmp = Path(tempfile.mkdtemp(prefix="sondagem-furto-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"
sys.path.insert(0, str(SERVER_DIR))
import motor  # noqa: E402
import arbiter  # noqa: E402
import app as server_app  # noqa: E402

ELGA_DIR = _tmp / "world" / "taverna-do-gancho" / "elga-taverneira"
N = int(os.environ.get("SONDAGEM_N", "6"))


def _item(item_id, name, prosa):
    d = ELGA_DIR / item_id
    d.mkdir(parents=True, exist_ok=True)
    (d / "item.md").write_text(
        f"---\ntype: item\nid: {item_id}\nname: {name}\nvalue: 3\nsize: P\n"
        f"weight_kg: 0.2\norigin: editorial\n---\n{prosa}\n", encoding="utf-8")


# mesmo peso/valor; só a prosa muda
_item("carne-a-vista", "Carne no Balcão",
      "Um naco de carne assada fumega SOBRE O BALCÃO, à mão de qualquer um, o "
      "cheiro se espalhando pelo salão.")
_item("anel-escondido", "Anel da Mãe",
      "Um anel simples que Elga mantém PRESO POR DENTRO DO PUNHO DA MANGA, contra "
      "a pele, onde só ela sabe que está.")


def nota_de_exposicao_para(item_id):
    """Roda o Árbitro pedindo para furtar `item_id` e devolve a exposição proposta."""
    arb = server_app.CONFIG["arbiter"]
    loop = server_app.build_loop_fn(arb)
    ctx = motor.get_context("torvin-ferreiro")
    capt = {"exposicao": None}

    def execute(name, args):
        if name == "steal" and args.get("item") == item_id:
            capt["exposicao"] = args.get("exposicao")
        return {"ok": True, "aplicado": args}
    try:
        arbiter.resolve_with_tools(
            {"action": f"furta discretamente o {motor.name_of(item_id)} da Elga"},
            ctx, loop)
    except Exception as e:  # noqa: BLE001
        print("  (erro no Árbitro:", e, ")")
    return capt["exposicao"]


def media(item_id):
    notas = [n for n in (nota_de_exposicao_para(item_id) for _ in range(N)) if n is not None]
    return (sum(notas) / len(notas)) if notas else None, len(notas)


if __name__ == "__main__":
    print(f"Sondagem de furto — {N} rodadas por item (precisa do Ollama).")
    m_vista, n_vista = media("carne-a-vista")
    m_esc, n_esc = media("anel-escondido")
    print(f"  carne À VISTA:   exposição média = {m_vista}  ({n_vista}/{N} propuseram steal)")
    print(f"  anel ESCONDIDO:  exposição média = {m_esc}  ({n_esc}/{N} propuseram steal)")
    if m_vista is not None and m_esc is not None:
        print("  VEREDITO:", "prosa LIDA ✓ (escondido < à vista)" if m_esc < m_vista
              else "sem diferença clara — revisar a REGUA_FURTO ou o modelo")
