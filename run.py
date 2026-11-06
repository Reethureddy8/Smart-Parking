"""Start SmartPark:  python run.py   (then open http://127.0.0.1:5000)"""
import logging
import os
import sys
import webbrowser
import threading

os.environ.setdefault("YOLO_VERBOSE", "False")

import uvicorn  # noqa: E402

from smartpark import config  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(name)s  %(message)s", datefmt="%H:%M:%S")
    url = f"http://{'127.0.0.1' if config.HOST in ('0.0.0.0', '::') else config.HOST}:{config.PORT}/"
    if "--open" in sys.argv:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    print(f"\n  SmartPark running at {url}\n  Press Ctrl+C to stop.\n")
    uvicorn.run("smartpark.main:app", host=config.HOST, port=config.PORT, log_level="warning")
