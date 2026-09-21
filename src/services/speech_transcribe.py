"""Server-side speech transcription (fallback for embedded browsers)."""

from __future__ import annotations

from typing import Optional

import httpx

from src.auth import LLM_CONFIG
from src.services.llm_client import refresh_llm_config_from_db
from src.web_common import is_masked_secret


def _resolve_openai_api_key() -> Optional[str]:
    refresh_llm_config_from_db()
    key = (LLM_CONFIG.get("api_key") or "").strip()
    if not key or is_masked_secret(key):
        return None
    provider = (LLM_CONFIG.get("provider") or "").strip().lower()
    if provider == "openai":
        return key
    # 其他提供商若配置了 sk- 开头密钥，也可用于 Whisper
    if key.startswith("sk-"):
        return key
    return None


async def transcribe_audio_bytes(
    data: bytes,
    *,
    filename: str = "speech.webm",
    content_type: str = "audio/webm",
    language: str = "zh",
) -> str:
    """Transcribe audio via OpenAI Whisper API."""
    api_key = _resolve_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "服务端语音识别需要 OpenAI API Key。"
            "请在管理后台 LLM 配置中填写，或使用 Chrome 浏览器进行本地语音输入。"
        )

    if not data:
        raise RuntimeError("录音为空，请重新录制")

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, data, content_type)},
            data={"model": "whisper-1", "language": language},
        )

    if response.status_code != 200:
        detail = response.text[:300]
        raise RuntimeError(f"语音识别失败 ({response.status_code}): {detail}")

    payload = response.json()
    text = (payload.get("text") or "").strip()
    if not text:
        raise RuntimeError("未识别到有效语音内容")
    return text
