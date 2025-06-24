from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict
from urllib.parse import quote
import logging
import json
import time
import random
import re
import httpx
import asyncio

app = FastAPI(title="Encar Proxy", version="1.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Proxy list
PROXY_CONFIGS = [
    {
        "name": "IPRoyal Korea Residential",
        "proxy": "geo.iproyal.com:11200",
        "auth": "tkYhzB2WFMzk6v7R:yH0EdPksqTLURsF2_country-kr",
        "location": "South Korea",
        "provider": "iproyal",
    },
    {
        "name": "Oxylabs Korea Residential",
        "proxy": "pr.oxylabs.io:7777",
        "auth": "customer-adapt_Yf2Vn-cc-kr:2NUmsvXdgsc+tm5",
        "location": "South Korea",
        "provider": "oxylabs",
    },
]

# User agents
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64)...",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_2)...",
    # и так далее...
]

# Прокси клиент
class EncarProxyClient:
    def __init__(self):
        self.current_proxy_index = 0
        self.request_count = 0
        self.last_request_time = 0

    def _get_headers(self) -> Dict[str, str]:
        ua = random.choice(USER_AGENTS)
        headers = {
            "accept": "application/json",
            "referer": "http://www.encar.com/",
            "origin": "http://www.encar.com",
            "user-agent": ua,
        }
        return headers

    def _rotate_proxy(self):
        proxy_info = PROXY_CONFIGS[self.current_proxy_index % len(PROXY_CONFIGS)]
        self.current_proxy_index += 1
        return proxy_info

    def _rate_limit(self):
        now = time.time()
        if now - self.last_request_time < 0.5:
            time.sleep(0.5 - (now - self.last_request_time))
        self.last_request_time = time.time()
        self.request_count += 1

    async def make_request(self, url: str, max_retries: int = 5) -> Dict:
        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_headers()
                proxy_info = self._rotate_proxy()
                proxy_url = f"http://{proxy_info['auth']}@{proxy_info['proxy']}"

                transport = httpx.AsyncHTTPTransport(proxy=proxy_url)

                async with httpx.AsyncClient(transport=transport, timeout=30) as client:
                    response = await client.get(url, headers=headers)

                if response.status_code == 200:
                    return {"success": True, "status_code": 200, "text": response.text}
                elif response.status_code in [403, 429, 503]:
                    await asyncio.sleep(5)
                else:
                    return {"success": False, "status_code": response.status_code, "text": response.text}
            except Exception as e:
                logging.error(f"Request failed: {type(e).__name__}: {e}")
                await asyncio.sleep(3)

        return {"success": False, "error": "Max retries exceeded"}

proxy_client = EncarProxyClient()

@app.get("/api/catalog")
async def proxy_catalog(q: str = Query(...), inav: str = Query(...)):
    encoded_q = quote(q, safe="()_.")
    encoded_inav = quote(inav, safe="|")
    url = f"https://api.encar.com/search/car/list/general?count=true&q={encoded_q}&inav={encoded_inav}"

    result = await proxy_client.make_request(url)

    if result.get("success"):
        try:
            data = json.loads(result["text"])
            return JSONResponse(content=data)
        except json.JSONDecodeError:
            return JSONResponse(status_code=502, content={"error": "Invalid JSON"})
    return JSONResponse(status_code=502, content=result)

@app.get("/")
async def root():
    return {"message": "Proxy is working. Use /api/catalog?q=...&inav=..."}

