"""Fase 70 — O PRAZO COMO PRIMITIVA (spec 070).

O que este arquivo protege, e por que cada um importa:

1. **Vence UMA VEZ.** Sob N leituras e sob leituras concorrentes do mesmo turno. Sem
   isso, um pão poderia mofar dez vezes numa cena com dez olhares.
2. **Relógio para trás não ressuscita.** Restaurar um backup ou ajustar a hora não pode
   desfazer o que já venceu.
3. **Entidade sem prazo se comporta como hoje.** O mundo editorial tem centenas de itens
   sem uma linha de prazo, e nenhum deles pode mudar de comportamento (FR-010, SC-007).
4. **Forma inválida não vence** — e é REPORTADA, nunca ignorada em silêncio. Um prazo
   que vence e não faz nada é a família de defeito que mais custou a este projeto.
5. **Vencer não chama modelo.** É a restrição que impede o colapso: uma cena com N
   vencidos custa N trocas de string, nunca N chamadas de Árbitro.

Uso:  python3 selftest_phase70.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from motor import io, prazo  # noqa: E402

falhas: list[str] = []


def check(nome: str, cond: bool, detalhe: str = "") -> None:
    if cond:
        print(f"[ok  ] {nome}")
    else:
        print(f"[FALHA] {nome}" + (f" — {detalhe}" if detalhe else ""))
        falhas.append(nome)


def _item(raiz: Path, nome: str, fm_extra: dict, corpo: str = "Um pão escuro.") -> Path:
    pasta = raiz / nome
    pasta.mkdir(parents=True, exist_ok=True)
    fm = {"type": "item", "id": nome, "name": nome.replace("-", " ").title(),
          "weight_kg": 0.4}
    fm.update(fm_extra)
    io.write_doc(pasta / "item.md", fm, corpo)
    return pasta


def _recusa_ao_gravar(raiz: Path) -> bool:
    """O World Validator roda no `write_doc` — então o caminho autoritativo recusa um
    prazo torto ANTES de ele existir. Só o mundo editorial, escrito à mão, pode conter um.
    """
    try:
        _item(raiz, "nunca-gravada", {"prazo": {
            "vence_em": 1, "ao_vencer": {"verbo": "explodir"}, "vencido_em": None}})
    except io.ValidationError:
        return True
    return False


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="prazo-"))
    agora = time.time()
    try:
        print("--- 1. vence UMA VEZ, sob N leituras ------------------------------")
        p = _item(tmp, "pao-de-centeio", {"prazo": {
            "vence_em": agora - 10,
            "ao_vencer": {"verbo": "campo", "campo": "state.comestivel", "valor": False},
            "urgencia": "passa de um dia e azeda",
            "descricao_vencida": "pão duro e azedo, de cheiro ruim",
            "vencido_em": None}})
        fm, _ = io.read_doc(p / "item.md")
        primeiro = prazo.vencer_se_for_hora(p, fm)
        check("1a: a primeira leitura aplica", primeiro is not None, str(primeiro))
        fm, corpo = io.read_doc(p / "item.md")
        check("1b: o campo declarado foi escrito",
              fm.get("state", {}).get("comestivel") is False, str(fm.get("state")))
        check("1c: a prosa virou a descrição pós-vencimento",
              "azedo" in corpo, corpo[:60])
        check("1d: `vencido_em` foi carimbado", bool(fm["prazo"].get("vencido_em")))

        repetidas = [prazo.vencer_se_for_hora(p, io.read_doc(p / "item.md")[0])
                     for _ in range(10)]
        check("1e: dez leituras seguintes NÃO aplicam de novo",
              all(r is None for r in repetidas), str(repetidas))

        print("\n--- 2. leituras concorrentes do mesmo turno -----------------------")
        q = _item(tmp, "queijo", {"prazo": {
            "vence_em": agora - 5, "ao_vencer": {"verbo": "extinguir"},
            "urgencia": "", "descricao_vencida": "", "vencido_em": None}})
        fm_a, _ = io.read_doc(q / "item.md")
        fm_b = dict(fm_a)          # duas leituras com a MESMA foto, antes de qualquer escrita
        r1 = prazo.vencer_se_for_hora(q, fm_a)
        r2 = prazo.vencer_se_for_hora(q, fm_b)
        check("2a: a primeira aplica", r1 is not None)
        check("2b: a segunda, com a foto velha, NÃO aplica de novo", r2 is None, str(r2))

        print("\n--- 3. relógio para trás ------------------------------------------")
        depois, _ = io.read_doc(p / "item.md")
        check("3a: já vencido continua vencido mesmo consultando o passado",
              prazo.pendente(depois["prazo"], agora - 10_000) is False)

        print("\n--- 4. entidade SEM prazo ----------------------------------------")
        s = _item(tmp, "pedra", {})
        fm_s, corpo_s = io.read_doc(s / "item.md")
        check("4a: sem bloco `prazo`, nada acontece",
              prazo.vencer_se_for_hora(s, fm_s) is None)
        check("4b: e o arquivo não é tocado",
              io.read_doc(s / "item.md")[1] == corpo_s)
        check("4c: `tem_prazo` é falso", prazo.tem_prazo(fm_s) is False)

        print("\n--- 5. forma inválida --------------------------------------------")
        maus = [
            ({"vence_em": agora - 1, "ao_vencer": {"verbo": "explodir"}},
             "verbo fora do vocabulário"),
            ({"vence_em": agora - 1, "ao_vencer": {"verbo": "campo"}},
             "campo sem `campo`/`valor`"),
            ({"ao_vencer": {"verbo": "extinguir"}}, "sem `vence_em`"),
            ({"vence_em": agora - 1, "ao_vencer": {"verbo": "virar"}},
             "virar sem `descricao_vencida`"),
        ]
        for bloco, rotulo in maus:
            check(f"5: recusa e EXPLICA — {rotulo}",
                  prazo.forma_valida(bloco) is not None,
                  "passou como válido")
        # O ARQUIVO TORTO SÓ EXISTE SE ALGUÉM O ESCREVEU À MÃO — e isso é um achado, não
        # um contorno: `io.write_doc` já valida, então o Motor NUNCA grava um prazo
        # inválido. O caso que sobra é o mundo editorial, escrito por gente. Por isso
        # aqui o arquivo é criado a seco, sem passar pelo Motor.
        mau = tmp / "coisa-torta"
        mau.mkdir(parents=True, exist_ok=True)
        (mau / "item.md").write_text(
            "---\ntype: item\nid: coisa-torta\nname: Coisa Torta\nweight_kg: 0.1\n"
            "prazo:\n  vence_em: 1\n  ao_vencer:\n    verbo: explodir\n  vencido_em: null\n"
            "---\n\nUma coisa torta.\n", encoding="utf-8")
        fm_m, corpo_m = io.read_doc(mau / "item.md")
        check("5e: prazo inválido NÃO vence (e não corrompe o arquivo)",
              prazo.vencer_se_for_hora(mau, fm_m) is None
              and io.read_doc(mau / "item.md")[1] == corpo_m)
        check("5f: e o Motor nunca GRAVA um prazo inválido",
              _recusa_ao_gravar(tmp))

        print("\n--- 6. vencer não chama modelo ------------------------------------")
        # A restrição que impede o colapso. Se `aplicar` um dia importar `arbiter` ou
        # chamar `ctx.ask`, este teste é a rede — e o cenário é banal: dez coisas
        # vencidas numa cena custariam dez chamadas de Árbitro numa LEITURA.
        fonte = Path(__file__).parent / "motor" / "prazo.py"
        texto = fonte.read_text(encoding="utf-8")
        codigo = "\n".join(l for l in texto.splitlines()
                           if not l.strip().startswith("#"))
        check("6a: `motor/prazo.py` não importa o Árbitro",
              "import arbiter" not in codigo and "from arbiter" not in codigo)
        check("6b: e não pergunta nota a ninguém",
              ".ask(" not in codigo and "julgamento(" not in codigo)

        dez = []
        for i in range(10):
            dez.append(_item(tmp, f"vencido-{i}", {"prazo": {
                "vence_em": agora - 1, "ao_vencer": {"verbo": "extinguir"},
                "urgencia": "", "descricao_vencida": f"resto {i}",
                "vencido_em": None}}))
        t0 = time.time()
        aplicados = [prazo.vencer_se_for_hora(d, io.read_doc(d / "item.md")[0])
                     for d in dez]
        dt = time.time() - t0
        check("6c: dez vencimentos numa cena são dez trocas de string",
              all(a is not None for a in aplicados) and dt < 1.0,
              f"{dt:.3f}s")
        print("\n--- 7. O CICLO INTEIRO: alguém CARIMBA um prazo -------------------")
        # O FURO QUE ESTE BLOCO EXISTE PARA IMPEDIR. Na primeira entrega, `motor/prazo.py`
        # estava completo, o validator validava, o vencimento aplicava e o gancho
        # preguiçoso disparava — e NADA no jogo chamava `carimbar`. A feature inteira era
        # inerte, e nenhum teste percebeu, porque todos exercitavam a primitiva de
        # dentro. Este checa a ponta que faltava: uma capacidade real cria a coisa com
        # prazo.
        # TODA capacidade que cria coisa perecível precisa carimbar. Listar as seis aqui
        # é o que impede a feature de existir só para uma delas — que foi o furo da
        # primeira entrega, e depois o de a segunda cobrir só `craft`.
        # DOIS CAMINHOS, e a distinção é real — não é frouxidão do teste:
        #
        #  DIRETO   a capacidade cria a coisa e carimba ali mesmo (peça na bigorna,
        #           erva colhida, porção de carne).
        #  RESULTADO a capacidade cria uma PEÇA que termina sozinha, e a coisa só passa
        #           a existir na materialização. Quem carimba é `trabalho.resolver_prazos`,
        #           o ponto ÚNICO por onde cook e brew terminam — escrever a mesma regra
        #           dentro das duas seria a segunda via que o Princípio I proíbe.
        CRIADORAS = {
            "craft":    ("direto",    "peça em processo — janela de retomada"),
            "forja":    ("direto",    "peça na bigorna — janela de retomada"),
            "herbario": ("direto",    "o que se colhe — murcha"),
            "acougue":  ("direto",    "a carne crua — apodrece"),
            "cozinha":  ("resultado", "o prato feito — validade"),
            "botica":   ("resultado", "o preparo — validade"),
        }
        base = Path(__file__).parent / "motor"
        sem_comentario = lambda p: "\n".join(
            l for l in p.read_text(encoding="utf-8").splitlines()
            if not l.strip().startswith("#")) if p.exists() else ""
        for modulo, (via, oquee) in CRIADORAS.items():
            origem = sem_comentario(base / modulo / "executores.py")
            if via == "direto":
                ok = "prazo.carimbar" in origem
            else:
                ok = ("descricao_vencida" in origem and "dura_s" in origem)
            check(f"7-{modulo}: cria com prazo, via {via} ({oquee})", ok,
                  "não carimba nem alimenta o `resultado`")
        # e a ponta que materializa precisa mesmo carimbar
        check("7-materializacao: `trabalho` carimba a validade do que fica pronto",
              "prazo.carimbar" in sem_comentario(base / "trabalho.py"))

        # e o ciclo, de ponta a ponta, com o carimbo de verdade
        alvo = tmp / "peca-viva"
        alvo.mkdir(parents=True, exist_ok=True)
        io.write_doc(alvo / "item.md",
                     {"type": "item", "id": "peca-viva", "name": "Alaúde (em processo)",
                      "weight_kg": 1.0}, "Alaúde ainda em processo.")
        prazo.carimbar(alvo, -1, {"verbo": "virar"},
                       urgencia="a cola ainda está fresca",
                       descricao_vencida="alaúde colado de forma indevida, de som torto")
        fm_v, _ = io.read_doc(alvo / "item.md")
        feito = prazo.vencer_se_for_hora(alvo, fm_v)
        _, corpo_v = io.read_doc(alvo / "item.md")
        check("7c: carimbado, vencido e a prosa virou a pós-vencimento",
              feito is not None and "som torto" in corpo_v, corpo_v[:50])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if falhas:
        print(f"{len(falhas)} FALHA(S): " + ", ".join(falhas))
        return 1
    print("fase 70: o prazo vence uma vez, não volta atrás e não chama modelo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
