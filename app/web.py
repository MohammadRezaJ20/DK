from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Form, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.config import load_config
from app.database import get_connection, init_db
from app.digikala import extract_product_id, fetch_product, parse_product
from app.monitor import upsert_product


BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title="Digikala Monitor Web")


def get_app_config() -> dict:
    config_path = BASE_DIR / "config.yaml"
    return load_config(str(config_path))


def require_api_key(x_api_key: str | None, config: dict) -> None:
    expected = config.get("security", {}).get("api_key", "")
    if expected:
        if not x_api_key or x_api_key != expected:
            raise HTTPException(status_code=401, detail="Invalid API key")


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


def parse_int_or_none(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip().replace(",", "")
    if not value:
        return None
    return int(value)


def parse_lines_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [line.strip() for line in value.splitlines() if line.strip()]


def build_conditions_from_form(
    max_price_toman: str = "",
    min_discount_percent: str = "",
    notify_on_price_drop_percent: str = "",
    min_stock_count: str = "",
    seller_names_include: str = "",
    seller_names_exclude: str = "",
    allowed_warranties: str = "",
    blocked_warranties: str = "",
    only_digikala_seller: str | None = None,
    notify_when_available: str | None = None,
    notify_when_unavailable: str | None = None,
    notify_on_any_price_change: str | None = None,
    notify_on_seller_change: str | None = None,
    notify_on_new_seller: str | None = None,
    notify_on_removed_seller: str | None = None,
    notify_on_discount_change: str | None = None,
) -> dict:
    conditions = {
        "max_price_toman": parse_int_or_none(max_price_toman),
        "min_discount_percent": parse_int_or_none(min_discount_percent),
        "notify_on_price_drop_percent": parse_int_or_none(notify_on_price_drop_percent),
        "min_stock_count": parse_int_or_none(min_stock_count),
        "seller_names_include": parse_lines_to_list(seller_names_include),
        "seller_names_exclude": parse_lines_to_list(seller_names_exclude),
        "allowed_warranties": parse_lines_to_list(allowed_warranties),
        "blocked_warranties": parse_lines_to_list(blocked_warranties),
        "only_digikala_seller": parse_bool(only_digikala_seller),
        "notify_when_available": parse_bool(notify_when_available),
        "notify_when_unavailable": parse_bool(notify_when_unavailable),
        "notify_on_any_price_change": parse_bool(notify_on_any_price_change),
        "notify_on_seller_change": parse_bool(notify_on_seller_change),
        "notify_on_new_seller": parse_bool(notify_on_new_seller),
        "notify_on_removed_seller": parse_bool(notify_on_removed_seller),
        "notify_on_discount_change": parse_bool(notify_on_discount_change),
    }

    return {k: v for k, v in conditions.items() if v not in (None, [], "")}


def normalize_conditions_for_form(conditions: dict | None) -> dict:
    conditions = conditions or {}
    return {
        "max_price_toman": conditions.get("max_price_toman", ""),
        "min_discount_percent": conditions.get("min_discount_percent", ""),
        "notify_on_price_drop_percent": conditions.get("notify_on_price_drop_percent", ""),
        "min_stock_count": conditions.get("min_stock_count", ""),
        "seller_names_include": "\n".join(conditions.get("seller_names_include", [])),
        "seller_names_exclude": "\n".join(conditions.get("seller_names_exclude", [])),
        "allowed_warranties": "\n".join(conditions.get("allowed_warranties", [])),
        "blocked_warranties": "\n".join(conditions.get("blocked_warranties", [])),
        "only_digikala_seller": conditions.get("only_digikala_seller", False),
        "notify_when_available": conditions.get("notify_when_available", True),
        "notify_when_unavailable": conditions.get("notify_when_unavailable", True),
        "notify_on_any_price_change": conditions.get("notify_on_any_price_change", False),
        "notify_on_seller_change": conditions.get("notify_on_seller_change", True),
        "notify_on_new_seller": conditions.get("notify_on_new_seller", True),
        "notify_on_removed_seller": conditions.get("notify_on_removed_seller", True),
        "notify_on_discount_change": conditions.get("notify_on_discount_change", True),
    }


def group_seller_snapshots(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = defaultdict(list)

    for row in rows:
        checked_at = row.get("checked_at") or "Unknown"
        grouped[checked_at].append(dict(row))

    result = []
    for checked_at, items in grouped.items():
        available_prices = [
            item.get("price_toman")
            for item in items
            if item.get("is_available") and item.get("price_toman") is not None
        ]
        best_price = min(available_prices) if available_prices else None

        result.append(
            {
                "checked_at": checked_at,
                "best_price_toman": best_price,
                "count": len(items),
                "items": sorted(
                    items,
                    key=lambda x: (
                        0 if x.get("is_available") else 1,
                        x.get("price_toman") if x.get("price_toman") is not None else 10**18,
                    ),
                ),
            }
        )

    result.sort(key=lambda x: x["checked_at"], reverse=True)
    return result


@app.on_event("startup")
def startup() -> None:
    config = get_app_config()
    conn = get_connection(config["database_path"])
    init_db(conn)
    conn.close()


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    config = get_app_config()
    conn = get_connection(config["database_path"])

    query = """
    SELECT
        p.product_id,
        p.url,
        p.custom_name,
        p.title,
        p.brand,
        p.category,
        p.active,
        p.conditions_json,
        ps.best_price_toman,
        ps.best_seller_name,
        ps.best_discount_percent,
        ps.is_available,
        ps.checked_at
    FROM products p
    LEFT JOIN product_snapshots ps
      ON ps.id = (
          SELECT id
          FROM product_snapshots
          WHERE product_id = p.product_id
          ORDER BY checked_at DESC, id DESC
          LIMIT 1
      )
    ORDER BY p.updated_at DESC, p.id DESC
    """
    rows = conn.execute(query).fetchall()
    conn.close()

    products = [dict(row) for row in rows]

    stats = {
        "total": len(products),
        "active": sum(1 for p in products if p.get("active") == 1),
        "discounted": sum(
            1 for p in products
            if (p.get("best_discount_percent") or 0) > 0
        ),
        "unavailable": sum(
            1 for p in products
            if p.get("is_available") == 0
        ),
    }

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "products": products,
            "stats": stats,
        },
    )


@app.get("/product/{product_id}", response_class=HTMLResponse)
def product_detail(request: Request, product_id: int):
    config = get_app_config()
    conn = get_connection(config["database_path"])

    product = conn.execute(
        """
        SELECT *
        FROM products
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()

    if not product:
        conn.close()
        raise HTTPException(status_code=404, detail="Product not found")

    snapshots = conn.execute(
        """
        SELECT *
        FROM product_snapshots
        WHERE product_id = ?
        ORDER BY checked_at DESC, id DESC
        """,
        (product_id,),
    ).fetchall()

    notifications = conn.execute(
        """
        SELECT *
        FROM notifications
        WHERE product_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (product_id,),
    ).fetchall()

    seller_snapshots = conn.execute(
        """
        SELECT *
        FROM seller_snapshots
        WHERE product_id = ?
        ORDER BY checked_at DESC, id DESC
        """,
        (product_id,),
    ).fetchall()

    conn.close()

    product_dict = dict(product)
    snapshots_list = [dict(row) for row in snapshots]
    notifications_list = [dict(row) for row in notifications]
    seller_snapshots_list = [dict(row) for row in seller_snapshots]

    try:
        conditions = json.loads(product_dict.get("conditions_json") or "{}")
    except json.JSONDecodeError:
        conditions = {}

    seller_groups = group_seller_snapshots(seller_snapshots_list)

    chart_labels = [row.get("checked_at") for row in reversed(snapshots_list)]
    chart_prices = [row.get("best_price_toman") for row in reversed(snapshots_list)]

    return templates.TemplateResponse(
        request=request,
        name="product.html",
        context={
            "request": request,
            "product": product_dict,
            "conditions": conditions,
            "snapshots": snapshots_list,
            "notifications": notifications_list,
            "seller_snapshots": seller_snapshots_list,
            "seller_groups": seller_groups,
            "chart_labels": chart_labels,
            "chart_prices": chart_prices,
        },
    )


@app.get("/product/{product_id}/edit", response_class=HTMLResponse)
def edit_product_page(request: Request, product_id: int):
    config = get_app_config()
    conn = get_connection(config["database_path"])

    product = conn.execute(
        """
        SELECT *
        FROM products
        WHERE product_id = ?
        """,
        (product_id,),
    ).fetchone()

    conn.close()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    product_dict = dict(product)

    try:
        conditions = json.loads(product_dict.get("conditions_json") or "{}")
    except json.JSONDecodeError:
        conditions = {}

    form_data = normalize_conditions_for_form(conditions)

    return templates.TemplateResponse(
        request=request,
        name="product_edit.html",
        context={
            "request": request,
            "product": product_dict,
            "form_data": form_data,
            "conditions_pretty": json.dumps(conditions, ensure_ascii=False, indent=2),
        },
    )


@app.post("/product", response_class=HTMLResponse)
def add_product(
    request: Request,
    product_url: str = Form(...),
    custom_name: str = Form(""),
    max_price_toman: str = Form(""),
    min_discount_percent: str = Form(""),
    notify_on_price_drop_percent: str = Form(""),
    min_stock_count: str = Form(""),
    seller_names_include: str = Form(""),
    seller_names_exclude: str = Form(""),
    allowed_warranties: str = Form(""),
    blocked_warranties: str = Form(""),
    only_digikala_seller: str | None = Form(None),
    notify_when_available: str | None = Form(None),
    notify_when_unavailable: str | None = Form(None),
    notify_on_any_price_change: str | None = Form(None),
    notify_on_seller_change: str | None = Form(None),
    notify_on_new_seller: str | None = Form(None),
    notify_on_removed_seller: str | None = Form(None),
    notify_on_discount_change: str | None = Form(None),
    x_api_key: str | None = Header(default=None),
):
    config = get_app_config()
    require_api_key(x_api_key, config)

    product_id = extract_product_id(product_url)
    if not product_id:
        raise HTTPException(status_code=400, detail="Invalid Digikala product URL")

    conditions = build_conditions_from_form(
        max_price_toman=max_price_toman,
        min_discount_percent=min_discount_percent,
        notify_on_price_drop_percent=notify_on_price_drop_percent,
        min_stock_count=min_stock_count,
        seller_names_include=seller_names_include,
        seller_names_exclude=seller_names_exclude,
        allowed_warranties=allowed_warranties,
        blocked_warranties=blocked_warranties,
        only_digikala_seller=only_digikala_seller,
        notify_when_available=notify_when_available,
        notify_when_unavailable=notify_when_unavailable,
        notify_on_any_price_change=notify_on_any_price_change,
        notify_on_seller_change=notify_on_seller_change,
        notify_on_new_seller=notify_on_new_seller,
        notify_on_removed_seller=notify_on_removed_seller,
        notify_on_discount_change=notify_on_discount_change,
    )

    with httpx.Client(timeout=30.0) as client:
        payload = fetch_product(client, product_id)
        snapshot = parse_product(product_id=product_id, url=product_url, payload=payload)

    conn = get_connection(config["database_path"])
    upsert_product(
        conn=conn,
        product_id=product_id,
        url=product_url,
        custom_name=custom_name.strip(),
        title=snapshot.title,
        brand=snapshot.brand,
        category=snapshot.category,
        conditions_json=json.dumps(conditions, ensure_ascii=False),
    )
    conn.commit()
    conn.close()

    return RedirectResponse(url="/", status_code=303)


@app.post("/product/{product_id}/edit", response_class=HTMLResponse)
def edit_product(
    request: Request,
    product_id: int,
    product_url: str = Form(...),
    custom_name: str = Form(""),
    active: str | None = Form(None),
    max_price_toman: str = Form(""),
    min_discount_percent: str = Form(""),
    notify_on_price_drop_percent: str = Form(""),
    min_stock_count: str = Form(""),
    seller_names_include: str = Form(""),
    seller_names_exclude: str = Form(""),
    allowed_warranties: str = Form(""),
    blocked_warranties: str = Form(""),
    only_digikala_seller: str | None = Form(None),
    notify_when_available: str | None = Form(None),
    notify_when_unavailable: str | None = Form(None),
    notify_on_any_price_change: str | None = Form(None),
    notify_on_seller_change: str | None = Form(None),
    notify_on_new_seller: str | None = Form(None),
    notify_on_removed_seller: str | None = Form(None),
    notify_on_discount_change: str | None = Form(None),
    x_api_key: str | None = Header(default=None),
):
    config = get_app_config()
    require_api_key(x_api_key, config)

    extracted_product_id = extract_product_id(product_url)
    if not extracted_product_id:
        raise HTTPException(status_code=400, detail="Invalid Digikala product URL")

    conditions = build_conditions_from_form(
        max_price_toman=max_price_toman,
        min_discount_percent=min_discount_percent,
        notify_on_price_drop_percent=notify_on_price_drop_percent,
        min_stock_count=min_stock_count,
        seller_names_include=seller_names_include,
        seller_names_exclude=seller_names_exclude,
        allowed_warranties=allowed_warranties,
        blocked_warranties=blocked_warranties,
        only_digikala_seller=only_digikala_seller,
        notify_when_available=notify_when_available,
        notify_when_unavailable=notify_when_unavailable,
        notify_on_any_price_change=notify_on_any_price_change,
        notify_on_seller_change=notify_on_seller_change,
        notify_on_new_seller=notify_on_new_seller,
        notify_on_removed_seller=notify_on_removed_seller,
        notify_on_discount_change=notify_on_discount_change,
    )

    with httpx.Client(timeout=30.0) as client:
        payload = fetch_product(client, extracted_product_id)
        snapshot = parse_product(
            product_id=extracted_product_id,
            url=product_url,
            payload=payload,
        )

    conn = get_connection(config["database_path"])

    upsert_product(
        conn=conn,
        product_id=product_id,
        url=product_url,
        custom_name=custom_name.strip(),
        title=snapshot.title,
        brand=snapshot.brand,
        category=snapshot.category,
        conditions_json=json.dumps(conditions, ensure_ascii=False),
    )

    conn.execute(
        """
        UPDATE products
        SET active = ?, updated_at = CURRENT_TIMESTAMP
        WHERE product_id = ?
        """,
        (1 if parse_bool(active) else 0, product_id),
    )

    conn.commit()
    conn.close()

    return RedirectResponse(url=f"/product/{product_id}", status_code=303)


@app.post("/product/{product_id}/delete", response_class=HTMLResponse)
def delete_product(
    product_id: int,
    x_api_key: str | None = Header(default=None),
):
    config = get_app_config()
    require_api_key(x_api_key, config)

    conn = get_connection(config["database_path"])
    conn.execute("DELETE FROM products WHERE product_id = ?", (product_id,))
    conn.commit()
    conn.close()

    return RedirectResponse(url="/", status_code=303)
