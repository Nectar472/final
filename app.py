import asyncio
import time
import json
import re
import random
from typing import Dict
from urllib.parse import quote

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

app = FastAPI(title="Encar Proxy")

# CORS
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
        "auth": "tkYhzB2WFMzk6v7R:yH0EdPksqTLURsF2_country-kr",
    },
    {
        "name": "Oxylabs Korea Residential",
        "proxy": "pr.oxylabs.io:7777",
        "auth": "customer-adapt_Yf2Vn-cc-kr:2NUmsvXdgsc+tm5",
    }
]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.113 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.6422.61 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15"
]

class EncarProxyClient:
    def __init__(self):
        self.proxy_index = 0
        self.request_count = 0
        self.last_request_time = 0

    def _rotate_proxy(self) -> Dict:
        proxy = PROXY_CONFIGS[self.proxy_index % len(PROXY_CONFIGS)]
        self.proxy_index += 1
        logger.info(f"Using proxy: {proxy['name']}")
        return proxy

    def _get_headers(self) -> Dict[str, str]:
        ua = random.choice(USER_AGENTS)
        chrome_match = re.search(r"Chrome/(\d+)", ua)
        chrome_version = chrome_match.group(1) if chrome_match else "125"
        return {
            "accept": "application/json, text/javascript, */*; q=0.01",
            "accept-encoding": "gzip, deflate, br",
            "accept-language": "ko-KR,ko;q=0.9",
            "origin": "http://www.encar.com",
            "referer": "http://www.encar.com/",
            "user-agent": ua,
            "sec-ch-ua": f'"Google Chrome";v="{chrome_version}", "Chromium";v="{chrome_version}", "Not.A/Brand";v="24"',
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "cross-site",
        }

    async def make_request(self, url: str) -> Dict:
        self.request_count += 1
        if time.time() - self.last_request_time < 0.5:
            await asyncio.sleep(0.5)
        self.last_request_time = time.time()

        proxy = self._rotate_proxy()
        proxy_url = f"http://{proxy['auth']}@{proxy['proxy']}"
        transport = httpx.AsyncHTTPTransport(proxy=proxy_url)

        try:
            async with httpx.AsyncClient(timeout=30, transport=transport) as client:
                response = await client.get(url, headers=self._get_headers())

            logger.info(f"HTTP Request: {url} \"{response.status_code}\"")

            if response.status_code == 200:
                return {"success": True, "status_code": 200, "text": response.text}
            else:
                return {"success": False, "status_code": response.status_code, "text": response.text}
        except Exception as e:
            logger.warning(f"Proxy request error: {type(e).__name__}: {e}")
            return {"success": False, "status_code": None, "text": str(e)}

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
            logger.error("Invalid JSON from Encar.")
            return JSONResponse(status_code=502, content={"error": "Invalid JSON from Encar."})
    else:
        logger.warning(f"Encar request failed. Status: {result.get('status_code')}")
        return JSONResponse(status_code=502, content=result)

@app.get("/health")
async def health():
    return {"status": "ok", "requests": proxy_client.request_count}
