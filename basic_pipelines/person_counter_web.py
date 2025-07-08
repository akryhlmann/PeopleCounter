""# person_counter_web.py
from flask import Flask, render_template, Response
import cv2
import threading
import time
import logging
from flask import jsonify



app = Flask(__name__)

logging.basicConfig(level=logging.DEBUG)

# Denne bliver sat udefra
user_data = None

def generate_frames():
    global user_data
    while True:
        if user_data is None:
            print("user_data is None, waiting...")
            time.sleep(0.1)
            continue

        frame = user_data.get_frame()
        if frame is None:
            print("No frame available yet, waiting...")
            time.sleep(0.05)
            continue

        try:
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                print("Failed to encode frame")
                continue

            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
        except Exception as e:
            print(f"Exception in generate_frames: {e}")

@app.route('/')
def index():
    global user_data
    try:
        return render_template('index.html',
                               in_count=user_data.total_in if user_data else 0,
                               out_count=user_data.total_out if user_data else 0)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return "Internal Server Error", 500

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

def start_web_interface(passed_user_data):
    global user_data
    user_data = passed_user_data
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False), daemon=True).start()

@app.route('/get_counts')
def get_counts():
    global user_data
    return jsonify({
        'in': user_data.total_in if user_data else 0,
        'out': user_data.total_out if user_data else 0
    })

@app.route('/reset_counts', methods=['POST'])
def reset_counts():
    global user_data
    if user_data:
        user_data.total_in = 0
        user_data.total_out = 0
        user_data.track_positions = {}
        print("Tællere nulstillet via webinterface")
        return "OK", 200
    return "User data not ready", 500
