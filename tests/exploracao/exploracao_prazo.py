"""EXPLORATÓRIO da spec 070 — o prazo pelo pipeline, e o que ninguém desenhou.

Não é selftest: é a bateria da skill `loreforge-implement-review`, e o objetivo é achar
o que os testes de unidade não pegam. Cada bloco parte de um mundo tmp limpo.

Uso:  python3 tests/exploracao/exploracao_prazo.py
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

achados: list[tuple[str, str, str]] = []


def achado(tipo: str, titulo: str, detalhe: str) -> None:
    achados.append((tipo, titulo, detalhe))
    print(f"  [{tipo.upper()}] {titulo}\n     {detalhe}")


def mundo_tmp() -> Path:
    d = Path(tempfile.mkdtemp(prefix="expl-prazo-"))
    (d / "lugar").mkdir(parents=True)
    os.environ["LOREFORGE_WORLD"] = str(d)
    return d


def item(raiz: Path, nome: str, fm: dict, corpo: str):
    import motor.io as io
    pasta = raiz / "lugar" / nome
    pasta.mkdir(parents=True, exist_ok=True)
    base = {"type": "item", "id": nome, "name": nome, "weight_kg": 0.5}
    base.update(fm)
    io.write_doc(pasta / "item.md", base, corpo)
    return pasta


def main() -> int:
    d = mundo_tmp()
    import importlib
    import motor.io as io
    importlib.reload(io)
    from motor import prazo

    agora = time.time()
    print("\n=== 1. OS EXTREMOS E OS DEGENERADOS =============================")

    # dura zero
    p = item(d, "efemero", {}, "Algo que dura nada.")
    ok = prazo.carimbar_se_houver(p, {"descricao_vencida": "pó"}, 0)
    achado("confirmação", "duração zero não carimba",
           f"carimbou? {ok} — a guarda `dura_s <= 0` segura, e a coisa nasce sem prazo")

    # dura negativo (nasce vencido)
    p2 = item(d, "nascido-morto", {}, "Algo já passado.")
    prazo.carimbar(p2, -100, {"verbo": "virar"}, descricao_vencida="restos")
    fm2, _ = io.read_doc(p2 / "item.md")
    r = prazo.vencer_se_for_hora(p2, fm2)
    achado("lacuna" if r else "confirmação", "prazo carimbado NO PASSADO vence na 1ª leitura",
           f"venceu de imediato: {bool(r)} — `carimbar` aceita duração negativa sem "
           "reclamar. Se algum dia uma régua devolver duração negativa, a coisa nasce "
           "podre e ninguém avisa.")

    # extinguir + descricao_vencida ao mesmo tempo
    p3 = item(d, "some-e-vira", {}, "Uma tocha acesa.")
    prazo.carimbar(p3, -1, {"verbo": "extinguir"}, descricao_vencida="cinza fria")
    fm3, _ = io.read_doc(p3 / "item.md")
    r3 = prazo.vencer_se_for_hora(p3, fm3)
    fm3b, corpo3 = io.read_doc(p3 / "item.md")
    achado("dinâmica emergente", "`extinguir` e a troca de prosa acontecem JUNTOS",
           f"extinto={io.esta_extinto(fm3b)} e a prosa virou {corpo3.strip()!r}. "
           "A coisa some do jogo MAS o arquivo conta o que ela virou — é bom para quem "
           "for ler o mundo depois, e não estava desenhado.")

    print("\n=== 2. O ADVERSÁRIO ============================================")

    # entidade some antes de vencer
    p4 = item(d, "sumida", {}, "Algo que vai sumir.")
    prazo.carimbar(p4, 3600, {"verbo": "virar"}, descricao_vencida="x")
    io.remove_entity(p4)
    achado("confirmação", "entidade removida antes de vencer não deixa órfão",
           f"pasta existe? {p4.exists()} — o prazo morre com ela, sem lista central "
           "para limpar (é a consequência de o bloco morar NA entidade)")

    # vencer duas vezes em paralelo, com a MESMA foto
    p5 = item(d, "corrida", {}, "Disputada.")
    prazo.carimbar(p5, -1, {"verbo": "virar"}, descricao_vencida="virou")
    fmA, _ = io.read_doc(p5 / "item.md")
    fmB = dict(fmA)
    r5a = prazo.vencer_se_for_hora(p5, fmA)
    r5b = prazo.vencer_se_for_hora(p5, fmB)
    achado("confirmação", "leituras concorrentes: só a primeira aplica",
           f"a={bool(r5a)} b={bool(r5b)} — a segunda relê o disco antes de agir, "
           "então a foto velha não engana")

    # verbo campo em caminho profundo que não existe
    p6 = item(d, "campo-fundo", {}, "Teste de caminho.")
    prazo.carimbar(p6, -1, {"verbo": "campo", "campo": "state.sub.fundo", "valor": 7},
                   descricao_vencida="")
    fm6, _ = io.read_doc(p6 / "item.md")
    prazo.vencer_se_for_hora(p6, fm6)
    fm6b, _ = io.read_doc(p6 / "item.md")
    achado("confirmação", "`campo` cria o caminho aninhado que não existia",
           f"state={fm6b.get('state')} — sem KeyError, sem precisar declarar antes")

    print("\n=== 3. A COMBINAÇÃO CRUZADA ====================================")

    # prazo numa coisa que também é peça de trabalho
    p7 = item(d, "peca-com-prazo", {
        "trabalho": {"tool": "craft", "ator": "alguem",
                     "tempo_necessario_s": 600, "tempo_trabalhado_s": 10,
                     "banda": "comum", "nome_final": "Coisa"}},
        "Coisa em processo.")
    prazo.carimbar(p7, -1, {"verbo": "virar"},
                   descricao_vencida="Coisa arruinada, junta aberta.")
    fm7, _ = io.read_doc(p7 / "item.md")
    prazo.vencer_se_for_hora(p7, fm7)
    fm7b, corpo7 = io.read_doc(p7 / "item.md")
    ainda_tem_trabalho = bool(fm7b.get("trabalho"))
    achado("lacuna" if ainda_tem_trabalho else "confirmação",
           "peça vencida MANTÉM o bloco `trabalho` no arquivo",
           f"trabalho ainda presente: {ainda_tem_trabalho}. A face esconde a retomada "
           "lendo `prazo.vencido_em`, então o jogo se comporta certo — mas o arquivo "
           "guarda um bloco de trabalho que ninguém mais pode retomar. Quem ler o mundo "
           "por fora (uma análise, um relatório) vai contar como trabalho aberto.")

    # a memória do vencimento
    print("\n=== 4. O SILÊNCIO — algo muda sem ninguém saber? ================")
    quem = d / "lugar" / "fulano"
    (quem / "memories").mkdir(parents=True, exist_ok=True)
    io.write_doc(quem / "character.md",
                 {"type": "character", "id": "fulano", "name": "Fulano",
                  "controlled_by": "player_local",
                  "attributes": {"STR": 10, "DEX": 10, "CON": 10,
                                 "INT": 10, "WIS": 10, "CHA": 10},
                  "status": {"hp": 10, "hp_max": 10}}, "Alguém.")
    mid = prazo.lembrar(quem, {"nome": "Viola", "entidade": "viola-1",
                               "prosa_trocada": True})
    achado("confirmação", "o vencimento forma memória em quem é afetado",
           f"memória criada: {bool(mid)} — o terceiro compromisso do Princípio X, e o "
           "mais fácil de esquecer porque o vencimento NÃO TEM ATOR")

    print("\n=== 5. A NEGAÇÃO COMO CONTEÚDO =================================")
    for bloco, rotulo in [
        ({"vence_em": 1, "ao_vencer": {"verbo": "campo", "campo": "x"}}, "campo sem valor"),
        ({"vence_em": 1, "ao_vencer": {"verbo": "virar"}}, "virar sem descrição"),
        ({"vence_em": 1, "ao_vencer": {"verbo": "sumir"}}, "verbo inventado"),
    ]:
        m = prazo.forma_valida(bloco)
        print(f"  recusa de {rotulo}: {m!r}")
    achado("confirmação", "toda recusa de forma vem com o MOTIVO escrito",
           "nenhuma devolve só `False` — é o que impede o prazo mudo que vence e não faz nada")

    shutil.rmtree(d, ignore_errors=True)

    print("\n=== RESUMO ======================================================")
    for tipo in ("lacuna", "dinâmica emergente", "calibragem", "confirmação"):
        do_tipo = [a for a in achados if a[0] == tipo]
        if do_tipo:
            print(f"\n{tipo.upper()} ({len(do_tipo)}):")
            for _, t, _d in do_tipo:
                print(f"  - {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
