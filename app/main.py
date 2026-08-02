import time

from app.config import load_config
from app.database import get_connection, init_db
from app.monitor import monitor_once


def main():
    config = load_config()
    conn = get_connection(config["app"]["database_url"])
    init_db(conn)

    interval = config["app"]["poll_interval_seconds"]

    while True:
        try:
            monitor_once(conn, config)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            print(f"monitor error: {e}")

        time.sleep(interval)
