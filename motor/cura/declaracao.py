"""DECLARAÇÃO + CORPO da tool de CURA (spec 038, L3).

`heal` migrada de `arbiter_tools/cura.py` (deletado). O corpo ENFILEIRA em
`ctx.queue["cura_ops"]` (a rolagem/veredito saem no executor, no flush) — opera
sobre o `ctx` duck-typed, sem importar o Árbitro. Byte-equivalente a v2.0.0.
"""
from __future__ import annotations

import json
from .. import juizo

from ..io import name_of
from ..registro import ToolSpec, inworld, tool_spec
from ..rolagem import NEUTRAL_ADVANTAGE


# --- A RÉGUA (spec 043) — mora COM a capacidade que a lê -------------------- #
# ESCRITA AGORA, não migrada: `heal` NUNCA teve régua. A descrição dela prometia
# "pela régua canônica do prompt" e o prompt do Árbitro não continha nenhuma — a nota
# do socorro sempre foi chute do modelo, desde a spec 032. É a lacuna que só apareceu
# quando as réguas foram inventariadas para migrar.
#
# Ancorada no MEIO (5 = socorro comum), ao contrário da de furto ou da de ceder um
# bem: prestar socorro a quem caiu é o que uma pessoa razoável faz, e o que decide o
# grau é a CENA — não a boa vontade de quem socorre.
REGUA_SOCORRO = """\
Régua do SOCORRO (o quanto a CENA favorece reerguer quem caiu — leia o lugar, o
estado do ferido e o que quem socorre tem à mão; nunca a vontade de ajudar, que se
presume):
  0  impossível ali — fogo, água funda, desabamento; ninguém socorre nada (sem teste)
  1  quase inviável — perigo ativo em cima dos dois, sem um instante de calma
  2  muito contra — escuro, chuva, chão que não firma, ferido preso
  3  desfavorável — lugar apertado ou hostil, nada com que estancar
  4  levemente contra — falta uma luz, falta um pano, o chão é ruim
  5  socorro comum — nada ajuda e nada atrapalha; as mãos e o tino decidem
  6  levemente a favor — lugar calmo, espaço para deitar o ferido
  7  favorável — abrigo, luz boa, água por perto
  8  muito favorável — um leito, panos limpos, tempo sem ninguém por perto
  9  quase ideal — tudo à mão e alguém segurando a cena
  10 perfeito — abrigo, insumos e calma plena; o corpo responde (sem teste)
O ESTADO DO FERIDO PESA: quem acabou de cair é diferente de quem está lá há muito.
A nota é segredo do mundo: NUNCA mencione o número na narrativa. Entre 1 e 9 há um
teste resolvido na aplicação — não narre o resgate como certo."""


@inworld("cura_ops_applied")
def _iw_cura(op):
    alvo = name_of(op.get("alvo"))
    if op.get("curou"):
        # o percentual/nível NUNCA aparece aqui — só o efeito sensorial (Princípio V):
        # o corpo que volta a se mexer, a lembrança que falta.
        return (f"socorreu {alvo}, que voltou a se mexer, mas "
                f"não se lembra bem de algumas coisas")
    return f"tentou socorrer {alvo}, sem sucesso"


def _heal(name: str, args: dict, ctx) -> tuple[dict, bool]:
    alvo = args.get("alvo")
    outros_caidos = ctx.validos({c: n for c, n in ctx.chars.items() if c in ctx.cand["heal"]})
    if alvo == ctx.actor:
        return ctx.err("é ele quem socorre — escolha outro personagem presente",
                      "alvo", outros_caidos), False
    if alvo not in ctx.cand["heal"]:
        return ctx.err(f"'{alvo}' não é alguém caído que se possa socorrer", "alvo",
                       outros_caidos), False
    if alvo in ctx.curados:
        return ctx.err(f"o resgate de '{alvo}' já foi tentado neste turno — o desfecho "
                      "sai na aplicação; NÃO repita: siga para outra ação ou narrate"), False
    # spec 043 — CONTRATO DE ANÁLISE: a régua do socorro lê o LUGAR e o estado de
    # quem caiu, nunca a boa vontade de quem socorre (essa se presume).
    vantagem = juizo.nota(
        ctx.ask(REGUA_SOCORRO + juizo.NOTA_0_10,
                json.dumps({"ferido": ctx.describe(alvo),
                           "cena": ctx.describe(ctx.place_id),
                           "prosa": ctx.prosa}, ensure_ascii=False, indent=2)),
        default=NEUTRAL_ADVANTAGE)   # socorro comum
    ctx.curados.add(alvo)
    ctx.queue["cura_ops"].append({"alvo": alvo, "vantagem": vantagem})
    return {"ok": True, "aplicado": {"alvo": alvo,
                                    "nota": "o desfecho sai na aplicação"}}, False


HEAL = tool_spec(ToolSpec(
    names=("heal",),
    juizo=(("vantagem", REGUA_SOCORRO),),
    description=("Tenta socorrer OUTRO personagem presente que está incapacitado "
    "(caído) — nunca quem já morreu, nunca a si mesmo. Reerguer sempre custa "
    "algo: o corpo volta só em parte, e quem foi socorrido perde por "
    "completo uma fração do que vivia — nunca um resgate de graça."),
    params={"alvo": {"type": "string"},
           "vantagem": {"type": "integer", "minimum": 0, "maximum": 10}},
    required=("alvo", "vantagem"),
    enum_sources={"alvo": "heal"},
    apply=_heal,
))
