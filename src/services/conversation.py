"""In-memory conversation state and multi-turn LLM helpers."""

from __future__ import annotations

from typing import Dict, List, Tuple

from src.auth import LLM_CONFIG

from src.services.llm_client import (
    call_anthropic_api,
    call_gemini_api,
    call_ollama_api,
    call_openai_api,
)

CONVERSATION_HISTORY: Dict[str, List[Dict]] = {}


def conversation_storage_key(username: str, conversation_id: str) -> str:
    safe_user = (username or "anonymous").strip() or "anonymous"
    safe_id = (conversation_id or "default").strip() or "default"
    return f"{safe_user}:{safe_id}"


def get_conversation_history(username: str, conversation_id: str) -> List[Dict]:
    return CONVERSATION_HISTORY.get(conversation_storage_key(username, conversation_id), [])


def set_conversation_history(username: str, conversation_id: str, history: List[Dict]) -> None:
    CONVERSATION_HISTORY[conversation_storage_key(username, conversation_id)] = history


def clear_conversation_history(username: str = None, conversation_id: str = None) -> None:
    if username is None and conversation_id is None:
        CONVERSATION_HISTORY.clear()
        return
    if username and conversation_id:
        CONVERSATION_HISTORY.pop(conversation_storage_key(username, conversation_id), None)
        return
    if username:
        prefix = f"{username}:"
        for key in list(CONVERSATION_HISTORY.keys()):
            if key.startswith(prefix):
                del CONVERSATION_HISTORY[key]


async def call_openai_api_conversation(
    prompt: str, history: List[Dict], api_key: str, model: str, endpoint: str
) -> str:
    import httpx

    if not api_key:
        return "请先在系统设置中配置OpenAI API密钥"

    url = endpoint or "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    messages = [{"role": "system", "content": "你是一位专业的游戏数据分析顾问。"}]
    for item in history[-5:]:
        messages.append({"role": item["role"], "content": item["content"]})
    messages.append({"role": "user", "content": prompt})
    data = {"model": model, "messages": messages, "max_tokens": 1000}

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


async def call_ollama_api_conversation(
    prompt: str, history: List[Dict], model: str, endpoint: str
) -> str:
    import httpx

    url = endpoint or "http://localhost:11434/api/generate"
    context = "\n".join([f"{item['role']}: {item['content']}" for item in history[-5:]])
    full_prompt = f"{context}\n\n用户: {prompt}\n\n请作为游戏数据分析顾问回答:"
    data = {"model": model, "prompt": full_prompt, "stream": False}

    async with httpx.AsyncClient(timeout=httpx.Timeout(120.0)) as client:
        response = await client.post(url, json=data)
        response.raise_for_status()
        return response.json().get("response", "")


async def call_anthropic_api_conversation(prompt: str, api_key: str, model: str) -> str:
    import httpx

    if not api_key:
        return "请先在系统设置中配置Anthropic API密钥"

    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    data = {"model": model, "messages": [{"role": "user", "content": prompt}], "max_tokens": 1000}

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        response = await client.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.json()["content"][0]["text"]


async def call_gemini_api_conversation(prompt: str, api_key: str, model: str) -> str:
    import httpx

    if not api_key:
        return "请先在系统设置中配置Google Gemini API密钥"

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 1000},
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        response = await client.post(url, headers={"Content-Type": "application/json"}, json=data)
        response.raise_for_status()
        return response.json()["candidates"][0]["content"]["parts"][0]["text"]


async def generate_conversation_reply(
    context_prompt: str, username: str, conversation_id: str
) -> str:
    history = get_conversation_history(username, conversation_id)
    provider = LLM_CONFIG["provider"]
    model = LLM_CONFIG["model"]
    api_key = LLM_CONFIG.get("api_key", "")
    endpoint = LLM_CONFIG.get("endpoint", "")

    if provider == "openai":
        return await call_openai_api_conversation(context_prompt, history, api_key, model, endpoint)
    if provider == "ollama":
        return await call_ollama_api_conversation(context_prompt, history, model, endpoint)
    if provider == "anthropic":
        return await call_anthropic_api_conversation(context_prompt, api_key, model)
    if provider == "gemini":
        return await call_gemini_api_conversation(context_prompt, api_key, model)
    return "当前未配置LLM，无法进行对话。请在系统设置中配置LLM。"
