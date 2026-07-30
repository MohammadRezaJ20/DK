# main.py - تغییر پیشنهادی برای اجرای یک‌باره
from app.config import load_config
from app.database import init_db, get_db_connection
from app.monitor import monitor_once

def run_single_poll():
    config = load_config()
    db_path = config["app"]["db_path"]
    conn = get_db_connection(db_path)
    init_db(conn)
    
    # فقط یک بار اجرا می‌شود و دیگر حلقه ندارد
    print("Starting single poll...")
    monitor_once(conn, config)
    print("Poll finished.")
    conn.close()

if __name__ == "__main__":
    run_single_poll()
