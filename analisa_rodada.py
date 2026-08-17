"""Relatório de uma RODADA de um personagem — os números que a análise usa.

Nasceu de fazer isto à mão cinco vezes numa sessão (Nerissa, Torvin, Tobias,
Petrila, Draven) e errar duas. Os erros estão codificados aqui como guardas:

  · O DEVLOG É INTERCALADO entre personagens que jogam ao mesmo tempo. A janela de
    um turno vai até a próxima proposta DE QUALQUER UM, não a próxima deste
    personagem. Recortar errado inflou uma taxa de recusa de 31% para 46%.
  · `turno_id` FALTA em parte dos registros. Agrupar "mesmo turno" sem excluir os
    nulos joga tudo num balde e inventa repetição onde não há — foi assim que eu
    "descobri" que alguém dormiu 3x num turno, quando as duas extras haviam sido
    corretamente recusadas.
  · O LIMIAR DE RAJADA sai da própria amostra (a distribuição é bimodal: um turno
    real leva dezenas de segundos, um despejo leva 2), nunca de um número fixo.

Uso:
  python3 server/analisa_rodada.py --personagem <id> --desde 2026-08-14
                                   [--ate 2026-08-15] [--versao 2.11.0]
                                   [--md relatorio.md]

Fontes: `server/devlog.log` (o que o MUNDO viu), `registro/<id>.jsonl` (o que A
MENTE pensou — racional, custo, origem) e `world/` (estado de AGORA, não de então).
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "loreforge-server"))

F = "%Y-%m-%d %H:%M:%S"
_BLOCO = re.compile(
    r"────────\s+(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)\s+·\s+(?:(v[\d.]+)\s+·\s+)?"
    r"(.+?)\s+────────\n")

# As FAMÍLIAS de recusa, por frase in-world. Classificar é o que separa "a Mente
# errou o alvo" de "o mundo disse não" — e o segundo é CONTEÚDO, não defeito.
FAMILIAS = [
    ("alvo fantasma (id inventado ou ausente)",
     ["não é lugar a que ele saiba", "não parte daqui", "não é alguém a quem ele possa",
      "não é algo que ele perceba", "não é alguém a que", "não reconhecido",
      "não é um personagem presente", "não é outro personagem presente",
      "não está ao alcance do olhar"]),
    ("schema / parâmetro",
     ["precisa ser um valor só", "informe '", "'None'", "informe SOBRE",
      "não guarda nada dentro"]),
    ("sequência / posse / corpo",
     ["não está com quem age", "mãos ocupadas", "já está na mão", "não está ao alcance",
      "isso não se veste", "está com outra pessoa", "já está dormindo",
      "não está dormindo"]),
    ("RECUSA IN-WORLD (é conteúdo, não defeito)",
     ["não abriu o que sabe", "não quis dizer", "nada sabe", "não se desfez do que é seu",
      "os rabiscos não se deixaram", "ouviu, pensou", "já sabe todos os caminhos",
      "não está à venda"]),
]


def _instante_local(bruto) -> dt.datetime | None:
    """O instante do REGISTRO em hora local.

    O registro grava `new Date().toISOString()` — UTC, com sufixo Z. O devlog grava
    hora LOCAL. Somar os dois sem converter desloca tudo pelo fuso: aqui eram 3
    horas, o que fazia o filtro de janela pegar o turno errado e imprimir racional
    com horário que não existe no devlog ao lado. Silencioso e convincente.
    """
    if not isinstance(bruto, str) or not bruto:
        return None
    try:
        q = dt.datetime.fromisoformat(bruto.replace("Z", "+00:00"))
    except ValueError:
        return None
    if q.tzinfo is None:            # sem fuso declarado: trata como já-local
        return q.replace(microsecond=0)
    return q.astimezone().replace(tzinfo=None, microsecond=0)


def familia(msg: str) -> str:
    for nome, chaves in FAMILIAS:
        if any(k in msg for k in chaves):
            return nome
    return "outro"


def le_devlog(caminho: Path):
    txt = caminho.read_text(encoding="utf-8", errors="ignore")
    marks = list(_BLOCO.finditer(txt))
    for i, m in enumerate(marks):
        fim = marks[i + 1].start() if i + 1 < len(marks) else len(txt)
        yield {"ts": m.group(1), "v": m.group(2), "t": m.group(3).strip(),
               "c": txt[m.end():fim].strip()}


# SÃO DOIS MODELOS, e confundi-los é fácil: quase caí nisso ao escrever esta seção.
#
#   · A MENTE decide o que tentar. Quando ela não devolve tool call, o conector cai
#     no caminho de prosa e a proposta chega ao mundo por `/api/act` — que o devlog
#     registra como `RECEBIDO DO CLIENT`. É o único sinal DURÁVEL da queda dela, e
#     ele traz `character_id`, então dá para atribuir.
#   · O ÁRBITRO julga. Os marcadores abaixo saem todos de `arbiter.py` e falam do
#     modelo DELE degradando — nada a ver com o tool-calling da Mente.
#
# LACUNA CONHECIDA: o aviso próprio da Mente ("SEM TOOL CALLS — caindo no caminho de
# prosa") vai para o STDERR do conector, que não é log durável. Então a taxa de queda
# só se mede aqui por tabela — pela proporção entre proposta e `/api/act`.
DESVIOS_DO_ARBITRO = {
    "MODELO RESPONDEU TEXTO (sem tools) — parse leniente": "respondeu TEXTO, sem tools",
    "TOOLS DESCRITAS EM PROSA — executando pela guarda": "descreveu tools em PROSA",
    "PROSA IGNORADA — parâmetros obrigatórios ausentes": "prosa sem params obrigatórios",
    "PROSA IGNORADA — tool fora do manifest": "prosa citando tool fora do manifest",
    "JUÍZO FALHOU — a capacidade cai no default": "juízo indisponível",
}


def turnos_do_personagem(blocos, quem, desde, ate, versao):
    """Recorta os turnos DESTE personagem, com a janela correta (até a próxima
    proposta de QUALQUER UM) — ver o aviso no topo do arquivo."""
    B = list(blocos)
    abre = [i for i, b in enumerate(B)
            if b["t"] in ("PROPOSTA DA MENTE", "RECEBIDO DO CLIENT")]
    saida = []
    for k, i in enumerate(abre):
        b = B[i]
        if b["t"] != "PROPOSTA DA MENTE":
            continue
        ts = dt.datetime.strptime(b["ts"], F)
        if ts < desde or (ate and ts > ate):
            continue
        if versao and b["v"] != f"v{versao}".replace("vv", "v"):
            continue
        try:
            p = json.loads(b["c"])
        except json.JSONDecodeError:
            continue
        if p.get("character_id") != quem:
            continue
        janela = B[i + 1:(abre[k + 1] if k + 1 < len(abre) else len(B))]
        rec = pane = None
        for j in janela:
            if j["t"] == "PROPOSTA RECUSADA (sem LLM)" and rec is None:
                m = re.search(r'"erro"\s*:\s*"([^"]{0,160})', j["c"])
                rec = m.group(1) if m else "?"
            if j["t"].startswith("JUÍZO FALHOU"):
                pane = True
        # `aconteceu` NÃO mora no bloco OUTCOME do devlog (lá o campo é `applied`);
        # ele é montado depois, por `app.inworld_effects`, e só o REGISTRO o guarda.
        # Ler do OUTCOME dava 100% de "propostas mudas" — o mesmo erro de leitura já
        # cometido à mão nesta análise, agora com o campo certo.
        aconteceu = None
        saida.append({"ts": ts, "v": b["v"], "cap": p.get("capacidade"),
                      "alvos": p.get("alvos") or {},
                      "prosa": (p.get("prosa") or {}).get("acao") or "",
                      "rec": rec, "pane": bool(pane), "aconteceu": aconteceu})
    return saida


def cadeias(T, limiar):
    """Agrupa as propostas que nasceram da MESMA resposta do modelo.

    Por `turno_id` quando ele existe — isso é VERDADE, não estimativa: um turno é
    uma resposta, e o id vem do conector. O limiar de tempo é só o plano B para
    registro sem id, e ele erra nos dois sentidos: um limiar de 3s perdia as 14
    acusações da Petrila (7s entre si, porque cada `accuse` paga um julgamento) e
    um limiar largo funde turnos vizinhos legítimos."""
    T = sorted(T, key=lambda x: x["ts"])
    com = [t for t in T if t.get("turno_id")]
    out = []
    if com:
        por = collections.OrderedDict()
        for t in com:
            por.setdefault(t["turno_id"], []).append(t)
        out.extend(por.values())
    resto = [t for t in T if not t.get("turno_id")]
    i = 0
    while i < len(resto):
        j = i
        while j + 1 < len(resto) and \
                (resto[j + 1]["ts"] - resto[j]["ts"]).total_seconds() <= limiar:
            j += 1
        out.append(resto[i:j + 1])
        i = j + 1
    return sorted(out, key=lambda c: c[0]["ts"])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--personagem", required=True)
    ap.add_argument("--desde", required=True, help="AAAA-MM-DD ou AAAA-MM-DD HH:MM:SS")
    ap.add_argument("--ate", default=None)
    ap.add_argument("--versao", default=None, help="ex.: 2.11.0 (sem o 'v')")
    ap.add_argument("--md", default=None, help="grava o relatório neste arquivo")
    a = ap.parse_args()

    def data(s, fim=False):
        if not s:
            return None
        return dt.datetime.strptime(
            s if len(s) > 10 else s + (" 23:59:59" if fim else " 00:00:00"), F)

    quem, desde, ate = a.personagem, data(a.desde), data(a.ate, fim=True)
    L: list[str] = []
    # Os MESMOS números do relatório, em forma de máquina. O `.md` é para ler; o
    # `.json` é para cruzar rodadas, plotar, ou outra pessoa processar sem reparsear
    # prosa. Um só cálculo alimenta os dois — duas contas divergem com o tempo.
    D: dict = {"personagem": quem, "filtro": {"desde": a.desde, "ate": a.ate,
                                              "versao": a.versao},
               "gerado_em": dt.datetime.now().strftime(F)}

    def w(linha=""):
        L.append(linha)

    devlog = RAIZ / "loreforge-server" / "devlog.log"
    reg = RAIZ / "registro" / f"{quem}.jsonl"
    blocos = list(le_devlog(devlog))
    T = turnos_do_personagem(blocos, quem, desde, ate, a.versao)
    # o caminho tomado, na janela (todos os personagens — o devlog não separa)
    caminhos = collections.Counter()
    pela_prosa = 0
    for b in blocos:
        rot = DESVIOS_DO_ARBITRO.get(b["t"])
        ehProsa = b["t"] == "RECEBIDO DO CLIENT" and f'"{quem}"' in b["c"]
        if not rot and not ehProsa:
            continue
        try:
            bts = dt.datetime.strptime(b["ts"], F)
        except ValueError:
            continue
        if bts < desde or (ate and bts > ate):
            continue
        if a.versao and b["v"] != f"v{a.versao}":
            continue
        if ehProsa:
            pela_prosa += 1
        else:
            caminhos[rot] += 1

    # O REGISTRO é a fonte de `aconteceu` e de `turno_id` — o devlog não os tem no
    # caminho do MCP. Casa por (instante, capacidade): é o par que identifica a
    # proposta nos dois lados.
    # A junção é TOLERANTE no tempo: o devlog carimba o INÍCIO da requisição e o
    # registro o FIM, e entre os dois cabe o julgamento do Árbitro (segundos, às
    # vezes minutos). Casar por igualdade de instante casava 10 de 72. A chave é
    # (capacidade, alvos) e vence o registro mais próximo no tempo, dentro da
    # tolerância — e cada registro só casa UMA vez, para uma repetição não roubar
    # o desfecho da outra.
    TOL = 600
    por_chave: dict = collections.defaultdict(list)
    if reg.exists():
        for linha in reg.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            if r.get("lado") != "mundo":
                continue
            rts = _instante_local(r.get("instante"))
            if rts is None:
                continue
            k = (r.get("capacidade"),
                 json.dumps(r.get("alvos") or {}, sort_keys=True, ensure_ascii=False))
            por_chave[k].append((rts, r))
    usados: set = set()
    casadas = 0
    for t_ in T:
        k = (t_["cap"], json.dumps(t_["alvos"], sort_keys=True, ensure_ascii=False))
        melhor = None
        for idx, (rts, r) in enumerate(por_chave.get(k, [])):
            if (k, idx) in usados:
                continue
            d = abs((rts - t_["ts"]).total_seconds())
            if d <= TOL and (melhor is None or d < melhor[0]):
                melhor = (d, idx, r)
        if melhor is not None:
            usados.add((k, melhor[1]))
            casadas += 1
            t_["aconteceu"] = melhor[2].get("aconteceu") or []
            t_["turno_id"] = melhor[2].get("turno_id")
        else:
            t_["aconteceu"] = None      # DESCONHECIDO, nunca "vazio"
            t_["turno_id"] = None

    w(f"# Rodada de `{quem}`")
    w()
    w(f"- **janela**: {a.desde} → {a.ate or 'agora'}"
      + (f" · **versão** v{a.versao}" if a.versao else " · todas as versões"))
    w(f"- **fontes**: `{devlog.name}` (o que o mundo viu)"
      + (f", `registro/{quem}.jsonl` (o que A Mente pensou)" if reg.exists()
         else f", registro AUSENTE — sem racional nem custo"))
    if not T:
        w()
        w("Nenhuma proposta nesta janela.")
        print("\n".join(L))
        return 0

    # ---- macro ------------------------------------------------------------- #
    rec = [t for t in T if t["rec"]]
    dur = (T[-1]["ts"] - T[0]["ts"])
    w(f"- **período observado**: {T[0]['ts']} → {T[-1]['ts']} ({dur})")
    w(f"- **casadas com o registro**: {casadas}/{len(T)}"
      + ("" if casadas == len(T) else
         " — o resto fica com desfecho DESCONHECIDO, não com desfecho vazio"))
    vs = collections.Counter(t["v"] for t in T)
    if len(vs) > 1:
        w(f"- ⚠ **mais de uma versão na janela**: {dict(vs)} — números somados"
          " misturam código diferente")
    w()
    w("## Macro")
    w()
    w("| medida | valor |")
    w("|---|---|")
    D["macro"] = {
        "propostas": len(T), "aceitas": len(T) - len(rec), "recusadas": len(rec),
        "inicio": T[0]["ts"].strftime(F), "fim": T[-1]["ts"].strftime(F),
        "duracao_s": int(dur.total_seconds()),
        "casadas_com_registro": casadas,
        "versoes": {k: v for k, v in vs.items()},
        "capacidades_distintas": len({t["cap"] for t in T}),
        "turnos_com_pane": sum(1 for t in T if t["pane"]),
    }
    w(f"| propostas | {len(T)} |")
    w(f"| aceitas | {len(T) - len(rec)} ({(len(T)-len(rec))/len(T):.0%}) |")
    w(f"| recusadas antes do Árbitro | {len(rec)} ({len(rec)/len(T):.0%}) |")
    sabidas = [t for t in T if not t["rec"] and t["aconteceu"] is not None]
    mudas = [t for t in sabidas if not t["aconteceu"]]
    D["macro"]["aceitas_com_registro"] = len(sabidas)
    D["macro"]["aceitas_sem_frase_de_mundo"] = len(mudas)
    if sabidas:
        w(f"| aceitas sem `aconteceu` | {len(mudas)}/{len(sabidas)} "
          f"({len(mudas)/len(sabidas):.0%} das aceitas com registro) |")
    else:
        w("| aceitas SEM frase de mundo | sem registro para saber |")
    w(f"| turnos com pane do juízo | {sum(1 for t in T if t['pane'])} |")
    w(f"| capacidades distintas | {len({t['cap'] for t in T})} |")

    # ---- cadência ---------------------------------------------------------- #
    gaps = [(b["ts"] - x["ts"]).total_seconds() for x, b in zip(T, T[1:])]
    if gaps:
        med = statistics.median(gaps)
        curtos = sum(1 for g in gaps if g <= 3)
        D["cadencia"] = {"mediana_s": med, "p10_s": sorted(gaps)[len(gaps)//10],
                         "intervalos_ate_3s": curtos, "n": len(gaps)}
        w(f"| mediana entre propostas | {med:.0f}s |")
        w(f"| intervalos ≤3s (despejo) | {curtos} ({curtos/len(gaps):.0%}) |")
    w()

    # ---- caminho tomado ---------------------------------------------------- #
    w("## Caminho tomado — e são DOIS modelos")
    w()
    w("### A Mente (decide o que tentar)")
    w()
    w("Sem tool call, o conector cai na prosa e a ação chega ao mundo por `/api/act`."
      " É o que decide se o resto vale: **sem tool call não há sessão, não há"
      " histórico de `tool_result`, e o schema deixa de ser imposto**.")
    w()
    tot_mente = len(T) + pela_prosa
    w("| caminho | n | % |")
    w("|---|---|---|")
    w(f"| tool-calling nativo (proposta) | {len(T)} | {len(T)/max(1,tot_mente):.0%} |")
    w(f"| prosa (`/api/act`) | {pela_prosa} | {pela_prosa/max(1,tot_mente):.0%} |")
    w()
    w("> ⚠ **LACUNA**: o aviso próprio da Mente (\"SEM TOOL CALLS — caindo no caminho"
      " de prosa\") vai para o STDERR do conector, que não é log durável. A tabela"
      " acima é a melhor aproximação que o devlog permite.")
    w()
    w("### O Árbitro (julga)")
    w()
    w("Estes marcadores saem de `arbiter.py` e falam do modelo DELE degradando —"
      " nada a ver com o tool-calling da Mente. Contam a JANELA inteira, porque o"
      " devlog não os atribui a ninguém.")
    w()
    if not caminhos:
        w("Nenhum desvio do Árbitro na janela.")
    else:
        w("| desvio | n |")
        w("|---|---|")
        for rot, n in caminhos.most_common():
            w(f"| {rot} | {n} |")
    w()
    D["caminho"] = {"mente_tools": len(T), "mente_prosa": pela_prosa,
                    "arbitro_desvios": dict(caminhos)}

    # ---- capacidades ------------------------------------------------------- #
    w("## Capacidades")
    w()
    w("> **`sem_aconteceu` NÃO é o mesmo que muda.** Capacidade CONSULTIVA (`examine`,"
      " `ask_wares`, `ask_directions`) não produz `aconteceu` por desenho — ela devolve"
      " MATERIAL (`lido`, `wares`, `falas`), e o registro **não guarda o material**."
      " Então aqui não há como distinguir \"consultou e recebeu\" de \"consultou e"
      " voltou vazio\", que era exatamente o defeito do item 52.3. Para capacidade que"
      " MUTA o mundo, porém, sem `aconteceu` é silêncio de verdade.")
    w()
    w("| capacidade | total | recusadas | sem `aconteceu` |")
    w("|---|---|---|---|")
    D["capacidades"] = {}
    for cap, n in collections.Counter(t["cap"] for t in T).most_common():
        dela = [t for t in T if t["cap"] == cap]
        D["capacidades"][cap] = {
            "total": n, "recusadas": sum(1 for t in dela if t["rec"]),
            "mudas": sum(1 for t in dela if not t["rec"] and t["aconteceu"] == [])}
        r = sum(1 for t in dela if t["rec"])
        m = sum(1 for t in dela if not t["rec"] and t["aconteceu"] == [])
        w(f"| `{cap}` | {n} | {r} | {m} |")
    w()

    # ---- recusas ----------------------------------------------------------- #
    if rec:
        w("## Recusas, por família")
        w()
        fam = collections.Counter(familia(t["rec"]) for t in rec)
        D["recusas"] = {"total": len(rec), "por_familia": dict(fam),
                        "motivos": dict(collections.Counter(t["rec"] for t in rec))}
        w("| família | n | % das recusas |")
        w("|---|---|---|")
        for f_, n in fam.most_common():
            w(f"| {f_} | {n} | {n/len(rec):.0%} |")
        w()
        w("<details><summary>motivos, na íntegra</summary>")
        w()
        for msg, n in collections.Counter(t["rec"] for t in rec).most_common():
            w(f"- `{n}x` {msg}")
        w()
        w("</details>")
        w()

    # ---- racional (registro da Mente) -------------------------------------- #
    racionais: dict = {}
    mente: list = []
    pretendia: dict = {}      # instante → a foto das intenções daquele turno
    if reg.exists():
        for linha in reg.read_text(encoding="utf-8").splitlines():
            if not linha.strip():
                continue
            try:
                r = json.loads(linha)
            except json.JSONDecodeError:
                continue
            ts = _instante_local(r.get("instante"))
            if ts is None:
                continue
            if ts < desde or (ate and ts > ate):
                continue
            if r.get("lado") == "mente":
                mente.append((ts, r))
                pretendia[ts] = (r.get("corpo") or {}).get("intencoes")
                corpo = r.get("corpo") or {}
                # `pensamento` é o nome de hoje; `racional` é como o campo se
                # chamava antes de 2026-08-14 — os `.jsonl` velhos continuam
                # legíveis, senão a mudança de nome apagaria o histórico.
                corpo["_pensamento"] = corpo.get("pensamento") or corpo.get("racional")
                if corpo["_pensamento"]:
                    # por TURNO: é a chave que liga o que A Mente pensou ao que o
                    # mundo recebeu, e ela já veio na junção acima
                    racionais[r.get("turno_id")] = corpo

    # ---- rajada ------------------------------------------------------------ #
    w("## Rajada — a sequência que nasceu de uma resposta só")
    w()
    limiar = 3
    C = cadeias(T, limiar)
    tam = collections.Counter(len(c) for c in C)
    semid = sum(1 for t in T if not t.get("turno_id"))
    w("Cadeia = propostas do MESMO turno, pelo `turno_id` do registro — uma resposta"
      " do modelo, uma cadeia."
      + (f" ({semid} proposta(s) sem id caíram no plano B, ≤{limiar}s entre si;"
         f" a mediana da janela é {statistics.median(gaps):.0f}s.)" if semid else ""))
    w()
    D["rajada"] = {"por_tamanho": {}, "maior": max(tam) if tam else 0, "casos": []}
    w("| tamanho | cadeias | propostas | recusa | alvo em comum |")
    w("|---|---|---|---|---|")
    for n in sorted(tam):
        sel = [c for c in C if len(c) == n]
        props = [t for c in sel for t in c]
        r = sum(1 for t in props if t["rec"])
        coer = sum(1 for c in sel if n > 1 and set.intersection(
            *[set(map(str, t["alvos"].values())) or {"—"} for t in c]))
        D["rajada"]["por_tamanho"][str(n)] = {
            "cadeias": len(sel), "propostas": len(props), "recusadas": r,
            "coerentes": coer if n > 1 else None}
        w(f"| {n} | {len(sel)} | {len(props)} | {r/max(1,len(props)):.0%} |"
          f" {f'{coer}/{len(sel)}' if n > 1 else '—'} |")
    w()
    longas = [c for c in C if len(c) >= 3]
    if longas:
        w("**Recusa por POSIÇÃO na cadeia** (só cadeias de 3+). Se cresce, o plano"
          " está sendo executado contra um mundo que já mudou.")
        w()
        pos = collections.defaultdict(lambda: [0, 0])
        for c in longas:
            for idx, t in enumerate(c):
                pos[min(idx, 5)][0] += 1
                pos[min(idx, 5)][1] += 1 if t["rec"] else 0
        w("| posição | recusadas | % |")
        w("|---|---|---|")
        D["rajada"]["recusa_por_posicao"] = {}
        for p in sorted(pos):
            n, r = pos[p]
            D["rajada"]["recusa_por_posicao"][str(p + 1) if p < 5 else "6+"] = \
                {"n": n, "recusadas": r}
            w(f"| {p+1 if p < 5 else '6+'}ª | {r}/{n} | {r/n:.0%} |")
        w()
        w("**O RACIONAL de cada rajada** — o que A Mente disse que queria, contra o"
          " que ela emitiu. A incoerência entre os dois é o achado.")
        w()
        for c in longas:
            caps = ", ".join(f"`{t['cap']}`" for t in c)
            w(f"- **{c[0]['ts'].strftime('%H:%M:%S')}** · {len(c)} propostas: {caps}")
            tids = {t_["turno_id"] for t_ in c if t_.get("turno_id")}
            racs = [racionais[x]["_pensamento"] for x in tids if x in racionais]
            if len(tids) > 1:
                w(f"  - ⚠ a cadeia atravessa {len(tids)} turnos — não é uma resposta só")
            for r_ in racs:
                w(f"  - racional: *\"{r_}\"*")
            if not racs:
                w("  - racional: (o registro desta janela não o tem)")
            # a INCOERÊNCIA que interessa: um racional de uma frase, N propostas
            if racs and len(c) >= 3:
                w(f"  - **{len(c)} propostas para {len(racs)} racional(is)** —"
                  " se o racional pede uma coisa, o resto é despejo")
            D["rajada"]["casos"].append({
                "instante": c[0]["ts"].strftime(F), "propostas": len(c),
                "capacidades": [t_["cap"] for t_ in c],
                "turnos": len(tids), "racionais": racs})
        w()

    # ---- ações repetidas --------------------------------------------------- #
    w("## Ações repetidas")
    w()
    chave = lambda t: (t["cap"], json.dumps(t["alvos"], sort_keys=True,
                                            ensure_ascii=False))
    reps = collections.Counter(chave(t) for t in T)
    reps = {k: v for k, v in reps.items() if v > 1}
    if not reps:
        w("Nenhuma proposta idêntica repetida.")
    else:
        w("| n | capacidade | alvos | recusas |")
        w("|---|---|---|---|")
        D["repetidas"] = []
        for (cap, alv), n in sorted(reps.items(), key=lambda kv: -kv[1]):
            r = sum(1 for t in T if chave(t) == (cap, alv) and t["rec"])
            D["repetidas"].append({"capacidade": cap, "alvos": json.loads(alv),
                                   "vezes": n, "recusadas": r})
            w(f"| {n}x | `{cap}` | `{alv[:70]}` | {r} |")
        w()
        w("**Racional das repetidas** — se ele é o mesmo a cada vez, o personagem"
          " não está aprendendo com o desfecho.")
        w()
        D["racionais"] = []
        vistos = set()
        for ts, r in mente:
            corpo = r.get("corpo") or {}
            rac = corpo.get("pensamento") or corpo.get("racional")
            if not rac or rac in vistos:
                continue
            vistos.add(rac)
            aut = corpo.get("racional_autonomo")
            D["racionais"].append({"instante": ts.strftime(F),
                                   "origem": corpo.get("origem"),
                                   "pensamento": rac, "racional_autonomo": aut})
            w(f"- `{ts.strftime('%H:%M:%S')}` ({corpo.get('origem') or '—'}) *\"{rac}\"*")
            if aut:
                w(f"    - decidiu agir porque: *\"{aut}\"*")
        w()

    # ---- FASES: a rodada fatiada pelo COMPROMISSO em vigor ------------------ #
    #
    # Pedido do mantenedor, e é a pergunta certa: cada bloco de análise tem de ser
    # lido CONTRA a intenção que existia naquele momento. Sem isso os números viram
    # média de coisas incomparáveis — um trecho sem compromisso nenhum somado a um
    # trecho perseguindo um, como se fossem o mesmo jogo.
    #
    # A fatia vem da FOTO gravada no registro (`corpo.intencoes`), não do estado de
    # hoje: intenção criada e abandonada não deixa rastro no `world/`, e era
    # exatamente o caso que a análise não conseguia ver.
    if pretendia:
        w("## Fases — a rodada contra o COMPROMISSO em vigor")
        w()
        w("Cada fase é um trecho com o MESMO conjunto de intenções ativas. Os números"
          " gerais no topo somam fases incomparáveis; é aqui que se vê se ter"
          " compromisso muda o comportamento.")
        w()
        w("A fatia vem da FOTO gravada no registro a cada turno, não do estado de hoje:"
          " intenção criada e ABANDONADA não deixa rastro no `world/`, e era justamente"
          " o caso que a análise não conseguia ver.")
        w()
        marcos = sorted(pretendia.items())

        def _assinatura(ints):
            # AUSENTE ≠ VAZIO, e confundir os dois mente com cara de dado: o campo
            # `intencoes` nasceu em 2026-08-14, então registro anterior não o tem — e
            # marcá-lo "sem compromisso" afirmaria o contrário do que aconteceu (o
            # Doncel TINHA uma: "trabalhar na taverneira por mais alguns dias").
            if ints is None:
                return "(não registrado — turno anterior a 2026-08-14)"
            if not ints:
                return "(sem compromisso)"
            return " · ".join((i.get("content") or "?") for i in ints)

        fases: list = []
        for ts, ints in marcos:
            assin = _assinatura(ints)
            if not fases or fases[-1]["assinatura"] != assin:
                fases.append({"assinatura": assin, "de": ts, "ate": ts, "turnos": 0})
            fases[-1]["ate"] = ts
            fases[-1]["turnos"] += 1
        # as propostas de cada fase: as que caem na janela dela
        for k, f in enumerate(fases):
            fim = fases[k + 1]["de"] if k + 1 < len(fases) else None
            dentro = [x for x in T if x["ts"] >= f["de"] and (fim is None or x["ts"] < fim)]
            f["propostas"] = dentro
        D["fases"] = []
        for k, f in enumerate(fases, 1):
            dentro = f["propostas"]
            rr = [x for x in dentro if x["rec"]]
            caps = collections.Counter(x["cap"] for x in dentro)
            w(f"### Fase {k} — {f['assinatura']}")
            w()
            w(f"- de `{f['de'].strftime('%H:%M:%S')}` a `{f['ate'].strftime('%H:%M:%S')}`"
              f" · {f['turnos']} turno(s) da Mente · {len(dentro)} proposta(s)")
            if dentro:
                w(f"- recusadas: {len(rr)} ({len(rr)/len(dentro):.0%})")
                w(f"- o que fez: " + ", ".join(f"`{c}`×{n}" for c, n in caps.most_common()))
                fam = collections.Counter(familia(x["rec"]) for x in rr)
                if fam:
                    w(f"- recusas por família: "
                      + ", ".join(f"{f_} ({n})" for f_, n in fam.most_common()))
            else:
                w("- nenhuma proposta chegou ao mundo nesta fase")
            w()
            D["fases"].append({
                "assinatura": f["assinatura"],
                "de": f["de"].strftime(F), "ate": f["ate"].strftime(F),
                "turnos": f["turnos"], "propostas": len(dentro),
                "recusadas": len(rr),
                "capacidades": dict(caps)})

    # ---- custo ------------------------------------------------------------- #
    if mente:
        w("## Custo e saúde do turno (lado da Mente)")
        w()
        ents = [ (r.get("custo") or {}).get("entrada") or 0 for _ts, r in mente]
        chs = [max(1, (r.get("custo") or {}).get("chamadas") or 1) for _ts, r in mente]
        porch = [e // c for e, c in zip(ents, chs)]
        durs = [((r.get("custo") or {}).get("duracao_ms") or 0)/1000 for _ts, r in mente]
        tout = [r for _ts, r in mente
                if any("timeout" in str(f).lower() or "abort" in str(f).lower()
                       for f in ((r.get("corpo") or {}).get("falhas") or []))]
        semesc = [r for _ts, r in mente if not ((r.get("corpo") or {}).get("escolhas") or [])]
        w("| medida | valor |")
        w("|---|---|")
        w(f"| turnos da Mente | {len(mente)} |")
        # `custo.entrada` é a SOMA das chamadas do turno, não o tamanho de um prompt.
        # Ler a soma como tamanho é o erro que fez este relatório avisar "o contexto
        # CRESCEU" quando ele havia até ENCOLHIDO: no Doncel, 10.347 → 35.389 de soma
        # era 1 → 4 chamadas de ~8.800 cada. Quem responde "o contexto cresceu?" é o
        # POR CHAMADA; quem responde "a vez ficou caro?" é a soma.
        w(f"| tokens POR CHAMADA | {porch[0]:,} → {porch[-1]:,} (máx {max(porch):,}) |")
        w(f"| tokens somados no turno | {ents[0]:,} → {ents[-1]:,} (máx {max(ents):,}) |")
        w(f"| chamadas ao modelo por turno | {chs[0]} → {chs[-1]} (máx {max(chs)}) |")
        w(f"| duração do turno | {durs[0]:.0f}s → {durs[-1]:.0f}s (máx {max(durs):.0f}s) |")
        w(f"| com TIMEOUT | {len(tout)} ({len(tout)/len(mente):.0%}) |")
        w(f"| sem escolha nenhuma | {len(semesc)} ({len(semesc)/len(mente):.0%}) |")
        orig = collections.Counter((r.get("corpo") or {}).get("origem") for _ts, r in mente)
        w(f"| origem | {dict(orig)} |")
        D["custo"] = {
            "turnos_da_mente": len(mente),
            "tokens_entrada_inicio": ents[0], "tokens_entrada_fim": ents[-1],
            "tokens_entrada_max": max(ents),
            "duracao_s_inicio": round(durs[0]), "duracao_s_fim": round(durs[-1]),
            "duracao_s_max": round(max(durs)),
            "tokens_por_chamada_inicio": porch[0], "tokens_por_chamada_fim": porch[-1],
            "tokens_por_chamada_max": max(porch),
            "chamadas_por_turno_max": max(chs),
            "com_timeout": len(tout), "sem_escolha": len(semesc),
            "origem": dict(orig)}
        w()
        if porch and porch[-1] > 1.3 * porch[0]:
            w("⚠ O CONTEXTO cresceu (por chamada). Costuma ser memória duplicada —"
              " cruze com a seção de memória abaixo.")
            w()
        if chs and max(chs) > 2:
            # o turno normal são DUAS chamadas (escolher + narrar). Cada volta a mais
            # é uma consulta ou uma recusa que fez A Mente repensar — e ela paga o
            # contexto inteiro outra vez enquanto não houver cache de prefixo.
            caras = [c for c in chs if c > 2]
            w(f"⚠ {len(caras)} turno(s) com mais de 2 chamadas ao modelo (até"
              f" {max(chs)}). Cada volta extra é uma consulta ou uma recusa que fez"
              " A Mente repensar, e custa o contexto inteiro de novo.")
            w()

    # ---- intenções --------------------------------------------------------- #
    w("## Intenções")
    w()
    w("> ⚠ **LIMITAÇÃO**: as intenções EM VIGOR a cada turno não são gravadas em"
      " lugar nenhum. O que se pode reconstruir é (a) o que foi criado/mexido na"
      " janela, pelas chamadas de `set_intention`, e (b) o estado de AGORA — que"
      " não é o de então.")
    w()
    si = [t for t in T if t["cap"] == "set_intention"]
    D["intencoes"] = {"mexidas_na_janela": [
        {"instante": t["ts"].strftime(F), "aceita": not t["rec"],
         "recusa": t["rec"], "alvos": t["alvos"]} for t in si]}
    if si:
        w("**Mexidas na janela:**")
        w()
        for t in si:
            alvo = t["alvos"]
            w(f"- `{t['ts'].strftime('%H:%M:%S')}` "
              + (f"✗ {t['rec']}" if t["rec"] else "✓")
              + f" · `{json.dumps(alvo, ensure_ascii=False)[:120]}`")
        w()
    else:
        w("Nenhuma chamada de `set_intention` na janela.")
        w()
    try:
        import motor
        pasta = motor.find_character_folder(quem)
        agora = motor.intencoes.get_active_intentions(pasta)
        w(f"**Ativas AGORA** ({len(agora)}):")
        w()
        D["intencoes"]["ativas_agora"] = [
            {"status": i.get("status"), "content": i.get("content")} for i in agora]
        for i in agora:
            w(f"- `{i.get('status')}` — {i.get('content')}")
        if not agora:
            w("- (nenhuma)")
        w()
    except Exception as e:  # noqa: BLE001
        w(f"(não foi possível ler o estado atual: {e})")
        w()

    # ---- memória ----------------------------------------------------------- #
    try:
        import motor
        pasta = motor.find_character_folder(quem)
        mems = list((pasta / "memories").glob("*.md"))
        ev = collections.Counter()
        corpos = collections.Counter()
        vivas = 0
        for p in mems:
            fm, corpo = motor.read_doc(p)
            ev[fm.get("evento") or "—"] += 1
            corpos[corpo.strip()] += 1
            if motor._is_alive(fm):
                vivas += 1
        dupl = sum(v - 1 for v in corpos.values() if v > 1)
        w("## Memória (estado de agora)")
        w()
        w("| medida | valor |")
        w("|---|---|")
        D["memoria"] = {"arquivos": len(mems), "vivas": vivas,
                        "excedente_identico": dupl, "por_evento": dict(ev)}
        w(f"| arquivos | {len(mems)} |")
        w(f"| VIVAS (é o que entra no contexto) | {vivas} |")
        w(f"| excedente de corpo idêntico | {dupl} |")
        w()
        w("| evento | n |")
        w("|---|---|")
        for k, n in ev.most_common(12):
            w(f"| `{k}` | {n} |")
        w()
        if dupl:
            w(f"⚠ {dupl} memória(s) repetem corpo idêntico — inflam o contexto e"
              " enviesam a bússola do tick autônomo. Ver `sanea_mundo.py`.")
            w()
    except Exception as e:  # noqa: BLE001
        w(f"(memória não lida: {e})")
        w()

    # ---- deslocamento e estado -------------------------------------------- #
    mov = [t for t in T if t["cap"] in ("enter_route", "travel_to")]
    D["deslocamento"] = [{"instante": t["ts"].strftime(F), "cap": t["cap"],
                          "alvos": t["alvos"], "recusa": t["rec"]} for t in mov]
    if mov:
        w("## Deslocamento")
        w()
        for t in mov:
            w(f"- `{t['ts'].strftime('%H:%M:%S')}` `{t['cap']}` "
              f"{json.dumps(t['alvos'], ensure_ascii=False)}"
              + (f" ✗ {t['rec']}" if t["rec"] else ""))
        w()
    try:
        import motor
        import face
        ctx = motor.get_context(quem)
        # `capacidades` NÃO vem do Motor: quem a monta é `face.build`, e isso só
        # acontece no caminho HTTP (`app.py`). Lendo o contexto cru, o relatório
        # dizia "face: 0 capacidades" para TODO personagem vivo — número errado e
        # convincente, do tipo que faz diagnosticar um problema que não existe.
        ctx["capacidades"] = face.build(ctx)
        st = (ctx.get("self") or {}).get("status") or {}
        w("## Estado agora")
        w()
        w(f"- local: **{(ctx.get('location') or {}).get('name')}** · presentes: "
          + (", ".join(c["name"] for c in ctx.get("characters_present") or []
                       if c.get("id") != quem) or "ninguém"))
        w(f"- fome `{st.get('hunger')}` · fadiga `{st.get('fatigue')}` ·"
          f" humor `{st.get('mood')}` · hp {st.get('hp')}/{st.get('hp_max')}")
        D["estado_agora"] = {
            "local": (ctx.get("location") or {}).get("name"),
            "presentes": [c["name"] for c in ctx.get("characters_present") or []
                          if c.get("id") != quem],
            "hunger": st.get("hunger"), "fatigue": st.get("fatigue"),
            "mood": st.get("mood"), "hp": st.get("hp"), "hp_max": st.get("hp_max"),
            "capacidades_na_face": len(ctx.get("capacidades") or [])}
        w(f"- face: {len(ctx.get('capacidades') or [])} capacidades")
        w()
    except Exception:  # noqa: BLE001
        pass

    # ---- sinais ------------------------------------------------------------ #
    w("## Sinais de alerta (automáticos)")
    w()
    sinais = []
    if len(rec) / len(T) > 0.30:
        sinais.append(f"recusa alta: {len(rec)/len(T):.0%} das propostas")
    if sabidas and len(mudas) / len(sabidas) > 0.15:
        sinais.append(f"{len(mudas)/len(sabidas):.0%} das propostas aceitas sem"
                      " `aconteceu` — confira quais são consultivas antes de concluir"
                      " (o material não é registrado)")
    if any(len(c) >= 3 for c in C):
        pior = max(len(c) for c in C)
        sinais.append(f"rajada: cadeia de até {pior} propostas numa resposta só")
    if reps:
        sinais.append(f"{len(reps)} ação(ões) repetida(s) com alvos idênticos")
    if pela_prosa:
        sinais.append(f"{pela_prosa} turno(s) pelo caminho de PROSA — ali o schema não"
                      " é imposto e o raciocínio não persiste")
    if sum(1 for t in T if t["pane"]):
        sinais.append(f"{sum(1 for t in T if t['pane'])} turno(s) com pane do juízo —"
                      " o desfecho caiu no padrão, e não é o personagem falhando")
    D["sinais"] = sinais
    for s in sinais or ["nada fora do esperado nos limiares atuais."]:
        w(f"- {s}")
    w()

    texto = "\n".join(L)
    if a.md:
        Path(a.md).write_text(texto, encoding="utf-8")
        print(f"relatório gravado em {a.md} ({len(texto.splitlines())} linhas)")
        return 0

    # --- a PASTA leva o nome do filtro ------------------------------------- #
    # Assim duas análises do mesmo personagem em janelas diferentes não se
    # sobrescrevem, e o nome da pasta já responde "o que foi filtrado aqui?" sem
    # abrir nada. Rodar de novo o MESMO filtro sobrescreve de propósito: é a
    # mesma pergunta, com dados mais novos.
    def _slug(s: str) -> str:
        return re.sub(r"[^0-9A-Za-z.-]+", "-", str(s)).strip("-") or "x"

    nome = "__".join([
        _slug(quem),
        f"de-{_slug(a.desde)}",
        f"ate-{_slug(a.ate) if a.ate else 'agora'}",
        f"v{_slug(a.versao) if a.versao else 'todas'}",
    ])
    destino = RAIZ / "analises" / nome
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "relatorio.md").write_text(texto, encoding="utf-8")
    (destino / "dados.json").write_text(
        json.dumps(D, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"analises/{nome}/")
    print(f"  relatorio.md  ({len(texto.splitlines())} linhas)")
    print(f"  dados.json    ({len(D)} seções)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
