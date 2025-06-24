from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from urllib.parse import urlencode
import logging
import json

# Твой клиент EncarProxyClient импортируем
from proxy_client import EncarProxyClient  # имя файла с клиентом

app = FastAPI(title="Encar Proxy", version="1.0")

# CORS на всякий случай
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")

proxy_client = EncarProxyClient()

@app.get("/api/catalog")
async def proxy_catalog(q: str = Query(...), inav: str = Query(...)):
    params = {
        "count": "true",
        "q": q,
        "inav": inav
    }

    # Корректное кодирование (safe символы не трогаем)
    encoded_url = f"https://api.encar.com/search/car/list/general?{urlencode(params, safe='()_.|')}"
    logger.info(f"Encoded URL: {encoded_url}")

    result = await proxy_client.make_request(encoded_url)

    if result.get("success"):
        try:
            parsed = json.loads(result["text"])
            return JSONResponse(content=parsed)
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received: {result['text'][:300]}")
            return JSONResponse(status_code=502, content={"error": "Invalid JSON"})

    logger.warning(f"Request failed. Status: {result.get('status_code')}, Text: {result.get('text', '')[:300]}")
    return JSONResponse(status_code=502, content=result)

@app.get("/health")
async def health():
    return {"status": "ok"}
