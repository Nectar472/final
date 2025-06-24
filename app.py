import requests
import asyncio
import random
import time
from typing import Dict
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Encar Direct Proxy", version="2.1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROXY_CONFIGS = [
    {
        "name": "IPRoyal Korea Residential",
        "proxy": "geo.iproyal.com:11200",
        "auth": "oGKgjVaIooWADkOR:O8J73QYtjYWgQj4m_country-kr",
        "location": "South Korea",
        "provider": "iproyal",
    },
    {
        "name": "Oxylabs Korea Residential",
        "proxy": "pr.oxylabs.io:7777",
        "auth": "customer-admin_27be3-cc-KR:5e=JR+RsR829icd",
        "location": "South Korea",
        "provider": "oxylabs",
    },
]

def get_proxy_config(proxy_info):
    proxy_url = f"http://{proxy_info['auth']}@{proxy_info['proxy']}"
    return {"http": proxy_url, "https": proxy_url}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.78 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.61 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; rv:124.0) Gecko/20100101 Firefox/124.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 13; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.6367.78 Mobile Safari/537.36",
]

BASE_HEADERS = {
    "accept": "*/*",
    "accept-language": "en,ru;q=0.9",
    "origin": "https://cars.prokorea.trading",
    "referer": "https://cars.prokorea.trading/",
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"macOS"',
    "sec-fetch-dest": "empty",
    "sec-fetch-mode": "cors",
    "sec-fetch-site": "cross-site",
}

class EncarProxyClient:
    def __init__(self):
        self.session = requests.Session()
        self.current_proxy_index = 0
        self.request_count = 0
        self.last_request_time = 0
        self.session_rotation_count = 0
        self.session.timeout = (10, 30)
        self.session.max_redirects = 3
        self._rotate_proxy()

    def _get_dynamic_headers(self) -> Dict[str, str]:
        ua = random.choice(USER_AGENTS)
        headers = BASE_HEADERS.copy()
        headers["user-agent"] = ua
        headers["sec-ch-ua"] = '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"'
        return headers

    def _rotate_proxy(self):
        proxy_info = PROXY_CONFIGS[self.current_proxy_index % len(PROXY_CONFIGS)]
        self.session.proxies = get_proxy_config(proxy_info)
        self.current_proxy_index += 1
        logger.info(f"Switched to proxy: {proxy_info['name']} ({proxy_info['location']})")

    def _create_new_session(self):
        logger.info("Resetting session and rotating proxy...")
        self.session.close()
        self.session = requests.Session()
        self.session.timeout = (10, 30)
        self.session.max_redirects = 3
        self._rotate_proxy()
        self.session_rotation_count += 1

    def _rate_limit(self):
        now = time.time()
        if now - self.last_request_time < 0.5:
            time.sleep(0.5 - (now - self.last_request_time))
        self.last_request_time = time.time()
        if self.request_count % 15 == 0:
            self._rotate_proxy()
        if self.request_count % 50 == 0:
            self._create_new_session()
        self.request_count += 1

    async def make_request(self, url: str, max_retries: int = 3) -> Dict:
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_dynamic_headers()
                loop = asyncio.get_event_loop()
                response = await loop.run_in_executor(None, lambda: self.session.get(url, headers=headers))
                if response.status_code == 200:
                    return {"success": True, "status_code": 200, "text": response.text}
                elif response.status_code == 403:
                    self._create_new_session()
                    await asyncio.sleep(2)
                elif response.status_code == 407:
                    self._rotate_proxy()
                elif response.status_code in [429, 503]:
                    await asyncio.sleep(2 ** attempt)
                    self._rotate_proxy()
                else:
                    return {"success": False, "status_code": response.status_code, "text": response.text}
            except Exception as e:
                logger.error(f"Request failed: {e}")
                await asyncio.sleep(1)
        return {"success": False, "error": "Max retries exceeded"}

proxy_client = EncarProxyClient()

@app.get("/api/catalog")
async def proxy_catalog(q: str = Query(...), sr: str = Query(...)):
    url = f"https://api.encar.com/search/car/list?count=true&q={q}&sr={sr}"
    result = await proxy_client.make_request(url)
    if result.get("success"):
        try:
            parsed = json.loads(result["text"])
            return JSONResponse(content=parsed)
        except json.JSONDecodeError:
            return JSONResponse(status_code=502, content={"error": "Invalid JSON"})
    return JSONResponse(status_code=502, content=result)

@app.get("/health")
async def health():
    return {
        "status": "ok",
        "proxy_index": proxy_client.current_proxy_index,
        "request_count": proxy_client.request_count,
        "session_rotations": proxy_client.session_rotation_count,
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
