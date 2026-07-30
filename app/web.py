import os
import asyncio
import json
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.config import load_config
from app.database import get_connection, init_db
from app.digikala import (
    extract_product_id,
    fetch_product,
    parse_product,
)
from app.monitor import upsert_product
from run_once import run_single_poll


app = FastAPI(
    title="DK Monitor",
    version="1.0.0",
)


# ---------------------------------------------------------
# Paths and database initialization
# ---------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent.parent

templates = Jinja2Templates(
    directory=str(BASE_DIR / "templates")
)

config = load_config()

# اتصال اصلی فعلی برنامه برای نمایش صفحات
conn = get_connection(config["app"]["db_path"])
init_db(conn)

_monitor_lock = asyncio.Lock()


# ---------------------------------------------------------
# Request models
# ---------------------------------------------------------

class AddProductRequest(BaseModel):
    """
    JSON body accepted by POST /add-product
    """

    url: str = Field(
        ...,
        min_length=10,
        description="Digikala product URL",
    )

    name: str | None = Field(
        default=None,
        description="Optional custom name for the product",
    )

    max_price: int | None = Field(
        default=None,
        ge=0,
        description="Maximum acceptable price in toman",
    )

    min_discount: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description="Minimum acceptable discount percentage",
    )

    only_digikala_seller: bool = Field(
        default=False,
        description="Accept only Digikala seller",
    )


# ---------------------------------------------------------
# Authentication helper
# ---------------------------------------------------------

def verify_api_key(x_api_key: str | None) -> None:
    """
    Validate the x-api-key header against CRON_SECRET.
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


# ---------------------------------------------------------
# Product creation helper
# ---------------------------------------------------------

def add_product_to_database(
    request_data: AddProductRequest,
) -> dict[str, Any]:
    """
    Fetch product data from Digikala and insert/update it in SQLite.

    This function is synchronous because the existing Digikala functions
    use httpx.Client and the existing database layer is synchronous.
    It is executed in a threadpool by the FastAPI endpoint.
    """

    current_config = load_config()

    db_path = current_config["app"]["db_path"]
    timeout_seconds = current_config["app"].get(
        "request_timeout_seconds",
        20,
    )

    # Extract Digikala product ID from submitted URL
    try:
        product_id = extract_product_id(request_data.url)
    except Exception as exc:
        raise ValueError(
            "Could not extract product ID from the submitted URL"
        ) from exc

    if not product_id:
        raise ValueError(
            "The submitted URL does not contain a valid Digikala product ID"
        )

    # Fetch and parse product information
    try:
        with httpx.Client(
            timeout=timeout_seconds,
            follow_redirects=True,
        ) as client:
            payload = fetch_product(
                client,
                product_id,
            )

        snapshot = parse_product(
            product_id,
            request_data.url,
            payload,
        )

    except httpx.HTTPStatusError as exc:
        raise RuntimeError(
            f"Digikala returned HTTP {exc.response.status_code}"
        ) from exc

    except httpx.RequestError as exc:
        raise RuntimeError(
            f"Could not connect to Digikala: {exc}"
        ) from exc

    # Start with configured default conditions
    defaults = current_config.get("defaults", {})
    conditions = dict(
        defaults.get("conditions", {})
    )

    # Override defaults when values are supplied by the user
    if request_data.max_price is not None:
        conditions["max_price_toman"] = request_data.max_price

    if request_data.min_discount is not None:
        conditions["min_discount_percent"] = request_data.min_discount

    if request_data.only_digikala_seller:
        conditions["only_digikala_seller"] = True

    # Use an independent connection for this request.
    # This is safer than sharing the global web connection
    # inside the threadpool.
    product_conn = get_connection(db_path)

    try:
        init_db(product_conn)

        upsert_product(
            conn=product_conn,
            product_id=product_id,
            url=request_data.url,
            custom_name=request_data.name,
            title=snapshot.title,
            brand=snapshot.brand,
            category=snapshot.category,
            conditions_json=json.dumps(
                conditions,
                ensure_ascii=False,
            ),
        )

        product_conn.commit()

    finally:
        product_conn.close()

    return {
        "product_id": product_id,
        "title": snapshot.title,
        "brand": snapshot.brand,
        "category": snapshot.category,
        "conditions": conditions,
    }


# ---------------------------------------------------------
# Web pages
# ---------------------------------------------------------

@app.get(
    "/",
    response_class=HTMLResponse,
)
def index(request: Request):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT p.*,
               (
                   SELECT best_price_toman
                   FROM product_snapshots ps
                   WHERE ps.product_id = p.product_id
                   ORDER BY ps.id DESC
                   LIMIT 1
               ) AS best_price_toman,
               (
                   SELECT best_seller_name
                   FROM product_snapshots ps
                   WHERE ps.product_id = p.product_id
                   ORDER BY ps.id DESC
                   LIMIT 1
               ) AS best_seller_name,
               (
                   SELECT is_available
                   FROM product_snapshots ps
                   WHERE ps.product_id = p.product_id
                   ORDER BY ps.id DESC
                   LIMIT 1
               ) AS is_available,
               (
                   SELECT checked_at
                   FROM product_snapshots ps
                   WHERE ps.product_id = p.product_id
                   ORDER BY ps.id DESC
                   LIMIT 1
               ) AS checked_at
        FROM products p
        ORDER BY p.id ASC
        """
    )

    products = cur.fetchall()

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "products": products,
        },
    )


@app.get(
    "/product/{product_id}",
    response_class=HTMLResponse,
)
def product_detail(
    request: Request,
    product_id: int,
):
    cur = conn.cursor()

    cur.execute(
        """
        SELECT *
        FROM products
        WHERE product_id = ?
        """,
        (product_id,),
    )
    product = cur.fetchone()

    cur.execute(
        """
        SELECT
            checked_at,
            best_price_toman,
            best_seller_name,
            best_discount_percent,
            is_available
        FROM product_snapshots
        WHERE product_id = ?
        ORDER BY id ASC
        """,
        (product_id,),
    )
    history = cur.fetchall()

    cur.execute(
        """
        SELECT *
        FROM notifications
        WHERE product_id = ?
        ORDER BY id DESC
        LIMIT 50
        """,
        (product_id,),
    )
    notifications = cur.fetchall()

    cur.execute(
        """
        SELECT *
        FROM seller_snapshots
        WHERE product_id = ?
        ORDER BY id DESC
        LIMIT 100
        """,
        (product_id,),
    )
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


# ---------------------------------------------------------
# Health check
# ---------------------------------------------------------

@app.get("/health")
def health():
    return {
        "ok": True,
        "service": "DK Monitor",
        "status": "running",
    }


# ---------------------------------------------------------
# Add product API
# ---------------------------------------------------------

@app.post("/add-product")
async def add_product_api(
    request_data: AddProductRequest,
    x_api_key: str | None = Header(default=None),
):
    """
    Add or update a Digikala product.

    Authentication:
        x-api-key: value of CRON_SECRET
    """

    verify_api_key(x_api_key)

    try:
        result = await run_in_threadpool(
            add_product_to_database,
            request_data,
        )

        return {
            "ok": True,
            "detail": "Product added successfully",
            **result,
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not add product: {exc}",
        ) from exc


# ---------------------------------------------------------
# Monitor trigger API
# ---------------------------------------------------------

@app.get("/trigger-monitor")
async def trigger_monitor(
    x_api_key: str | None = Header(default=None),
):
    verify_api_key(x_api_key)

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
            await run_in_threadpool(
                run_single_poll
            )

            return {
                "ok": True,
                "detail": "Monitor job finished successfully",
            }

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Monitor job failed: {exc}",
            ) from exc
