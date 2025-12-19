import os
import random
import string
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel


app = FastAPI(title="PaaS URL Shortener")

# -----------------------------
# Optional Redis (won't crash if not available)
# -----------------------------
USE_REDIS = True
r = None

try:
    import redis  # must be in requirements.txt

    REDIS_URL = os.getenv("REDIS_URL")
    if REDIS_URL:
        r = redis.from_url(REDIS_URL, decode_responses=True)
    else:
        # If you have Redis service, set these ENV vars
        r = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            decode_responses=True,
        )
except Exception:
    USE_REDIS = False
    r = None

# In-memory fallback storage
mem_url = {}
mem_count = {}

URL_KEY_PREFIX = "url:"
COUNT_KEY_PREFIX = "count:"
BASE_URL = os.getenv("BASE_URL", "").rstrip("/")  # optional


class URLInput(BaseModel):
    url: str


def gen_code(n: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(n))


def store_set(code: str, long_url: str) -> None:
    if USE_REDIS and r is not None:
        r.set(f"{URL_KEY_PREFIX}{code}", long_url)
        r.set(f"{COUNT_KEY_PREFIX}{code}", 0)
    else:
        mem_url[code] = long_url
        mem_count[code] = 0


def store_get_url(code: str) -> Optional[str]:
    if USE_REDIS and r is not None:
        return r.get(f"{URL_KEY_PREFIX}{code}")
    return mem_url.get(code)


def store_incr(code: str) -> None:
    if USE_REDIS and r is not None:
        r.incr(f"{COUNT_KEY_PREFIX}{code}")
    else:
        mem_count[code] = mem_count.get(code, 0) + 1


def store_get_count(code: str) -> int:
    if USE_REDIS and r is not None:
        val = r.get(f"{COUNT_KEY_PREFIX}{code}")
        return int(val or 0)
    return int(mem_count.get(code, 0))


@app.get("/")
def health():
    return {"status": "ok", "storage": "redis" if (USE_REDIS and r is not None) else "memory"}


@app.post("/shorten")
def shorten(payload: URLInput):
    long_url = payload.url.strip()

    if not (long_url.startswith("http://") or long_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # make unique code
    for _ in range(30):
        code = gen_code()
        if store_get_url(code) is None:
            store_set(code, long_url)
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique code")

    # if BASE_URL not set, return relative path too
    short_url = f"{BASE_URL}/{code}" if BASE_URL else f"/{code}"
    return {"code": code, "short_url": short_url, "url": long_url}


@app.get("/stats/{code}")
def stats(code: str):
    url = store_get_url(code)
    if not url:
        raise HTTPException(status_code=404, detail="Not found")
    return {"code": code, "url": url, "clicks": store_get_count(code)}


@app.get("/{code}")
def go(code: str):
    url = store_get_url(code)
    if not url:
        raise HTTPException(status_code=404, detail="Not found")
    store_incr(code)
    return RedirectResponse(url=url, status_code=307)


if __name__ == "__main__":
    import uvicorn

    # ParsPack usually expects 8000 (your panel shows port 8000)
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app:app", host="0.0.0.0", port=port, log_level="info")
