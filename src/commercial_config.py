"""Deployment profile, payment mode, and production readiness checks."""

from __future__ import annotations

import os
from typing import Any, Dict, List

_DEV_SECRET = "dev-secret-key-change-me-before-production"


def _truthy(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def app_env() -> str:
    return os.getenv("APP_ENV", "development").lower()


def demo_accounts_enabled() -> bool:
    # 统一走 database 的单一定义（production 默认关闭, 显式配置优先）
    from src.database import demo_accounts_enabled as _enabled

    return _enabled()


def payment_test_mode_enabled() -> bool:
    default = app_env() != "production"
    return _truthy("PAYMENT_TEST_MODE", default=default)


def webhook_secret_configured() -> bool:
    if bool(os.getenv("PAYMENT_WEBHOOK_SECRET", "").strip()):
        return True
    try:
        from src.services.stripe_orders import stripe_webhook_configured

        if stripe_webhook_configured():
            return True
    except Exception:
        pass
    try:
        from src.services.waffo_payment import waffo_webhook_configured

        if waffo_webhook_configured():
            return True
    except Exception:
        pass
    try:
        from src.services.waffo_pancake import pancake_webhook_configured

        return pancake_webhook_configured()
    except Exception:
        return False


def stripe_checkout_available() -> bool:
    try:
        from src.services.stripe_orders import stripe_configured

        return stripe_configured()
    except Exception:
        return False


def waffo_checkout_available() -> bool:
    try:
        from src.services.waffo_payment import waffo_configured

        return waffo_configured()
    except Exception:
        return False


def waffo_pancake_checkout_available() -> bool:
    try:
        from src.services.waffo_pancake import pancake_configured

        return pancake_configured()
    except Exception:
        return False


def payment_mode() -> str:
    """
    demo — 前端可点「支付完成」模拟开通（POC / 公网 Demo）
    webhook — 生产：仅服务端回调确认订单
    blocked — 生产但未配置回调且未开测试模式（应修复配置）
    """
    if payment_test_mode_enabled():
        return "demo"
    if app_env() == "production":
        return "webhook" if webhook_secret_configured() else "blocked"
    return "demo"


def deploy_profile() -> str:
    """
    development — 本地开发
    public_demo — 公网演示（Demo 账号和/或模拟支付）
    pilot — 生产环境试点（可仍用模拟支付，需显式标注）
    production — 生产收费（Webhook + 关 Demo 账号）
    """
    env = app_env()
    if env != "production":
        return "development"
    if payment_test_mode_enabled() or demo_accounts_enabled():
        if webhook_secret_configured() and not payment_test_mode_enabled():
            return "pilot"
        return "public_demo"
    if webhook_secret_configured():
        return "production"
    return "pilot"


def production_startup_warnings() -> List[str]:
    warnings: List[str] = []
    if app_env() != "production":
        return warnings

    secret = os.getenv("SECRET_KEY", "").strip()
    if not secret or secret == _DEV_SECRET:
        warnings.append("SECRET_KEY 未设置或仍为开发默认值")

    if demo_accounts_enabled():
        warnings.append("ALLOW_DEMO_ACCOUNTS 在生产环境仍为 true（仅适合公网 Demo）")

    if payment_test_mode_enabled():
        warnings.append("PAYMENT_TEST_MODE=true：支付为演示流程，不会产生真实扣款")

    if not payment_test_mode_enabled() and not webhook_secret_configured():
        warnings.append(
            "未配置 PAYMENT_WEBHOOK_SECRET 或 Stripe Webhook，且已关闭演示支付（用户无法完成订阅）"
        )

    if not os.getenv("INITIAL_ADMIN_PASSWORD", "").strip():
        warnings.append("建议设置 INITIAL_ADMIN_PASSWORD（首次初始化管理员）")

    return warnings


def payment_mode_message(mode: str | None = None) -> str:
    mode = mode or payment_mode()
    if mode == "demo":
        return "当前为演示支付流程，不会产生真实扣款。"
    if mode == "webhook":
        return "支付由服务端回调确认；完成扫码后请稍候，无需点击「支付完成」。"
    return "支付尚未配置：请联系销售开通试点或配置支付回调密钥。"


def commercial_status_payload() -> Dict[str, Any]:
    mode = payment_mode()
    profile = deploy_profile()
    warnings = production_startup_warnings()
    public_demo_url = os.getenv("PUBLIC_DEMO_BASE_URL", "").strip().rstrip("/")

    return {
        "app_env": app_env(),
        "deploy_profile": profile,
        "deploy_profile_label": {
            "development": "开发环境",
            "public_demo": "公网演示",
            "pilot": "生产试点",
            "production": "生产环境",
        }.get(profile, profile),
        "payment_mode": mode,
        "payment_test_mode": payment_test_mode_enabled(),
        "payment_message": payment_mode_message(mode),
        "demo_accounts_enabled": demo_accounts_enabled(),
        "webhook_configured": webhook_secret_configured(),
        "stripe_checkout_available": stripe_checkout_available(),
        "waffo_checkout_available": waffo_checkout_available() or waffo_pancake_checkout_available(),
        "waffo_pancake_checkout_available": waffo_pancake_checkout_available(),
        "public_demo_url": public_demo_url or None,
        "pilot_contact_email": os.getenv("PILOT_CONTACT_EMAIL", "sales@gameanalyzer.com").strip(),
        "data_trust_path": "/trust",
        "pricing_path": "/pricing",
        "production_warnings": warnings,
        "ready_for_paid_pilot": profile in ("pilot", "production")
        and mode in ("webhook", "demo")
        and not warnings,
    }
