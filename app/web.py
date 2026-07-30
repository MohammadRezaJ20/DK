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

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

config = load_config()
conn = get_connection(config["app"]["db_path"])
init_db(conn)

_monitor_lock = asyncio.Lock()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    cur = conn.cursor()
    cur.execute("""
    SELECT p.*,
           (SELECT best_price_toman FROM product_snapshots ps WHERE ps.product_id = p.product_id ORDER BY ps.id DESC LIMIT 1) AS best_price_toman,
           (SELECT best_seller_name FROM product_snapshots ps WHERE ps.product_id = p.product_id ORDER BY ps.id DESC LIMIT 1) AS best_seller_name,
           (SELECT is_available FROM product_snapshots ps WHERE ps.product_id = p.product_id ORDER BY ps.id DESC LIMIT 1) AS is_available,
           (SELECT checked_at FROM product_snapshots ps WHERE ps.product_id = p.product_id ORDER BY ps.id DESC LIMIT 1) AS checked_at
    FROM products p
    ORDER BY p.id ASC
    """)
    products = cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"request": request, "products": products},
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    cur = conn.cursor()

    cur.execute("SELECT * FROM products WHERE product_id = ?", (product_id,))
    product = cur.fetchone()

    cur.execute("""
    SELECT checked_at, best_price_toman, best_seller_name, best_discount_percent, is_available
    FROM product_snapshots
    WHERE product_id = ?
    ORDER BY id ASC
    """, (product_id,))
    history = cur.fetchall()

    cur.execute("""
    SELECT * FROM notifications
    WHERE product_id = ?
    ORDER BY id DESC
    LIMIT 50
    """, (product_id,))
    notifications = cur.fetchall()

    cur.execute("""
    SELECT * FROM seller_snapshots
    WHERE product_id = ?
    ORDER BY id DESC
    LIMIT 100
    """, (product_id,))
    seller_rows = cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="product.html",
        context={
            "request": request,
            "product": product,
            "history": history,
            "notifications": notifications,
            "seller_rows": seller_rows,
        },
    )


@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "DK Monitor",
        "status": "running",
    }


@app.get("/trigger-monitor")
async def trigger_monitor(x_api_key: str | None = Header(default=None)):
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
