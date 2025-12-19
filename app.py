import os
import random
import string

import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


app = FastAPI(title="PaaS URL Shortener with Analytics")

# -------------------------
# Redis configuration (PaaS-friendly)
# -------------------------
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    r = redis.from_url(REDIS_URL, decode_responses=True)
else:
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", "6379")),
        password=os.getenv("REDIS_PASSWORD") or None,
        decode_responses=True,
    )

# Base URL for showing short links (optional; ParsPack gives domain)
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# Prefix keys
URL_KEY_PREFIX = "url:"
COUNT_KEY_PREFIX = "count:"


class URLInput(BaseModel):
    url: str


def generate_code(length: int = 6) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(random.choice(alphabet) for _ in range(length))


@app.get("/")
def health():
    return {"status": "ok", "service": "url-shortener"}


@app.post("/shorten")
def shorten(data: URLInput):
    long_url = data.url.strip()
    if not (long_url.startswith("http://") or long_url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")

    # generate unique code
    for _ in range(10):
        code = generate_code()
        if not r.get(f"{URL_KEY_PREFIX}{code}"):
            break
    else:
        raise HTTPException(status_code=500, detail="Could not generate unique code")

    r.set(f"{URL_KEY_PREFIX}{code}", long_url)
    r.set(f"{COUNT_KEY_PREFIX}{code}", 0)

    return {
        "code": code,
        "short_url": f"{BASE_URL.rstrip('/')}/{code}",
    }


@app.get("/{code}")
def redirect(code: str):
    long_url = r.get(f"{URL_KEY_PREFIX}{code}")
    if not long_url:
        raise HTTPException(status_code=404, detail="URL not found")

    r.incr(f"{COUNT_KEY_PREFIX}{code}")

    # Redirect response
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url=long_url, status_code=307)


@app.get("/stats/{code}")
def stats(code: str):
    long_url = r.get(f"{URL_KEY_PREFIX}{code}")
    if not long_url:
        raise HTTPException(status_code=404, detail="URL not found")

    count = r.get(f"{COUNT_KEY_PREFIX}{code}") or "0"
    return {"code": code, "url": long_url, "clicks": int(count)}


# -------------------------
# IMPORTANT: Run on 0.0.0.0 and correct port for ParsPack
# -------------------------
if __name__ == "__main__":
    import uvicorn

    # ParsPack usually exposes port 8000 (as you saw). But we still read env if exists.
    port = int(os.getenv("PORT", "8000"))

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
    )
