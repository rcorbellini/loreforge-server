"""Server-side do Loreforge — A FRONTEIRA entre client e mundo.

(Este módulo já se chamou "o MCP" aqui, no sentido metafórico da spec 003 — a
camada de fronteira. Desde a spec 043 o Model Context Protocol de verdade existe
no projeto, em `mcp_server.py`, e a sigla ficou reservada a ele.)

Expõe uma API HTTP mínima (stdlib apenas) e, por conveniência de desenvolvimento
local, também serve os arquivos estáticos do client. A separação lógica se mantém:
o código do client nunca importa o server — só fala com esta API.

Endpoints (leitura livre para o client):
  GET  /api/context?character_id=ID   -> proximity_context
  GET  /api/character?character_id=ID -> definição + estado
  GET  /api/inventory?character_id=ID -> árvore de inventário
  GET  /api/entity?id=ID              -> detalhe diegético
  POST /api/tools/<nome>              -> resolver_proposta() (o guichê único —
                                         spec 045 aposentou o /api/act legado)
  POST /api/mcp                       -> mcp_core.tratar() (o caminho da Mente)

Escrita é exclusiva do server (Princípio III).
Rodar:  python3 server/app.py [--port 8777]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import arbiter
import devlog
import face
import mcp_core
import openapi
import registro_turno
from version import __version__
import llm
import motor
import auth

REPO_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = REPO_ROOT / "loreforge-client"
SERVER_DIR = Path(__file__).resolve().parent

# --- spec 022: streaming do turno + trava de turno-em-andamento --------------- #
# Cadência do batimento: menor que os timeouts ociosos típicos de rede móvel
# (≥30–60 s). Módulo-level para ser INJETÁVEL em teste (selftest_phase24).
HEARTBEAT_SECS = 6.0
# Trava de turno-em-andamento POR PERSONAGEM (FR-005b). NÃO é o WRITE_LOCK do Motor
# (aquele protege a gravação por-op); esta protege o TURNO: um /act por personagem por
# vez. Um 2º /act do mesmo personagem enquanto o turno corre é REJEITADO (não enfileira).
_TURNS_IN_FLIGHT: set[str] = set()
_TURNS_GUARD = threading.Lock()

# Trava do vínculo jogador↔personagem (spec 056, FR-013): claim/release fazem
# ler→checar→escrever no mesmo character.md; sem trava, dois claims concorrentes
# passam ambos no `if fm.get("owner")` antes de qualquer um escrever. Mesmo
# padrão de _TURNS_GUARD, mas escopo diferente (posse, não turno-em-andamento).
_OWNERSHIP_GUARD = threading.Lock()


def _claim_turn(character_id: str) -> bool:
    """Marca o turno do personagem como em andamento. False se já havia um (rejeita)."""
    with _TURNS_GUARD:
        if character_id in _TURNS_IN_FLIGHT:
            return False
        _TURNS_IN_FLIGHT.add(character_id)
        return True


def _release_turn(character_id: str) -> None:
    with _TURNS_GUARD:
        _TURNS_IN_FLIGHT.discard(character_id)

# Config do Árbitro (server-side). config.server.json é gitignored; há três exemplos
# (Ollama local, Claude remoto e OpenRouter). Os defaults dependem do runtime escolhido.
_ARBITER_DEFAULTS = {
    "ollama": {
        "runtime": "ollama",
        "endpoint": "http://localhost:11434",
        "model": "llama3.1:8b",
        "temperature": 0.2,
        "tool_calling": "auto",  # auto | on | off (spec 003)
        "max_tool_calls": 8,
    },
    "anthropic": {
        "runtime": "anthropic",
        "endpoint": "https://api.anthropic.com",
        "model": "claude-haiku-4-5-20251001",
        "temperature": 0.2,
        "max_tokens": 2048,
        "api_key": "",
        "tool_calling": "auto",
        "max_tool_calls": 8,
    },
    "openrouter": {
        "runtime": "openrouter",
        "endpoint": "https://openrouter.ai/api/v1",
        "model": "poolside/laguna-m.1:free",
        "temperature": 0.2,
        "max_tokens": 2048,
        "api_key": "",
        "tool_calling": "auto",
        "max_tool_calls": 8,
    },
}

# Memoriza, por processo, um runtime que já se revelou sem suporte a tools —
# em "auto" os turnos seguintes nem tentam (spec 003, FR-005).
TOOLS_STATE = {"unsupported": False}


def load_config() -> dict:
    doc = {}
    path = SERVER_DIR / "config.server.json"
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            doc = {}
    raw = doc.get("arbiter") or {}
    runtime = (raw.get("runtime") or "ollama").lower()
    if runtime == "claude":  # apelido amigável
        runtime = "anthropic"
    base = _ARBITER_DEFAULTS.get(runtime, _ARBITER_DEFAULTS["ollama"])
    arb = {**base, **raw, "runtime": runtime}
    # seção "server" (transporte): o streaming pode ser DESLIGADO — alguns proxies
    # (ex.: ngrok free) resetam a conexão chunked longa. Com o modelo quente (~3s), a
    # resposta única (Content-Length) atravessa o proxy como o GET e não estoura.
    server = doc.get("server") or {}
    stream = server.get("stream")
    auth_conf = doc.get("auth") or {}
    return {"arbiter": arb, "server": {"stream": True if stream is None else bool(stream)}, "auth": auth_conf}


def build_ask(arb: dict, falhas: list | None = None):
    """O transporte do JUÍZO (spec 043) — `ask(system, user) -> str`, de um tiro.

    Reusa as `make_*_fn` de `llm.py`, que existiam para os três runtimes e estavam
    ÓRFÃS desde a spec 020 (o caminho clássico do Árbitro foi removido e ninguém mais
    as chamava). O juízo as ressuscita em vez de escrever transporte novo.

    Sem tools, sem laço: a pergunta é fechada ("dada esta régua e esta cena, qual a
    nota?"). Falha de rede devolve VAZIO em vez de estourar — cada capacidade cai no
    PRÓPRIO default (`juizo.nota`), e o turno segue. Um juízo é degradável por
    desenho; derrubar o turno por causa dele seria trocar o certo pelo cosmético.
    """
    runtime = arb.get("runtime", "ollama")
    try:
        if runtime == "anthropic":
            endpoint = arb.get("endpoint") or ""
            if "anthropic" not in endpoint:
                endpoint = "https://api.anthropic.com"
            fn = llm.make_anthropic_fn(
                arb.get("api_key") or os.environ.get("ANTHROPIC_API_KEY", ""),
                arb["model"], temperature=arb.get("temperature", 0.2),
                endpoint=endpoint)
        elif runtime == "openrouter":
            # o ENDPOINT é trocável (qualquer host que fale openai-completions, ex.
            # o Zen da OpenCode) e a chave é DELE. Não repassar isto mandava a chave
            # de um provider para o outro — 401, juízo caindo no default em silêncio.
            fn = llm.make_openrouter_fn(
                arb.get("api_key") or os.environ.get("OPENROUTER_API_KEY", ""),
                arb["model"], temperature=arb.get("temperature", 0.2),
                endpoint=arb.get("endpoint") or "https://openrouter.ai/api/v1")
        else:
            fn = llm.make_ollama_fn(arb["endpoint"], arb["model"],
                                    temperature=arb.get("temperature", 0.2))
    except Exception as exc:               # runtime mal configurado
        devlog.log("JUÍZO INDISPONÍVEL — capacidades cairão no default", repr(exc))
        if falhas is not None:
            falhas.append(str(exc))
        return lambda _s, _u: ""

    def ask(system: str, user: str) -> str:
        try:
            raw = fn(system, user)
        except Exception as exc:
            devlog.log("JUÍZO FALHOU — a capacidade cai no default", repr(exc))
            # ITEM 52.1: a pane do juízo tem de SAIR daqui. Um `devlog.log` só o
            # mantenedor lê — e a Nerissa jogou 11 horas com 148 dessas, das quais
            # UMA chegou ao registro. O jogo degradava em silêncio: a Mente propunha,
            # o mundo dizia "ok", nada acontecia, e o jogador culpava o personagem.
            #
            # Por que uma LISTA por turno e não um estado global: a pergunta que
            # importa é "ESTE turno foi julgado?", não "o provedor está de pé?". Um
            # turno pode ter 3 capacidades julgadas e falhar só numa.
            if falhas is not None:
                falhas.append(str(exc))
            return ""
        # spec 053: ÍNTEGRA, não recorte. Antes registrava 80 caracteres da resposta
        # e NADA do prompt — e o docstring do devlog prometia "system + user". Sem o
        # que foi ENVIADO não há como reproduzir um julgamento errado: quando o
        # Árbitro deu combustibilidade 9 a uma pederneira (2026-08-24), a causa
        # (o mesmo objeto em `materiais` e em `em_maos`) só apareceu por dedução.
        devlog.log("JUÍZO — ENVIADO (system)", system)
        devlog.log("JUÍZO — ENVIADO (user)", user)
        devlog.log("JUÍZO — RESPOSTA (íntegra)", raw or "")
        return raw

    return ask


CONFIG = load_config()


# Recusas de combate (spec 008) não falam em "mover": quem apanha não é carregado.
_REGRAS_DE_COMBATE = {"ataque_errou", "golpe_absorvido", "alvo_ja_morto"}
# Transporte (spec 010): quem falha em levar alguém não "não foi movido" — a
# pessoa é que não saiu do lugar.
_REGRAS_DE_TRANSPORTE = {"peso_excede_arrasto", "alvo_resistiu", "alvo_desacordado"}
# Comércio (spec 011): o que falha aqui não "foi movido" — não mudou de mãos.
# Recusas sobre um ITEM específico nomeiam o item...
_REGRAS_DE_COMERCIO = {"nao_esta_a_venda", "nao_e_negociavel", "item_nao_e_seu",
                       "pagamento_nao_e_dinheiro", "destino_ocupado"}
# ...e recusas sobre o NEGÓCIO inteiro não nomeiam nada: dizer "'isso' não mudou
# de mãos" quando o problema é o preço soa quebrado, e é a Mente que vai narrar.
_REGRAS_DE_NEGOCIO = {"valor_insuficiente", "necessidade_insuficiente",
                      "sem_espaco_para_receber", "parceiro_incapaz"}
# Recusas sem sujeito no mundo: não há item nem alvo a nomear na frase.
_REGRAS_SEM_SUJEITO = {"atacante_caido", "sem_alvo_valido"}
# Jornada (spec 012): quem não sabe o caminho não teve NADA "não movido" — e
# nomear um item aqui produzia "'isso' não foi movido — você não sabe como
# chegar lá", que é o mesmo defeito que o comércio corrigiu na spec 011. A
# recusa é sobre a viagem inteira, e não há sujeito a apontar.
_REGRAS_DE_JORNADA = {"caminho_desconhecido", "ja_esta_la", "viagem_interrompida",
                      "rota_indisponivel"}
# Leitura (spec 014): falhar em decifrar é ROTINA com DC 12, não exceção. A frase
# precisa soar como dificuldade de leitura — nunca como proibição, e nunca como
# "item não movido", que foi o defeito que o comércio e a jornada já corrigiram.
_REGRAS_DE_LEITURA = {"leitura_falhou", "rota_inexistente", "nada_a_examinar",
                      # faltava desde a spec 014: caía no ramo genérico e o
                      # jogador lia "'isso' não foi movido" sobre uma leitura
                      "citacao_nao_confere"}

# Recusas de CONVERSA (spec 015). Família própria porque nenhuma das outras
# frases serve: ninguém "não foi movido" ao ser mal recebido.
_REGRAS_DE_CONVERSA = {"recusou_informar", "informante_indisponivel",
                       "informante_nao_sabe", "fonte_omitida",
                       # boato (spec 017): a fofoca que não se contou
                       "nao_confiou", "nada_a_contar"}
# dentro da conversa, o boato tem moldura própria (não é "o caminho não foi
# ensinado" — é "ela não abriu o que sabe")
_REGRAS_DE_BOATO = {"nao_confiou", "nada_a_contar"}


def _dedupe_por_id(pacotes: list) -> list:
    """Um reconhecimento por entidade (spec 018): o ambiente e a tool `recognize`
    podem trazer a mesma pessoa/coisa; A Mente não deve tecê-la duas vezes.
    Preserva a ordem e a primeira ocorrência.
    """
    visto, out = set(), []
    for p in pacotes:
        chave = p.get("id") or p.get("name")
        if chave in visto:
            continue
        visto.add(chave)
        out.append(p)
    return out


def inworld_effects(outcome: dict) -> list[str]:
    """O que REALMENTE aconteceu, em linguagem de mundo, para A Mente narrar.

    Contraparte de `inworld_failures`, e a assimetria que existia era grave: o
    narrador recebia o que FALHOU e não recebia o que ACONTECEU — ele narrava a
    partir da intenção do jogador, que é um desejo, não um fato.

    Foi assim que a Hulda tirou o gibão de placas e o deixou no chão da praça sem
    que uma palavra disso chegasse ao jogador: o mundo registrou, a narração nem
    soube. Imprevisibilidade do modelo ao AGIR é o jogo; narrar um fato que não
    aconteceu — ou calar um que aconteceu — é defeito.

    Frases curtas e factuais, com NOMES e nunca ids. A Mente decide como contar;
    o que ela não pode é ignorar.
    """
    # spec 038 (T041): cada canal declara a PRÓPRIA frase in-world, co-localizada com
    # a tool (`@registro.inworld`); aqui só se ITERA o registro. Acrescentar uma tool
    # narrável não toca mais este ponto. A ordem é irrelevante — os consumidores checam
    # PERTINÊNCIA (substring/`any`), não sequência.
    ditos = []
    for chave, frase in motor.registro.inworld_phrases().items():
        for op in outcome.get(chave) or []:
            dito = frase(op)
            if dito:
                ditos.append(dito)
    return ditos


def _passo_nao_dado(character_id: str, intent: dict, outcome: dict) -> list[dict]:
    """Avisa A Mente quando o ATOR devia partir e não partiu (spec 012).

    Nasceu de um turno real: a intenção era "Hulda começa a caminhar em direção
    à Ladeira do Sal", e o Árbitro resolveu PERSUADIR outra pessoa a ir. As
    recusas diziam que a Sarga não se moveu — nada dizia que a Hulda não andou.
    Com a dica narrativa falando em caminhar, A Mente narrou o passo que o mundo
    não deu.

    Isto não força a mão do Árbitro: ele PODE decidir que o personagem não parte,
    e a dica de movimento continua sendo dica (foi essa a lição da spec 010, que
    tirou o atalho de movimento da fronteira). O que não pode é o player ler um
    deslocamento que não aconteceu — então quando o ator pediu para andar e
    continua onde estava, a narração recebe isso por escrito.
    """
    if not isinstance(intent, dict):
        return []
    movimento = intent.get("movement") or {}
    if not isinstance(movimento, dict) or not movimento.get("enter_route"):
        return []
    # o ator saiu do lugar por algum caminho? qualquer um serve — o Árbitro pode
    # ter escolhido rota diferente da sugerida, e isso é decisão legítima dele
    if outcome.get("travel_ops_applied"):
        return []
    for op in outcome.get("carry_ops_applied") or []:
        if isinstance(op, dict):
            return []  # foi levado por alguém: saiu do lugar
    try:
        fm, _ = motor.read_doc(motor.find_character_folder(character_id) / "character.md")
    except motor.MotorError:
        return []
    if isinstance(fm.get("transit"), dict):
        return []  # está a caminho: o passo aconteceu
    return [{
        "o_que_falhou": "o passo não aconteceu — você continua onde estava",
        "regra": "ator_nao_partiu",
        "valores": {"rota_pretendida": movimento.get("enter_route")},
    }]


# As recusas cujo texto fala de ALGUÉM e precisa dizer QUEM. Fora daqui ficam as que
# falam do ATO ou da COISA ("o golpe passou ao largo", "isso não se veste"), onde um
# nome colado na frente sairia torto.
# Só as que o texto ACEITA um sujeito na frente. As impessoais ficam de fora — "não
# há onde vestir isso nesse corpo" com um nome colado sai torto, e uma frase torta
# atrapalha a narração mais do que a falta do nome.
_REGRAS_COM_SUJEITO = {
    "maos_ocupadas", "slot_ocupado",
    "peso_excede_carga", "peso_excede_empurrar", "peso_excede_arrasto",
    "nao_cedeu", "nada_a_ceder", "nao_confiou", "recusou_informar",
    "alvo_resistiu", "necessidade_insuficiente",
    "parceiro_incapaz", "personagem_inacessivel",
    # Entraram em 2026-08-20: falam do ALVO e o pronome vazava gênero errado
    # ("disso ela nada sabe" sobre o Torvin). Foram reordenadas para começar
    # pelo pronome, que é o que esta troca exige — o nome entra no lugar dele.
    "nada_a_contar", "informante_nao_sabe", "alvo_nao_caido",
    "destino_e_o_dono",
}


def nomear_sujeito(regra: str, why: str, valores: dict) -> str:
    """Põe o NOME de quem a recusa fala, quando o texto aceita sujeito.

    Existe porque a recusa segue por DOIS caminhos e os dois chegam ao jogador: a
    rejeição de uma op aplicada (via `inworld_failures`) e a recusa DIRETA da
    capacidade (o `erro` que volta da proposta, e que vira beat e matéria de
    narração). Nomear só num deles deixava o outro dizendo "está de mãos ocupadas"
    sem sujeito — e A Mente entendia que eram as mãos de QUEM AGE. Achado real: a
    entrega de uma moeda a Tobias virou "suas mãos estão cheias".

    Troca o PRONOME pelo nome; os textos sociais já começam com "ele/ela", e prefixar
    daria "Tobias ele ouviu".
    """
    if regra not in _REGRAS_COM_SUJEITO:
        return why
    quem = ((valores or {}).get("personagem") or (valores or {}).get("informante")
            or (valores or {}).get("alvo") or (valores or {}).get("parceiro"))
    if not quem:
        return why
    nome = motor.name_of(quem)
    trocado = re.sub(r"^(ele|ela|Ele|Ela)\b", nome, why)
    return trocado if trocado != why else f"{nome} {why}"


def inworld_failures(rejected: list) -> list[str]:
    """Traduz rejeições do Motor em frases de mundo para a narração do client.

    O Árbitro pode narrar um efeito que o Motor negou (id inexistente, destino
    ambíguo...). A narrativa final precisa ser coerente com o ESTADO REAL — então o
    client recebe, em linguagem de mundo, o que NÃO se concretizou, e o narrador
    conta a tentativa frustrada em vez do sucesso imaginado.
    """
    out = []
    for r in rejected:
        why = r.get("why") or ""
        if r.get("regra"):
            # negação física estruturada (spec 004): o texto resume, e o par
            # {regra, valores} segue junto — matéria-prima suficiente para a
            # Mente narrar a recusa sem nova consulta (FR-011/SC-007). Os
            # valores nunca chegam crus ao player: morrem na Mente.
            valores = r.get("valores") or {}
            item = (r.get("item") or valores.get("item")
                    or valores.get("alvo") or "isso")  # persuasão: o alvo (spec 007)
            # DE QUEM é o corpo que recusou. Recusa de capacidade física (mão, slot)
            # pode ser de QUEM RECEBE, não de quem age — e sem o nome o jogador lê
            # como sendo dele. Achado real: "as mãos já estão ocupadas" numa entrega
            # eram as de quem ia receber.
            # DE QUEM se fala. A maioria das recusas diz "ele"/"ela" sem nome, e numa
            # cena com cinco pessoas A Mente não tem como saber de quem — ela roda no
            # client e não vê o que o Motor viu. Sem o nome, a narração ou erra a
            # pessoa ou vira vaga. Vale para o corpo que recusou (mãos, slot, peso) E
            # para quem recusou socialmente (não cedeu, não contou, resistiu).
            why = nomear_sujeito(r["regra"], why, valores)
            if r["regra"] in _REGRAS_DE_CONVERSA:
                # a `atitude` entra na PRÓPRIA frase, e não só nos valores: é a
                # única matéria que A Mente tem para narrar o MOTIVO da recusa.
                # Ela roda no client e não vê as memórias do informante — sem
                # isto, a negativa chega ao jogador como silêncio sem causa.
                if r["regra"] in _REGRAS_DE_BOATO:
                    frase = f"ela não abriu o que sabe — {why}"
                else:
                    frase = f"o caminho não foi ensinado — {why}"
                if valores.get("atitude"):
                    frase += f"; {valores['atitude']}"
            elif r["regra"] in _REGRAS_DE_LEITURA:
                frase = f"nada disso ficou — {why}"
            elif r["regra"] in _REGRAS_DE_JORNADA:
                frase = f"a viagem não aconteceu — {why}"
            elif r["regra"] in _REGRAS_DE_NEGOCIO:
                frase = f"o negócio não se fez — {why}"
            elif r["regra"] in _REGRAS_DE_COMERCIO:
                frase = f"'{item}' não mudou de mãos — {why}"
            elif r["regra"] in _REGRAS_DE_TRANSPORTE:
                frase = f"'{item}' não saiu do lugar — {why}"
            elif r["regra"] in _REGRAS_SEM_SUJEITO:
                frase = f"nada aconteceu — {why}"
            elif r["regra"] in _REGRAS_DE_COMBATE:  # ninguém "não foi movido" ao apanhar
                frase = f"'{item}' não foi ferido — {why}"
            else:
                frase = f"'{item}' não foi movido — {why}"
            out.append({
                "o_que_falhou": frase,
                "regra": r["regra"],
                "valores": valores,
            })
        elif "item" in r:  # transferência negada (motivos não-físicos)
            item, to = r.get("item"), r.get("to")
            if "não existe" in why:
                out.append(f"'{item}' não estava ao alcance de ninguém — nada mudou de mãos")
            elif "si mesmo" in why:
                out.append(f"não foi possível guardar '{item}' dentro de si mesmo")
            elif "colisão" in why:
                out.append(f"não havia lugar para '{item}' em '{to}' — ficou onde estava")
            else:  # destinatário não presente na cena, ou ambíguo
                out.append(
                    f"'{item}' continua onde estava — não se encontrou '{to}' "
                    "ao alcance para recebê-lo"
                )
        elif "path" in r:  # mutação negada (alvo ausente, identidade, raiz proibida)
            out.append(f"a mudança tentada em '{r.get('target')}' não se concretizou")
        # deslocamento negado não entra: _apply_movement já devolve o hint honesto
    return out

# spec 052 — o vocabulário in-world das rolagens de BANDA. Uma entrada por tipo;
# acrescentar uma quinta é acrescentar uma linha, não um ramo. As frases dizem o que
# aconteceu sem dizer NENHUM número: nem dado, nem nota, nem banda, nem DC (Princípio
# V — os números seguem na `rolagem` e morrem na Mente).
_BANDA_BOA = {
    "cozinha": {"otima"},
    "cura": {"alta"},
    "acougue": {"farto"},
    "forja": {"incomum", "raro", "lendario"},
    "craft": {"incomum", "raro", "lendario"},
}

_FRASES_DE_BANDA = {
    "cozinha": {
        "critico_bom": "o ponto saiu como raramente sai",
        "critico_ruim": "o fogo virou contra o preparo na hora errada",
        "virada_boa": "não havia por que aquilo ficar bom — e ficou",
        "virada_ruim": "estava tudo a favor, e ainda assim o preparo se perdeu",
    },
    "cura": {
        "critico_bom": "as mãos souberam exatamente o que fazer",
        "critico_ruim": "as mãos falharam justo em quem mais precisava",
        "virada_boa": "não parecia haver mais o que fazer — e ainda assim melhorou",
        "virada_ruim": "era socorro simples, e o corpo não respondeu",
    },
    "acougue": {
        "critico_bom": "a lâmina achou cada junta na primeira tentativa",
        "critico_ruim": "a lâmina se perdeu no corpo e estragou o que havia",
        "virada_boa": "aquele corpo não prometia nada — e rendeu",
        "virada_ruim": "prometia fartura, e sobrou quase nada",
    },
    "forja": {
        "critico_bom": "o metal respondeu como raramente responde",
        "critico_ruim": "o metal traiu a peça no pior momento",
        "virada_boa": "não havia por que aquilo virar coisa boa — e virou",
        "virada_ruim": "tudo estava a favor, e a peça saiu torta",
    },
    "craft": {
        "critico_bom": "as mãos acharam o jeito certo sem um erro sequer",
        "critico_ruim": "as mãos escorregaram bem na hora que não podia",
        "virada_boa": "não havia por que aquilo sair bem — e saiu",
        "virada_ruim": "tudo estava a favor, e saiu torto mesmo assim",
    },
}


def fate_twists(rolls: list) -> list[dict]:
    """Desfechos marcantes das rolagens (specs 006/007): virada (resultado
    invertido do natural/da tendência) e, na persuasão, também os críticos
    naturais do dado. Frase in-world + rolagem crua — A Mente narra o feito ou o
    azar; os números morrem nela (Princípio V)."""
    out = []
    for r in rolls or []:
        if r.get("tipo") == "negociacao":
            if not (r.get("virada") or r.get("critico")):
                continue
            sucesso = r.get("resultado") == "sucesso"
            if r.get("critico") == "sucesso":
                frase = "a proposta caiu como uma luva"
            elif r.get("critico") == "falha":
                frase = "uma palavra a mais, e o negócio morreu ali"
            elif sucesso:
                frase = "não havia por que ele aceitar — e aceitou"
            else:
                frase = "o negócio estava feito — e escapou na última palavra"
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "parceiro": r.get("parceiro"),
                        "resultado": r.get("resultado"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        if r.get("tipo") == "transporte":
            if not (r.get("virada") or r.get("critico")):
                continue
            sucesso = r.get("resultado") == "sucesso"
            if r.get("regime") == "disputa":
                frase = ("ele se firmou o quanto pôde, e ainda assim foi levado"
                         if sucesso else "bastava um puxão — mas ele escapou")
            else:
                frase = ("o corpo não devia sair do chão — e saiu" if sucesso
                         else "devia ser simples erguer — e hoje não foi")
            if r.get("critico") == "sucesso":
                frase = "o corpo respondeu como raramente responde"
            elif r.get("critico") == "falha":
                frase = "as mãos falharam na hora errada"
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": r.get("alvo"), "regime": r.get("regime"),
                        "resultado": r.get("resultado"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        # spec 053 — ACENDER. Sem este ramo, uma virada de ignição caía no genérico
        # de FORÇA e narrava "'None' não devia ceder a esses braços": o mesmo tipo de
        # ruído que a 052/T017 tirou da forja, com um `None` literal no texto. A
        # ignição é BINÁRIA, então não há banda a narrar — só o improvável.
        if r.get("tipo") == "fogo":
            if not (r.get("virada") or r.get("critico")):
                continue
            sucesso = r.get("resultado") == "sucesso"
            # `critico` aqui é BOOLEANO (padrão de `cook`/`roll_kindle_check`), não a
            # string "sucesso"/"falha" que `combate` usa — o desfecho vem de
            # `resultado`. Confundir os dois faz o crítico cair no ramo comum, calado.
            if r.get("critico") and sucesso:
                frase = "a primeira faísca bastou"
            elif r.get("critico"):
                frase = "a mão escapou no pior momento, e a faísca morreu"
            elif r.get("virada"):
                frase = ("aquilo não devia pegar — e pegou" if sucesso else
                         "era fogo certo — e a chama não veio")
            else:
                frase = ("a chama pegou" if sucesso else "a chama não pegou")
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "resultado": r.get("resultado"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        if r.get("tipo") == "combate":
            if not (r.get("virada") or r.get("critico")):
                continue
            sucesso = r.get("resultado") == "sucesso"
            if r.get("virada"):
                frase = ("o golpe não tinha como entrar — e entrou" if sucesso else
                         "era um golpe certo — e ainda assim passou longe")
            elif r.get("critico") == "sucesso":
                frase = "a lâmina achou exatamente o lugar"
            else:
                frase = "o corpo traiu o golpe no pior momento"
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": r.get("alvo"), "arma": r.get("arma"),
                        "resultado": r.get("resultado"),
                        "tendencia": r.get("tendencia"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        if r.get("tipo") == "persuasao":
            if not (r.get("virada") or r.get("critico")):
                continue
            alvo = r.get("alvo")
            sucesso = r.get("resultado") == "sucesso"
            if r.get("virada"):
                frase = (f"'{alvo}' não tinha por que ir — e algo nas palavras o "
                         "fez levantar" if sucesso else
                         f"'{alvo}' estava quase indo — mas algo travou, e ficou")
            elif r.get("critico") == "sucesso":
                frase = (f"as palavras caíram perfeitas — '{alvo}' partiu sem "
                         "hesitar")
            else:
                frase = (f"a conversa azedou — '{alvo}' fechou a cara e não "
                         "arredou o pé")
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": alvo, "resultado": r.get("resultado"),
                        "tendencia": r.get("tendencia"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        if r.get("tipo") == "persuade_give":  # convencer a dar (spec 023)
            if not (r.get("virada") or r.get("critico")):
                continue
            sucesso = r.get("resultado") == "sucesso"
            if r.get("virada"):
                frase = ("não havia por que abrir mão do que era seu — e a mão se abriu"
                         if sucesso else
                         "a mão já se estendia — e recolheu o que era dela")
            elif r.get("critico") == "sucesso":
                frase = "cedeu antes mesmo de o pedido terminar"
            else:
                frase = "uma palavra a mais, e o que era dele seguiu sendo dele"
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": r.get("alvo"), "para": r.get("para"),
                        "item": r.get("item"), "resultado": r.get("resultado"),
                        "critico": r.get("critico"), "rolagem": r.get("rolagem")})
            continue
        if r.get("tipo") == "furto":  # roubar (spec 023)
            if not (r.get("virada") or r.get("critico")):
                continue
            limpo = r.get("resultado") == "limpo"
            if r.get("critico") == "sucesso":
                frase = "a mão foi mais rápida que qualquer olhar — nem sombra de suspeita"
            elif r.get("critico") == "falha":
                frase = "os dedos tremeram na hora errada, e o flagra foi geral"
            elif limpo:
                frase = "estava à vista de todos — e ninguém viu a mão passar"
            else:
                frase = "parecia moleza — e o dono ergueu os olhos no pior instante"
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": r.get("alvo"), "item": r.get("item"),
                        "resultado": r.get("resultado"),
                        "critico": r.get("critico"), "rolagem": r.get("rolagem")})
            continue
        # spec 052 — AS ROLAGENS DE BANDA. Cozinhar (048), curar (032), esquartejar
        # (050) e forjar (052) calculam `virada`/`critico` desde que nasceram, e até
        # aqui NENHUMA delas conseguia narrá-los: não havia ramo, o laço final exige
        # `virada` (então o crítico natural das três antigas era descartado em
        # silêncio), e a virada caía no ramo genérico de FORÇA lá embaixo, saindo
        # como uma frase sobre um item que "devia ceder a esses braços" — com o id
        # vazio, porque nenhuma delas tem esse formato. Era violação do Princípio X
        # (aplicar sem relatar) em produção. O guard aqui aceita `virada OR critico`,
        # como combate e furto já faziam.
        if r.get("tipo") in _BANDA_BOA:
            if not (r.get("virada") or r.get("critico")):
                continue
            frases = _FRASES_DE_BANDA[r["tipo"]]
            bom = r.get("resultado") in _BANDA_BOA[r["tipo"]]
            d20 = (r.get("rolagem") or {}).get("d20")
            critico = r.get("critico")
            # `critico` nasce booleano nas três antigas e nomeado em `forja` —
            # normaliza pelo dado, que é o fato de onde os dois saem.
            if critico == "sucesso" or (critico and d20 == 20):
                frase = frases["critico_bom"]
            elif critico == "falha" or (critico and d20 == 1):
                frase = frases["critico_ruim"]
            else:
                frase = frases["virada_boa"] if bom else frases["virada_ruim"]
            out.append({"o_que": frase, "personagem": r.get("personagem"),
                        "alvo": r.get("alvo"), "item": r.get("item"),
                        "resultado": r.get("resultado"),
                        "critico": r.get("critico"),
                        "rolagem": r.get("rolagem")})
            continue
        if not r.get("virada"):
            continue
        item = r.get("item")
        if r.get("resultado") == "sucesso":
            frase = (f"'{item}' não devia ceder a esses braços — e cedeu: um "
                     "arranque de força além do corpo")
        else:
            frase = (f"'{item}' devia ceder — mas desta vez o corpo falhou")
        out.append({"o_que": frase, "personagem": r.get("personagem"),
                    "item": item, "resultado": r.get("resultado"),
                    "natural_conseguiria": r.get("natural_conseguiria"),
                    "rolagem": r.get("rolagem")})
    return out


_STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
}

_IMAGE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


class _MundoLocal:
    """O `mundo` do `mcp_core` quando o MCP roda DENTRO do server (spec 043).

    Ao contrário do `mcp_server.py` (stdio), que é cliente HTTP porque roda em OUTRO
    processo e precisa respeitar a trava de turno de fora, aqui já se está dentro do
    processo dono da trava — o despacho é o MESMO de `/api/tools/<nome>`, direto,
    sem uma volta pela rede.
    """

    def __init__(self, handler, character_id: str, turno_id: str | None = None):
        self.h = handler
        self.cid = character_id
        # spec 044: o id do turno vem do CONECTOR, e serve para costurar as duas
        # metades do registro (a que o mundo sabe e a que só a Mente sabe). Viaja
        # na query, nunca nos argumentos da capacidade — argumento de capacidade
        # é matéria de julgamento, e isto não é.
        self.turno_id = turno_id

    def contexto(self) -> dict:
        # personagem inexistente NÃO pode derrubar a sessão: `get_context` levanta
        # MotorError, e sem isto a conexão morria sem resposta (o host via um socket
        # fechado, não um erro). Face vazia é resposta honesta: não há o que tentar.
        try:
            ctx = motor.get_context(self.cid)
        except motor.MotorError:
            return {"capacidades": []}
        ctx["capacidades"] = face.build(ctx)
        return ctx

    def propor(self, nome: str, corpo: dict) -> dict:
        return self.h.resolver_proposta(
            nome, {**corpo, "character_id": self.cid, "turno_id": self.turno_id})


class Handler(BaseHTTPRequestHandler):
    server_version = "Loreforge/0.1"

    # ---- helpers ---------------------------------------------------------- #

    def _cors(self) -> None:
        # Localhost/MVP: permissivo, e aceita Origin: null (client file://, RF-10.11).
        origin = self.headers.get("Origin", "*")
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _query(self, parsed) -> dict:
        return {k: v[0] for k, v in parse_qs(parsed.query).items()}

    # ---- verbs ------------------------------------------------------------ #

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            return self._handle_api_get(path, self._query(parsed))
        return self._serve_static(path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/tools/"):
            return self._handle_tool(parsed.path[len("/api/tools/"):])
        if parsed.path == "/api/mcp":
            return self._handle_mcp()
        if parsed.path == "/api/registro":
            return self._handle_registro()
        if parsed.path.startswith("/api/auth/"):
            return self._handle_auth_post(parsed.path, self._query(parsed))
        self._send_json({"error": "rota não encontrada"}, 404)

    # ---- API -------------------------------------------------------------- #

    def _authenticate(self) -> dict | None:
        if not getattr(self.server, "auth_enabled", False):
            return {"sub": "local", "email": "", "name": "local"}
        header = self.headers.get("Authorization")
        if not header or not header.startswith("Bearer "):
            self._send_json({"error": "Unauthorized"}, 401)
            return None
        token = header[len("Bearer "):]
        secret = CONFIG.get("auth", {}).get("secret")
        if not secret:
            self._send_json({"error": "Unauthorized"}, 401)
            return None
        payload = auth.jwt_decode(token, secret)
        if not payload:
            self._send_json({"error": "Unauthorized"}, 401)
            return None
        return payload

    def _authorize_character(self, sub: str, character_id: str) -> bool:
        if not getattr(self.server, "auth_enabled", False):
            return True
        if not character_id:
            self._send_json({"error": "Missing character_id"}, 400)
            return False
        try:
            fm, _ = motor.read_doc(motor.find_character_folder(character_id) / "character.md")
            # FR-006: posse exige owner == sub — um personagem sem dono ainda não
            # foi reivindicado por ninguém, e não é por isso que vira jogável por
            # qualquer JWT válido (era exatamente esse buraco que a spec fechava).
            if fm.get("owner") != sub:
                self._send_json({"error": "Forbidden"}, 403)
                return False
            return True
        except Exception:
            self._send_json({"error": "Character not found"}, 404)
            return False

    def _handle_auth_post(self, path: str, q: dict) -> None:
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) if length else b"{}")
        except json.JSONDecodeError:
            return self._send_json({"error": "JSON inválido"}, 400)
        
        if path == "/api/auth/login":
            client_id = CONFIG.get("auth", {}).get("google_client_id")
            if not client_id:
                return self._send_json({"error": "Auth disabled"}, 400)
            id_token = payload.get("id_token")
            user = auth.verify_google_token(id_token, client_id)
            if not user:
                return self._send_json({"error": "Invalid token"}, 401)
            secret = CONFIG.get("auth", {}).get("secret")
            jwt_token = auth.jwt_encode(user, secret)
            return self._send_json({"jwt": jwt_token, **user})
            
        user = self._authenticate()
        if not user:
            return
            
        if path == "/api/auth/claim-character":
            cid = payload.get("character_id")
            if not cid:
                return self._send_json({"error": "character_id needed"}, 400)
            try:
                with _OWNERSHIP_GUARD:
                    cpath = motor.find_character_folder(cid) / "character.md"
                    fm, md = motor.read_doc(cpath)
                    if fm.get("owner"):
                        return self._send_json({"error": "Already claimed"}, 409)
                    fm["owner"] = user["sub"]
                    motor.write_doc(cpath, fm, md)
                return self._send_json({"ok": True})
            except Exception as e:
                return self._send_json({"error": str(e)}, 500)
                
        if path == "/api/auth/release-character":
            cid = payload.get("character_id")
            if not cid:
                return self._send_json({"error": "character_id needed"}, 400)
            try:
                with _OWNERSHIP_GUARD:
                    cpath = motor.find_character_folder(cid) / "character.md"
                    fm, md = motor.read_doc(cpath)
                    if fm.get("owner") != user["sub"]:
                        return self._send_json({"error": "Forbidden"}, 403)
                    if "owner" in fm:
                        del fm["owner"]
                    motor.write_doc(cpath, fm, md)
                return self._send_json({"ok": True})
            except Exception as e:
                return self._send_json({"error": str(e)}, 500)
                
        self._send_json({"error": "Not found"}, 404)

    def _handle_api_get(self, path: str, q: dict) -> None:
        try:
            if path.startswith("/api/auth/"):
                if path == "/api/auth/me":
                    user = self._authenticate()
                    if user:
                        return self._send_json(user)
                    return
            if path == "/api/characters/mine":
                user = self._authenticate()
                if not user: return
                chars = motor.list_characters()
                mine = [c for c in chars if c.get("owner") == user["sub"]]
                return self._send_json(mine)
            if path == "/api/characters/available":
                user = self._authenticate()
                if not user: return
                chars = motor.list_characters()
                avail = [c for c in chars if not c.get("owner")]
                return self._send_json(avail)
                
            if path not in ("/api/analises", "/api/analise", "/api/spec", "/api/world/health",
                             "/api/characters", "/api/auth/config", "/api/character/image"):
                # All other existing GET routes require authentication
                if not self._authenticate():
                    return
                    
            if path == "/api/auth/config":
                return self._send_json({"google_client_id": CONFIG.get("auth", {}).get("google_client_id")})
                
            # As ANÁLISES geradas por `server/analisa_rodada.py`. Rota de LEITURA
            # pura, servida daqui para caber no mesmo túnel do jogo — a ideia é abrir
            # no celular sem montar servidor à parte.
            if path == "/api/analises":
                base = REPO_ROOT / "analises"
                itens = []
                for d in sorted(base.iterdir() if base.is_dir() else []):
                    md = d / "relatorio.md"
                    if not (d.is_dir() and md.exists()):
                        continue
                    dados = {}
                    try:
                        dados = json.loads((d / "dados.json").read_text("utf-8"))
                    except Exception:  # noqa: BLE001
                        pass
                    itens.append({
                        "nome": d.name,
                        "personagem": dados.get("personagem"),
                        "filtro": dados.get("filtro") or {},
                        "gerado_em": dados.get("gerado_em"),
                        "propostas": (dados.get("macro") or {}).get("propostas"),
                        "sinais": len(dados.get("sinais") or []),
                        "bytes": md.stat().st_size,
                    })
                itens.sort(key=lambda x: x.get("gerado_em") or "", reverse=True)
                return self._send_json(itens)
            if path == "/api/analise":
                nome = self._require(q, "nome")
                base = (REPO_ROOT / "analises").resolve()
                alvo = (base / nome).resolve()
                # travessia de caminho: `nome` vem da query, então confina no diretório
                if base not in alvo.parents or not alvo.is_dir():
                    return self._send_json({"error": "análise não encontrada"}, 404)
                md = alvo / "relatorio.md"
                if not md.exists():
                    return self._send_json({"error": "análise sem relatório"}, 404)
                dados = None
                try:
                    dados = json.loads((alvo / "dados.json").read_text("utf-8"))
                except Exception:  # noqa: BLE001
                    pass
                return self._send_json({"nome": nome, "markdown": md.read_text("utf-8"),
                                        "dados": dados})
            if path == "/api/characters":
                return self._send_json(motor.list_characters())
            if path == "/api/context":
                # spec 043 (FR-007): a face desce JUNTO, no mesmo payload — não em
                # chamada separada. O filtro depende da cena, então a face e o
                # contexto que a gerou têm de ser a mesma foto; separá-los abriria a
                # janela em que a Mente escolhe contra uma cena que não existe mais.
                ctx = motor.get_context(self._require(q, "character_id"))
                ctx["capacidades"] = face.build(ctx)
                return self._send_json(ctx)
            if path == "/api/character":
                return self._send_json(motor.get_character(self._require(q, "character_id")))
            if path == "/api/character/image":
                return self._serve_character_image(self._require(q, "character_id"))
            if path == "/api/inventory":
                return self._send_json(motor.get_inventory(self._require(q, "character_id")))
            if path == "/api/entity":
                return self._send_json(motor.get_entity_detail(self._require(q, "id")))
            if path == "/api/observe":
                obs = motor.observe_entity(
                    self._require(q, "character_id"), self._require(q, "id")
                )
                devlog.log("OBSERVAR (tool consultiva)", {
                    "character_id": q.get("character_id"), "id": q.get("id"),
                })
                return self._send_json(obs)
            if path == "/api/known_routes":
                # o mapa que ele traz na cabeça. Consultivo de client: memória de
                # rota não desce no contexto, mas o que ELE sabe é percepção dele.
                return self._send_json(
                    motor.known_routes(self._require(q, "character_id")))
            if path == "/api/proficiencies":
                # nível por domínio, derivado da memória (spec 029). Consultivo de
                # client: percepção do personagem sobre SI MESMO (Princípio IX,
                # nível 2) — zero LLM, mesmo molde de known_routes.
                return self._send_json(
                    motor.proficiencies_for(self._require(q, "character_id")))
            if path == "/api/spec":
                # spec 043: o contrato da fronteira, GERADO do registro a cada
                # chamada. Substitui o portal: não há cópia curada a dessincronizar.
                return self._send_json(openapi.gerar())
            if path == "/api/world/health":
                problems = motor.validate_world()
                return self._send_json({"ok": not problems, "problems": problems,
                                        "avisos": motor.world_warnings()})
            if path == "/api/consult":
                # spec 040: despacho GENÉRICO das tools de CONSULTA (lane paralela,
                # read-only). Uma consulta nova NÃO toca este endpoint — só se
                # auto-declara no Motor (consult_specs). Devolve PROSA; a escrita
                # segue no Árbitro (Princípio III). Molde de /api/observe.
                tool = self._require(q, "tool")
                spec = motor.consult_specs().get(tool)
                if spec is None:
                    return self._send_json(
                        {"error": f"consulta '{tool}' não existe"}, 404)
                # `q` já vem achatado (uma string por chave, ver _query).
                cid = q.get("character_id")
                args = {k: v for k, v in q.items()
                        if k not in ("tool", "character_id")}
                result = spec.query(cid, args)
                devlog.log("CONSULTA (tool consultiva, spec 040)",
                           {"tool": tool, "character_id": cid, "args": args})
                return self._send_json(result)
            self._send_json({"error": "rota não encontrada"}, 404)
        except motor.MotorError as exc:
            self._send_json({"error": str(exc)}, 404)
        except KeyError as exc:
            self._send_json({"error": f"parâmetro obrigatório ausente: {exc}"}, 400)

    def _handle_mcp(self) -> None:
        """POST /api/mcp — o Model Context Protocol sobre HTTP (spec 043).

        É O CAMINHO DA MENTE. Ela roda no NAVEGADOR, e navegador não abre processo —
        sem transporte HTTP, o MCP simplesmente não a alcança, e o stdio serve só a
        host externo. Isto é o que torna o protocolo o caminho do jogo, não um anexo.

        O HTTP direto (`/api/tools/<nome>`, `/api/spec`, `spec.html`) NÃO é a via da
        Mente: é a bancada do mantenedor — inspecionar params, testar à mão.

        Mesmo núcleo do stdio (`mcp_core`): se as duas faces divergissem, uma Mente
        proporia o que a outra não pode, e o erro seria invisível dos dois lados.
        Aceita UMA mensagem ou um LOTE — o `initialize`+`tools/list` de abertura cabe
        numa ida só, e o navegador agradece.
        """
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) if length else b"{}")
        except json.JSONDecodeError:
            return self._send_json({"error": "JSON inválido"}, 400)
        devlog.requisicao("POST", "/api/mcp", payload, self.server.server_address[1])

        if not isinstance(payload, (dict, list)):
            return self._send_json(
                {"error": "payload precisa ser uma mensagem JSON-RPC ou um lote"}, 400)
        msgs = [m for m in (payload if isinstance(payload, list) else [payload])
                if isinstance(m, dict)]
        # SÓ NOTIFICAÇÕES (sem `id`) não precisam de sessão: não há o que responder,
        # e cobrar `character_id` delas confundia um "não tenho nada a dizer" com um
        # erro de uso.
        if msgs and not any(m.get("id") is not None for m in msgs):
            return self._send_json([] if isinstance(payload, list) else {})
        cid = self._query(urlparse(self.path)).get("character_id")
        for m in msgs:
            if isinstance(m, dict):
                cid = cid or (m.get("params") or {}).get("character_id")
        if not cid:
            return self._send_json(
                {"error": "informe 'character_id' (uma sessão MCP é UM personagem)"},
                400)

        user = self._authenticate()
        if not user:
            return
        if not self._authorize_character(user["sub"], cid):
            return

        turno_id = self._query(urlparse(self.path)).get("turno_id")
        sessao = mcp_core.Sessao(_MundoLocal(self, cid, turno_id))
        saidas = []
        for m in msgs:
            if isinstance(m, dict):
                saidas.extend(mcp_core.tratar(m, sessao))
        self._send_json(saidas if isinstance(payload, list) else
                        (saidas[0] if saidas else {}))

    def _handle_registro(self) -> None:
        """POST /api/registro — a metade do turno que SÓ O CONECTOR sabe.

        Canal PRÓPRIO, fora do caminho da proposta (spec 044). O que sobe numa
        proposta é lido pelo mundo para DECIDIR; engordar aquilo com o racional
        da Mente inflaria o contexto e degradaria TODAS as decisões do turno.

        Não devolve nada do mundo, e nunca falha de um jeito que o conector
        precise tratar: registrar é secundário ao jogo, sempre.
        """
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) if length else b"{}")
        except json.JSONDecodeError:
            return self._send_json({"ok": False}, 204)
        devlog.requisicao("POST", "/api/registro", payload, self.server.server_address[1])
        if isinstance(payload, dict):
            registro_turno.anotar_corpo(payload)
        self._send_json({"ok": True})

    def _handle_tool(self, nome: str) -> None:
        """POST /api/tools/<nome> — a BANCADA DO MANTENEDOR (spec 043).

        Uma rota por capacidade, para inspecionar params e testar à mão sem nenhuma
        Mente no meio (SC-009). NÃO é a via do jogo: quem propõe pelo jogo é a Mente,
        e ela fala MCP (`POST /api/mcp`). Os dois desembocam no MESMO
        `resolver_proposta`, então testar aqui testa o que o jogo faz.
        """
        length = int(self.headers.get("Content-Length", 0))
        try:
            payload = json.loads(self.rfile.read(length) if length else b"{}")
        except json.JSONDecodeError:
            return self._send_json({"error": "JSON inválido"}, 400)
        devlog.requisicao("POST", f"/api/tools/{nome}", payload,
                          self.server.server_address[1])
        if not isinstance(payload, dict):
            return self._send_json({"error": "payload precisa ser um objeto"}, 400)
        out = self.resolver_proposta(nome, payload)
        self._send_json(out, out.pop("_status", 200))

    def resolver_proposta(self, nome: str, payload: dict) -> dict:
        """A PROPOSTA, resolvida — o caminho único dos dois transportes.

        A ordem importa e é o coração da spec:
          1. a capacidade existe? está ativa? é interna?   -> recusa, ZERO LLM
          2. CHECAGEM FORTE contra a cena real (o corpo)    -> recusa, ZERO LLM
          3. só se houver JUÍZO declarado, a capacidade pergunta a nota ao mundo
          4. o Motor valida contra os arquivos e escreve

        CADA CHAMADA É UM TURNO: trava própria, fecho próprio, custo próprio.
        """
        character_id = payload.get("character_id")
        if not character_id:
            return {"ok": False, "erro": "informe 'character_id'", "_status": 400}
            
        user = self._authenticate()
        if not user:
            return {"ok": False, "erro": "Unauthorized", "_status": 401}
        if not self._authorize_character(user["sub"], character_id):
            return {"ok": False, "erro": "Forbidden", "_status": 403}

        # CONSULTA ANTES DE TUDO (spec 040): perguntar não é propor. Sai daqui sem
        # prosa, sem juízo, sem trava de turno e sem tocar arquivo — é leitura. Fica
        # ANTES da exigência de prosa porque a ordem é o que dá o comportamento:
        # depois dela, `consultar_momento` (que não tem param nenhum) seria recusada
        # por não encenar uma ação.
        consulta = motor.consult_specs().get(nome)
        if consulta is not None:
            args = {k: v for k, v in payload.items()
                    if k not in ("character_id", "prosa", "origem", "turno_id")}
            resultado = consulta.query(character_id, args) or {}
            devlog.log("CONSULTA (lane 040, pela face)",
                       {"tool": nome, "character_id": character_id, "args": args})
            # `aconteceu` é o campo que os dois transportes já sabem resumir — a
            # resposta da consulta é a prosa que A MENTE vai interpretar, e ela chega
            # pelo mesmo canal de qualquer outra frase de mundo.
            #
            # O ECO NÃO É RESPOSTA: `consultar_memoria` devolve `{sobre, lembra}`, e
            # `sobre` é a pergunta de volta. Devolver as duas faria a Mente ler a
            # própria pergunta como se fosse fato do mundo. Regra geral e sem tabela
            # por tool: valor de chave que veio nos args é eco, e morre aqui.
            return {"ok": True, "capacidade": nome, "consulta": True,
                    "aconteceu": [v for k, v in resultado.items()
                                  if isinstance(v, str) and k not in args and v.strip()],
                    **resultado}

        # FR-019/FR-035: a prosa é OBRIGATÓRIA e é parâmetro da proposta. Sem ela não
        # há o que julgar (a régua lê COMO se tentou) nem o que narrar.
        prosa = payload.get("prosa")
        if not isinstance(prosa, dict) or not (prosa.get("acao") or "").strip():
            return {"ok": False, "campo": "prosa",
                    "erro": "informe 'prosa.acao' — o que o personagem faz. Sem isso "
                            "não há o que narrar.", "_status": 400}

        spec = motor.registro.get_spec(nome)
        if spec is None or spec.interna:
            # a caneta do mundo não se empresta (Princípio IX, classe 2) — e para quem
            # pergunta, uma capacidade interna simplesmente não existe.
            return {"ok": False, "erro": f"não existe capacidade '{nome}'",
                    "_status": 404}
        if not motor.ativacao.is_active(nome):
            return {"ok": False, "erro": f"'{nome}' não é possível neste mundo",
                    "_status": 409}

        args = {k: v for k, v in payload.items()
                if k not in ("character_id", "prosa", "origem", "turno_id")}
        # FR-005: nota vinda de fora é DESCARTADA em silêncio (ruído de transporte,
        # não erro do jogador). A capacidade pergunta a sua ao mundo — todas as
        # notas de julgamento, se houver mais de uma (spec 046).
        for p, _ in spec.juizo:
            args.pop(p, None)

        if not _claim_turn(character_id):
            return {"ok": False, "_status": 409,
                    "erro": "uma ação já está em andamento para este personagem — "
                            "aguarde o desfecho"}
        try:
            context = motor.get_context(character_id)
            caido = self._refuse_if_down(character_id, context)
            if caido is not None:
                return caido

            devlog.log("PROPOSTA DA MENTE", {"capacidade": nome, "alvos": args,
                                             "character_id": character_id,
                                             "prosa": prosa})
            # ITEM 52.1: a lista viaja com o `ask` deste turno e é lida depois — quem
            # perguntou a nota não precisa saber que alguém coleta a pane.
            juizo_falhas: list = []
            ctx = arbiter.build_ctx(context,
                                    ask=build_ask(CONFIG["arbiter"], juizo_falhas),
                                    prosa=prosa, orienta_laco=False)
            resultado, _done = ctx.execute(nome, args)
            if not resultado.get("ok"):
                # RECUSA ESTRUTURADA: motivo, campo e o que seria válido no lugar —
                # e nenhum modelo foi tocado para produzi-la. O `erro` daqui vira
                # BEAT e matéria de narração, então precisa dizer DE QUEM fala tanto
                # quanto o `failed_effects` do caminho de sucesso.
                if resultado.get("regra"):
                    resultado["erro"] = nomear_sujeito(
                        resultado["regra"], resultado.get("erro") or "",
                        resultado.get("valores") or {})
                devlog.log("PROPOSTA RECUSADA (sem LLM)", resultado)
                registro_turno.anotar_proposta(
                    character_id, payload.get("turno_id"), nome, args, prosa,
                    resultado, aceito=False)
                return {**resultado, "capacidade": nome}
            outcome = arbiter.finalize_turn(ctx, acao=prosa.get("acao") or "")
            outcome["capacidade"] = nome
            outcome["context"] = motor.get_context(character_id)
            outcome["failed_effects"] = inworld_failures(
                outcome.get("tool_rejections") or [])
            outcome["aconteceu"] = inworld_effects(outcome)
            outcome["viradas"] = fate_twists(outcome.get("rolls") or [])
            # A PANE DO JUÍZO SOBE COM O TURNO (item 52.1). NÃO é `failed_effects`:
            # aquele canal é matéria de NARRAÇÃO, e "o mundo não conseguiu julgar" não
            # é fato in-world — narrá-lo poria vocabulário de máquina na boca do
            # personagem (Princípio V). Sai por um campo próprio, que o conector
            # transforma em recado de SISTEMA e anota no registro do turno.
            if juizo_falhas:
                outcome["juizo_indisponivel"] = {
                    "quantas": len(juizo_falhas),
                    "porque": juizo_falhas[0][:200],
                }
            # spec 044: o CAMINHO ÚNICO é onde o registro do turno nasce — um
            # lugar só, nunca espalhado por capacidade. Quem esquecesse sumiria
            # do histórico em silêncio, que é o pior modo de perder um dado.
            registro_turno.anotar_proposta(
                character_id, payload.get("turno_id"), nome, args, prosa, outcome,
                aceito=True)
            return outcome
        except motor.MotorError as exc:
            return {"ok": False, "erro": str(exc), "_status": 404}
        finally:
            _release_turn(character_id)

    def _refuse_if_down(self, character_id: str, context: dict) -> dict | None:
        """Recusa in-world de agir por quem está caído, ou None se ele pode agir.

        O client normalmente nem oferece o sussurro a um caído (cortesia), mas a
        regra é esta: nenhuma ação em nome de quem caiu chega ao Árbitro ou ao
        Motor, venha de onde vier. Sem consultar modelo, sem escrever no mundo.
        """
        status = (context.get("self") or {}).get("status") or {}
        conds = status.get("conditions") or []
        # morto vence incapacitado: quem morreu carried_item_ids as duas condições, e a
        # recusa precisa dizer a verdade mais forte
        estado = (motor.DEAD if motor.DEAD in conds
                  else next((c for c in conds if c in motor.DOWN_CONDITIONS), None))
        if estado is None:
            return None
        devlog.log("AÇÃO DE PERSONAGEM CAÍDO — recusada sem Árbitro",
                   {"character_id": character_id, "estado": estado})
        hint = ("Está morto — não há mais nada que ele faça."
                if estado == motor.DEAD else
                "Está caído, sem forças para agir — só outra pessoa pode tirá-lo daí.")
        rejected = [{"acao": "qualquer", "regra": "atacante_caido",
                     "valores": {"personagem": character_id, "estado": estado},
                     "why": motor._WHY_BY_REGRA["atacante_caido"]}]
        return {
            "narrative_hint": hint,
            "applied": [], "rejected": rejected,
            "failed_effects": inworld_failures(rejected),
            "item_transfers": [], "equip_ops": [], "lock_ops": [],
            "attack_ops": [], "carry_ops": [], "trade_ops": [], "wares": [],
            "informes": [], "persuade_ops": [], "viradas": [],
            "context": context,
        }

    def _require(self, q: dict, key: str) -> str:
        if key not in q:
            raise KeyError(key)
        return q[key]

    # ---- estáticos (client) ---------------------------------------------- #

    def _serve_character_image(self, character_id: str) -> None:
        # O RETRATO fica JUNTO do personagem (`retrato.<ext>` na própria pasta),
        # não referenciado por URL externa: link de terceiro expira (já expirou
        # uma vez nesta mesma spec) e o Motor não tem como garantir que segue
        # no ar. Sem auth (ver `_handle_api_get`): é só uma imagem, e uma tag
        # `<img>` de navegador não manda `Authorization` de qualquer forma.
        try:
            folder = motor.find_character_folder(character_id)
        except motor.MotorError:
            return self._send_json({"error": "personagem não encontrado"}, 404)
        for nome, tipo in _IMAGE_TYPES.items():
            alvo = folder / f"retrato{nome}"
            if alvo.exists():
                dados = alvo.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", tipo)
                self.send_header("Content-Length", str(len(dados)))
                self.send_header("Cache-Control", "public, max-age=3600")
                self._cors()
                self.end_headers()
                self.wfile.write(dados)
                return
        self._send_json({"error": "sem retrato"}, 404)

    def _serve_static(self, path: str) -> None:
        rel = "index.html" if path in ("", "/") else path.lstrip("/")
        target = (CLIENT_DIR / rel).resolve()
        inside = target == CLIENT_DIR or CLIENT_DIR in target.parents
        if not inside or not target.exists() or target.is_dir():
            self._send_json({"error": "arquivo não encontrado"}, 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", _STATIC_TYPES.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(data)))
        # sem cache: o client muda a cada sessão de trabalho, e um `app.js` velho
        # servido de cache já custou tempo de depuração perseguindo um defeito
        # que não existia mais no disco.
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self._cors()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args) -> None:  # silêncio moderado
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Loreforge server (local).")
    parser.add_argument("--port", type=int, default=8777)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    
    path = SERVER_DIR / "config.server.json"
    doc = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8")) or {}
        except Exception:
            pass
    auth_conf = doc.get("auth") or {}
    if auth_conf.get("google_client_id") and not auth_conf.get("secret"):
        auth_conf["secret"] = os.urandom(32).hex()
        doc["auth"] = auth_conf
        try:
            path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
        except Exception:
            pass
        CONFIG["auth"] = auth_conf
    auth_enabled = bool(auth_conf.get("google_client_id") or auth_conf.get("secret"))
    httpd.auth_enabled = auth_enabled

    url = f"http://localhost:{args.port}"
    arb = CONFIG["arbiter"]
    print(f"Loreforge v{__version__} no ar. Abra no navegador:  {url}", flush=True)
    print(f"(mundo: {motor.WORLD_DIR}) — Ctrl+C para parar.", flush=True)
    print(f"(Árbitro: {arb['runtime']} · modelo {arb['model']} · "
          f"tools {arb.get('tool_calling', 'auto')})", flush=True)

    # ID DUPLICADO vem PRIMEIRO e SEPARADO. Já vinha misturado ao relatório de
    # schema, sob o rótulo "(ignorados no jogo)" — que é falso: duplicata não é
    # ignorada, é JOGADA. Em 2026-08-20 eram 1002 linhas rolando na subida, o que
    # garante que ninguém leia. Agora conta por ID (12, não 1002) e diz o que fazer.
    dups = motor.duplicate_ids()
    if dups:
        print(f"\n⛔ {len(dups)} id(s) DUPLICADO(S) no mundo — o mesmo id em duas "
              "pastas. Isto NÃO é ignorado: é jogado, e o Motor recusa carregar "
              "personagem assim.", flush=True)
        for d in dups[:10]:
            print(f"   - {d['id']}: {', '.join(d['paths'])}", flush=True)
        if len(dups) > 10:
            print(f"   … e mais {len(dups) - 10}.", flush=True)
        print("   → python3 loreforge-server/sanea_duplicatas.py\n", flush=True)

    problems = [p for p in motor.validate_world()
                if not any(e.startswith("id duplicado") for e in p["errors"])]
    if problems:
        print(f"⚠ {len(problems)} arquivo(s) do mundo com schema inválido "
              "(ignorados no jogo):", flush=True)
        for p in problems:
            print(f"   - {p['path']}: {'; '.join(p['errors'])}", flush=True)
    elif not dups:
        print("(mundo validado: todos os arquivos ok)", flush=True)
    warns = motor.world_warnings()
    for w in warns:
        print(f"⚠ aviso: {w['path']}: {w['aviso']}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nencerrando.", flush=True)
        httpd.server_close()


if __name__ == "__main__":
    main()
