"""Auto-teste da Fase 45 — a FACE EXPOSTA (spec 043, US1/US2).

(Número de FASE ≠ número de SPEC.)

A rede que guarda a fronteira do Princípio IX (v2.0.0 — ESCOLHA × JUÍZO) no ponto em
que ela de fato acontece: o que o mundo entrega para A Mente escolher.

Os invariantes de `contracts/face-exposta.md`, um a um:
  1. nenhum parâmetro de JUÍZO desce — nem como alvo, nem como exigência
  2. nenhuma capacidade INTERNA desce (a caneta do mundo)
  3. os alvos são só o que existe NAQUELA cena
  4. capacidade com alvo obrigatório sem candidato SOME
  5. capacidade fora do manifesto de ativação do mundo SOME
  6. quem dorme vê só a capacidade de acordar
  7. a face NÃO diverge do manifesto que a engine usa (é derivada dele, não uma
     segunda montagem) — divergir faria a Mente propor o que o mundo recusa
  8. quem caiu não vê capacidade nenhuma

Zero LLM: tudo é derivado do registro e da cena.

Uso:  python3 server/selftest_phase45.py
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parent

_tmp = Path(tempfile.mkdtemp(prefix="loreforge-test45-"))
shutil.copytree(SERVER_DIR / "tests" / "world", _tmp / "world")
os.environ["LOREFORGE_WORLD"] = str(_tmp / "world")
os.environ["LOREFORGE_LOG"] = "0"

sys.path.insert(0, str(SERVER_DIR))
import arbiter  # noqa: E402
import face  # noqa: E402
import mcp_core  # noqa: E402
import openapi  # noqa: E402  (o contrato que o `spec.html` lê — a face nao pode divergir dele)
import motor  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print(f"[{'ok  ' if cond else 'FALHA'}] {name}"
          + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _um_personagem() -> str:
    return sorted(c["id"] for c in motor.list_characters())[0]


def run() -> int:
    FAILS.clear()
    cid = _um_personagem()
    ctx = motor.get_context(cid)
    f = face.build(ctx)
    bruto = json.dumps(f, ensure_ascii=False)

    check("a face tem capacidades", len(f) > 0, f"{len(f)}")

    # --- 1. nenhum JUÍZO desce ------------------------------------------------ #
    juizo_params = set()
    vistos = set()
    for nome, spec in motor.registro.specs().items():
        if id(spec) in vistos:
            continue
        vistos.add(id(spec))
        if spec.juizo:
            juizo_params.add(spec.juizo[0])
    vazando = []
    for cap in f:
        for p in juizo_params:
            if p in cap["alvos"] or p in cap["exige"]:
                vazando.append(f"{cap['nome']}.{p}")
    check("nenhum parâmetro de JUÍZO desce (nem alvo, nem exigência)",
          not vazando, ", ".join(vazando))
    check("há juízo declarado para guardar (senão o teste 1 é vazio)",
          len(juizo_params) > 0, f"{sorted(juizo_params)}")

    # --- 2. nenhuma INTERNA desce --------------------------------------------- #
    internas = {n for n, s in motor.registro.specs().items() if s.interna}
    na_face = {c["nome"] for c in f} & internas
    check("nenhuma capacidade INTERNA desce (a caneta do mundo)",
          not na_face, f"vazou: {sorted(na_face)}")
    check("há interna declarada para guardar", len(internas) >= 3, f"{sorted(internas)}")

    # --- 3. os alvos são da CENA ---------------------------------------------- #
    presentes = {c["id"] for c in (ctx.get("characters_present") or [])}
    presentes |= {i["id"] for i in (ctx.get("items_present") or [])}
    presentes |= {o["id"] for o in (ctx.get("objects_present") or [])}
    presentes |= {r["id"] for r in (ctx.get("routes") or [])}
    # inventário do próprio ator também é alvo legítimo
    presentes |= {i["id"] for i in (((ctx.get("self") or {}).get("inventory")) or [])}
    forasteiros = []
    for cap in f:
        for p, alvos in cap["alvos"].items():
            for a in alvos:
                if isinstance(a, str) and a not in presentes and not a.startswith("mem-"):
                    # ids de rota do mundo e estados/intensidades são enums de
                    # vocabulário, não de cena — não checáveis contra presentes
                    if a in ("ativa", "concluida", "abandonada",
                             "small", "medium", "large", "giant"):
                        continue
                    forasteiros.append(f"{cap['nome']}.{p}={a}")
    check("os alvos não citam nada fora da cena (amostra)",
          len(forasteiros) < 40, f"{len(forasteiros)}: {forasteiros[:5]}")

    # --- 7. a face NÃO diverge do manifesto da engine -------------------------- #
    # A face = (manifesto de MUTAÇÃO − internas) + a lane de CONSULTA (spec 040).
    # A parcela de consulta entrou depois: existia no Motor e era servida por
    # `/api/consult`, mas nenhum ponto de `get_context -> face.build ->
    # mcp_core.tools()` a lia, então a Mente não podia verificar condição nenhuma
    # antes de agir. As duas parcelas vêm de registros SEPARADOS — `registro.specs()`
    # e `registro.consult_specs()` — e é por isso que a soma tem de ser checada aqui.
    manifesto = {t["name"] for t in arbiter.build_tools(ctx)}
    consultas = set(motor.consult_specs())
    da_face = {c["nome"] for c in f}
    check("a face é o manifesto menos as internas, mais a lane de consulta",
          da_face == (manifesto - internas) | consultas,
          f"só na face: {sorted(da_face - manifesto - consultas)} | "
          f"faltando: {sorted(((manifesto - internas) | consultas) - da_face)}")
    # TODA capacidade da face TEM FICHA no contrato (`/api/spec`). O filtro por
    # personagem do `spec.html` casa os dois pelo nome: o que está na face e não tem
    # ficha simplesmente desaparece da tela quando se escolhe alguém — a bancada
    # mentiria por omissão, que foi exatamente o buraco de `openapi._capacidades`
    # iterar só o registro de mutação.
    contrato = set((openapi.gerar().get("components") or {}).get("schemas") or {})
    check("toda capacidade da face tem ficha em /api/spec",
          da_face <= contrato, f"na face e fora do contrato: {sorted(da_face - contrato)}")

    check("a consulta desce MARCADA (e a mutação não)",
          all(c["consulta"] for c in f if c["nome"] in consultas)
          and not any(c["consulta"] for c in f if c["nome"] not in consultas),
          str([(c["nome"], c["consulta"]) for c in f if c["nome"] in consultas]))
    # Perguntar não é tentar: sem `prosa` obrigatória no schema, senão a Mente teria
    # de encenar uma ação para consultar o relógio.
    for c in f:
        if not c["consulta"]:
            continue
        check(f"schema de `{c['nome']}` não exige prosa",
              "prosa" not in mcp_core.input_schema(c).get("required", []),
              str(mcp_core.input_schema(c)))

    # --- 4. gate de alvo vazio ------------------------------------------------ #
    # numa cena sem OUTRO personagem, o que exige alguém presente some.
    sozinho = None
    for c in motor.list_characters():
        outros = [o for o in (motor.get_context(c["id"]).get("characters_present") or [])
                  if o.get("state") != "self"]
        if not outros:
            sozinho = c["id"]
            break
    if sozinho:
        f_só = {c["nome"] for c in face.build(motor.get_context(sozinho))}
        check("sozinho: o que exige outra pessoa SOME da face",
              not (f_só & {"attack", "persuade", "give", "ask_about", "ask_directions"}),
              f"sobrou: {sorted(f_só & {'attack', 'persuade', 'give'})}")
    else:
        check("sozinho: cenário disponível no mundo de teste", True)

    # --- 6. gate de descanso -------------------------------------------------- #
    pasta = motor.find_character_folder(cid)
    fm, body = motor.read_doc(pasta / "character.md")
    status_original = dict(fm.get("status") or {})
    # `is_resting` (spec 031) lê `descansando_desde` — é a ÚNICA definição
    # de "está dormindo" no código; nenhuma condição textual substitui.
    fm["status"] = {**status_original, "descansando_desde": 1700000000}
    motor.write_doc(pasta / "character.md", fm, body)
    try:
        f_dormindo = face.build(motor.get_context(cid))
        # item 50: a capacidade de quem dorme é `wake_up`, e ela CHEGA AQUI PELO
        # REGISTRO — antes o gate escrevia esta face à mão dentro de `build_tools`.
        # O nome é o que a Mente lê para escolher: `sleep` a quem já dorme mediu
        # 6/10, `wake_up` mediu 10/10 (item 30).
        check("quem dorme vê SÓ a capacidade de acordar",
              [c["nome"] for c in f_dormindo] == ["wake_up"],
              str([c["nome"] for c in f_dormindo]))
        # e a marca é declarada na tool, não deduzida do nome aqui
        check("a capacidade de acordar se declara `only_while_resting`",
              motor.registro.get_spec("wake_up").only_while_resting is True)
        check("deitar NÃO é `only_while_resting` (senão sumiria de quem está de pé)",
              motor.registro.get_spec("sleep").only_while_resting is False)
    finally:
        fm["status"] = status_original
        motor.write_doc(pasta / "character.md", fm, body)

    # --- 8. quem caiu não age ------------------------------------------------- #
    # ESTE CHECK JÁ EXISTIU E PASSAVA VAZIO. Era
    #     "attack" not in f_caido  OR  len(f_caido) <= len(f)
    # e o `or` salvava sempre: `attack` ESTAVA na face do caído, então a condição
    # caía no comparador de tamanho, verdadeiro em qualquer cena normal. Resultado —
    # 23 capacidades desciam para um MORTO (medido no mundo real: o Bramm), a Mente
    # propunha `attack`, e o mundo respondia "está morto" depois de a vez já ter
    # queimado uma chamada de modelo. Um check com `or` entre duas condições, das
    # quais só uma é a que interessa, não é um check.
    #
    # Agora é exato, e separa os dois estados como o `_refuse_if_down` separa.
    fm, body = motor.read_doc(pasta / "character.md")
    consultas_nomes = set(motor.consult_specs())
    try:
        fm["status"] = {**status_original, "conditions": [motor.INCAPACITATED]}
        motor.write_doc(pasta / "character.md", fm, body)
        f_incap = {c["nome"] for c in face.build(motor.get_context(cid))}
        check("INCAPACITADO vê SÓ a lane de consulta (lembra e olha a hora; não age)",
              f_incap == consultas_nomes, str(sorted(f_incap)))

        fm["status"] = {**status_original,
                        "conditions": [motor.INCAPACITATED, motor.DEAD]}
        motor.write_doc(pasta / "character.md", fm, body)
        f_morto = face.build(motor.get_context(cid))
        check("MORTO não vê nada — nem consulta", f_morto == [],
              str(sorted(c["nome"] for c in f_morto)))

        # e o gate não pode ser frouxo com o `morto` sozinho, sem `incapacitado`
        fm["status"] = {**status_original, "conditions": [motor.DEAD]}
        motor.write_doc(pasta / "character.md", fm, body)
        check("MORTO sem `incapacitado` também não vê nada",
              face.build(motor.get_context(cid)) == [])
    finally:
        fm["status"] = status_original
        motor.write_doc(pasta / "character.md", fm, body)

    # a rede contra o oposto: um gate que apagasse a face de QUEM ESTÁ DE PÉ passaria
    # nos três checks acima e mataria o jogo inteiro em silêncio.
    check("quem está de pé continua vendo a face cheia",
          len({c["nome"] for c in face.build(motor.get_context(cid))}) > len(consultas_nomes))

    # `conditions` FORA DE LISTA não pode virar busca de substring. Não é hipótese:
    # há personagem no mundo de verdade com uma frase gravada nesse campo, e um teste
    # de pertinência escrito à mão (`motor.DEAD in conds`) sobre uma string acharia
    # "morto" dentro de "não está morto de cansaço" — apagando a face de quem está de
    # pé. O gate reusa `motor.is_down`, que guarda; este check é o que impede alguém
    # de "simplificar" de volta.
    for conds in ("não está morto de cansaço", "[]", None, 42):
        check(f"`conditions` inválido ({type(conds).__name__}) não apaga a face de quem está de pé",
              face._gate_de_caido({"self": {"status": {"conditions": conds}}}) is None,
              repr(conds))
    # o caso que merece rótulo próprio: `conditions: "morto"` (string, não lista) NÃO
    # gateia — e isso é DELIBERADO, não descuido. `motor.is_down` trata campo fora de
    # lista como "nenhuma condição", e a face concordar com a única definição do
    # código vale mais que adivinhar a intenção de um arquivo malformado. Quem quer o
    # personagem morto escreve `conditions: [morto]`; o World Validator é o lugar de
    # reclamar do resto, não este gate.
    check("`conditions: \"morto\"` como STRING não gateia (a face segue a definição do Motor)",
          face._gate_de_caido({"self": {"status": {"conditions": "morto"}}}) is None
          and not motor.is_down({"status": {"conditions": "morto"}}))

    # --- descrição: é a player-facing, não a interna --------------------------- #
    check("toda capacidade da face tem descrição",
          all((c["descricao"] or "").strip() for c in f),
          str([c["nome"] for c in f if not (c["descricao"] or "").strip()]))
    check("a face não vaza mecânica (mesma régua da Fase 44)",
          not any(t in bruto.lower() for t in ("0-10", "régua", "segredo do mundo",
                                               "na aplicação")),
          "termo de mecânica encontrado na face")

    print()
    if FAILS:
        print(f"{len(FAILS)} FALHA(S) na Fase 45: {', '.join(FAILS)}")
        return 1
    print("todos os checks da Fase 45 passaram.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(run())
    finally:
        shutil.rmtree(_tmp, ignore_errors=True)
