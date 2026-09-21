"""LLM provider configuration routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from src.auth import LLM_CONFIG, LLM_PROVIDERS
from src.database import LLMConfigRepository, OperationLogRepository
from src.web_common import get_current_user, is_masked_secret, mask_config_secrets, mask_secret
from src.services.llm_client import (
    call_anthropic_api,
    call_gemini_api,
    call_ollama_api,
    call_openai_api,
    get_local_ollama_models,
)

router = APIRouter(tags=["llm"])

@router.get("/api/llm/providers")
async def get_llm_providers(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    providers = []
    ollama_models = await get_local_ollama_models()
    
    for key, value in LLM_PROVIDERS.items():
        provider_data = {
            "id": key,
            "name": value["name"],
            "models": value["models"],
            "default_model": value["default_model"],
            "color": value["color"]
        }
        
        if key == "ollama" and ollama_models:
            provider_data["models"] = ollama_models
            provider_data["default_model"] = ollama_models[0] if ollama_models else "llama3.2"
        
        providers.append(provider_data)
    
    return {"success": True, "providers": providers}

@router.get("/api/llm/config")
async def get_llm_config(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    db_config = LLMConfigRepository.get()
    if db_config:
        config = {
            'provider': db_config['provider'],
            'model': db_config['model'],
            'api_key': mask_secret(db_config.get('api_key', '')),
            'has_api_key': bool(db_config.get('api_key', '')),
            'endpoint': db_config.get('endpoint', ''),
            'temperature': db_config.get('temperature', 0.7),
            'max_tokens': db_config.get('max_tokens', 2000)
        }
    else:
        config = {
            **LLM_CONFIG,
            "api_key": mask_secret(LLM_CONFIG.get("api_key", "")),
            "has_api_key": bool(LLM_CONFIG.get("api_key", "")),
        }
    
    return {"success": True, "config": config}

@router.put("/api/llm/config")
async def update_llm_config(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以修改LLM配置")
    
    body = await request.json()
    config = {}
    existing = LLMConfigRepository.get() or {}
    
    if "provider" in body:
        if body["provider"] not in LLM_PROVIDERS:
            raise HTTPException(status_code=400, detail="不支持的LLM提供商")
        config["provider"] = body["provider"]
        provider_info = LLM_PROVIDERS[body["provider"]]
        if "model" not in body:
            if body["provider"] == "ollama":
                endpoint = (body.get("endpoint") or (existing or {}).get("endpoint") or "http://localhost:11434").strip()
                local_models = await get_local_ollama_models(endpoint)
                config["model"] = local_models[0] if local_models else provider_info["default_model"]
            else:
                config["model"] = provider_info["default_model"]
    
    if "model" in body:
        provider_id = config.get("provider", LLM_CONFIG["provider"])
        
        if provider_id == "ollama":
            # Ollama 模型名因本机安装而异（如 gemma4:latest），不做硬编码列表校验
            config["model"] = body["model"]
        else:
            provider = LLM_PROVIDERS.get(provider_id, {})
            if body["model"] not in provider.get("models", []):
                raise HTTPException(status_code=400, detail="该模型不在可用列表中")
            config["model"] = body["model"]
    
    if "api_key" in body:
        key = (body.get("api_key") or "").strip()
        if key and not is_masked_secret(key):
            config["api_key"] = key
    
    if "endpoint" in body:
        config["endpoint"] = (body.get("endpoint") or "").strip()
    
    if "temperature" in body:
        temp = float(body["temperature"])
        if temp < 0 or temp > 2:
            raise HTTPException(status_code=400, detail="temperature必须在0-2之间")
        config["temperature"] = temp
    
    if "max_tokens" in body:
        config["max_tokens"] = int(body["max_tokens"])

    merged = {
        k: v
        for k, v in existing.items()
        if k not in ("id", "updated_at")
    }
    merged.update(config)
    if merged.get("provider") == "ollama" and not merged.get("endpoint"):
        merged["endpoint"] = "http://localhost:11434"

    LLMConfigRepository.save(merged)
    from src.services.llm_client import refresh_llm_config_from_db

    refresh_llm_config_from_db()
    
    OperationLogRepository.log(current_user.username, 'update_llm_config', f'Updated LLM config: {merged.get("provider")}/{merged.get("model")}')
    
    return {"success": True, "message": "LLM配置已保存到数据库", "config": merged}

@router.post("/api/llm/test")
async def test_llm_connection(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    body = await request.json()
    provider = body.get("provider", LLM_CONFIG["provider"])
    model = body.get("model", LLM_CONFIG["model"])
    api_key = body.get("api_key", LLM_CONFIG.get("api_key", ""))
    endpoint = body.get("endpoint", LLM_CONFIG.get("endpoint", ""))
    if is_masked_secret(api_key):
        from src.services.llm_client import refresh_llm_config_from_db

        refresh_llm_config_from_db()
        api_key = LLM_CONFIG.get("api_key", "")
    if provider == "ollama" and not endpoint:
        endpoint = "http://localhost:11434"

    if provider == "ollama":
        local_models = await get_local_ollama_models(endpoint)
        if not local_models:
            return {
                "success": False,
                "message": (
                    f"无法连接 Ollama（{endpoint}）。请确认服务已启动，"
                    "地址填写 http://localhost:11434（不要带 /api/generate）。"
                ),
            }
        if model not in local_models:
            sample = "、".join(local_models[:3])
            return {
                "success": False,
                "message": (
                    f"模型「{model}」未在本机安装。已检测到：{sample}"
                    f"{' 等' if len(local_models) > 3 else ''}。"
                    "请在下方模型下拉框选择已安装模型后重试。"
                ),
            }

    test_prompt = "请回复'连接测试成功'，只需要回复这四个字。"
    
    try:
        if provider == "openai":
            result = await call_openai_api(test_prompt, api_key, model, endpoint)
        elif provider == "anthropic":
            result = await call_anthropic_api(test_prompt, api_key, model)
        elif provider == "gemini":
            result = await call_gemini_api(test_prompt, api_key, model)
        elif provider == "ollama":
            result = await call_ollama_api(test_prompt, model, endpoint)
        else:
            return {"success": False, "message": "不支持的LLM提供商"}
        
        return {"success": True, "message": "连接测试成功", "response": result}
    except Exception as e:
        return {"success": False, "message": f"连接测试失败: {str(e)}"}

