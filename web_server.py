# web_server.py
"""Entry point for Fleet Tracker web application.
Starts background tracking threads dynamically based on DB targets.
"""
import threading
import time
import logging
import uvicorn
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from index import app, track_device, init_db, init_live_csv, SessionLocal, Target, DB_PATH

# Dictionary to keep track of running threads: {target_id: thread}
active_trackers = {}
stop_events = {}

def sync_targets():
    """Periodically sync tracking threads with targets in the database."""
    global active_trackers, stop_events
    
    while True:
        try:
            session = SessionLocal()
            db_targets = session.query(Target).all()
            db_target_ids = {t.id for t in db_targets}
            
            # 1. Start threads for new targets with specific IP only
            for target in db_targets:
                if target.ip_address and target.id not in active_trackers:
                    logging.info(f"Starting new tracker for: {target.name} (ID={target.id}, IP={target.ip_address})")
                    stop_ev = threading.Event()
                    t = threading.Thread(
                        target=track_device,
                        kwargs={
                            "device_id": target.id,
                            "device_name": target.name,
                            "ip_address": target.ip_address,
                            "poll_interval": 30,
                            "stop_event": stop_ev,
                        },
                        daemon=True
                    )
                    t.start()
                    active_trackers[target.id] = t
                    stop_events[target.id] = stop_ev
            
            # 2. Stop threads for deleted targets
            active_ids = list(active_trackers.keys())
            for tid in active_ids:
                if tid not in db_target_ids:
                    logging.info(f"Stopping tracker for deleted ID={tid}")
                    stop_events[tid].set()
                    active_trackers[tid].join(timeout=1)
                    del active_trackers[tid]
                    del stop_events[tid]
            
            session.close()
        except Exception as e:
            logging.error(f"Error syncing targets: {e}")
            
        time.sleep(10) # Refresh target list every 10 seconds

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    init_db()
    init_live_csv()
    
    # Start the sync loop in a background thread
    sync_thread = threading.Thread(target=sync_targets, daemon=True)
    sync_thread.start()

    try:
        uvicorn.run(app, host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        logging.info("Shutting down...")
