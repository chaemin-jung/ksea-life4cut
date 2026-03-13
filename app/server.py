from flask import Flask, request, send_file, jsonify, Response
import cv2
import time
import threading
import numpy as np
from pathlib import Path
from PIL import Image
from datetime import datetime

# ------------------------
# IMAGE FIT FUNCTION
# ------------------------

def fit(img, w, h):

    scale = max(w / img.width, h / img.height)

    new_w = int(img.width * scale)
    new_h = int(img.height * scale)

    img = img.resize((new_w, new_h))

    left = (new_w - w) // 2
    top = (new_h - h) // 2

    return img.crop((left, top, left + w, top + h))

def find_photo_slots(frame_overlay):

    import numpy as np

    frame_np = np.array(frame_overlay)

    gray = cv2.cvtColor(frame_np, cv2.COLOR_BGR2GRAY)

    _, th = cv2.threshold(gray,240,255,cv2.THRESH_BINARY)

    contours,_ = cv2.findContours(th,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)

    slots = []

    for c in contours:

        x,y,w,h = cv2.boundingRect(c)

        if w*h < 20000:
            continue

        slots.append((x,y,w,h))

    slots = sorted(slots, key=lambda b:(b[0],b[1]))

    return slots


# ------------------------
# FLASK APP
# ------------------------

app = Flask(__name__, static_folder="../web", static_url_path="")

@app.route("/")
def index():
    return send_file("../web/index.html")


# ------------------------
# PATHS
# ------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = BASE_DIR / "web" / "assets"
OUTPUT_DIR = BASE_DIR / "outputs"

OUTPUT_DIR.mkdir(exist_ok=True)


# ------------------------
# CAMERA
# ------------------------

camera = cv2.VideoCapture(0)


# ------------------------
# GLOBAL STATE
# ------------------------

shots = []
selected_frame = "frame1.png"
capture_done = False


# ------------------------
# CAMERA PREVIEW STREAM
# ------------------------

def gen_frames():

    while True:

        success, frame = camera.read()

        if not success:
            continue

        frame = cv2.flip(frame,1)

        ret, buffer = cv2.imencode('.jpg', frame)
        frame = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')


@app.route('/preview')
def preview():
    return Response(
        gen_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame'
    )


# ------------------------
# FRAME SELECT
# ------------------------

@app.route('/select_frame', methods=["POST"])
def select_frame():

    global selected_frame

    selected_frame = request.json["frame"]

    print("Frame selected:", selected_frame)

    return jsonify({"ok":True})

@app.route("/capture_status")
def capture_status():
    global capture_done
    return jsonify({"done": capture_done})


# ------------------------
# CAPTURE STATUS
# ------------------------

@app.route("/countdown")
def get_countdown():
    return jsonify({"count": countdown})


# ------------------------
# CAPTURE SEQUENCE
# ------------------------

def capture_sequence():

    global shots, capture_done, countdown

    shots = []
    selected_frame = "frame1.png"
    capture_done = False
    countdown = 0

    for i in range(4):

        print("Countdown 10 seconds")

        for t in range(10,0,-1):

            countdown = t
            print(t)

            time.sleep(1)

        countdown = 0

        ret, frame = camera.read()

        frame = cv2.flip(frame,1)

        path = OUTPUT_DIR / f"shot{i}.jpg"

        cv2.imwrite(str(path), frame)

        shots.append(path)

    compose()

    capture_done = True

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

def compose():

    frame_overlay = Image.open(ASSET_DIR / selected_frame).convert("RGBA")
    frame_overlay = frame_overlay.resize((1200,1800))

    images = [Image.open(p) for p in shots]

    canvas = Image.new("RGB",(1200,1800),(255,255,255))

    # 실제 프레임 슬롯 좌표
    left_x = 190
    right_x = 640

    photo_w = 370
    photo_h = 260

    top = 210
    gap = 60

    y = top

    for img in images:

        fitted = fit(img, photo_w, photo_h)

        canvas.paste(fitted,(left_x,y))
        canvas.paste(fitted,(right_x,y))

        y += photo_h + gap

    # 프레임 덮기
    canvas = Image.alpha_composite(canvas.convert("RGBA"), frame_overlay)

    out = OUTPUT_DIR / f"result_{datetime.now().timestamp()}.jpg"

    canvas.convert("RGB").save(out)

    print("Saved:", out)

# ------------------------
# RUN SERVER
# ------------------------

app.run(host="0.0.0.0",port=5050)