from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from typing import Optional, Dict, List
import json
import os

APP_ENV = os.getenv("APP_ENV", "development").lower()
SECRET_KEY = os.getenv("SECRET_KEY")
if APP_ENV == "production" and not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set when APP_ENV=production")
SECRET_KEY = SECRET_KEY or "dev-secret-key-change-me-before-production"
ALGORITHM = "HS256"
def _default_token_minutes() -> int:
    raw = os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "").strip()
    if raw.isdigit():
        return max(30, int(raw))
    return 120 if APP_ENV == "production" else 480


ACCESS_TOKEN_EXPIRE_MINUTES = _default_token_minutes()

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class User(BaseModel):
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    disabled: Optional[bool] = None
    role: str = "user"
    plan: str = "free"
    games_limit: int = 1
    api_quota: int = 1000

class UserInDB(User):
    hashed_password: str

class PlanConfig(BaseModel):
    name: str
    price: float
    games_limit: int
    api_quota: int
    features: List[str]
    description: str

PLANS: Dict[str, PlanConfig] = {
    "free": PlanConfig(
        name="免费版",
        price=0.0,
        games_limit=1,
        api_quota=1000,
        features=["基础指标监控", "1款游戏", "周报生成", "社区支持"],
        description="适合独立开发者体验"
    ),
    "pro": PlanConfig(
        name="专业版",
        price=2999.0,
        games_limit=10,
        api_quota=50000,
        features=["多平台数据", "AI分析", "预警系统", "10款游戏", "API访问", "邮件支持"],
        description="适合中型游戏公司"
    ),
    "enterprise": PlanConfig(
        name="企业版",
        price=0.0,
        games_limit=-1,
        api_quota=-1,
        features=["私有化部署", "定制开发", "专属客服", "无限游戏", "SLA保障", "高级安全"],
        description="适合大型厂商（定制报价）"
    )
}

LLM_PROVIDERS: Dict[str, Dict] = {
    "openai": {
        "name": "OpenAI GPT",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"],
        "default_model": "gpt-4o-mini",
        "color": "#10a37f"
    },
    "anthropic": {
        "name": "Claude (Anthropic)",
        "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229", "claude-3-haiku-20240307"],
        "default_model": "claude-3-5-sonnet-20241022",
        "color": "#d97706"
    },
    "azure": {
        "name": "Azure OpenAI",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4", "gpt-35-turbo"],
        "default_model": "gpt-4o-mini",
        "color": "#0078d4"
    },
    "gemini": {
        "name": "Google Gemini",
        "models": ["gemini-2.0-flash-exp", "gemini-1.5-pro", "gemini-1.5-flash"],
        "default_model": "gemini-2.0-flash-exp",
        "color": "#4285f4"
    },
    "ollama": {
        "name": "Ollama (本地)",
        "models": ["llama3.2", "llama3.1", "mistral", "qwen2.5"],
        "default_model": "llama3.2",
        "color": "#800080"
    }
}

LLM_CONFIG: Dict[str, Dict] = {
    "provider": "openai",
    "model": "gpt-4o-mini",
    "api_key": "",
    "endpoint": "",
    "temperature": 0.7,
    "max_tokens": 2000
}

def verify_password(plain_password, hashed_password):
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt
