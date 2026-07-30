import os
import asyncio
from pathlib import Path

from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from config import load_config
from database import get_connection, init_db
from run_once import run_single_poll


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="DK Monitor")

_monitor_lock = asyncio.Lock()


def get_app_config():
    return load_config()


def get_db():
    config = get_app_config()
    db_path = config["app"]["db_path"]
    conn = get_connection(db_path)
    init_db(conn)
    return conn


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "DK Monitor",
        "status": "running",
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    """
    صفحه اصلی.
    اگر index.html قبلاً متغیر خاصی لازم داشته باشد، بعد از دیدن خطای template اصلاحش می‌کنیم.
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
        },
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_page(request: Request, product_id: str):
    """
    صفحه محصول.
    فعلاً حداقلی است تا template باز شود.
    اگر product.html متغیرهای خاصی لازم داشته باشد، بعداً دقیق هماهنگش می‌کنیم.
    """
    return templates.TemplateResponse(
        "product.html",
        {
            "request": request,
            "product_id": product_id,
        },
    )


@app.get("/trigger-monitor")
async def trigger_monitor(x_api_key: str | None = Header(default=None)):
    """
    این endpoint را cron-job.org صدا می‌زند.

    Header لازم:
    X-API-Key: مقدار CRON_SECRET در Render
    """

    expected_secret = os.getenv("CRON_SECRET")

    if not expected_secret:
        raise HTTPException(
            status_code=500,
            detail="CRON_SECRET is not configured on server",
        )

    if x_api_key != expected_secret:
        raise HTTPException(
            status_code=403,
            detail="Forbidden",
        )

    if _monitor_lock.locked():
        return JSONResponse(
            status_code=429,
            content={
                "ok": False,
                "detail": "Monitor job is already running",
            },
        )

    async with _monitor_lock:
        try:
            await run_in_threadpool(run_single_poll)
            return {
                "ok": True,
                "detail": "Monitor job finished successfully",
            }
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Monitor job failed: {e}",
            )
