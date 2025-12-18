from fastapi import FastAPI
from pydantic import BaseModel
import redis
import os
import string
import random

app = FastAPI(title="PaaS URL Shortener with Analytics")

# Redis configuration (PaaS friendly)
REDIS_URL = os.getenv("REDIS_URL")

if REDIS_URL:
    r = redis.from_url(REDIS_URL, decode_responses=True)
else:
    r = redis.Redis(
        host=os.getenv("REDIS_HOST", "localhost"),
        port=int(os.getenv("REDIS_PORT", 6379)),
        password=os.getenv("REDIS_PASSWORD"),
        decode_responses=True
    )

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

class URLInput(BaseModel):
    url: str


def generate_code(length=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/shorten")
def shorten_url(data: URLInput):
    code = generate_code()
    r.set(f"url:{code}", data.url)
    r.set(f"count:{code}", 0)
    return {
        "short_url": f"{BASE_URL}/{code}",
        "code": code
    }


@app.get("/{code}")
def redirect_info(code: str):
    url = r.get(f"url:{code}")
    if not url:
        return {"error": "URL not found"}
    r.incr(f"count:{code}")
    return {
        "original_url": url,
        "message": "Redirect simulated (for demo)"
    }


@app.get("/stats/{code}")
def stats(code: str):
    url = r.get(f"url:{code}")
    count = r.get(f"count:{code}")
    if not url:
        return {"error": "URL not found"}
    return {
        "url": url,
        "clicks": int(count)
    }
