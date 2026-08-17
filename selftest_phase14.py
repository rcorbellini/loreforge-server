"""Auto-teste da Fase 14 — Troca e Compra entre Personagens (spec 011).

Cobre, com rolagem forçada (motor._roll_d20 injetável):
  - unidades: value_of, is_currency/is_for_sale/is_negotiable, total_value,
    trade_dc decrescente na necessidade E na razão de valor
  - o PORTÃO (SC-009a): item sem marca não entra em negócio, em nenhum modo
  - compra por ARITMÉTICA (SC-009): paga ⇒ aceita sem dado; não paga ⇒
    valor_insuficiente, mesmo com nota máxima
  - troca por necessidade + valor + dado (SC-010/SC-012): extremos sem rolagem,
    faixa 1-9 rola uma vez, nota generosa não garante desfecho
  - atomicidade (SC-002/SC-007): perna impossível ⇒ NADA se move, mundo idêntico
  - equivalência com o `give` (risco D6): uma perna aceita/recusa nos mesmos casos
  - recusas distintas (SC-003) e pureza narrativa (SC-008)

Cenário: taverna. Torvin CHA 8 (mod −1) e Elga CHA 13 (mod +1).
Fixture de comércio: 3x moeda-de-prata (value 10, currency), frasco-de-unguento
(value 25, for_sale + negotiable), corda-encerada (value 8, negotiable),
anel-da-mae (value 200, SEM marca — o intocável).

Uso:  python3 server/selftest_phase14.py
"""

from __future__ import annotations

import hashlib
import json
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
MOEDAS = ["moeda-de-prata-1", "moeda-de-prata-2", "moeda-de-prata-3"]
FRASCO, CORDA, ANEL = "frasco-de-unguento", "corda-encerada", "anel-da-mae"


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}" + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def force_roll(v):
    motor._roll_d20 = lambda: v


def forbid_roll():
    def _boom():
        raise AssertionError("rolagem não deveria acontecer aqui")
    motor._roll_d20 = _boom


def res(**parts):
    base = {"narrative_hint": "negocia", "movement": None, "mutations": [],
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "persuade_ops": [], "attack_ops": [], "carry_ops": [],
            "trade_ops": [], "memories": []}
    base.update(parts)
    return base


def negociar(actor, modo, parceiro, dou, recebo, necessidade=None):
    op = {"modo": modo, "parceiro": parceiro, "dou": dou, "recebo": recebo}
    if necessidade is not None:
        op["necessidade"] = necessidade
    return motor.apply_resolution(actor, res(trade_ops=[op]))


def ifolder(item_id) -> Path:
    return motor.find_entity(item_id)[0].parent


def ifm(item_id) -> dict:
    return motor.find_entity(item_id)[1]


def dono(item_id) -> str:
    """Quem CARREGA o item, subindo a cadeia de contêineres — uma moeda dentro da
    bolsa pertence a quem veste a bolsa, não à bolsa."""
    porter = motor.porter_of(ifolder(item_id))
    return porter.name if porter else ifolder(item_id).parent.name


def dar(cid, item_id, slot=None):
    """Coloca o item com o personagem (montagem de cenário)."""
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm["state"] = {**(fm.get("state") or {}), "slot": slot or motor.HAND_SLOT}
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.find_character_folder(cid) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def guardar(item_id, container_id):
    """Guarda o item dentro de um contêiner (sem slot: está guardado)."""
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    dest = ifolder(container_id) / folder.name
    if folder != dest:
        os.replace(folder, dest)


def chao(item_id):
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    fm.pop("state", None)
    motor.write_doc(folder / "item.md", fm, body)
    dest = motor.WORLD_DIR / TAVERNA / folder.name
    if folder != dest:
        os.replace(folder, dest)


def marcar(item_id, **campos):
    folder = ifolder(item_id)
    fm, body = motor.read_doc(folder / "item.md")
    for k, v in campos.items():
        if v is None:
            fm.pop(k, None)
        else:
            fm[k] = v
    motor.write_doc(folder / "item.md", fm, body)


def digital() -> str:
    """Onde cada ITEM está. Não usa o mundo inteiro de propósito: toda ação grava
    `status.action` do ator (garantia de consequência, FR-014), então o mundo muda
    mesmo numa recusa. O que a atomicidade promete é que nenhum item se moveu."""
    h = hashlib.sha256()
    for p in sorted(motor.WORLD_DIR.rglob("item.md")):
        h.update(str(p.relative_to(motor.WORLD_DIR)).encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def scripted_loop(calls):
    def loop_fn(system, user, tools, execute, max_calls):
        for name, args in calls:
            execute(name, args)
        return {"stopped": "limit", "text": None, "calls": len(calls)}
    return loop_fn


try:
    # cenário: Torvin com a bolsa de moedas; Elga com a mercadoria.
    # As moedas vão DENTRO da bolsa — ninguém tem três mãos, e é assim que o
    # jogo já trata dinheiro miúdo.
    # Quem vende precisa de onde GUARDAR o dinheiro: duas mãos não recebem três
    # moedas. É consequência real do modelo físico, e vale para o mundo também.
    BOLSA, CAIXA = "bolsa-pequena", "mochila-de-couro"
    dar(TORVIN, BOLSA)
    for m in MOEDAS:
        guardar(m, BOLSA)
    dar(ELGA, CAIXA)
    dar(ELGA, FRASCO)
    dar(ELGA, ANEL, slot="dedo")
    dar(ELGA, CORDA)

    # --- unidades ------------------------------------------------------------ #
    check("value_of: declarado e ausente",
          motor.value_of(ifm(FRASCO)) == 25.0 and motor.value_of({}) is None)
    check("marcas: currency / for_sale / negotiable",
          motor.is_currency(ifm(MOEDAS[0])) and motor.is_for_sale(ifm(FRASCO))
          and motor.is_negotiable(ifm(CORDA))
          and not motor.is_for_sale(ifm(ANEL))
          and not motor.is_negotiable(ifm(ANEL)))
    check("total_value soma; e é None se algum item não tem preço",
          motor.total_value([ifm(m) for m in MOEDAS]) == 30.0
          and motor.total_value([ifm(FRASCO), {}]) is None)
    check("trade_dc decresce na NECESSIDADE",
          motor.trade_dc(3, 1.0) > motor.trade_dc(7, 1.0))
    check("trade_dc decresce na RAZÃO DE VALOR (SC-009b)",
          motor.trade_dc(5, 0.5) >= motor.trade_dc(5, 1.0) >= motor.trade_dc(5, 2.0)
          and motor.trade_dc(5, 2.0) < motor.trade_dc(5, 1.0),
          f"{motor.trade_dc(5,0.5)} {motor.trade_dc(5,1.0)} {motor.trade_dc(5,2.0)}")

    # --- o PORTÃO (SC-009a) --------------------------------------------------- #
    forbid_roll()
    antes = digital()
    out = negociar(TORVIN, "buy", ELGA, MOEDAS, [ANEL])
    check("portão: comprar o intocável ⇒ nao_esta_a_venda, SEM avaliação",
          any(r.get("regra") == "nao_esta_a_venda" for r in out["rejected"])
          and digital() == antes)

    out = negociar(TORVIN, "trade", ELGA, [MOEDAS[0]], [ANEL], necessidade=10)
    check("portão: trocar pelo intocável ⇒ nao_e_negociavel, mesmo com nota 10",
          any(r.get("regra") == "nao_e_negociavel" for r in out["rejected"])
          and digital() == antes)

    out = negociar(TORVIN, "buy", ELGA, [MOEDAS[0]], [CORDA])
    check("portão: comprar item negociável mas NÃO à venda ⇒ nao_esta_a_venda",
          any(r.get("regra") == "nao_esta_a_venda" for r in out["rejected"]))

    marcar(CORDA, currency=None)
    out = negociar(TORVIN, "buy", ELGA, [FRASCO], [CORDA])
    check("portão: pagar com bens no buy ⇒ pagamento_nao_e_dinheiro",
          any(r.get("regra") in ("pagamento_nao_e_dinheiro", "item_nao_e_seu")
              for r in out["rejected"]))

    # --- COMPRA: aritmética (SC-009) ------------------------------------------ #
    forbid_roll()
    out = negociar(TORVIN, "buy", ELGA, MOEDAS[:2], [FRASCO])   # 20 < 25
    check("compra que não paga ⇒ valor_insuficiente, sem dado, mundo intacto",
          any(r.get("regra") == "valor_insuficiente" for r in out["rejected"])
          and out["rolls"] == [] and dono(FRASCO) == ELGA)

    forbid_roll()
    out = negociar(TORVIN, "buy", ELGA, MOEDAS, [FRASCO])       # 30 >= 25
    check("compra que paga ⇒ aceita SEM rolagem, itens trocam nos dois sentidos",
          out["trade_ops_applied"] and out["rolls"] == []
          and dono(FRASCO) == TORVIN
          and all(dono(m) == ELGA for m in MOEDAS))

    # devolve o cenário
    for m in MOEDAS:
        guardar(m, BOLSA)
    dar(ELGA, FRASCO)

    # --- TROCA: necessidade + valor + dado ------------------------------------ #
    marcar(CORDA, negotiable=True)
    dar(TORVIN, CORDA)          # Torvin oferece a corda (8) pelo frasco (25)

    forbid_roll()
    out = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=0)
    check("necessidade 0 ⇒ recusa SEM rolagem (SC-012)",
          any(r.get("regra") == "necessidade_insuficiente" for r in out["rejected"])
          and out["rolls"] == [] and dono(FRASCO) == ELGA)

    forbid_roll()
    out = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=10)
    check("necessidade 10 ⇒ aceita SEM rolagem",
          out["trade_ops_applied"] and out["rolls"] == []
          and dono(FRASCO) == TORVIN and dono(CORDA) == ELGA)
    dar(TORVIN, CORDA); dar(ELGA, FRASCO)

    force_roll(20)
    out = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=5)
    check("necessidade 5 + dado alto ⇒ aceita, rolando UMA vez",
          out["trade_ops_applied"] and len(out["rolls"]) == 1
          and out["rolls"][0]["tipo"] == "negociacao")
    dar(TORVIN, CORDA); dar(ELGA, FRASCO)

    force_roll(1)
    out = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=5)
    check("necessidade 5 + dado baixo ⇒ necessidade_insuficiente, nada se move",
          any(r.get("regra") == "necessidade_insuficiente" for r in out["rejected"])
          and dono(FRASCO) == ELGA and dono(CORDA) == TORVIN)

    # SC-010: nota generosa NÃO garante — com dado ruim ainda falha
    force_roll(2)
    out = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=7)
    check("SC-010: necessidade 7 com dado ruim ainda falha",
          any(r.get("regra") == "necessidade_insuficiente" for r in out["rejected"]),
          str([r.get("regra") for r in out["rejected"]]))

    # SC-009b em desfecho real: mesma necessidade e dado, oferta maior nunca pior
    dc_pobre = motor.trade_dc(5, 8 / 25)
    dc_rica = motor.trade_dc(5, 30 / 25)
    check("SC-009b: com a mesma necessidade, oferta maior nunca é mais difícil",
          dc_rica <= dc_pobre, f"rica={dc_rica} pobre={dc_pobre}")

    # --- ATOMICIDADE (SC-002/SC-007) ------------------------------------------ #
    # Elga com as duas mãos ocupadas não tem como receber mais nada
    marcar(FRASCO, negotiable=True)
    dar(ELGA, FRASCO); dar(ELGA, ANEL, slot="mao")
    marcar(ANEL, negotiable=True)
    dar(TORVIN, CORDA)
    for m in MOEDAS:
        guardar(m, BOLSA)
    marcar(MOEDAS[0], negotiable=True)
    marcar(MOEDAS[1], negotiable=True)
    antes = digital()
    force_roll(20)
    out = negociar(TORVIN, "trade", ELGA, [CORDA, MOEDAS[0], MOEDAS[1]],
                   [FRASCO], necessidade=9)
    coube = bool(out["trade_ops_applied"])
    check("atomicidade: se alguma perna não cabe, NADA se move",
          coube or digital() == antes,
          "houve mudança parcial" if not coube else "")
    if coube:  # cenário coube: desfaz para seguir
        dar(TORVIN, CORDA)
        guardar(MOEDAS[0], BOLSA); guardar(MOEDAS[1], BOLSA)
        dar(ELGA, FRASCO)

    marcar(ANEL, negotiable=None)     # volta a ser o intocável

    # recusa qualquer ⇒ mundo idêntico
    antes = digital()
    forbid_roll()
    negociar(TORVIN, "buy", ELGA, [MOEDAS[0]], [ANEL])
    check("SC-002: após recusa, mundo idêntico byte a byte", digital() == antes)

    # --- equivalência com o give (risco D6) ----------------------------------- #
    # As duas rotas usam os MESMOS check_*, mas têm políticas de destino
    # diferentes de propósito: a negociação guarda numa bolsa quando há (senão
    # comprar com três moedas seria impossível), enquanto o `give` põe na mão.
    # A equivalência que precisa valer é a das REGRAS: sem contêiner disponível,
    # os dois têm de dar o mesmo veredito.
    chao(CAIXA)                       # tira a bolsa da Elga: só restam as mãos
    dar(TORVIN, CORDA); dar(ELGA, FRASCO)
    marcar(CORDA, negotiable=True); marcar(FRASCO, negotiable=True)
    forbid_roll()
    out_neg = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=10)
    ok_neg = bool(out_neg["trade_ops_applied"])
    dar(TORVIN, CORDA); dar(ELGA, FRASCO)
    out_give = motor.apply_resolution(TORVIN, res(
        item_transfers=[{"item": CORDA, "to": ELGA}]))
    ok_give = bool(out_give["item_transfers_applied"])
    check("equivalência com o give (sem contêiner): mesmo veredito físico",
          ok_neg == ok_give, f"negociacao={ok_neg} give={ok_give}")
    dar(TORVIN, CORDA); dar(ELGA, CAIXA)

    # --- recusas distintas (SC-003) e pureza (SC-008) ------------------------- #
    dar(ELGA, FRASCO)
    regras = set()
    forbid_roll()
    for o in (negociar(TORVIN, "buy", ELGA, MOEDAS, [ANEL]),
              negociar(TORVIN, "trade", ELGA, [CORDA], [ANEL], necessidade=8),
              negociar(TORVIN, "buy", ELGA, MOEDAS[:1], [FRASCO]),
              negociar(TORVIN, "buy", ELGA, MOEDAS, ["nao-existe"]),
              negociar(TORVIN, "buy", "ninguem-aqui", MOEDAS, [FRASCO])):
        regras |= {r.get("regra") for r in o["rejected"] if r.get("regra")}
    force_roll(1)
    regras |= {r.get("regra") for r in
               negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO],
                        necessidade=5)["rejected"] if r.get("regra")}
    check("SC-003: causas distintas e não intercambiáveis",
          {"nao_esta_a_venda", "nao_e_negociavel", "valor_insuficiente",
           "necessidade_insuficiente", "item_nao_e_seu",
           "personagem_inacessivel"} <= regras, str(sorted(regras)))

    # parceiro caído
    folder = motor.find_character_folder(ELGA)
    fm, body = motor.read_doc(folder / "character.md")
    fm["status"] = {**fm["status"], "hp": 0, "conditions": ["incapacitado"]}
    motor.write_doc(folder / "character.md", fm, body)
    forbid_roll()
    out = negociar(TORVIN, "buy", ELGA, MOEDAS, [FRASCO])
    check("SC-005: parceiro caído ⇒ parceiro_incapaz, sem avaliação",
          any(r.get("regra") == "parceiro_incapaz" for r in out["rejected"]))
    fm["status"] = {**fm["status"], "hp": 90, "conditions": []}
    motor.write_doc(folder / "character.md", fm, body)

    force_roll(1)
    out_sec = negociar(TORVIN, "trade", ELGA, [CORDA], [FRASCO], necessidade=5)
    frases = [f["o_que_falhou"] for f in
              server_app.inworld_failures(out_sec["rejected"]) if isinstance(f, dict)]
    frases += [t["o_que"] for t in server_app.fate_twists(out_sec["rolls"])]
    check("SC-008: nenhum número ou nome de campo nas FRASES in-world",
          frases and not any(any(c.isdigit() for c in f) for f in frases)
          and not any(t in f for f in frases
                      for t in ("value", "necessidade", "dc", "for_sale")),
          str(frases))

    # --- guarda do Árbitro ---------------------------------------------------- #
    dar(TORVIN, CORDA)
    for m in MOEDAS:
        guardar(m, BOLSA)
    dar(ELGA, FRASCO)
    ctx = motor.get_context(TORVIN)
    tools = {t["name"]: t for t in arbiter.build_tools(ctx)}
    check("manifest: buy e trade presentes, com enums filtrados pelo portão",
          "buy" in tools and "trade" in tools
          and FRASCO in tools["buy"]["parameters"]["properties"]["mercadoria"]["items"]["enum"]
          and ANEL not in tools["buy"]["parameters"]["properties"]["mercadoria"]["items"]["enum"]
          and ANEL not in tools["trade"]["parameters"]["properties"]["quero"]["items"]["enum"],
          str(tools.get("buy", {}).get("parameters", {})))

    r_self = arbiter.resolve_with_tools(
        {"action": "negocia consigo"}, ctx,
        scripted_loop([("buy", {"parceiro": TORVIN, "pagamento": MOEDAS,
                                "mercadoria": [FRASCO]})]))
    check("guarda: parceiro == ator é recusado", not (r_self.get("trade_ops") or []))

    r_dup = arbiter.resolve_with_tools(
        {"action": "negocia duas vezes"}, ctx,
        scripted_loop([("buy", {"parceiro": ELGA, "pagamento": MOEDAS,
                                "mercadoria": [FRASCO]}),
                       ("buy", {"parceiro": ELGA, "pagamento": MOEDAS,
                                "mercadoria": [FRASCO]})]))
    check("guarda: segunda negociação com o mesmo parceiro é ignorada",
          len(r_dup.get("trade_ops") or []) == 1)

    r_anel = arbiter.resolve_with_tools(
        {"action": "compra o anel"}, ctx,
        scripted_loop([("buy", {"parceiro": ELGA, "pagamento": MOEDAS,
                                "mercadoria": [ANEL]})]))
    check("guarda: o intocável é barrado já no Árbitro",
          not (r_anel.get("trade_ops") or []))

    # spec 020: os buys de guarda APLICARAM por-op (fase única) — FRASCO foi para
    # TORVIN e as MOEDAS para ELGA. Restaura o estado pré-compra para os testes da
    # banca, que assumem a mercadoria com a Elga e o comprador com dinheiro.
    for _m in MOEDAS:
        _mf = ifolder(_m)
        _dst = motor.find_character_folder(TORVIN) / _mf.name
        if _mf != _dst:
            os.replace(_mf, _dst)
    _frf = ifolder(FRASCO)
    _frd = motor.find_character_folder(ELGA) / _frf.name
    if _frf != _frd:
        _ffm, _fbody = motor.read_doc(_frf / "item.md")
        _ffm.pop("state", None)
        motor.write_doc(_frf / "item.md", _ffm, _fbody)
        os.replace(_frf, _frd)

    # --- a banca do mascate: estar à venda NÃO é estar à vista ---------------- #
    # A mercadoria guardada continua invisível a terceiros (spec 004 FR-009). Quem
    # sabe o que o outro vende é o ÁRBITRO, lendo o mundo — e o player descobre
    # PERGUNTANDO (ask_wares), não olhando.
    guardar(FRASCO, CAIXA)          # a mercadoria vai para dentro da bolsa da Elga
    guardar(ANEL, CAIXA)
    marcar(ANEL, negotiable=None, for_sale=None)
    vistos = {i["id"] for i in motor._visible_item_refs(motor.find_character_folder(ELGA))}
    check("bolsa comum (fechado ausente): conteúdo NÃO vaza a terceiros",
          FRASCO not in vistos and ANEL not in vistos, str(sorted(vistos)))

    # escancarar de propósito: `fechado: false` põe o conteúdo à mostra
    cf = ifolder(CAIXA) / "item.md"
    cfm, cbody = motor.read_doc(cf)
    cfm["state"] = {**(cfm.get("state") or {}), "fechado": False}
    motor.write_doc(cf, cfm, cbody)
    vistos_ab = {i["id"] for i in motor._visible_item_refs(motor.find_character_folder(ELGA))}
    check("contêiner ESCANCARADO (fechado: false): conteúdo fica à mostra",
          FRASCO in vistos_ab and ANEL in vistos_ab, str(sorted(vistos_ab)))
    check("o que está à mostra diz onde está",
          any(i.get("a_mostra_em") == CAIXA
              for i in motor._visible_item_refs(motor.find_character_folder(ELGA))))
    cfm["state"] = {k: v for k, v in cfm["state"].items() if k != "fechado"}
    motor.write_doc(cf, cfm, cbody)

    oferta = motor.offered_by(ELGA)
    check("consulta de server: o Árbitro sabe o que ela vende",
          FRASCO in [i["id"] for i in oferta["a_venda"]]
          and ANEL not in [i["id"] for i in oferta["trocaveis"]], str(oferta))

    ctx2 = motor.get_context(TORVIN)
    tools2 = {t["name"]: t for t in arbiter.build_tools(ctx2)}
    check("com a mercadoria guardada, buy AINDA é oferecida (enum vem do server)",
          "buy" in tools2
          and FRASCO in tools2["buy"]["parameters"]["properties"]["mercadoria"]["items"]["enum"])
    check("ask_wares está no manifest", "ask_wares" in tools2)

    r_ask = arbiter.resolve_with_tools(
        {"action": "pergunta o que ela vende"}, ctx2,
        scripted_loop([("ask_wares", {"parceiro": ELGA})]))
    check("perguntar devolve a lista para A Mente narrar",
          r_ask.get("wares") and FRASCO in
          [i["id"] for i in r_ask["wares"][0]["a_venda"]], str(r_ask.get("wares")))

    print("\n--- Guarda de prosa: JSON descrito não é ato ------------------------")

    _ctx_g = motor.get_context(TORVIN)
    _por_nome = {t["name"]: t for t in arbiter.build_tools(_ctx_g)}

    def _extrai(texto):
        """Espelha a extração da guarda, para testá-la sem chamar o modelo."""
        achados = []
        for obj in arbiter._json_objects(texto):
            if not isinstance(obj, dict) or not obj.get("name"):
                continue
            spec = _por_nome.get(obj["name"])
            if spec is None:
                continue
            args = obj.get("parameters")
            if not isinstance(args, dict):
                args = obj.get("arguments")
            if not isinstance(args, dict):
                args = {}
            if [k for k in (spec["parameters"].get("required") or []) if k not in args]:
                continue
            achados.append((obj["name"], args))
        return achados

    # o caso real: o modelo escreveu prosa com um JSON de unequip, e a guarda
    # largou o gibão de um personagem no chão da praça quando o jogador só
    # queria perguntar o que o mascate tinha para trocar
    check("tool fora do manifest NÃO vira ato",
          _extrai('poderia usar {"name": "teleportar", "parameters": {"x": 1}}') == [])
    check("menção SEM os parâmetros obrigatórios NÃO vira ato",
          _extrai('eu poderia {"name": "drop"} se quisesse') == [],
          str(_extrai('eu poderia {"name": "drop"} se quisesse')))
    _ok = _extrai('{"name": "ask_wares", "parameters": {"parceiro": "%s"}}' % ELGA)
    check("chamada COMPLETA e no manifest continua sendo executada",
          any(n == "ask_wares" for n, _ in _ok), str(_ok))

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S): {', '.join(FAILS)}")
        sys.exit(1)
    print("todos os checks da Fase 14 (spec 011) passaram.")
finally:
    shutil.rmtree(_tmp, ignore_errors=True)
