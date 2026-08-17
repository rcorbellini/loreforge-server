"""Cliente de modelo server-side (O Árbitro) — Ollama via stdlib.

Sem dependências: usa urllib. Fala com a API /api/chat do Ollama. O client-side
(A Mente) tem seu próprio cliente em JavaScript; este módulo é só do server.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import version

# Alguns hosts atrás de proteção anti-bot (Cloudflare) recusam requisições sem
# User-Agent com 403 "error code: 1010" — o padrão do urllib
# ("Python-urllib/3.x") já basta pra ser tratado como bot. Achado testando o
# Zen da OpenCode (endpoint compatível com o runtime "openrouter", spec do
# Big Pickle) — a chave e o payload estavam certos, só faltava isto. Aplicado
# a TODO request deste módulo, não só ao caso que o revelou.
_USER_AGENT = f"loreforge-server/{version.__version__} (+https://github.com/rcorbellini/loreforge)"


class LLMError(Exception):
    """Falha ao falar com o modelo (conexão, timeout, resposta inesperada)."""


def ollama_chat(
    endpoint: str,
    model: str,
    system: str,
    user: str,
    *,
    force_json: bool = True,
    temperature: float = 0.2,
    timeout: int = 180,
) -> str:
    """Chama /api/chat do Ollama e retorna o conteúdo textual da resposta."""
    url = endpoint.rstrip("/") + "/api/chat"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "options": {"temperature": temperature},
    }
    if force_json:
        payload["format"] = "json"

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise LLMError(
            f"não foi possível falar com o modelo em {endpoint} "
            f"(modelo '{model}'): {getattr(exc, 'reason', exc)}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"resposta do modelo não é JSON válido: {exc}") from exc

    message = obj.get("message") or {}
    content = message.get("content")
    if content is None:
        raise LLMError("resposta do modelo sem 'message.content'.")
    return content


def make_ollama_fn(endpoint: str, model: str, *, temperature: float = 0.2):
    """Devolve um model_fn(system, user) -> str preso a um endpoint/modelo."""
    def _fn(system: str, user: str) -> str:
        return ollama_chat(endpoint, model, system, user, temperature=temperature)
    return _fn


# --------------------------------------------------------------------------- #
# Claude remoto (Anthropic Messages API) — opcional para O Árbitro
# --------------------------------------------------------------------------- #
# A chave é do próprio server (fica no config.server.json, gitignored). Nada aqui
# tem relação com a chave d'A Mente, que vive só no navegador do player.

def anthropic_chat(
    api_key: str,
    model: str,
    system: str,
    user: str,
    *,
    endpoint: str = "https://api.anthropic.com",
    force_json: bool = True,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    anthropic_version: str = "2023-06-01",
    timeout: int = 180,
) -> str:
    """Chama a Messages API da Anthropic e retorna o texto da resposta.

    Com force_json, usa o prefill de assistant "{" para forçar início de JSON e
    recompõe o "{" na volta (mesmo truque do client).
    """
    url = endpoint.rstrip("/") + "/v1/messages"
    messages = [{"role": "user", "content": user}]
    if force_json:
        messages.append({"role": "assistant", "content": "{"})
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": min(temperature, 1.0),
        "system": system,
        "messages": messages,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": anthropic_version,
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = (body.get("error") or {}).get("message") or ""
        except Exception:  # noqa: BLE001 — mensagem de erro é best-effort
            pass
        raise LLMError(
            f"a Anthropic respondeu com erro ({exc.code})"
            + (f": {detail}" if detail else ".")
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(
            f"não foi possível falar com a Anthropic: {getattr(exc, 'reason', exc)}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"resposta da Anthropic não é JSON válido: {exc}") from exc

    blocks = obj.get("content") or []
    text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
    if not text:
        raise LLMError("resposta da Anthropic sem conteúdo de texto.")
    if force_json:
        text = "{" + text  # recompõe o prefill
    return text


def make_anthropic_fn(
    api_key: str,
    model: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    endpoint: str = "https://api.anthropic.com",
    anthropic_version: str = "2023-06-01",
):
    """Devolve um model_fn(system, user) -> str preso a uma chave/modelo Anthropic."""
    def _fn(system: str, user: str) -> str:
        return anthropic_chat(
            api_key, model, system, user,
            endpoint=endpoint, temperature=temperature, max_tokens=max_tokens,
            anthropic_version=anthropic_version,
        )
    return _fn


# --------------------------------------------------------------------------- #
# OpenRouter (API compatível com OpenAI) — opcional para O Árbitro
# --------------------------------------------------------------------------- #
# A chave é do próprio server (config.server.json, gitignored), como no runtime
# Anthropic. Sem response_format: os prompts já exigem JSON e o parse do Árbitro
# é leniente (mesma escolha do client em mente.js).

def openrouter_chat(
    api_key: str,
    model: str,
    system: str,
    user: str,
    *,
    endpoint: str = "https://openrouter.ai/api/v1",
    temperature: float = 0.2,
    max_tokens: int = 2048,
    timeout: int = 180,
) -> str:
    """Chama /chat/completions do OpenRouter e retorna o texto da resposta."""
    url = endpoint.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Title": "Loreforge",
            "User-Agent": _USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            obj = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            body = json.loads(exc.read().decode("utf-8"))
            detail = (body.get("error") or {}).get("message") or ""
        except Exception:  # noqa: BLE001 — mensagem de erro é best-effort
            pass
        raise LLMError(
            f"o OpenRouter respondeu com erro ({exc.code})"
            + (f": {detail}" if detail else ".")
        ) from exc
    except urllib.error.URLError as exc:
        raise LLMError(
            f"não foi possível falar com o OpenRouter: {getattr(exc, 'reason', exc)}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LLMError(f"resposta do OpenRouter não é JSON válido: {exc}") from exc

    choices = obj.get("choices") or []
    message = (choices[0].get("message") or {}) if choices else {}
    content = message.get("content")
    if not content:
        raise LLMError("resposta do OpenRouter sem conteúdo de texto.")
    return content


def make_openrouter_fn(
    api_key: str,
    model: str,
    *,
    temperature: float = 0.2,
    max_tokens: int = 2048,
    endpoint: str = "https://openrouter.ai/api/v1",
):
    """Devolve um model_fn(system, user) -> str preso a uma chave/modelo OpenRouter."""
    def _fn(system: str, user: str) -> str:
        return openrouter_chat(
            api_key, model, system, user,
            endpoint=endpoint, temperature=temperature, max_tokens=max_tokens,
        )
    return _fn

