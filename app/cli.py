import argparse
import json
import httpx

from app.config import load_config
from app.database import get_connection, init_db
from app.digikala import extract_product_id, fetch_product, parse_product
from app.monitor import upsert_product


def add_product(args):
    config = load_config()
    conn = get_connection(config["app"]["database_url"])
    init_db(conn)

    product_id = extract_product_id(args.url)

    conditions = config["defaults"]["conditions"].copy()
    if args.max_price is not None:
        conditions["max_price_toman"] = args.max_price
    if args.min_discount is not None:
        conditions["min_discount_percent"] = args.min_discount
    if args.only_digikala_seller:
        conditions["only_digikala_seller"] = True

    with httpx.Client(timeout=config["app"]["request_timeout_seconds"]) as client:
        payload = fetch_product(client, product_id)
        snapshot = parse_product(product_id, args.url, payload)

    upsert_product(
        conn=conn,
        product_id=product_id,
        url=args.url,
        custom_name=args.name,
        title=snapshot.title,
        brand=snapshot.brand,
        category=snapshot.category,
        conditions_json=json.dumps(conditions, ensure_ascii=False),
    )

    print("Product added successfully:")
    print(f"product_id: {product_id}")
    print(f"title: {snapshot.title}")
    print(f"brand: {snapshot.brand}")
    print(f"category: {snapshot.category}")
    print("conditions:")
    print(json.dumps(conditions, ensure_ascii=False, indent=2))


def list_products(args):
    config = load_config()
    conn = get_connection(config["app"]["database_url"])
    init_db(conn)
    cur = conn.cursor()
    cur.execute("SELECT * FROM products ORDER BY id ASC")
    rows = cur.fetchall()

    for row in rows:
        print(f"[{row['id']}] product_id={row['product_id']} active={row['active']} title={row['title']}")


def build_parser():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command")

    add_cmd = sub.add_parser("add")
    add_cmd.add_argument("url")
    add_cmd.add_argument("--name", default=None)
    add_cmd.add_argument("--max-price", type=int, default=None)
    add_cmd.add_argument("--min-discount", type=int, default=None)
    add_cmd.add_argument("--only-digikala-seller", action="store_true")
    add_cmd.set_defaults(func=add_product)

    list_cmd = sub.add_parser("list")
    list_cmd.set_defaults(func=list_products)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
