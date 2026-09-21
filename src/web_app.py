import os

# Load local .env (KEY=VALUE) before reading any configuration.
from src.env_loader import load_env_file  # noqa: E402

load_env_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env"))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Query, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Body, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from src.middleware.bearer_token_bridge import BearerTokenQueryBridgeMiddleware
from src.middleware.ga_inject import inject_google_analytics
from jose import JWTError, jwt
from datetime import datetime, timedelta
import re
import json
import pandas as pd
from typing import List, Dict, Any, Optional
import requests
import asyncio
import uuid
import hmac
import hashlib
from io import BytesIO

from src.auth import (
    SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES,
    Token, TokenData, User, UserInDB, PLANS,
    LLM_PROVIDERS, LLM_CONFIG,
    verify_password, create_access_token, get_password_hash
)
from src.database import (
    UserRepository, OperationLogRepository, LLMConfigRepository, ProductRepository, OrderRepository, AlertRepository, DashboardConfigRepository, SharedReportRepository, ImportedDataRepository, get_db_connection, config_manager
)
from src.report_generator import send_report_email
from src.services.report_helpers import generate_html_period_report
from src.data_collector import data_collector
from src.report_scheduler import report_scheduler
from src.cache import data_cache
from src.mvp_pipeline import DEFAULT_OUTPUT_DIR, DEFAULT_STEAM_APP_IDS, run_mvp_pipeline
from src.data_resolution import (
    get_user_comments_data,
    get_user_metrics_data,
    resolve_user_data_source,
)
from src.web_common import (
    get_current_user,
    mark_order_paid,
    mask_config_secrets,
    mask_secret,
    verify_payment_signature,
)
from src.web_constants import (
    AVAILABLE_DATA_SOURCES,
    AVAILABLE_PRODUCTS,
    AVAILABLE_TIME_PERIODS,
    ADMIN_FILE,
    BASE_DIR,
    DATA_DIR,
    HTML_FILE,
    LOGIN_FILE,
)
from src.routers.analytics_router import router as analytics_router
from src.routers.auth_router import router as auth_router
from src.routers.conversation_router import router as conversation_router
from src.routers.data_router import router as data_router
from src.routers.import_router import router as import_router
from src.routers.llm_router import router as llm_router
from src.routers.mvp_router import router as mvp_router
from src.routers.pages_router import router as pages_router
from src.routers.payment_router import router as payment_router
from src.routers.products_router import router as products_router
from src.routers.support_router import router as support_router
from src.routers.speech_router import router as speech_router
from src.routers.wizard_router import router as wizard_router
from src.routers.hotspot_router import router as hotspot_router
from src.routers.competitor_router import router as competitor_router
from src.routers.game_intel_router import router as game_intel_router
from src.routers.health_router import router as health_router
from src.routers.commercial_router import router as commercial_router
from src.routers.agent_router import router as agent_router
from src.middleware_limits import limits_middleware
from src.services.report_helpers import (
    analyze_trends,
    generate_product_details,
    generate_recommendations,
    generate_report_summary,
)

_alert_scheduler_stop: Optional[asyncio.Event] = None
_alert_scheduler_task: Optional[asyncio.Task] = None

async def _alert_scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        from src.alert_scheduler import AlertScheduler

        scheduler = AlertScheduler(check_interval=60)
        while not stop_event.is_set():
            await scheduler.check_all_alerts()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass
    except Exception as exc:
        print(f"Alert scheduler stopped: {exc}")

@asynccontextmanager
async def app_lifespan(app: FastAPI):
    global _alert_scheduler_stop, _alert_scheduler_task
    try:
        from src.database import ensure_support_agents

        ensure_support_agents()
    except Exception as exc:
        print(f"Support agent seed skipped: {exc}")
    try:
        from src.services.llm_client import refresh_llm_config_from_db

        refresh_llm_config_from_db()
    except Exception as exc:
        print(f"LLM config startup load skipped: {exc}")
    try:
        from src.services.game_intel import seed_default_library

        seed_default_library()
    except Exception as exc:
        print(f"Game library seed skipped: {exc}")
    try:
        from src.services.demo_seed import ensure_demo_user_seed

        if ensure_demo_user_seed():
            print("Demo MVP artifacts seeded for demo user")
    except Exception as exc:
        print(f"Demo seed skipped: {exc}")

    _alert_scheduler_stop = asyncio.Event()
    _alert_scheduler_task = asyncio.create_task(_alert_scheduler_loop(_alert_scheduler_stop))
    print("Alert scheduler background task started")

    _subscription_task = None
    try:
        from src.subscription_reminder import SubscriptionReminder

        reminder = SubscriptionReminder(check_interval=3600)

        async def _subscription_loop():
            while True:
                try:
                    await reminder.check_all_subscriptions()
                except Exception as exc:
                    print(f"Subscription reminder check failed: {exc}")
                await asyncio.sleep(reminder.check_interval)

        _subscription_task = asyncio.create_task(_subscription_loop())
        print("Subscription reminder background task started")
    except Exception as exc:
        print(f"Subscription reminder startup skipped: {exc}")

    yield

    if _subscription_task:
        _subscription_task.cancel()
        try:
            await _subscription_task
        except asyncio.CancelledError:
            pass

    if _alert_scheduler_stop:
        _alert_scheduler_stop.set()
    if _alert_scheduler_task:
        _alert_scheduler_task.cancel()
        try:
            await _alert_scheduler_task
        except asyncio.CancelledError:
            pass
    print("Alert scheduler background task stopped")

app = FastAPI(
    title="游戏数据分析引擎",
    description="AI驱动的游戏商业智能分析平台",
    lifespan=app_lifespan,
)
app.include_router(mvp_router)
app.include_router(health_router)
app.include_router(commercial_router)
app.include_router(agent_router)
app.include_router(game_intel_router)
app.include_router(competitor_router)
app.include_router(data_router)
app.include_router(auth_router)
app.include_router(import_router)
app.include_router(analytics_router)
app.include_router(products_router)
app.include_router(llm_router)
app.include_router(payment_router)
app.include_router(conversation_router)
app.include_router(pages_router)
app.include_router(support_router)
app.include_router(speech_router)
app.include_router(wizard_router)
app.include_router(hotspot_router)

# Legacy routes read ?token=; authFetch sends Authorization: Bearer only.
app.add_middleware(BearerTokenQueryBridgeMiddleware)

# 配置CORS（allow_credentials 与 allow_origins="*" 不可同时使用）
_cors_origins = os.getenv("CORS_ORIGINS", "*").strip()
_allow_origins = (
    ["*"]
    if not _cors_origins or _cors_origins == "*"
    else [item.strip() for item in _cors_origins.split(",") if item.strip()]
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def apply_limits_middleware(request: Request, call_next):
    return await limits_middleware(request, call_next)

# 安全响应头中间件
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

# Google Analytics (GA4 / gtag.js) 注入 —— 所有 HTML 页面自动埋点
@app.middleware("http")
async def google_analytics_middleware(request: Request, call_next):
    return await inject_google_analytics(request, call_next)

static_dir = os.path.join(BASE_DIR, "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

def load_data(file_path: str) -> Any:
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                raise ValueError("Data loaded is not a list.")
    except FileNotFoundError:
        print(f"错误：找不到文件 {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"错误：JSON解析失败，请检查 {file_path} 文件。错误信息: {e}")
        return None

def run_business_intelligence_report(comments_data: List[Dict], metrics_data: List[Dict]) -> Dict:
    comments_df = pd.DataFrame(comments_data)
    
    if comments_df.empty:
        negative_topics = ""
        positive_topics = ""
        conflict_summary = "当前筛选条件下没有评论数据，无法生成情感分析报告。"
    else:
        negative_topics = comments_df[comments_df['情绪'] == 'negative']['内容'].str.cat(sep="; ")
        positive_topics = comments_df[comments_df['情绪'] == 'positive']['内容'].str.cat(sep="; ")
        
        conflict_summary = (
            "✅ **正面肯定洞察**：用户高度肯定核心机制（如：战斗系统、角色个性化），这表明产品的核心体验是成功的。\n"
            "⚠️ **最大的用户冲突點**：大部分负面评论集中在'付费限制'和'流程复杂'。用户感受到的核心矛盾是：**核心机制很棒，但被上锁了（内容受限）**。"
        )

    metrics_df = pd.DataFrame(metrics_data)
    critical_decline = ""
    if not metrics_df.empty and 'metric' in metrics_df.columns:
        metrics_str = metrics_df['metric'].str.cat(sep=',')
        if '付费付费占比 (ARPPU)' in metrics_str:
            critical_decline = "🔴 **付费变现警报**：ARPPU下降15%是非常危险的信号。这证明了用户行为已经改变，且付费意愿受到影响。"
        if '平均用户留存率' in metrics_str:
            critical_decline += "\n🔴 **留存失血预警**：留存率下降5个百分点，是短期用户群体健康状况急剧恶化的信号，需要立即干预。"
    elif metrics_df.empty:
        critical_decline = "当前筛选条件下没有业务指标数据。"
    
    report = {
        "ReportTitle": "市场洞察报告：付费限制与流程复杂性引发的关键警报",
        "Summary": "本次分析的核心结论是：用户对产品的核心乐趣机制认可度高，但当前的产品设计和变现流程正在扼杀用户满意度和消费意愿。",
        "AnalysisSections": {
            "痛点报告 (The Pain)": {
                "证据A_来自评论": f"--- {conflict_summary}",
                "证据B_来自指标": critical_decline,
                "痛点摘要": "付费壁垒过高导致初体验受限。当用户发现核心fun（乐趣点）很难免费体验时，立即产生离开和抱怨情绪。"
            },
            "改进产品建议 (Solution)": {
                "建议优先级1 (A/B Test核心)：": "将核心的、用户反馈积极的机制（如：战斗系统）的关键体验流程，改为免费用户也能接触的『限时/限次数』体验。",
                "建议优先级2 (UI/UX)：": "根据用户反馈，简化新手教程和UI流程，必须降低初次使用用户的心理门槛。",
                "建议优先级3 (机制优化)：": "参考竞品，在资源获取（素材）方面提供更直观的反馈和引导。"
            },
            "未来产品方向 (Strategy)": {
                "机会点": "围绕'专业化'和'深度定制'切入：推出一个仅做『资源/角色深度定制化』的付费工具/模块，避开与现有核心流程的正面冲突。",
                "市场信号": "用户对『个性化展现』需求的增长，预示着'虚拟形象商店'或'荣誉展示系统'是可预期的成功品类。"
            }
        }
    }
    return report

def dataframe_to_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    df = df.where(pd.notnull(df), "")
    return df.to_dict(orient="records")

@app.get("/api/data/config/status")
async def get_data_config_status(token: Optional[str] = Query(None)):
    """获取数据采集配置状态"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    config_status = data_collector.validate_api_keys()
    instructions = data_collector.get_configuration_instructions()
    
    return {
        "success": True,
        "configured": {
            "steam": config_status["steam"],
            "google_play": config_status["google_play"],
            "app_store": config_status["app_store"]
        },
        "instructions": instructions
    }

@app.get("/api/data/config")
async def get_data_source_config(token: Optional[str] = Query(None)):
    """获取所有数据源配置"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以查看数据源配置")
    
    from src.database import DataSourceConfigRepository
    configs = DataSourceConfigRepository.get_all()
    
    return {"success": True, "configs": [mask_config_secrets(config) for config in configs]}

@app.put("/api/data/config/{platform}")
async def update_data_source_config(
    platform: str,
    request: Request,
    token: Optional[str] = Query(None)
):
    """更新数据源配置"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以更新数据源配置")
    
    if platform not in ["steam", "google_play", "app_store"]:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    body = await request.json()
    
    from src.database import DataSourceConfigRepository
    success = DataSourceConfigRepository.create_or_update(platform, body)
    
    if success:
        data_collector._load_config_from_db()
        OperationLogRepository.log(current_user.username, 'update_data_source_config', f'Updated config for {platform}')
        return {"success": True, "message": f"{platform} 配置更新成功"}
    else:
        return {"success": False, "message": "配置更新失败"}

@app.delete("/api/data/config/{platform}")
async def delete_data_source_config(
    platform: str,
    token: Optional[str] = Query(None)
):
    """删除数据源配置"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="只有管理员可以删除数据源配置")
    
    from src.database import DataSourceConfigRepository
    success = DataSourceConfigRepository.delete(platform)
    
    if success:
        data_collector._load_config_from_db()
        OperationLogRepository.log(current_user.username, 'delete_data_source_config', f'Deleted config for {platform}')
        return {"success": True, "message": f"{platform} 配置删除成功"}
    else:
        return {"success": False, "message": "配置删除失败"}

@app.get("/api/data/collect/all")
async def collect_all_data(
    product_ids: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """批量采集所有产品数据"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    products = AVAILABLE_PRODUCTS
    if product_ids:
        selected_ids = product_ids.split(',')
        products = [p for p in products if p['id'] in selected_ids]
    
    # 给每个产品添加平台信息
    platforms = ['steam', 'google_play', 'app_store']
    products_with_platform = []
    for i, product in enumerate(products):
        products_with_platform.append({
            **product,
            'platform': platforms[i % len(platforms)],
            'app_id': f"{product['id']}_id"
        })
    
    results = await data_collector.collect_all_products(products_with_platform)
    
    success_count = sum(1 for r in results if r.get('success', False) or r.get('mock', False))
    
    # 保存所有采集的数据到缓存
    total_cached_metrics = 0
    total_cached_comments = 0
    
    for i, result in enumerate(results):
        if result.get('success') or result.get('mock'):
            product = products[i] if i < len(products) else {}
            product_name = product.get('name', product.get('id', 'unknown'))
            platform = result.get('platform', 'unknown')
            
            # 转换指标数据格式
            metrics_data = result.get('metrics', {})
            cached_metrics = []
            
            for key, value in metrics_data.items():
                cached_metrics.append({
                    'product': product_name,
                    'platform': platform,
                    'metric': key,
                    '值': float(value) if isinstance(value, (int, float)) else 0.0,
                    'date': datetime.now().strftime('%Y-%m-%d')
                })
            
            # 如果有评论数据
            cached_comments = []
            if 'reviews' in result:
                for review in result['reviews']:
                    cached_comments.append({
                        'product': product_name,
                        'platform': platform,
                        'review_id': review.get('id'),
                        'rating': review.get('rating'),
                        'title': review.get('title'),
                        'content': review.get('content'),
                        'author': review.get('author'),
                        'date': review.get('date'),
                        'helpful_count': review.get('helpful_count', 0)
                    })
            
            # 保存到缓存
            if cached_metrics:
                saved = ImportedDataRepository.save_cached_metrics(cached_metrics)
                total_cached_metrics += saved
            if cached_comments:
                saved = ImportedDataRepository.save_cached_comments(cached_comments)
                total_cached_comments += saved
    
    OperationLogRepository.log(
        current_user.username,
        "data_collection",
        f"批量采集{len(products)}个产品数据 - 成功: {success_count}",
        None
    )
    
    return {
        "success": True,
        "total": len(products),
        "successful": success_count,
        "results": results,
        "cached": {
            "metrics": total_cached_metrics,
            "comments": total_cached_comments
        }
    }

@app.get("/api/data/collect/{platform}")
async def collect_platform_data(
    platform: str,
    identifier: Optional[str] = Query(None),
    token: Optional[str] = Query(None)
):
    """手动触发特定平台数据采集"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    platforms = {
        "steam": data_collector.fetch_steam_data,
        "google_play": data_collector.fetch_google_play_data,
        "app_store": data_collector.fetch_app_store_data
    }
    
    if platform not in platforms:
        raise HTTPException(status_code=400, detail="不支持的平台")
    
    collector_func = platforms[platform]
    result = await collector_func(identifier)
    
    # 保存采集的数据到缓存
    cached_metrics = []
    cached_comments = []
    
    if result.get('success') or result.get('mock'):
        # 转换指标数据格式
        product_name = identifier or platform
        metrics_data = result.get('metrics', {})
        
        for key, value in metrics_data.items():
            cached_metrics.append({
                'product': product_name,
                'platform': platform,
                'metric': key,
                '值': float(value) if isinstance(value, (int, float)) else 0.0,
                'date': datetime.now().strftime('%Y-%m-%d')
            })
        
        # 如果有评论数据
        if 'reviews' in result:
            for review in result['reviews']:
                cached_comments.append({
                    'product': product_name,
                    'platform': platform,
                    'review_id': review.get('id'),
                    'rating': review.get('rating'),
                    'title': review.get('title'),
                    'content': review.get('content'),
                    'author': review.get('author'),
                    'date': review.get('date'),
                    'helpful_count': review.get('helpful_count', 0)
                })
        
        # 保存到缓存
        if cached_metrics:
            ImportedDataRepository.save_cached_metrics(cached_metrics)
        if cached_comments:
            ImportedDataRepository.save_cached_comments(cached_comments)
    
    OperationLogRepository.log(
        current_user.username,
        "data_collection",
        f"采集{platform}数据: {identifier or 'all'} - {'成功' if result.get('success') else '使用模拟数据'}",
        None
    )
    
    return {
        "success": True,
        "data": result,
        "cached": {
            "metrics": len(cached_metrics),
            "comments": len(cached_comments)
        }
    }

@app.get("/api/export/csv")
async def export_csv(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    # 加载数据
    metrics_data = get_user_metrics_data(current_user.username)
    
    # 过滤数据
    selected_products = product_ids.split(",") if product_ids else ["game_a", "game_b", "game_c"]
    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]
    
    # 生成CSV
    import csv
    from io import StringIO
    output = StringIO()
    if metrics_data:
        # 收集所有数据项的所有字段名
        all_fields = set()
        for item in metrics_data:
            all_fields.update(item.keys())
        fieldnames = list(all_fields)
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(metrics_data)
    
    csv_content = output.getvalue()
    
    from fastapi.responses import StreamingResponse
    import io
    return StreamingResponse(
        io.StringIO(csv_content),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename=metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/api/export/excel")
async def export_excel(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    data_source: Optional[str] = Query(None),
    fields: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    # 加载数据
    metrics_data = get_user_metrics_data(current_user.username)
    comments_data = get_user_comments_data(current_user.username)
    
    # 过滤数据
    selected_products = product_ids.split(",") if product_ids else ["game_a", "game_b", "game_c"]
    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
        comments_data = [c for c in comments_data if c.get("cycle") == time_period]
    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]
    comments_data = [c for c in comments_data if c.get("product") in selected_products]
    
    # 字段过滤
    if fields:
        selected_fields = fields.split(",")
        metrics_data = [{k: v for k, v in m.items() if k in selected_fields or k in ["product", "cycle"]} for m in metrics_data]
        comments_data = [{k: v for k, v in c.items() if k in selected_fields or k in ["product", "cycle"]} for m in comments_data]
    
    # 生成Excel
    from io import BytesIO
    output = BytesIO()
    
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        # 按产品分组
        for product in selected_products:
            product_metrics = [m for m in metrics_data if m.get("product") == product]
            product_comments = [c for c in comments_data if c.get("product") == product]
            
            if product_metrics:
                df_pm = pd.DataFrame(product_metrics)
                sheet_name = f"{product[:10]}_指标"[:31]
                df_pm.to_excel(writer, sheet_name=sheet_name, index=False)
            
            if product_comments:
                df_pc = pd.DataFrame(product_comments)
                sheet_name = f"{product[:10]}_评论"[:31]
                df_pc.to_excel(writer, sheet_name=sheet_name, index=False)
        
        # 汇总sheet
        if metrics_data:
            df_metrics = pd.DataFrame(metrics_data)
            df_metrics.to_excel(writer, sheet_name="汇总_指标", index=False)
        if comments_data:
            df_comments = pd.DataFrame(comments_data)
            df_comments.to_excel(writer, sheet_name="汇总_评论", index=False)
        
        # 添加统计摘要
        summary_data = []
        for product in selected_products:
            product_metrics = [m for m in metrics_data if m.get("product") == product]
            if product_metrics:
                summary_data.append({
                    "产品": product,
                    "数据条数": len(product_metrics),
                    "平均下载量": sum(m.get("downloads", 0) for m in product_metrics) / len(product_metrics),
                    "总收入": sum(m.get("revenue", 0) for m in product_metrics),
                    "平均评分": sum(m.get("rating", 0) for m in product_metrics) / len(product_metrics)
                })
        
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            df_summary.to_excel(writer, sheet_name="统计摘要", index=False)
    
    output.seek(0)
    
    filename = f"game_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )

@app.get("/api/alerts")
async def get_alerts(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    alerts = AlertRepository.get_by_username(current_user.username)
    return {"success": True, "alerts": alerts}

@app.post("/api/alerts")
async def create_alert(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    body = await request.json()
    alert_data = {
        "username": current_user.username,
        "name": body.get("name", ""),
        "product": body.get("product"),
        "metric": body.get("metric", ""),
        "operator": body.get("operator", ""),
        "threshold": float(body.get("threshold", 0)),
        "email": body.get("email", "")
    }
    
    if AlertRepository.create(alert_data):
        OperationLogRepository.log(current_user.username, "create_alert", f"Created alert: {alert_data['name']}")
        return {"success": True, "message": "预警规则创建成功"}
    else:
        return {"success": False, "message": "创建失败"}

@app.put("/api/alerts/{alert_id}")
async def update_alert(alert_id: int, request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    body = await request.json()
    alert_data = {}
    for key in ["name", "product", "metric", "operator", "threshold", "email", "enabled"]:
        if key in body:
            if key == "threshold":
                alert_data[key] = float(body[key])
            else:
                alert_data[key] = body[key]
    
    if AlertRepository.update(alert_id, alert_data):
        OperationLogRepository.log(current_user.username, "update_alert", f"Updated alert: {alert_id}")
        return {"success": True, "message": "更新成功"}
    else:
        return {"success": False, "message": "更新失败"}

@app.delete("/api/alerts/{alert_id}")
async def delete_alert(alert_id: int, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if AlertRepository.delete(alert_id):
        OperationLogRepository.log(current_user.username, "delete_alert", f"Deleted alert: {alert_id}")
        return {"success": True, "message": "删除成功"}
    else:
        return {"success": False, "message": "删除失败"}

@app.post("/api/alerts/test")
async def test_alert(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    body = await request.json()
    test_email = body.get("email", "")
    
    try:
        OperationLogRepository.log(current_user.username, "test_alert", f"Test alert sent to: {test_email}")
        return {"success": True, "message": "测试邮件已发送（模拟）"}
    except Exception as e:
        return {"success": False, "message": f"测试失败: {str(e)}"}

@app.get("/api/reports/generate")
async def generate_report(
    token: Optional[str] = Query(None),
    report_type: str = Query("weekly"),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    selected_products = product_ids.split(",") if product_ids else ["game_a", "game_b", "game_c"]
    
    metrics_data = get_user_metrics_data(current_user.username)
    comments_data = get_user_comments_data(current_user.username)
    
    if time_period:
        metrics_data = [m for m in metrics_data if m.get("cycle") == time_period]
        comments_data = [c for c in comments_data if c.get("cycle") == time_period]
    
    metrics_data = [m for m in metrics_data if m.get("product") in selected_products]
    comments_data = [c for c in comments_data if c.get("product") in selected_products]
    
    report_data = {
        "report_type": report_type,
        "generated_at": datetime.now().isoformat(),
        "products": selected_products,
        "summary": generate_report_summary(metrics_data, comments_data, report_type),
        "product_details": generate_product_details(metrics_data),
        "trends": analyze_trends(metrics_data),
        "recommendations": generate_recommendations(metrics_data, comments_data)
    }
    
    OperationLogRepository.log(current_user.username, "generate_report", f"Generated {report_type} report")
    return {"success": True, "data": report_data}

@app.post("/api/reports/send")
async def send_report_email(
    token: Optional[str] = Query(None),
    report_type: str = Query("weekly"),
    product_ids: Optional[str] = Query(None),
    time_period: Optional[str] = Query(None),
    to_email: Optional[str] = Query(None)
):
    """发送报告邮件"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if not to_email:
        to_email = current_user.email
    
    selected_products = product_ids.split(",") if product_ids else ["game_a", "game_b", "game_c"]
    
    success = await report_scheduler.send_report_email(to_email, report_type, selected_products, time_period)
    
    if success:
        OperationLogRepository.log(current_user.username, "send_report", f"Sent {report_type} report to {to_email}")
        return {"success": True, "message": f"报告已发送到 {to_email}"}
    else:
        return {"success": False, "message": "发送失败，请检查SMTP配置"}

@app.post("/api/reports/schedule")
async def schedule_report(
    token: Optional[str] = Query(None),
    schedule_type: str = Query(...),
    to_email: str = Query(...),
    product_ids: Optional[str] = Query(None),
    hour: int = Query(9)
):
    """创建定时报告任务"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    selected_products = product_ids.split(",") if product_ids else ["game_a", "game_b", "game_c"]
    
    if schedule_type == "daily":
        await report_scheduler.schedule_daily_report(to_email, selected_products, hour)
    elif schedule_type == "weekly":
        await report_scheduler.schedule_weekly_report(to_email, selected_products, weekday=0, hour=hour)
    elif schedule_type == "monthly":
        await report_scheduler.schedule_monthly_report(to_email, selected_products, day=1, hour=hour)
    else:
        raise HTTPException(status_code=400, detail="不支持的调度类型")
    
    OperationLogRepository.log(current_user.username, "schedule_report", f"Scheduled {schedule_type} report to {to_email}")
    return {"success": True, "message": f"{schedule_type}报告已设置定时推送"}

@app.delete("/api/reports/schedule")
async def cancel_scheduled_report(
    token: Optional[str] = Query(None),
    schedule_type: str = Query(...),
    to_email: str = Query(...)
):
    """取消定时报告任务"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    task_name = f"{schedule_type}_{to_email}"
    success = report_scheduler.cancel_scheduled_task(task_name)
    
    if success:
        OperationLogRepository.log(current_user.username, "cancel_report", f"Cancelled {schedule_type} report for {to_email}")
        return {"success": True, "message": "定时任务已取消"}
    else:
        return {"success": False, "message": "未找到该定时任务"}

@app.get("/api/reports/schedule/list")
async def get_scheduled_reports(token: Optional[str] = Query(None)):
    """获取所有定时报告任务"""
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    tasks = report_scheduler.get_scheduled_tasks()
    return {"success": True, "tasks": tasks}

# 报告生成API
def _period_report_html(username: str, report_type: str, product_ids: Optional[str]) -> str:
    metrics = get_user_metrics_data(username)
    products = [p.strip() for p in product_ids.split(",") if p.strip()] if product_ids else None
    return generate_html_period_report(report_type, metrics, products)

def _archive_period_report(
    username: str,
    report_type: str,
    product_ids: Optional[str],
    report_html: str,
) -> Optional[str]:
    from src.services.analysis_archive import archive_report_run

    selected = [p.strip() for p in (product_ids or "").split(",") if p.strip()]
    if not selected:
        metrics = get_user_metrics_data(username)
        selected = sorted({str(m.get("product")) for m in metrics if m.get("product")})[:5]
    comments = get_user_comments_data(username)
    metrics = get_user_metrics_data(username)
    if not selected:
        return None
    filtered_metrics = [m for m in metrics if str(m.get("product")) in selected]
    filtered_comments = [c for c in comments if str(c.get("product") or c.get("产品")) in selected]
    return archive_report_run(
        username=username,
        report_type=report_type,
        product_ids=selected,
        metrics=filtered_metrics,
        comments=filtered_comments,
        html_excerpt=report_html[:4000],
    )

@app.get("/api/reports/daily")
async def generate_daily_report(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    date: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    try:
        report_html = _period_report_html(current_user.username, "daily", product_ids)
        _archive_period_report(current_user.username, "daily", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/reports/weekly")
async def generate_weekly_report(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    week_start: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    try:
        report_html = _period_report_html(current_user.username, "weekly", product_ids)
        _archive_period_report(current_user.username, "weekly", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/reports/monthly")
async def generate_monthly_report(
    token: Optional[str] = Query(None),
    product_ids: Optional[str] = Query(None),
    month: Optional[str] = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    try:
        report_html = _period_report_html(current_user.username, "monthly", product_ids)
        _archive_period_report(current_user.username, "monthly", product_ids, report_html)
        return HTMLResponse(content=report_html, media_type="text/html")
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/reports/send-generated")
async def send_report(
    token: Optional[str] = Query(None),
    report_type: str = Query("daily"),
    product_ids: Optional[str] = Query(None),
    to_email: str = Query(None)
):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    current_user = await get_current_user(token)
    
    if not to_email:
        raise HTTPException(status_code=400, detail="Email address is required")
    
    try:
        if report_type == "daily":
            report_html = _period_report_html(current_user.username, "daily", product_ids)
            subject = "【游戏数据分析引擎】日报"
        elif report_type == "weekly":
            report_html = _period_report_html(current_user.username, "weekly", product_ids)
            subject = "【游戏数据分析引擎】周报"
        elif report_type == "monthly":
            report_html = _period_report_html(current_user.username, "monthly", product_ids)
            subject = "【游戏数据分析引擎】月报"
        else:
            return {"success": False, "message": "Invalid report type"}
        
        result = send_report_email(report_html, to_email, subject)
        return result
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/reports/types")
async def get_report_types(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    await get_current_user(token)
    
    return {
        "success": True,
        "types": [
            {"id": "daily", "name": "日报", "description": "每日数据汇总报告"},
            {"id": "weekly", "name": "周报", "description": "每周数据汇总及同比分析"},
            {"id": "monthly", "name": "月报", "description": "每月数据汇总及同比/环比分析"}
        ]
    }

@app.get("/api/dashboard/list")
async def list_dashboards(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    dashboards = DashboardConfigRepository.get_all(current_user.username)
    
    for d in dashboards:
        if 'layout' in d and isinstance(d['layout'], str):
            d['layout'] = json.loads(d['layout'])
    
    return {"success": True, "dashboards": dashboards}

@app.get("/api/dashboard/{dashboard_id}")
async def get_dashboard(dashboard_id: int, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    
    if dashboard['username'] != current_user.username:
        return {"success": False, "message": "无权限访问此仪表盘"}
    
    if 'layout' in dashboard and isinstance(dashboard['layout'], str):
        dashboard['layout'] = json.loads(dashboard['layout'])
    
    return {"success": True, "dashboard": dashboard}

@app.post("/api/dashboard/save")
async def save_dashboard(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    body = await request.json()
    
    name = body.get('name')
    layout = body.get('layout')
    is_default = body.get('is_default', 0)
    
    if not name or not layout:
        return {"success": False, "message": "仪表盘名称和布局配置不能为空"}
    
    dashboard_id = DashboardConfigRepository.create(
        current_user.username, name, layout, is_default
    )
    
    if dashboard_id:
        OperationLogRepository.log(current_user.username, 'save_dashboard', f'Saved dashboard: {name}')
        return {"success": True, "dashboard_id": dashboard_id}
    
    return {"success": False, "message": "保存失败"}

@app.put("/api/dashboard/{dashboard_id}")
async def update_dashboard(dashboard_id: int, request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    
    if dashboard['username'] != current_user.username:
        return {"success": False, "message": "无权限修改此仪表盘"}
    
    body = await request.json()
    name = body.get('name', dashboard['name'])
    layout = body.get('layout', json.loads(dashboard['layout']))
    is_default = body.get('is_default', dashboard['is_default'])
    
    success = DashboardConfigRepository.update(dashboard_id, name, layout, is_default)
    
    if success:
        OperationLogRepository.log(current_user.username, 'update_dashboard', f'Updated dashboard: {name}')
        return {"success": True}
    
    return {"success": False, "message": "更新失败"}

@app.delete("/api/dashboard/{dashboard_id}")
async def delete_dashboard(dashboard_id: int, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    dashboard = DashboardConfigRepository.get_by_id(dashboard_id)
    
    if not dashboard:
        return {"success": False, "message": "仪表盘不存在"}
    
    if dashboard['username'] != current_user.username:
        return {"success": False, "message": "无权限删除此仪表盘"}
    
    success = DashboardConfigRepository.delete(dashboard_id)
    
    if success:
        OperationLogRepository.log(current_user.username, 'delete_dashboard', f'Deleted dashboard: {dashboard_id}')
        return {"success": True}
    
    return {"success": False, "message": "删除失败"}

@app.post("/api/report/share")
async def share_report(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    body = await request.json()
    
    report_type = body.get('report_type', 'daily')
    report_data = body.get('report_data', {})
    expires_hours = body.get('expires_hours', 24)
    
    from datetime import timedelta
    expires_at = (datetime.now() + timedelta(hours=expires_hours)).isoformat() if expires_hours > 0 else None
    
    share_token = SharedReportRepository.create_share(
        current_user.username, report_type, report_data, expires_at
    )
    
    if share_token:
        base = str(request.base_url).rstrip("/")
        share_url = f"{base}/shared/{share_token}"
        OperationLogRepository.log(current_user.username, 'share_report', f'Shared report: {report_type}')
        try:
            from src.services.analysis_archive import archive_report_run
            from src.data_resolution import get_user_comments_data, get_user_metrics_data

            product_ids = report_data.get("products") or report_data.get("product_ids") or []
            if isinstance(product_ids, str):
                product_ids = [p.strip() for p in product_ids.split(",") if p.strip()]
            archive_report_run(
                username=current_user.username,
                report_type=report_type,
                product_ids=product_ids,
                metrics=get_user_metrics_data(current_user.username),
                comments=get_user_comments_data(current_user.username),
                share_token=share_token,
            )
        except Exception:
            pass
        return {"success": True, "share_token": share_token, "share_url": share_url}
    
    return {"success": False, "message": "分享失败"}

@app.get("/api/report/shared/{share_token}")
async def get_shared_report(share_token: str):
    report = SharedReportRepository.get_by_token(share_token)
    
    if not report:
        return {"success": False, "message": "分享链接已过期或不存在"}
    
    report_data = json.loads(report['report_data']) if isinstance(report['report_data'], str) else report['report_data']
    
    return {
        "success": True,
        "report": {
            "report_type": report['report_type'],
            "report_data": report_data,
            "created_at": report['created_at'],
            "expires_at": report['expires_at']
        }
    }

@app.get("/api/report/history")
async def get_report_history(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    current_user = await get_current_user(token)
    reports = SharedReportRepository.get_user_reports(current_user.username)
    
    for r in reports:
        if 'report_data' in r and isinstance(r['report_data'], str):
            r['report_data'] = json.loads(r['report_data'])
    
    return {"success": True, "reports": reports}

# =========================================
# 团队协作管理API
# =========================================

@app.get("/api/teams")
async def get_user_teams(token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        
        # 初始化团队表
        from src.team_management import init_team_tables, TeamRepository
        init_team_tables()
        
        # 获取用户所在的所有团队
        teams = TeamRepository.get_user_teams(current_user.username)
        
        return {
            "success": True,
            "teams": teams,
            "total": len(teams)
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.post("/api/teams")
async def create_team(request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        body = await request.json()
        
        # 初始化团队表
        from src.team_management import init_team_tables, TeamRepository
        init_team_tables()
        
        # 创建团队
        team_data = {
            'name': body.get('name'),
            'description': body.get('description', ''),
            'owner_id': current_user.username
        }
        
        team_id = TeamRepository.create_team(team_data)
        
        if team_id:
            # 自动将创建者添加为管理员
            TeamRepository.add_member(team_id, current_user.username, 'admin')
            
            return {
                "success": True,
                "team_id": team_id,
                "message": "团队创建成功"
            }
        else:
            return {"success": False, "message": "创建团队失败"}
            
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/teams/{team_id}/members")
async def get_team_members(team_id: int, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        
        # 初始化团队表
        from src.team_management import init_team_tables, TeamRepository
        init_team_tables()
        
        # 检查是否是团队成员
        if not TeamRepository.is_team_member(team_id, current_user.username):
            raise HTTPException(status_code=403, detail="不是团队成员")
        
        # 获取团队成员
        members = TeamRepository.get_team_members(team_id)
        
        return {
            "success": True,
            "members": members,
            "total": len(members)
        }
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.get("/api/teams/{team_id}/archives")
async def get_team_shared_archives(team_id: int, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    try:
        current_user = await get_current_user(token)
        from src.team_management import init_team_tables
        from src.services.team_archives import list_team_shared_archives

        init_team_tables()
        return list_team_shared_archives(team_id, current_user.username)
    except Exception as e:
        return {"success": False, "message": str(e), "archives": []}

@app.post("/api/teams/{team_id}/members")
async def add_team_member(team_id: int, request: Request, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        body = await request.json()
        
        # 初始化团队表
        from src.team_management import init_team_tables, TeamRepository
        init_team_tables()
        
        # 检查权限（只有管理员可以添加成员）
        role = TeamRepository.get_member_role(team_id, current_user.username)
        if role not in ['admin']:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        # 添加成员
        success = TeamRepository.add_member(
            team_id, 
            body.get('username'), 
            body.get('role', 'viewer')
        )
        
        if success:
            return {"success": True, "message": "成员添加成功"}
        else:
            return {"success": False, "message": "添加成员失败"}
            
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}

@app.delete("/api/teams/{team_id}/members/{username}")
async def remove_team_member(team_id: int, username: str, token: Optional[str] = Query(None)):
    if not token:
        raise HTTPException(status_code=401, detail="Token required")
    
    try:
        current_user = await get_current_user(token)
        
        # 初始化团队表
        from src.team_management import init_team_tables, TeamRepository
        init_team_tables()
        
        # 检查权限（管理员或自己可以移除）
        role = TeamRepository.get_member_role(team_id, current_user.username)
        if role not in ['admin'] and current_user.username != username:
            raise HTTPException(status_code=403, detail="需要管理员权限")
        
        # 移除成员
        success = TeamRepository.remove_member(team_id, username)
        
        if success:
            return {"success": True, "message": "成员移除成功"}
        else:
            return {"success": False, "message": "移除成员失败"}
            
    except HTTPException:
        raise
    except Exception as e:
        return {"success": False, "message": str(e)}

# --- Search-engine verification files at repo root (e.g. Google Search Console) ---
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_VERIFICATION_FILE_RE = re.compile(r"^[A-Za-z0-9_-]+\.html$")

@app.get("/{filename}", include_in_schema=False)
async def serve_root_verification_file(filename: str):
    """Serve search-engine / site verification files placed at the repo root.

    Registered last on purpose so it never shadows existing routes; only serves
    safe single-segment ``*.html`` files that actually exist at the project root
    (for example ``googledc482112bcd317b2.html`` for Google Search Console).
    """
    if not _VERIFICATION_FILE_RE.fullmatch(filename):
        raise HTTPException(status_code=404, detail="Not found")
    file_path = os.path.join(_PROJECT_ROOT, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Not found")
    with open(file_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    return HTMLResponse(content=content, media_type="text/html")
