from app.config import load_config
from app.database import get_connection, init_db
from app.monitor import monitor_once


def run_single_poll():
    config = load_config()
    database_url = config["app"]["database_url"]

    conn = get_connection(database_url)
    try:
        init_db(conn)
        print("Starting single poll...")
        monitor_once(conn, config)
        print("Poll finished.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_single_poll()
