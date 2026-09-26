"""O Motor / intencoes — PRIMITIVAS (item 31 §3: DDD por domínio).

Funções puras (validação, rolagem, helpers). Sem turno/LLM. Ver executores.py.
"""
from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

from .. import fisica, registro
from ..io import (
    arquivos_em,
    arquivos_no_mundo,
    _fail,
    new_id,
    read_doc,
    write_doc,
)

# Duplicado de `validator.INTENTION_STATES` de propósito — mesmo padrão que
# `memoria._MEMORY_INTENSITIES` já usa: o Motor valida a PRÓPRIA regra de
# negócio (rejeitar graciosamente) antes de `write_doc` validar o SCHEMA
# (que levantaria exceção, não uma rejeição estruturada).
_INTENTION_STATUSES = {"ativa", "concluida", "abandonada"}

# Teto de exposição no contexto (Decisão 5, research.md da spec 026) — mesmo
# espírito de `memoria._MEMORY_CONTEXT_CAP`, mas aqui não há relógio de
# expiração: sem teto, um personagem mal-comportado acumularia intenções
# ativas sem limite. As mais RECENTES ficam; as mais antigas cedem lugar.
_INTENTION_CONTEXT_CAP = 20



# O CRITÉRIO DE FIM (spec 073, FR-001/FR-002) — as famílias que o MUNDO confere.
#
# Nesta fatia só a de LEITURA DE CAMPO. As outras três (posse, lugar, fato lembrado)
# estão desenhadas em `specs/073-intention-cycle/research.md` §R2 e entram nas fatias
# seguintes; a de memória é o risco 3 da spec, e nunca foi testada como FECHAMENTO.
#
# Por que enum fechado e não prosa: o mundo tem de CONFERIR, e prosa não se confere.
# Foi o defeito de "sem pressa e com cuidado" (Pip), uma das quatro intenções podres
# que o `medicoes.md` §2 catalogou.
_CRITERIO_POR_CAMPO = {
    "hunger": "hunger",
    "thirst": "thirst",
    "sleep": "fatigue",     # o campo se chama `fatigue`; a Mente diz "sleep"
    # US4: a carência do MUNDO entra pela mesma porta, e por isso pelo mesmo enum.
    # `peca` = "a peça que eu deixei no meio está terminada". É leitura de campo
    # como as outras três — o `trabalho` do objeto diz quanto falta —, só que num
    # arquivo que não é o do corpo. A família não muda; o arquivo, sim.
    "peca": "peca",
    # A FAMÍLIA POSSE (research.md §R2), e ela é ESTRUTURALMENTE diferente das
    # quatro acima: precisa dizer O QUÊ. "Não estou mais faminto" se confere sozinho;
    # "a garra está comigo" não diz nada sem a garra.
    #
    # POR QUE ELA ENTROU AGORA. Medido (§15.6): sem ela, um compromisso de FAZER um
    # remédio recebia `pronto_quando: hunger` — 3/3 —, porque nenhum critério servia
    # e o modelo escolhe o primeiro que não é absurdo. O compromisso fecharia no
    # instante em que o personagem comesse: um FALSO FECHAMENTO que o SC-002
    # contaria como acerto. O vocabulário pequeno demais não recusa: ele VAZA.
    "posse": "posse",
    # A FAMÍLIA LUGAR (research.md §R2), a quarta e mais barata de todas: é leitura
    # do lugar ONDE ELE ESTÁ, e o mundo já a tem na cena.
    #
    # Ela entra porque "chegar lá" é metade do que a Mente escreve — o FR-007 foi
    # corrigido justamente por isso: um plano de mais de um passo atravessa cenas de
    # propósito ("ir à forja", depois "forjar"). Sem `lugar`, o compromisso de ir a
    # algum lugar não tinha como fechar, e vazava para a família mais próxima —
    # o mesmo defeito que a §15.6 mediu com o remédio caindo em `hunger`.
    #
    # Usa o MESMO `pronto_quando_alvo` da posse: o campo é genérico ("o que o
    # critério aponta"), e um segundo campo para dizer a mesma coisa seria a segunda
    # via que o Princípio I proíbe.
    "lugar": "lugar",
}

# O ALVO DA POSSE É NOME, NUNCA ID — e isto é decisão, não descuido.
#
# O que se promete ter muitas vezes AINDA NÃO EXISTE: o remédio a preparar, a lâmina
# a forjar. Um id de cena não pode nomear o que ninguém criou, e exigir id obrigaria
# a prometer só o que já se vê — que é o oposto de um compromisso.
#
# O casamento é o mesmo de `casar_e_riscar`: todo pedaço de >=3 letras do alvo tem de
# aparecer no nome do que se carrega. "raiz torta" casa "Remédio de Raiz Torta" e não
# casa "Raiz Seca".
# As famílias que não se conferem sozinhas: ter O QUÊ, estar ONDE. Nasce como
# conjunto e não como `== "posse"` porque a segunda chegou uma hora depois da
# primeira, e a terceira chegará — a lista é o lugar de acrescentar.
_PRECISAM_DE_ALVO = ("posse", "lugar")


def _carrega(carregados, alvo: str | None) -> bool:
    if not alvo:
        return False
    pedacos = [p for p in _dobrar(alvo).split() if len(p) >= 3]
    if not pedacos:
        return False
    for nome in (carregados or []):
        tem = _dobrar(str(nome))
        if all(f" {p} " in tem for p in pedacos):
            return True
    return False

# Quando a necessidade DEIXOU de apertar. O rótulo é o do mundo (`hunger_label` e
# irmãos); estes são os que contam como "ainda aperta".
_AINDA_APERTA = ("faminto", "com fome", "sedento", "com sede",
                 "exausto", "muito cansado", "caindo de sono",
                 # US4: o rótulo do trabalho parado. Mesma forma dos do corpo — o
                 # que desce é a LEITURA, nunca "199 de 1800 segundos".
                 "parada no meio")


def criterio_cumprido(needs: dict | None, pronto_quando: str | None,
                      alvo: str | None = None,
                      carregados: list | None = None) -> bool:
    """O `pronto_quando` já é verdade? (spec 073, FR-013a — família de leitura de campo)

    PRIMITIVA, não lógica no handler (Princípio XII): quem confere o critério é o
    mundo, e a conferência é uma leitura de campo — grátis, e por isso roda A CADA
    TURNO. Rodar todo turno não é luxo: é o que faz o compromisso fechar quando é
    cumprido POR ACASO. Se a fome passa por outro motivo, o compromisso encerra —
    cumprir é cumprir, não importa o caminho. Conferindo só no fim do plano, o
    personagem seguiria perseguindo uma fome que já passou.
    """
    campo = _CRITERIO_POR_CAMPO.get(pronto_quando or "")
    if not campo:
        return False
    # A POSSE não é rótulo: é uma pergunta sobre o que se carrega AGORA. O `alvo`
    # vem da própria intenção (`pronto_quando_alvo`), porque é dela que ele é.
    if campo == "posse":
        return _carrega(carregados, alvo)
    # O LUGAR é a mesma pergunta de forma: o alvo casa com onde ele está? O `needs`
    # traz `lugar` como "<id> <nome>" — os dois, porque a Mente pode ter escrito
    # qualquer um dos dois ao firmar.
    if campo == "lugar":
        return _carrega([(needs or {}).get("lugar") or ""], alvo)
    rotulo = str((needs or {}).get(campo) or "").strip().lower()
    if not rotulo:
        return False
    return not any(a in rotulo for a in _AINDA_APERTA)


def create_intention(folder: Path, content: str, status: str = "ativa",
                     memoria_id: str | None = None,
                     pronto_quando: str | None = None,
                     pronto_quando_alvo: str | None = None) -> str:
    """Cria uma intenção nova na pasta de quem a possui. Devolve o id novo.

    `memoria_id` (spec 030, opcional): quando a intenção nasce de um
    compromisso (`prometer`, spec 027), referencia a memória ORIGINAL desse
    compromisso, na mesma pasta — é o que permite à Frente D (dormir com
    pendência) achar qual memória intensificar, sem inferir por conteúdo.
    Mesma identidade-por-id de `intention_id`/`memoria_id` em outras tools
    (`give`/`acusar`), nunca interpretação."""
    now = int(time.time())
    iid = new_id("int")
    fm = {
        "type": "intention", "id": iid, "status": status,
        "created_ts": now, "updated_ts": now,
    }
    if memoria_id:
        fm["memoria_id"] = memoria_id
    if pronto_quando:
        fm["pronto_quando"] = pronto_quando
        # Só a família POSSE tem alvo; guardar a chave nas outras seria convidar a
        # próxima leitura a perguntar "alvo de quê?" numa intenção de fome.
        if pronto_quando_alvo:
            fm["pronto_quando_alvo"] = pronto_quando_alvo
    write_doc(folder / "intentions" / f"{iid}.md", fm, content)
    return iid


def marcar_prazo(folder: Path, intention_id: str, ate_quando: str) -> bool:
    """A intenção ganha HORA (spec 070, FR-016) — em PROSA, como quem promete fala.

    Guarda o texto ("antes do anoitecer", "na próxima vez que nos virmos"), não um
    instante: converter prosa em relógio é decisão do mundo, e ela precisa da mesma
    leitura que carimba os prazos de item. Enquanto essa conversão não existe, o texto
    é o que há — e é o que a Mente lê quando a intenção desce ao contexto.

    Por que aqui e não numa entidade nova: a expectativa de cobrar é um PLANO, e plano é
    intenção. É o raciocínio da tríade temporal que dissolveu a "classe de compromisso"
    antes de ela nascer, na spec 027.
    """
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return False
    fm, body = read_doc(path)
    if fm.get("status") != "ativa":
        return False
    fm["ate_quando"] = ate_quando
    fm["updated_ts"] = int(time.time())
    write_doc(path, fm, body)
    return True


def update_intention(folder: Path, intention_id: str, content: str,
                     status: str = "ativa") -> bool:
    """Reescreve uma intenção EXISTENTE no lugar (mesmo arquivo, mesmo id).

    Só opera sobre intenção ATIVA — não reabre concluída/abandonada (uma
    continuação nasce como intenção nova, com o próprio id: research.md,
    Decisão 4). Devolve False se o id não existir nesta pasta ou não estiver
    ativa; quem chama decide como relatar isso (rejeição estruturada)."""
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return False
    fm, _ = read_doc(path)
    if fm.get("status") != "ativa":
        return False
    fm["status"] = status
    fm["updated_ts"] = int(time.time())
    write_doc(path, fm, content)
    return True


def close_intention(folder: Path, intention_id: str,
                    status: str = "concluida") -> bool:
    """Fecha uma intenção ATIVA da PRÓPRIA pasta SEM reescrever o conteúdo
    (spec 027) — usado quando quem fecha é um efeito colateral de `give`/
    `trade` cumprindo um compromisso, não o Árbitro autorando texto novo
    (`set_intention`, que sempre reescreve o corpo inteiro). Mesmas regras de
    `update_intention` (só ATIVA, só da própria pasta); devolve False sem
    tocar o arquivo se não existir ou já não estiver ativa."""
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return False
    fm, body = read_doc(path)
    if fm.get("status") != "ativa":
        return False
    # CUMPRIR EXTINGUE O PRAZO (spec 070, FR-016 / T026). Uma promessa cumprida antes da
    # hora não pode vencer depois — seria o mundo cobrando algo que já foi feito.
    #
    # A limpeza é aqui, no fecho, e não em cada tool que cumpre: `give` e `trade` já
    # chamam esta função, e escrever a mesma regra nas duas seria a segunda via que o
    # Princípio I proíbe.
    if fm.pop("ate_quando", None) is not None:
        write_doc(path, fm, body)
    return update_intention(folder, intention_id, body, status=status)


# AS TRAVAS DO NASCIMENTO (spec 073, FR-003).
#
# Cada uma nasce de um defeito REAL, gravado no mundo hoje (`medicoes.md` §2) — não
# de higiene imaginada. E todas são checáveis DETERMINISTICAMENTE: nenhuma pede juízo
# de modelo, que é o que as torna baratas e justas.
#
# A prosa que delata a meta-instrução. O caso do Draven é literal: "Análise o contexto
# e decida o que achar melhor" é instrução para um modelo, gravada como compromisso de
# vida de um personagem, e está ATIVA há semanas. Passou por todo o pipeline sem nada
# barrar.
_META = ("analis", "decida o que", "decidir o que", "avalie o contexto",
         "avaliar o contexto", "considere as opções", "reflita sobre",
         "pense no que", "leia o contexto")


def travas_do_nascimento(content: str, pronto_quando: str | None,
                         nome_proprio: str | None = None,
                         pronto_quando_alvo: str | None = None
                         ) -> tuple[str, dict] | None:
    """A intenção pode nascer? Devolve `(regra, valores)` da recusa, ou `None`.

    TRÊS TRAVAS, e a honestidade sobre a quarta:

      1. META-INSTRUÇÃO — o caso do Draven.
      2. SEM CRITÉRIO — o caso do Pip ("sem pressa e com cuidado"): sem
         `pronto_quando` não há como o mundo saber que acabou, e o que não fecha não
         ensina.
      3. APONTA PARA SI — o caso da Nerissa ("aprender o caminho com Nerissa",
         escrito por ela mesma). Nasceu torta e nada percebeu.

    A QUARTA NÃO CABE AQUI, e isto é uma correção ao FR-003 como escrito.

    O defeito do Tobias ("inventário completo dos frascos de vidro") é "não há
    primeiro passo que a face ofereça" — e a face não está disponível no ato de
    firmar; ela é da cena, e muda. Essa trava mora no PLANO (FR-007), onde os passos
    são validados contra os verbos do mundo.

    E o FR-003 dizia "não nomeie sujeito concreto", que rejeitaria a própria US1:
    "matar minha fome" não nomeia entidade externa nenhuma, e é um compromisso
    perfeitamente bom. A trava certa é a de META-INSTRUÇÃO, não a de sujeito.
    """
    texto = (content or "").strip()
    baixo = texto.lower()
    if not texto:
        return ("intencao_vazia", {})
    if any(m in baixo for m in _META):
        return ("intencao_meta", {"trecho": texto[:60]})
    if not pronto_quando:
        return ("intencao_sem_criterio", {})
    if pronto_quando not in _CRITERIO_POR_CAMPO:
        return ("intencao_criterio_desconhecido",
                {"pedido": pronto_quando,
                 "validos": sorted(_CRITERIO_POR_CAMPO)})
    # A POSSE PRECISA DIZER O QUÊ. As outras famílias se conferem sozinhas ("não
    # estou mais faminto"); "está comigo" não diz nada sem o objeto. Sem o alvo, a
    # intenção nasceria com um critério que NUNCA vira verdade — pior que sem
    # critério, porque parece ter um.
    if pronto_quando in _PRECISAM_DE_ALVO and not (pronto_quando_alvo or "").strip():
        return ("intencao_posse_sem_alvo", {})
    # APONTA PARA SI: o personagem citando o próprio nome como se fosse outro.
    # "Vou aprender o caminho com Nerissa" dito PELA Nerissa.
    if nome_proprio:
        primeiro = nome_proprio.split(",")[0].strip().lower()
        if len(primeiro) >= 3 and f" {primeiro}" in f" {baixo}":
            # "minha fome" e "eu" não contam — só o NOME em terceira pessoa
            return ("intencao_aponta_pra_si", {"nome": primeiro})
    return None


def _dobrar(texto: str) -> str:
    """minúsculas, sem acento, só letras e dígitos separados por espaço."""
    plano = unicodedata.normalize("NFKD", texto or "")
    plano = "".join(c for c in plano if not unicodedata.combining(c))
    return " " + re.sub(r"[^a-z0-9]+", " ", plano.lower()).strip() + " "


def passos_do_plano(body: str) -> list[str]:
    """As linhas de checklist do corpo da intenção (`- passo`), na ordem.

    O corpo é `compromisso\n- passo\n- passo`: a primeira linha é o COMPROMISSO
    (o que se quer), as de traço são o PLANO (como). Uma intenção sem plano
    devolve lista vazia — e nunca risca, que é o certo: não há passo a cumprir.
    """
    passos = []
    for linha in (body or "").splitlines():
        limpa = linha.strip()
        if limpa.startswith(("- ", "* ")):
            passos.append(limpa[2:].strip())
    return passos


# === O PASSO SEM VERBO (spec 073, FR-007) ==================================== #
#
# O defeito do Tobias, literal e ativo no mundo: *"fazer um inventário completo dos
# frascos de vidro"*. Não há verbo nenhum ali que o mundo saiba executar — nasceu
# impossível, e nada percebeu. É o irmão da meta-instrução do Draven: uma trava do
# NASCIMENTO, determinística, sem juízo de modelo.
#
# CONTRA O QUE SE VALIDA — e isto é uma CORREÇÃO ao FR-007 como escrito.
#
# O requisito dizia "validados contra a FACE". A face é da CENA, e um plano de mais
# de um passo atravessa cenas de propósito: "ir à Forja de Ferro" e depois "forjar a
# lâmina" é plano bom, e `forge_weapon` NÃO está na face de quem ainda está na praça.
# Validar contra a face rejeitaria exatamente os planos que se movem — os melhores.
#
# A régua certa é o VOCABULÁRIO DO MUNDO: os verbos que existem, ativos neste mundo.
# Ela pega o caso que importa (o passo que não nomeia ato nenhum) e deixa passar o
# que só depende de o personagem chegar lá.
def passos_sem_verbo(content: str, verbos) -> list[str]:
    """Os passos do plano que não nomeiam nenhum verbo do mundo, na ordem.

    Compara por SEQUÊNCIA DE PALAVRAS INTEIRAS sobre o texto dobrado: `take` casa em
    "take o pão" e em "Take a maçã", e NÃO casa dentro de "retaken". O verbo também é
    dobrado, que é o que faz `travel_to` casar com "travel to Forja" — o underscore
    vira espaço dos dois lados, e a comparação continua sendo de palavra inteira.
    (A primeira versão testava `verbo in passo.lower()` como atalho para o
    underscore, e o próprio teste pegou: "retaken o pão" passava.)

    Um `content` sem plano nenhum (só o compromisso) devolve lista vazia — não há
    passo a reprovar, e um compromisso sem plano continua legítimo.
    """
    vocab = [_dobrar(v).strip() for v in (verbos or [])]
    vocab = [v for v in vocab if v]
    if not vocab:
        return []          # sem vocabulário não há régua; nunca reprove no escuro
    ruins = []
    for passo in passos_do_plano(content):
        alvo = _dobrar(passo)
        if any(f" {v} " in alvo for v in vocab):
            continue
        ruins.append(passo)
    return ruins


# O CASAMENTO DO PASSO (`casar_e_riscar`, `riscar_passo`) e o FECHAMENTO POR CRITÉRIO
# (`fechar_por_criterio`) SAÍRAM DAQUI na spec 075 (opção 2: o world guarda, o harness
# decide). Quem confere se um passo andou e se o desejo se cumpriu é o harness do
# conector (C8/C8D), lendo o contexto por regra; o Motor só grava a intenção.


def abandonar(folder: Path, intention_id: str, personagem: str) -> dict | None:
    """A desistência, e ela VIRA MEMÓRIA (spec 073, FR-015).

    Um compromisso que morre em silêncio não ensina nada — e é exatamente por isso
    que o mundo tem hoje quatro intenções podres ativas há semanas, com ZERO
    abandonos em 425 turnos (`medicoes.md` §1).

    A valência e a intensidade viajam COM o ato, nunca numa tabela central: as
    `_VALENCE_BY_EVENT`/`_RELEVANCE_BY_EVENT` morreram na spec 038, justamente porque
    eram o par que uma feature nova esquecia de atualizar e a memória saía errada em
    silêncio (o anti-padrão que a spec 013 nomeou).

    `medium` e negativa: desistir do que se prometeu a si mesmo pesa — mas não é
    trauma. `large`/`giant` dispararia o portão de `sofreu_trauma_de`, e largar um
    plano não é agressão.
    """
    path = folder / "intentions" / f"{intention_id}.md"
    if not path.exists():
        return None
    fm, body = read_doc(path)
    if fm.get("status") != "ativa":
        return None
    fm["status"] = "abandonada"
    fm["updated_ts"] = int(time.time())
    write_doc(path, fm, body)
    texto = " ".join(body.strip().split())[:90]
    from ..memoria import remember
    remember(personagem, f"Desisti: {texto}",
             intensity="medium", summary=f"Desisti: {texto[:50]}",
             valence={personagem: "negativa"})
    return {"id": intention_id, "content": body.strip()}


def get_active_intentions(folder: Path) -> list[dict]:
    """Intenções ATIVAS de quem possui `folder`, para o contexto (consultivo de
    client, Princípio IX nível 2) — mesmo shape enxuto de `data-model.md`:
    {id, status, content}. Encerradas somem daqui, mas continuam no disco."""
    dir_ = folder / "intentions"
    if not dir_.exists():
        return []
    out = []
    for path in arquivos_em(dir_):
        fm, body = read_doc(path)
        if fm.get("status") != "ativa":
            continue
        entrada = {"id": fm.get("id"), "status": fm.get("status"),
                   "content": body.strip()}
        # spec 070: a hora da promessa desce junto — é o que dá SENTIDO à pressa, e é
        # texto, nunca instante (o número é medida interna, Princípio V).
        if fm.get("ate_quando"):
            entrada["ate_quando"] = fm["ate_quando"]
        # spec 073: o CRITÉRIO e o PROGRESSO. O critério desce como veio (é enum
        # fechado, vocabulário, não id de cena). O progresso desce como CONTAGEM —
        # quantos passos do plano já foram riscados —, que é o que o prompt de
        # executar lê para separar o feito do faltante.
        if fm.get("pronto_quando"):
            entrada["pronto_quando"] = fm["pronto_quando"]
            # o ALVO da posse desce junto: sem ele o compromisso chega à Mente como
            # "ter algo", e ela não sabe o que estava perseguindo.
            if fm.get("pronto_quando_alvo"):
                entrada["pronto_quando_alvo"] = fm["pronto_quando_alvo"]
        out.append(entrada)
    if len(out) > _INTENTION_CONTEXT_CAP:
        out = out[-_INTENTION_CONTEXT_CAP:]  # as mais RECENTES ficam
    return out


