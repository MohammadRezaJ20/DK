from config import load_config
from database import get_connection, init_db
from monitor import monitor_once


def run_single_poll():
    config = load_config()
    db_path = config["app"]["db_path"]

    conn = get_connection(db_path)
    try:
        init_db(conn)

        # فقط یک بار اجرا می‌شود و دیگر حلقه ندارد
        print("Starting single poll...")
        monitor_once(conn, config)
        print("Poll finished.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_single_poll()
