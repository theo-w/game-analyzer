import os
import asyncio
import requests
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json
import hashlib


class DataCollector:
    """游戏数据采集器 - 支持Steam、Google Play和App Store"""
    
    def __init__(self):
        self._load_config_from_db()
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'GameAnalyzer/1.0',
            'Accept': 'application/json'
        })
    
    def _load_config_from_db(self):
        """从数据库加载API配置"""
        # 先初始化默认值
        self._load_default_config()
        
        try:
            from src.database import DataSourceConfigRepository
            configs = DataSourceConfigRepository.get_all()
            
            for config in configs:
                platform = config.get('platform')
                if platform == 'steam':
                    self.steam_api_key = config.get('api_key', '')
                elif platform == 'google_play':
                    self.google_credentials = config.get('credentials', '')
                    self.google_endpoint = config.get('endpoint', '')
                elif platform == 'app_store':
                    self.appstore_key_id = config.get('key_id', '')
                    self.appstore_issuer_id = config.get('issuer_id', '')
                    self.appstore_private_key = config.get('private_key', '')
                    self.appstore_endpoint = config.get('endpoint', '')
        except Exception as e:
            print(f"Failed to load config from DB, using defaults: {e}")
    
    def _load_default_config(self):
        """加载默认配置"""
        self.steam_api_key = os.getenv('STEAM_API_KEY', '')
        self.google_credentials = os.getenv('GOOGLE_PLAY_CREDENTIALS', '')
        self.google_endpoint = os.getenv('GOOGLE_PLAY_ENDPOINT', '')
        self.appstore_key_id = os.getenv('APPSTORE_KEY_ID', '')
        self.appstore_issuer_id = os.getenv('APPSTORE_ISSUER_ID', '')
        self.appstore_private_key = os.getenv('APPSTORE_PRIVATE_KEY', '')
        self.appstore_endpoint = os.getenv('APPSTORE_ENDPOINT', '')
    
    async def fetch_steam_data(self, app_id: str = None) -> Dict[str, Any]:
        """从Steam获取游戏数据"""
        if not self.steam_api_key:
            return self._generate_mock_data('steam', app_id)
        
        try:
            url = 'https://api.steampowered.com/ISteamNews/GetNewsForApp/v0002/'
            params = {
                'appid': app_id,
                'count': 20,
                'format': 'json',
                'key': self.steam_api_key
            }
            
            response = await self._make_request(url, params=params)
            
            if response:
                return {
                    "success": True,
                    "platform": "steam",
                    "app_id": app_id,
                    "news_count": len(response.get('appnews', {}).get('news_items', [])),
                    "last_update": datetime.now().isoformat(),
                    "source": "steam_api"
                }
        except Exception as e:
            print(f"Steam API Error: {e}")
        
        return self._generate_mock_data('steam', app_id)
    
    async def fetch_google_play_data(self, package_name: str = None) -> Dict[str, Any]:
        """从Google Play获取游戏数据"""
        if not self.google_credentials:
            return self._generate_mock_data('google_play', package_name)
        
        try:
            url = f'https://playconsole.googleapis.com/api/developerData'
            headers = {'Authorization': f'Bearer {self.google_credentials}'}
            
            response = await self._make_request(url, headers=headers)
            
            if response:
                return {
                    "success": True,
                    "platform": "google_play",
                    "package_name": package_name,
                    "data": response,
                    "last_update": datetime.now().isoformat(),
                    "source": "google_play_api"
                }
        except Exception as e:
            print(f"Google Play API Error: {e}")
        
        return self._generate_mock_data('google_play', package_name)
    
    async def fetch_app_store_data(self, app_id: str = None) -> Dict[str, Any]:
        """从App Store获取游戏数据"""
        if not self.appstore_key_id:
            return self._generate_mock_data('app_store', app_id)
        
        try:
            token = await self._generate_app_store_token()
            if not token:
                return self._generate_mock_data('app_store', app_id)
            
            url = f'https://api.appstoreconnect.apple.com/v1/apps/{app_id}/analytics'
            headers = {
                'Authorization': f'Bearer {token}',
                'X-Apple-Id-Organization-Id': self.appstore_issuer_id
            }
            
            response = await self._make_request(url, headers=headers)
            
            if response:
                return {
                    "success": True,
                    "platform": "app_store",
                    "app_id": app_id,
                    "data": response,
                    "last_update": datetime.now().isoformat(),
                    "source": "app_store_api"
                }
        except Exception as e:
            print(f"App Store API Error: {e}")
        
        return self._generate_mock_data('app_store', app_id)
    
    async def _make_request(self, url: str, method: str = 'GET', 
                           params: Dict = None, headers: Dict = None,
                           data: Dict = None, timeout: int = 10) -> Optional[Dict]:
        """通用HTTP请求方法"""
        try:
            loop = asyncio.get_event_loop()
            
            def _request():
                if method == 'GET':
                    return self.session.get(url, params=params, headers=headers, timeout=timeout)
                elif method == 'POST':
                    return self.session.post(url, json=data, headers=headers, timeout=timeout)
                return None
            
            response = await loop.run_in_executor(None, _request)
            
            if response.status_code == 200:
                return response.json()
            else:
                print(f"Request failed with status {response.status_code}: {url}")
                return None
        except Exception as e:
            print(f"Request error: {e}")
            return None
    
    async def _generate_app_store_token(self) -> Optional[str]:
        """生成App Store API Token"""
        if not all([self.appstore_key_id, self.appstore_issuer_id, self.appstore_private_key]):
            return None
        
        try:
            import jwt
            payload = {
                'iss': self.appstore_issuer_id,
                'exp': datetime.utcnow() + timedelta(hours=1),
                'aud': 'appstoreconnect-v1'
            }
            token = jwt.encode(payload, self.appstore_private_key, algorithm='ES256')
            return token
        except Exception as e:
            print(f"App Store token generation error: {e}")
            return None
    
    def _generate_mock_data(self, platform: str, identifier: str = None) -> Dict[str, Any]:
        """生成模拟数据"""
        import random
        
        base_data = {
            "success": False,
            "platform": platform,
            "identifier": identifier,
            "mock": True,
            "last_update": datetime.now().isoformat()
        }
        
        if platform == 'steam':
            return {
                **base_data,
                "metrics": {
                    "players": random.randint(100, 10000),
                    "concurrent_players": random.randint(50, 5000),
                    "reviews": random.randint(100, 5000),
                    "score": round(random.uniform(7.0, 9.5), 1)
                }
            }
        elif platform == 'google_play':
            return {
                **base_data,
                "metrics": {
                    "installs": random.randint(10000, 1000000),
                    "rating": round(random.uniform(3.5, 5.0), 1),
                    "reviews": random.randint(100, 5000),
                    "active_users": random.randint(1000, 100000)
                }
            }
        elif platform == 'app_store':
            return {
                **base_data,
                "metrics": {
                    "downloads": random.randint(10000, 500000),
                    "rating": round(random.uniform(3.5, 5.0), 1),
                    "reviews": random.randint(100, 3000),
                    "revenue": random.randint(10000, 500000)
                }
            }
        
        return base_data
    
    async def collect_all_products(self, products: List[Dict]) -> List[Dict]:
        """批量采集所有产品数据"""
        tasks = []
        
        for product in products:
            platform = product.get('platform', 'steam')
            app_id = product.get('app_id') or product.get('package_name') or product.get('identifier')
            
            if platform == 'steam':
                tasks.append(self.fetch_steam_data(app_id))
            elif platform == 'google_play':
                tasks.append(self.fetch_google_play_data(app_id))
            elif platform == 'app_store':
                tasks.append(self.fetch_app_store_data(app_id))
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return [r if not isinstance(r, Exception) else {"error": str(r)} for r in results]
    
    async def schedule_data_collection(self, products: List[Dict], interval_hours: int = 6):
        """定时数据采集"""
        while True:
            print(f"Starting scheduled data collection at {datetime.now()}")
            results = await self.collect_all_products(products)
            
            collected_count = sum(1 for r in results if r.get('success', False))
            print(f"Collected data for {collected_count}/{len(products)} products")
            
            await asyncio.sleep(interval_hours * 3600)
    
    def validate_api_keys(self) -> Dict[str, bool]:
        """验证API密钥配置"""
        return {
            "steam": bool(self.steam_api_key),
            "google_play": bool(self.google_credentials),
            "app_store": all([self.appstore_key_id, self.appstore_issuer_id, self.appstore_private_key])
        }
    
    def get_configuration_instructions(self) -> Dict[str, str]:
        """获取API配置说明"""
        return {
            "steam": """
            Steam API Key Configuration:
            1. Visit https://steamcommunity.com/dev/apikey
            2. Login with your Steam account
            3. Create a new API key for your domain
            4. Set the environment variable: export STEAM_API_KEY='your_key'
            """,
            "google_play": """
            Google Play Developer API Configuration:
            1. Go to Google Cloud Console
            2. Enable Google Play Developer API
            3. Create OAuth 2.0 credentials
            4. Download the credentials JSON file
            5. Set the environment variable: export GOOGLE_PLAY_CREDENTIALS='path_to_credentials.json'
            """,
            "app_store": """
            App Store Connect API Configuration:
            1. Go to App Store Connect
            2. Create an API key in Users and Access
            3. Note your Key ID and Issuer ID
            4. Download the private key
            5. Set environment variables:
               export APPSTORE_KEY_ID='your_key_id'
               export APPSTORE_ISSUER_ID='your_issuer_id'
               export APPSTORE_PRIVATE_KEY='your_private_key'
            """
        }


data_collector = DataCollector()
