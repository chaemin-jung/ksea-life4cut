from flask import Flask, send_file, jsonify, Response, request, send_from_directory
import cv2
import time
import threading
from pathlib import Path
from PIL import Image
from datetime import datetime
import subprocess

from pathlib import Path
import os

import math

latest_result = None

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# 서버 시작 시 예전 결과물 삭제
for f in OUTPUT_DIR.glob("*"):
    if f.suffix.lower() in [".jpg", ".jpeg", ".png"]:
        try:
            f.unlink()
        except:
            pass

try:
    subprocess.run("cancel -a", shell=True)
except:
    pass

app = Flask(__name__, static_folder="../web", static_url_path="")

BASE_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = BASE_DIR / "web" / "assets"
OUTPUT_DIR = BASE_DIR / "outputs"

OUTPUT_DIR.mkdir(exist_ok=True)

camera = None
latest_frame = None  # ⭐ 핵심

shots = []
countdown = 0
shot_count = 0
capture_done = False
capture_running = False
selected_frame = "frame1.png"

# ---------------- CAMERA ----------------

def init_camera():
    global camera
    if camera is None or not camera.isOpened():
        camera = cv2.VideoCapture(0)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

init_camera()

# ---------------- CAMERA LOOP ----------------

def camera_loop():
    global camera, latest_frame

    while True:
        if camera is None or not camera.isOpened():
            init_camera()
            time.sleep(1)
            continue

        success, frame = camera.read()

        if not success:
            continue

        # ⭐ 여기 추가 (핵심)
        h, w, _ = frame.shape
        frame = frame[:, int(w*0.125):int(w*0.875)]

        latest_frame = frame.copy()
        time.sleep(0.01)

# ---------------- STREAM ----------------

def gen_frames():
    global latest_frame

    while True:
        if latest_frame is None:
            time.sleep(0.01)
            continue

        ret, buffer = cv2.imencode(".jpg", latest_frame)

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )

@app.route('/preview')
def preview():
    return Response(gen_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame')

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return send_file("../web/index.html")

@app.route("/frame")
def frame():
    return send_file("../web/frame.html")

#@app.route("/capture")
#def capture():
    return send_file("../web/capture.html")

@app.route("/thanks")
def thanks():
    return send_file("../web/thanks.html")

@app.route("/outputs/<path:filename>")
def outputs(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)

@app.route("/stop_preview")
def stop_preview():
    global camera
    if camera:
        camera.release()
    return "ok"

@app.route('/reset')
def reset():
    global shots, countdown, shot_count, capture_done, capture_running

    shots = []
    countdown = 0
    shot_count = 0
    capture_done = False
    capture_running = False

    return "ok"

copies = 2 
@app.route("/set_copies", methods=["POST"])
def set_copies():
    global copies
    data = request.get_json() or {}
    copies = int(data.get("copies", 2))
    return jsonify({"ok": True})

# ---------------- FRAME SELECT ----------------

@app.route('/select_frame', methods=["POST"])
def select_frame():
    global selected_frame, shot_count, countdown, capture_done, capture_running

    selected_frame = request.json["frame"]

    shot_count = 0
    countdown = 0
    capture_done = False
    capture_running = False

    return jsonify({"ok": True})

# ---------------- STATUS ----------------

@app.route("/status")
def status():
    return jsonify({
        "countdown": countdown,
        "shot": shot_count,
        "done": capture_done
    })

# ---------------- CAPTURE ----------------

def capture_sequence():
    global shots, countdown, shot_count, capture_done, capture_running, latest_frame

    try:
        shots = []
        shot_count = 0
        countdown = 0
        capture_done = False

        for f in OUTPUT_DIR.glob("shot*.jpg"):
            try:
                f.unlink()
            except:
                pass

        for i in range(4):

            for t in range(10, 0, -1):
                countdown = t
                time.sleep(1)

            countdown = 0

            if latest_frame is None:
                raise RuntimeError("Camera frame missing")

            frame = latest_frame.copy()

            path = OUTPUT_DIR / f"shot{i}.jpg"
            ok = cv2.imwrite(str(path), frame)

            if not ok:
                raise RuntimeError("Failed to save image")

            shots.append(path)
            shot_count += 1

            time.sleep(0.5)

        compose()
        capture_done = True

    except Exception as e:
        print("❌ Capture failed:", e)

    finally:
        countdown = 0
        capture_running = False

@app.route("/start_capture")
def start_capture():
    global capture_running, capture_done, shot_count

    if capture_running:
        return jsonify({"ok": False})

    capture_done = False
    shot_count = 0

    capture_running = True

    threading.Thread(target=capture_sequence).start()

    return jsonify({"ok": True})

# ---------------- IMAGE FIT ----------------
def fit(img, w, h):
    scale = max(w / img.width, h / img.height)

    new_size = (
        int(img.width * scale + 6),   # 🔥 +6으로 확장
        int(img.height * scale + 6)
    )

    img = img.resize(new_size)

    # ⭐ 완전 중앙 정렬 (round 사용)
    left = int(round((img.width - w) / 2))
    top = int(round((img.height - h) / 2))

    right = left + w
    bottom = top + h

    return img.crop((left, top, right, bottom))
# ---------------- COMPOSE ----------------

def compose():
    frame_overlay = Image.open(ASSET_DIR / selected_frame).convert("RGBA")

    # 🔥 핵심: frame 기준으로 canvas 생성
    canvas_w, canvas_h = frame_overlay.size
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))

    images = [Image.open(p).convert("RGB") for p in shots]

    slots = [
        (28, 38, 1016, 696),
        (1168, 38, 1016, 696),

        (28, 752, 1016, 696),
        (1168, 752, 1016, 696),

        (28, 1472, 1016, 696),
        (1168, 1472, 1016, 696),

        # 마지막 줄만 개별 보정
        (26, 2190, 1020, 700),      # 왼쪽 맨 아래
        (1168, 2192, 1016, 696),    # 오른쪽 맨 아래
    ]

    for i, img in enumerate(images):
        lx, ly, lw, lh = slots[i * 2]
        rx, ry, rw, rh = slots[i * 2 + 1]

        fitted_left = fit(img, lw, lh)
        fitted_right = fit(img, rw, rh)

        canvas.paste(fitted_left, (lx, ly))
        canvas.paste(fitted_right, (rx, ry))

    # 🔥 이제 사이즈 동일 → 에러 없음
    final_img = Image.alpha_composite(canvas, frame_overlay)

    global latest_result

    out = OUTPUT_DIR / f"result_{datetime.now().timestamp()}.jpg"
    final_img.convert("RGB").save(out, quality=95)

    latest_result = out  # ⭐ 핵심

    print("Saved:", out)

    try:
        for _ in range(copies // 2):   # ⭐ 여기 추가
            subprocess.run(["lp", str(out)])
    except Exception as e:
        print("Print failed:", e)

# ---------------- 🔥 NEW: EXTRA PRINT (2장 단위) ----------------

@app.route("/print_extra", methods=["POST"])
def print_extra():
    global latest_result

    data = request.get_json()
    copies = int(data.get("copies", 2))

    if latest_result is None:
        return jsonify({"ok": False, "error": "No image found"})

    try:
        for _ in range(copies // 2):
         subprocess.run(["lp", str(latest_result)])
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})

    return jsonify({"ok": True})

# ---------------- RUN ----------------

if __name__ == "__main__":

    threading.Thread(target=camera_loop, daemon=True).start()

    app.run(host="0.0.0.0", port=5050, threaded=True)