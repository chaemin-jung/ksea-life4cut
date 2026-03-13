from flask import Flask, send_file, jsonify, Response, request, send_from_directory
import cv2
import time
import threading
from pathlib import Path
from PIL import Image
from datetime import datetime

app = Flask(__name__, static_folder="../web", static_url_path="")

BASE_DIR = Path(__file__).resolve().parent.parent
ASSET_DIR = BASE_DIR / "web" / "assets"
OUTPUT_DIR = BASE_DIR / "outputs"

OUTPUT_DIR.mkdir(exist_ok=True)

camera = None

shots=[]
countdown=0
shot_count=0
capture_done=False
capture_running=False
selected_frame="frame1.png"


# ---------------- CAMERA ----------------

def init_camera():
    global camera

    if camera is None or not camera.isOpened():
        camera = cv2.VideoCapture(0)

init_camera()

# ---------------- CAMERA WATCHDOG ----------------

def camera_watchdog():
    global camera

    while True:

        try:

            if camera is None or not camera.isOpened():
                print("Camera reconnecting...")
                init_camera()

            else:
                ok, _ = camera.read()

                if not ok:
                    print("Camera read failed. Reconnecting...")
                    camera.release()
                    camera = None
                    init_camera()

        except Exception as e:
            print("Camera error:", e)

        time.sleep(2)

# ---------------- ROUTES ----------------

@app.route("/")
def index():
    return send_file("../web/index.html")


@app.route("/frame")
def frame():
    return send_file("../web/frame.html")


@app.route("/capture")
def capture():
    return send_file("../web/capture.html")


@app.route("/thanks")
def thanks():
    return send_file("../web/thanks.html")


@app.route("/outputs/<path:filename>")
def outputs(filename):
    return send_from_directory(str(OUTPUT_DIR), filename)


# ---------------- CAMERA STREAM ----------------

def gen_frames():

    global camera

    while True:

        if camera is None or not camera.isOpened():
            init_camera()
            time.sleep(1)
            continue

        success, frame = camera.read()

        if not success:
            camera.release()
            camera = None
            time.sleep(1)
            continue

        frame = cv2.flip(frame,1)

        ret, buffer = cv2.imencode(".jpg", frame)

        yield (
            b'--frame\r\n'
            b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n'
        )


@app.route('/preview')
def preview():
    return Response(gen_frames(),
        mimetype='multipart/x-mixed-replace; boundary=frame')


# ---------------- FRAME SELECT ----------------

@app.route('/select_frame',methods=["POST"])
def select_frame():

    global selected_frame

    selected_frame=request.json["frame"]

    return jsonify({"ok":True})


# ---------------- STATUS ----------------

@app.route("/status")
def status():

    return jsonify({
        "countdown":countdown,
        "shot":shot_count,
        "done":capture_done
    })


# ---------------- CAPTURE ----------------

def capture_sequence():

    global shots,countdown,shot_count,capture_done,capture_running

    shots=[]
    shot_count=0
    capture_done=False

    for f in OUTPUT_DIR.glob("shot*.jpg"):
        try:
            f.unlink()
        except:
            pass

    for i in range(4):

        for t in range(10,0,-1):

            countdown=t
            time.sleep(1)

        countdown=0

        ret,frame=camera.read()

        if not ret:
            init_camera()
            ret,frame=camera.read()

        frame=cv2.flip(frame,1)

        path=OUTPUT_DIR/f"shot{i}.jpg"

        cv2.imwrite(str(path),frame)

        shots.append(path)

        shot_count+=1

    compose()

    capture_done=True
    capture_running=False


@app.route("/start_capture")
def start_capture():

    global capture_running

    if capture_running:
        return jsonify({"ok":False})

    capture_running=True

    t=threading.Thread(target=capture_sequence)
    t.start()

    return jsonify({"ok":True})


# ---------------- IMAGE COMPOSE ----------------

def fit(img,w,h):

    scale=max(w/img.width,h/img.height)

    new_w=int(img.width*scale)
    new_h=int(img.height*scale)

    img=img.resize((new_w,new_h))

    left=(new_w-w)//2
    top=(new_h-h)//2

    return img.crop((left,top,left+w,top+h))


def compose():

    frame_overlay=Image.open(ASSET_DIR/selected_frame).convert("RGBA")
    frame_overlay=frame_overlay.resize((1200,1800))

    images=[Image.open(p) for p in shots]

    canvas=Image.new("RGB",(1200,1800),(255,255,255))

    left_x=190
    right_x=640

    photo_w=370
    photo_h=260

    top=210
    gap=60

    y=top

    for img in images:

        fitted=fit(img,photo_w,photo_h)

        canvas.paste(fitted,(left_x,y))
        canvas.paste(fitted,(right_x,y))

        y+=photo_h+gap

    canvas=Image.alpha_composite(canvas.convert("RGBA"),frame_overlay)

    out=OUTPUT_DIR/f"result_{datetime.now().timestamp()}.jpg"

    canvas.convert("RGB").save(out)

    print("Saved:",out)


# ---------------- RUN ----------------

if __name__=="__main__":

    # camera watchdog thread
    threading.Thread(target=camera_watchdog, daemon=True).start()

    app.run(
        host="0.0.0.0",
        port=5050,
        threaded=True
    )

