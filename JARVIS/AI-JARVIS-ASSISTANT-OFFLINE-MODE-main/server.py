import os
import time
import queue
import logging
import threading
import subprocess
from flask import Flask, Response

import jarvis

app = Flask(__name__, static_folder='static')

# Disable standard Flask logging to keep console clean for Jarvis
log = logging.getLogger('werkzeug')
log.disabled = True

@app.route('/')
def index():
    return app.send_static_file('index.html')

@app.route('/stream')
def stream():
    def event_stream():
        # Keep client alive and stream events
        while True:
            try:
                event = jarvis.ui_queue.get(timeout=1.0)
                # Ensure properly formatted SSE
                # type defines event type for JS, data is the payload
                yield f"event: {event['type']}\ndata: {event['data']}\n\n"
            except queue.Empty:
                # Send a ping so browser doesn't close connection
                yield ": ping\n\n"
    return Response(event_stream(), mimetype="text/event-stream")

def start_server():
    print(">>> Starting Jarvis Web Engine...")
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

def launch_ui():
    time.sleep(1.5)  # give flask a moment to bind to port 5000
    try:
        # Launch Chromium App mode
        subprocess.Popen('start msedge --app=http://localhost:5000', shell=True)
    except Exception as e:
        print(f"Failed to launch Edge, open http://localhost:5000 manually. Error: {e}")

if __name__ == '__main__':
    # Thread 1: The Jarvis infinite AI loop
    t_jarvis = threading.Thread(target=jarvis.run, daemon=True)
    t_jarvis.start()

    # Thread 2: The Browser Launcher
    t_browser = threading.Thread(target=launch_ui, daemon=True)
    t_browser.start()

    # Main Thread: Flask Web Server (blocking)
    start_server()
