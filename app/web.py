from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from config import load_config
from database import get_connection, init_db

app = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

config = load_config()
conn = get_connection(config["app"]["db_path"])
init_db(conn)


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
