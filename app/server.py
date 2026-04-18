from flask import Flask, send_file, jsonify, Response, request, send_from_directory
import cv2
import time
import threading
import subprocess
import queue
from pathlib import Path
from PIL import Image
from datetime import datetime
import traceback
import os

# ---------------- PATHS ----------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]

WEB_DIR = PROJECT_ROOT / "web"
ASSET_DIR = WEB_DIR / "assets"
OUTPUT_DIR = PROJECT_ROOT / "outputs"

app = Flask(__name__, static_folder=str(WEB_DIR), static_url_path="")

# ---------------- GLOBAL STATE ----------------

camera = None
camera_lock = threading.Lock()
state_lock = threading.Lock()

latest_frame = None
latest_frame_ts = 0.0
camera_ok = False
camera_fail_count = 0

shots = []
countdown = 0
shot_count = 0
capture_done = False
capture_running = False
selected_frame = "frame1.png"
latest_result = None
copies = 2
current_session_id = None
last_error = ""

print_queue = queue.Queue()
shutdown_event = threading.Event()

last_print_time = 0 

# ---------------- CONFIG ----------------

CAMERA_INDEX = 0
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
COUNTDOWN_SECONDS = 10
TOTAL_SHOTS = 4
SHOT_DELAY_SECONDS = 0.4
MAX_CAMERA_FAILS_BEFORE_REINIT = 20
PREVIEW_JPEG_QUALITY = 85

SLOTS = [
    (21, 20, 558, 367),
    (621, 20, 558, 367),

    (21, 407, 558, 367),
    (621, 407, 558, 367),

    (21, 794, 558, 366),
    (621, 794, 558, 366),

    (21, 1181, 558, 366),
    (621, 1181, 558, 366),
]

VALID_FRAMES = {f"frame{i}.png" for i in range(1, 6)}

# ---------------- HELPERS ----------------

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def set_error(msg: str) -> None:
    global last_error
    with state_lock:
        last_error = msg
    log(f"ERROR: {msg}")

def clear_error() -> None:
    global last_error
    with state_lock:
        last_error = ""

def cleanup_old_temp_files(max_age_hours: int = 3) -> None:
    now = time.time()
    for f in OUTPUT_DIR.glob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            age_hours = (now - f.stat().st_mtime) / 3600
            if age_hours > max_age_hours:
                f.unlink(missing_ok=True)
        except Exception:
            pass

def reset_capture_state() -> None:
    global shots, countdown, shot_count, capture_done, capture_running
    with state_lock:
        shots = []
        countdown = 0
        shot_count = 0
        capture_done = False
        capture_running = False

def safe_unlink(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

def fit(img, w, h):
    scale = max(w / img.width, h / img.height)  # 🔥 다시 max

    new_w = int(img.width * scale)
    new_h = int(img.height * scale)

    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = (new_w - w) // 2
    top = (new_h - h) // 2

    return img.crop((left, top, left + w, top + h))

# ---------------- CAMERA ----------------

def _create_camera():
    # macOS 안정화
    cam = cv2.VideoCapture(CAMERA_INDEX, cv2.CAP_AVFOUNDATION)
    cam.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cam.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
    cam.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cam

def init_camera(force: bool = False) -> bool:
    global camera, camera_ok, camera_fail_count

    with camera_lock:
        try:
            if force and camera is not None:
                try:
                    camera.release()
                except Exception:
                    pass
                camera = None

            if camera is None or not camera.isOpened():
                camera = _create_camera()
                time.sleep(0.3)

            if camera is None or not camera.isOpened():
                camera_ok = False
                return False

            ok, frame = camera.read()
            if not ok or frame is None:
                camera_ok = False
                return False

            camera_ok = True
            camera_fail_count = 0
            log("Camera initialized")
            return True

        except Exception as e:
            camera_ok = False
            set_error(f"Camera init failed: {e}")
            return False

def release_camera() -> None:
    global camera, camera_ok
    with camera_lock:
        if camera is not None:
            try:
                camera.release()
            except Exception:
                pass
            camera = None
        camera_ok = False

def camera_loop():
    global latest_frame, latest_frame_ts, camera_ok, camera_fail_count

    while not shutdown_event.is_set():
        if not init_camera():
            time.sleep(1.0)
            continue

        try:
            with camera_lock:
                ok, frame = camera.read()

            if not ok or frame is None:
                camera_fail_count += 1
                camera_ok = False

                if camera_fail_count >= MAX_CAMERA_FAILS_BEFORE_REINIT:
                    log("Camera read failed repeatedly. Reinitializing camera.")
                    init_camera(force=True)
                    camera_fail_count = 0

                time.sleep(0.05)
                continue

            camera_fail_count = 0
            camera_ok = True

            h, w, _ = frame.shape
            cropped = frame 

            latest_frame = cropped.copy()
            latest_frame_ts = time.time()

            time.sleep(0.01)

        except Exception as e:
            set_error(f"camera_loop exception: {e}")
            traceback.print_exc()
            init_camera(force=True)
            time.sleep(0.5)

# ---------------- PRINTER ----------------

def printer_worker():
    while not shutdown_event.is_set():
        try:
            job = print_queue.get(timeout=0.5)
        except queue.Empty:
            continue

        if job is None:
            break

        path, copies_to_print = job

        try:
            subprocess.run(["cancel", "-a"], timeout=5)
        except Exception:
            pass

        try:
            real_prints = copies_to_print // 2

            if real_prints <= 0:
                continue

            for _ in range(real_prints):
                subprocess.run(["cancel", "-a"], timeout=5)

                # 🔥 핵심 수정 (fit-to-page 제거)
                result = subprocess.run(
                    ["lp", "-o", "media=4x6", "-o", "fit-to-page", "-o", "page-border=none", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode != 0:
                    set_error(f"Print failed: {result.stderr.strip()}")
                else:
                    log(f"Printed: {path}")

                time.sleep(1)

        except subprocess.TimeoutExpired:
            set_error("Print timeout")
        except Exception as e:
            set_error(f"Printer worker exception: {e}")
        finally:
            print_queue.task_done()

# ---------------- PREVIEW STREAM ----------------

def gen_frames():
    encode_params = [int(cv2.IMWRITE_JPEG_QUALITY), PREVIEW_JPEG_QUALITY]

    while True:
        frame = latest_frame
        if frame is None:
            time.sleep(0.03)
            continue

        try:
            ok, buffer = cv2.imencode(".jpg", frame, encode_params)
            if not ok:
                time.sleep(0.03)
                continue

            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + buffer.tobytes() + b"\r\n"
            )
            time.sleep(0.03)

        except GeneratorExit:
            return
        except Exception:
            return

@app.route("/preview")
def preview():
    return Response(
        gen_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# ---------------- FILE ROUTES ----------------

@app.route("/")
def index():
    return send_file(WEB_DIR / "index.html")

@app.route("/frame")
def frame():
    return send_file(WEB_DIR / "frame.html")

@app.route("/thanks")
def thanks():
    return send_file(WEB_DIR / "thanks.html")

@app.route("/outputs/<path:filename>")
def outputs(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)

# ---------------- API ROUTES ----------------

@app.route("/reset")
def reset():
    reset_capture_state()
    clear_error()
    return jsonify({"ok": True})

@app.route("/health")
def health():
    with state_lock:
        return jsonify({
            "ok": True,
            "camera_ok": camera_ok,
            "capture_running": capture_running,
            "capture_done": capture_done,
            "selected_frame": selected_frame,
            "copies": copies,
            "last_error": last_error,
            "latest_frame_age_sec": round(time.time() - latest_frame_ts, 2) if latest_frame_ts else None,
            "print_queue_size": print_queue.qsize(),
        })

@app.route("/select_frame", methods=["POST"])
def select_frame():
    global selected_frame

    data = request.get_json(silent=True) or {}
    frame_name = str(data.get("frame", "frame1.png"))

    if frame_name not in VALID_FRAMES:
        return jsonify({"ok": False, "error": "Invalid frame"}), 400

    with state_lock:
        selected_frame = frame_name

    return jsonify({"ok": True})

@app.route("/set_copies", methods=["POST"])
def set_copies():
    global copies
    data = request.get_json(silent=True) or {}
    try:
        value = int(data.get("copies", 2))
    except Exception:
        value = 2

    if value not in {2, 4, 6, 8}:
        value = 2

    with state_lock:
        copies = value

    return jsonify({"ok": True, "copies": copies})

@app.route("/status")
def status():
    with state_lock:
        return jsonify({
            "countdown": countdown,
            "shot": shot_count,
            "done": capture_done,
            "running": capture_running,
            "frame": selected_frame,
            "error": last_error,
            "session_id": current_session_id
        })

@app.route("/print_extra", methods=["POST"])
def print_extra():
    global last_print_time

    now = time.time()
    if now - last_print_time < 3:   # ⭐ 2초 쿨타임
        return jsonify({"ok": False, "error": "Too fast"}), 429

    global latest_result
    data = request.get_json(silent=True) or {}
    try:
        extra_copies = int(data.get("copies", 2))
    except Exception:
        extra_copies = 2

    if latest_result is None or not Path(latest_result).exists():
        return jsonify({"ok": False, "error": "No image found"}), 400

    while not print_queue.empty():
        try:
            print_queue.get_nowait()
            print_queue.task_done()
        except:
            break

    if current_session_id is None or latest_result is None:
        return jsonify({"ok": False, "error": "No active session"}), 400

    # ⭐ 세션 ID 검증 (파일 이름 기반)
    if str(current_session_id) not in str(latest_result):
        return jsonify({"ok": False, "error": "Session mismatch"}), 403

    print_queue.put((Path(latest_result), extra_copies))
    last_print_time = now
    return jsonify({"ok": True})

# ---------------- CAPTURE ----------------

def compose(session_id: str, selected_frame_name: str, shot_paths: list[Path], copy_count: int) -> Path:
    global latest_result

    frame_path = ASSET_DIR / selected_frame_name
    if not frame_path.exists():
        raise FileNotFoundError(f"Frame not found: {frame_path}")

    frame_overlay = Image.open(frame_path).convert("RGBA")
    canvas = Image.new("RGBA", frame_overlay.size, (255, 255, 255, 255))

    images = []
    for p in shot_paths:
        if not p.exists():
            raise FileNotFoundError(f"Shot not found: {p}")
        images.append(Image.open(p).convert("RGB"))

    if len(images) != TOTAL_SHOTS:
        raise RuntimeError(f"Expected {TOTAL_SHOTS} shots, got {len(images)}")

    for i, img in enumerate(images):
        lx, ly, lw, lh = SLOTS[i * 2]
        rx, ry, rw, rh = SLOTS[i * 2 + 1]

        bleed_x = 0
        bleed_top = 0

        left_img = fit(img, lw + bleed_x, lh + bleed_top)
        right_img = fit(img, rw + bleed_x, rh + bleed_top)

        canvas.paste(left_img, (lx, ly - bleed_top))
        canvas.paste(right_img, (rx, ry - bleed_top))

    final_img = Image.alpha_composite(canvas, frame_overlay)

    shrink_ratio = 0.95 
    new_w = int(final_img.width * shrink_ratio)
    new_h = int(final_img.height * shrink_ratio)
    
    resized_img = final_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

    bg_color = (255, 255, 255, 255) 
    print_ready_img = Image.new("RGBA", final_img.size, bg_color)
    
    offset_x = (final_img.width - new_w) // 2
    offset_y = (final_img.height - new_h) // 2
    print_ready_img.paste(resized_img, (offset_x, offset_y))
    
    final_img = print_ready_img

    out_path = OUTPUT_DIR / f"result_{session_id}.jpg"
    final_img.convert("RGB").save(out_path, quality=95)

    latest_result = out_path
    log(f"Saved result: {out_path.name}")

    return out_path

def capture_sequence(session_id: str, frame_name: str, copy_count: int):
    global shots, countdown, shot_count, capture_done, capture_running, current_session_id
    

    local_shots: list[Path] = []

    try:
        clear_error()

        with state_lock:
            shots = []
            shot_count = 0
            countdown = 0
            capture_done = False
            capture_running = True
            current_session_id = session_id

        for old_shot in OUTPUT_DIR.glob("shot_*.jpg"):
            try:
                old_shot.unlink(missing_ok=True)
            except Exception:
                pass

        for i in range(TOTAL_SHOTS):
            for t in range(COUNTDOWN_SECONDS, 0, -1):
                with state_lock:
                    if current_session_id != session_id:
                        raise RuntimeError("Capture session replaced by newer session")
                    countdown = t
                time.sleep(1)

            with state_lock:
                countdown = 0

            frame = latest_frame
            if frame is None:
                raise RuntimeError("No camera frame available")

            shot_path = OUTPUT_DIR / f"shot_{session_id}_{i}.jpg"
            ok = cv2.imwrite(str(shot_path), frame)
            if not ok:
                raise RuntimeError(f"Failed to write {shot_path.name}")

            local_shots.append(shot_path)

            with state_lock:
                shots = [str(p.name) for p in local_shots]
                shot_count = len(local_shots)

            log(f"Captured shot {i + 1}/{TOTAL_SHOTS}: {shot_path.name}")
            time.sleep(SHOT_DELAY_SECONDS)

        compose(session_id, frame_name, local_shots, copy_count)

        while not print_queue.empty():
            try:
                print_queue.get_nowait()
                print_queue.task_done()
            except:
                break

        print_queue.put((Path(latest_result), copy_count))

        with state_lock:
            capture_done = True

    except Exception as e:
        set_error(f"Capture error: {e}")
        traceback.print_exc()

    finally:
        with state_lock:
            if current_session_id == session_id:
                capture_running = False
                countdown = 0

@app.route("/start_capture")
def start_capture():
    global capture_running

    with state_lock:
        if capture_running:
            return jsonify({"ok": False, "error": "Capture already running"}), 409

        session_id = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        frame_name = selected_frame
        copy_count = copies

    thread = threading.Thread(
        target=capture_sequence,
        args=(session_id, frame_name, copy_count),
        daemon=True
    )
    thread.start()

    return jsonify({"ok": True, "session_id": session_id})

# ---------------- STARTUP ----------------
def startup_cleanup():
    global latest_result, current_session_id

    latest_result = None
    current_session_id = None

    cleanup_old_temp_files()
    clear_error()

    try:
        subprocess.run("cancel -a", shell=True, timeout=10)
    except Exception:
        pass


if __name__ == "__main__":
    print("🔥 SERVER STARTING")
    startup_cleanup()

    threading.Thread(target=camera_loop, daemon=True).start()
    threading.Thread(target=printer_worker, daemon=True).start()

    app.run(host="0.0.0.0", port=5050, threaded=True)
