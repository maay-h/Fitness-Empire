import threading
import webbrowser
import os
import sys
import time

def start_flask():
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app import app, init_db
    init_db()
    app.run(host='127.0.0.1', port=5000, debug=False, use_reloader=False)

if __name__ == '__main__':
    t = threading.Thread(target=start_flask, daemon=True)
    t.start()
    time.sleep(3)
    webbrowser.open('http://127.0.0.1:5000')
    while True:
        time.sleep(1)
