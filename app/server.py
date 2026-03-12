from flask import Flask, request, send_file, jsonify, Response
import cv2
import time
import threading
from pathlib import Path
from PIL import Image
import subprocess
from datetime import datetime

app = Flask(__name__, static_folder="../web", static_url_path="")

OUTPUT_DIR = Path("outputs")
ASSET_DIR = Path("web/assets")

OUTPUT_DIR.mkdir(exist_ok=True)

camera = cv2.VideoCapture(0)

shots = []
selected_frame = None


# ------------------------
# CAMERA PREVIEW STREAM
# ------------------------

def gen_frames():

    while True:
        success, frame = camera.read()

        if not success:
            continue

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/preview')
def preview():
    return Response(gen_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame')


# ------------------------
# FRAME SELECT
# ------------------------

@app.route('/select_frame', methods=["POST"])
def select_frame():
    global selected_frame
    selected_frame = request.json["frame"]
    return jsonify({"ok":True})


# ------------------------
# CAPTURE LOGIC
# ------------------------

def capture_sequence():

    global shots

    shots = []

    for i in range(4):

        time.sleep(10)

        ret, frame = camera.read()

        path = OUTPUT_DIR / f"shot{i}.jpg"
        cv2.imwrite(str(path), frame)

        shots.append(path)

    compose_and_print()


# ------------------------
# START CAPTURE
# ------------------------

@app.route('/start_capture')
def start_capture():

    t = threading.Thread(target=capture_sequence)
    t.start()

    return jsonify({"ok":True})


# ------------------------
# COMPOSE IMAGE
# ------------------------

def compose_and_print():

    frame_overlay = Image.open(ASSET_DIR / selected_frame)

    images = [Image.open(p) for p in shots]

    canvas = Image.new("RGB",(1200,1800),(255,255,255))

    y = 50

    for img in images:

        img = img.resize((500,350))

        canvas.paste(img,(350,y))
        y += 380

    canvas = Image.alpha_composite(canvas.convert("RGBA"),frame_overlay)

    out = OUTPUT_DIR / f"result_{datetime.now().timestamp()}.jpg"

    canvas.convert("RGB").save(out)

    # subprocess.run(["lp",str(out)])
    print("TEST MODE: printing skipped")


# ------------------------

app.run(host="0.0.0.0",port=5050)