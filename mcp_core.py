"""O NÚCLEO do Model Context Protocol — comum aos dois transportes (spec 043).

O MCP é o caminho da MENTE: é por ele que a inteligência do personagem enxerga o que
pode tentar e propõe. O HTTP direto (`/api/tools/<nome>`, `/api/spec`, `spec.html`) é
a BANCADA DO MANTENEDOR — inspecionar params, testar à mão —, não a via do jogo.

Dois transportes, um núcleo:
  - `POST /api/mcp` (em `app.py`): a Mente roda no NAVEGADOR, e navegador não abre
    processo. Sem transporte HTTP, a Mente simplesmente não fala MCP.
  - stdio (em `mcp_server.py`): para um host MCP externo (Claude Desktop, outro
    agente) que fala o transporte clássico.

Este módulo não sabe de HTTP nem de stdio: recebe um `mundo` com dois métodos
(`contexto()` e `propor(nome, corpo)`) e responde mensagens JSON-RPC. Quem injeta o
`mundo` é que decide se ele lê o Motor direto (in-process) ou por rede.
"""
from __future__ import annotations

import json
import face

PROTOCOL = "2025-06-18"


def input_schema(cap: dict) -> dict:
    """O schema de uma capacidade, no formato que um host MCP entende.

    Os alvos viram `enum` — só o que existe NAQUELA cena.

    **CORREÇÃO POR MEDIÇÃO (spec 060, 2026-08-31).** Aqui se afirmava que "o schema é
    IMPOSTO pelo runtime de tool-calling, em vez de sugerido no prompt". Isso é
    **FALSO** para Ollama + `llama3.1:8b`: o runtime renderiza o enum como TEXTO no
    template do modelo, e um id fora dele saiu em **4 de 5** chamadas
    (`tests/exploracao/sondagem_enum_alvo_dificil.py`). A premissa estava no ar desde a
    spec 043 e alimentou o diagnóstico do item 52.5.

    O que o schema DE FATO entrega, e continua valendo: a FORMA (tipo do campo, campo
    obrigatório presente) — as falhas de `lista onde se espera string` e `campo omitido`
    que a 043 mediu. O que ele NÃO entrega é o CONTEÚDO do enum.

    Quem contém de verdade é a revalidação do Motor, e é por isso que ela nunca pôde ser
    dispensada. E é por isso que a spec 060 tirou o enum de id do que desce à Mente: ele
    custava 35% do bloco de capacidades, paralisava no alvo ambíguo e fazia o modelo
    SUBSTITUIR em silêncio no alvo ausente — sem impor nada em troca.

    `prosa` é OBRIGATÓRIA (FR-019/FR-035): a régua lê COMO se tentou, e sem ela não
    há o que narrar. Numa chamada de tool não existe campo irmão onde pendurá-la.

    EXCEÇÃO — a CONSULTA (`cap["consulta"]`): perguntar não é tentar. Não há régua
    que leia como se perguntou nem desfecho a narrar, então exigir `prosa` de
    `consultar_momento` seria cobrar a encenação de um pensamento. O schema fica
    só com os params declarados.
    """
    # O SCHEMA É COMPLETO — todo parâmetro, todo candidato. Quem recorta para a LLM
    # é o conector (o BFF): recorte é presentação, e esta é a API.
    #
    # Aqui havia três laços (`alvos`/`por_nome`/`exige`) e uma frase de dica no lugar
    # do enum cortado. O corte mudou de lado; a dica foi junto.
    props: dict = {}
    for nome, p in (cap.get("params") or {}).items():
        # PARÂMETRO DE REFERÊNCIA SEM NADA A APONTAR NÃO ENTRA NO SCHEMA.
        #
        # Oferecê-lo sem opções é pior que omiti-lo: ele aparece como campo válido, e
        # o modelo preenche com o que inventar. Medido — `intention_id` sem intenção
        # ativa recebeu `tincture_prep` e `elixir_cicatrizacao`, e as duas tentativas
        # de firmar compromisso morreram em "não é uma intenção ativa".
        if "candidatos" in p and not p["candidatos"]:
            continue
        campo = {"type": p.get("forma") or "string"}
        cands = [c["id"] for c in (p.get("candidatos") or [])]
        if cands:
            if campo["type"] == "array":
                campo["items"] = {"type": "string", "enum": cands}
            else:
                campo["enum"] = cands
        else:
            campo["description"] = ("texto livre — escreva você; não há lista de "
                                    "opções")
        props[nome] = campo
    if cap.get("consulta"):
        return {"type": "object", "properties": props,
                "required": list(cap.get("exige") or [])}
    props["prosa"] = {
        "type": "object",
        "description": ("O que o personagem FAZ e DIZ ao tentar isto, in-world. "
                        "Descreva a TENTATIVA — o desfecho quem decide é o mundo."),
        "properties": {
            "acao": {"type": "string", "description": "o que ele faz. Obrigatório."},
            "fala": {"type": "string", "description": "o que diz em voz alta, se disser"},
        },
        "required": ["acao"],
    }
    return {"type": "object", "properties": props,
            "required": list(cap.get("exige") or []) + ["prosa"]}


class Sessao:
    """Uma sessão = UM personagem. Um host não passa "de quem é o turno" em
    `tools/list`, e não precisa: uma Mente é um personagem, que é o modelo do
    projeto desde sempre."""

    def __init__(self, mundo):
        self.mundo = mundo
        self._assinatura = None

    def capacidades(self) -> list:
        return (self.mundo.contexto() or {}).get("capacidades") or []

    def tools(self) -> list:
        caps = self.capacidades()
        self._assinatura = self._assinar(caps)
        out = []
        for c in caps:
            tool = {"name": c["nome"],
                    "description": c.get("descricao") or "",
                    "inputSchema": input_schema(c)}
            # QUAIS PARÂMETROS SÃO REFERÊNCIA (2026-09-11). Com o enum de entidade
            # fora do schema, nada mais distinguia `ask_directions.quem` — que aponta
            # para alguém da cena — de `set_intention.content`, que é prosa livre. Os
            # dois ficavam "string sem enum", e um cliente que tentasse resolver os
            # dois transformaria o teor de um compromisso num id.
            #
            # A distinção é do MUNDO (é ele quem declara o parâmetro), então desce
            # dele, explícita. Vai em `annotations` porque é metadado da tool, não
            # forma do argumento — o mesmo lugar de `readOnlyHint`.
            # OS NOMES DOS CANDIDATOS, para quem for resolver por nome (spec 060) e
            # para quem for mostrar na tela. É DADO, não recorte: o schema acima já
            # traz os ids; aqui vai como cada um se chama na cena.
            nomes = {p: {x["id"]: x["nome"] for x in (v.get("candidatos") or [])}
                     for p, v in (c.get("params") or {}).items()
                     if v.get("candidatos")}
            if nomes:
                tool["annotations"] = {"byName": nomes}
            if c.get("consulta"):
                # `readOnlyHint` é o campo do PRÓPRIO MCP para "esta tool não muda
                # nada". Marcar aqui, e não inventar chave nossa, é o que faz um host
                # externo (Claude Desktop) e o nosso conector concordarem sem
                # combinação prévia — e é por esta marca que o conector sabe que
                # pode consultar e CONTINUAR pensando, em vez de encerrar a vez
                # achando que propôs algo ao mundo.
                #
                # MESCLA, não substitui: `byName` pode já estar aqui, e uma consulta
                # com alvo de cena (`examine`, `recognize`) precisa das duas marcas.
                tool.setdefault("annotations", {})["readOnlyHint"] = True
            out.append(tool)
        return out

    @staticmethod
    def _assinar(caps: list) -> str:
        """O que precisa mudar para o host relistar: nomes e alvos, não a prosa.

        `por_nome` ENTRA (2026-09-11). Quando os enums de entidade saíram do schema
        e foram para `annotations.byName`, quem mudava com a cena passou a ser ele:
        assinar só `alvos` faria a face parar de "mudar" quando alguém entra ou sai
        da taverna, e o host nunca relistaria. Silencioso, e do pior tipo — a Mente
        seguiria propondo sobre quem já foi embora.
        """
        return json.dumps([[c["nome"], c.get("alvos"), c.get("por_nome")]
                           for c in caps], sort_keys=True)

    def mudou(self) -> bool:
        """A cena mudou desde a última listagem?

        LIMITAÇÃO HONESTA: a checagem é preguiçosa, então só percebe o que a PRÓPRIA
        sessão causou — uma thread de polling seria relógio de fundo, que o Princípio
        VII proíbe. Mudança de outro personagem aparece no próximo `tools/list`, que
        sempre lê o mundo fresco. A face é foto, não contrato.
        """
        return self._assinatura is not None \
            and self._assinar(self.capacidades()) != self._assinatura


def _texto(conteudo: str, erro: bool = False) -> dict:
    return {"content": [{"type": "text", "text": conteudo}], "isError": erro}


def _recusa_estruturada(out: dict) -> dict | None:
    """O que a recusa tem de CORRIGÍVEL, como DADO — nunca como frase pronta.

    Aqui houve uma função que montava o texto ("Para 'de_quem', só valem: …") e o
    colava na mensagem de erro. Era presentação dentro da API, e deu no que dá:
    escrita preferindo o `id`, ela mandou "bram-pescador, coelho-do-cais" ao modelo,
    desfazendo pela porta dos fundos o que a spec 060 tirou da face.

    A API devolve o FATO — qual campo, quais valores, com id e nome. Quem escreve a
    frase para A LLM é o conector, que é o BFF dela e sabe contra qual modelo está
    falando. Um host MCP de terceiro recebe o mesmo dado e escreve a frase dele.

    `None` quando não há o que corrigir: a recusa de MÉRITO ("isso já é verdade
    agora") não tem campo nem lista, e inventar um convidaria o retry de algo que
    não é para ser re-tentado.
    """
    campo, validos = out.get("campo"), out.get("validos")
    if not campo and not validos:
        return None
    fora: dict = {}
    if campo:
        fora["campo"] = campo
    if validos:
        fora["validos"] = [v if isinstance(v, dict) else {"id": str(v), "nome": str(v)}
                           for v in validos]
    return fora


def _frase(x) -> str:
    """Uma linha de mundo, venha ela como texto ou como registro estruturado.

    `aconteceu` traz strings (as frases in-world do Motor), mas `failed_effects` pode
    trazer o par {texto, valores} da negação física (spec 004) — e um `join` cego
    sobre isso estoura. Aqui só o TEXTO sai; `valores` é dado de sistema e morre.
    """
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        for chave in ("texto", "why", "frase", "erro", "resumo"):
            if x.get(chave):
                return str(x[chave])
    return ""


def resumo(out: dict) -> str:
    """O que voltou, em linguagem de mundo — nunca a nota, nunca a rolagem."""
    cru = list(out.get("aconteceu") or []) + list(out.get("failed_effects") or [])
    partes = [f for f in (_frase(x) for x in cru) if f]
    if not partes and out.get("narrative_hint"):
        partes.append(str(out["narrative_hint"]))
    return "\n".join(partes) or "nada mudou."


def tratar(msg: dict, sessao: Sessao) -> list:
    """Trata UMA mensagem JSON-RPC. Devolve a lista de mensagens a emitir (a
    resposta, mais a notificação de face mudada quando for o caso)."""
    rid, metodo = msg.get("id"), msg.get("method")

    def resposta(result):
        return [{"jsonrpc": "2.0", "id": rid, "result": result}]

    if metodo == "initialize":
        return resposta({
            "protocolVersion": PROTOCOL,
            # a face MUDA a cada cena; o host precisa saber que pode ser avisado
            "capabilities": {"tools": {"listChanged": True}},
            "serverInfo": {"name": "loreforge", "version": "2.5.0"},
        })
    if metodo == "notifications/initialized":
        return []                       # notificação: não se responde
    if metodo == "tools/list":
        return resposta({"tools": sessao.tools()})
    if metodo == "tools/call":
        params = msg.get("params") or {}
        nome = params.get("name") or ""
        args = dict(params.get("arguments") or {})
        out = sessao.mundo.propor(nome, args) or {}
        if out.get("ok") is False or out.get("error"):
            # RECUSA IN-WORLD é resposta legítima do mundo, não defeito de
            # transporte: volta como resultado de tool com isError, nunca como erro
            # de protocolo. O host mostra o motivo à Mente, que escolhe outra coisa.
            # A FRASE IN-WORLD no `content` (é ela que o jogador lê), e o que há de
            # CORRIGÍVEL num canal à parte — dado, não texto. Mesmo padrão de
            # `_narrativa`/`_sistema`: o que é material de apresentação não se
            # mistura com o que é fato.
            _rec = _recusa_estruturada(out)
            msgs = resposta(_texto(out.get("erro") or out.get("error")
                                   or "o mundo recusou.", erro=True))
            if _rec:
                for _m in msgs:
                    if isinstance(_m, dict) and isinstance(_m.get("result"), dict):
                        _m["result"]["_recusa"] = _rec
        else:
            msgs = resposta(_texto(resumo(out)))
            # MATERIAL DE NARRAÇÃO para o client — e SÓ ele. `out` inteiro traz o
            # `context` do mundo (todos os presentes, memórias, físico de terceiros):
            # num resultado de tool isso vira ENTRADA DO MODELO, o que é desastre de
            # tokens e porta aberta para metagaming (Princípio IX). O client já relê o
            # contexto por conta própria; aqui vai só o que A Mente precisa para tecer.
            # ITEM 52.3 — `lido`, `wares` e `falas` FALTAVAM AQUI, e essa ausência é a
            # explicação de metade do que a Nerissa fez em 11 horas.
            #
            # São canais de MATERIAL (`arbiter._MATERIAL_CH`): o que uma capacidade
            # CONSULTIVA traz para A Mente tecer. Dos cinco, só `reconhecimentos` e
            # `informes` eram encaminhados — `lido` (o texto que o `examine` leu),
            # `wares` (o que o vendedor tem) e `falas` (o que o informante disse do
            # caminho) morriam no servidor.
            #
            # O efeito medido: `examine` 90x, `ask_directions` 83x, `ask_wares` 24x —
            # 197 dos 391 turnos dela — em capacidades cujo RESULTADO ela nunca
            # recebia. Ela olhava a mesma bolsa de ervas 40 vezes porque olhar não lhe
            # devolvia nada. Não era falta de rastro na memória: era a resposta não
            # chegando a quem perguntou.
            msgs[0]["result"]["_narrativa"] = {
                k: out.get(k) for k in
                ("narrative_hint", "aconteceu", "failed_effects", "viradas",
                 "informes", "reconhecimentos", "lido", "wares", "falas",
                 "capacidade")
                if out.get(k)
            }
            # FORA do `_narrativa`, de propósito (item 52.1): a pane do juízo não é
            # matéria de narração — é condição de SISTEMA. Se entrasse ali, A Mente a
            # teceria como fato do mundo e o jogador leria vocabulário de máquina.
            if out.get("juizo_indisponivel"):
                msgs[0]["result"]["_sistema"] = {
                    "juizo_indisponivel": out["juizo_indisponivel"]}
        if sessao.mudou():
            msgs.append({"jsonrpc": "2.0",
                         "method": "notifications/tools/list_changed"})
        return msgs
    if rid is not None:
        return [{"jsonrpc": "2.0", "id": rid,
                 "error": {"code": -32601, "message": f"método não suportado: {metodo}"}}]
    return []
