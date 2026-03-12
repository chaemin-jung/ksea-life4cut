#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
LIFEFourCut Booth - Stable Offline Version
Optimized for event environments

Camera: Sony A7RII via HDMI Capture
Printer: Canon SELPHY CP1500
Environment: Offline / Outdoor capable
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont


# ================================
# PATHS
# ================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "outputs"
ASSETS_DIR = PROJECT_ROOT / "assets"

OUTPUT_DIR.mkdir(exist_ok=True)


# ================================
# CANVAS SETTINGS
# ================================

DPI = 300
CANVAS_W = 1200
CANVAS_H = 1800

MARGIN = 40
STRIP_GAP = 0
BORDER = 10
NUM_SHOTS = 4

BG_COLOR = (255,255,255)

FRAME_OVERLAY = ASSETS_DIR / "frame_overlay.png"


# ================================
# CAMERA SETTINGS
# ================================

CAM_INDEX = 0
CAPTURE_WIDTH = 1920
CAPTURE_HEIGHT = 1080

SESSION_COUNTDOWN = 3
BETWEEN_COUNTDOWN = 10

MIRROR_PREVIEW = False
FREEZE_MS = 400


# ================================
# PRINTER
# ================================

AUTO_PRINT = False
PRINTER_NAME = "SELPHY"

LP_OPTIONS = [
"-o","media=Postcard",
"-o","borderless=true",
"-o","fit-to-page=false",
"-o","scaling=100"
]


# ================================
# CAMERA INIT
# ================================

def init_camera():

    for i in range(5):

        cap = cv2.VideoCapture(CAM_INDEX)

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

        if cap.isOpened():
            print("Camera connected")
            time.sleep(2)
            return cap

        print("Retry camera...", i)
        time.sleep(1)

    raise RuntimeError("Camera connection failed")


# ================================
# TEXT OVERLAY
# ================================

def overlay_center(frame, text, scale=2.5):

    h,w = frame.shape[:2]

    thickness = 5

    (tw,th),_ = cv2.getTextSize(text,cv2.FONT_HERSHEY_SIMPLEX,scale,thickness)

    x = (w-tw)//2
    y = h//2

    cv2.putText(frame,text,(x,y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,(255,255,255),thickness*2,cv2.LINE_AA)

    cv2.putText(frame,text,(x,y),
                cv2.FONT_HERSHEY_SIMPLEX,
                scale,(0,0,0),thickness,cv2.LINE_AA)

    return frame


# ================================
# CAPTURE
# ================================

def capture_shots():

    shots = []

    cap = init_camera()

    cv2.namedWindow("Lifefourcut", cv2.WINDOW_NORMAL)
    cv2.setWindowProperty("Lifefourcut", cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

    try:

        # WAIT FOR START

        while True:

            ret,frame = cap.read()

            if not ret:
                frame = np.zeros((1080,1920,3),dtype=np.uint8)

            if MIRROR_PREVIEW:
                frame = cv2.flip(frame,1)

            overlay_center(frame,"PRESS SPACE TO START",1.2)

            cv2.imshow("Lifefourcut",frame)

            k = cv2.waitKey(30)&0xFF

            if k == ord(' '):
                break

            if k == ord('q') or k == 27:
                raise KeyboardInterrupt


        # SESSION COUNTDOWN

        for i in range(SESSION_COUNTDOWN,0,-1):

            ret,frame = cap.read()

            if MIRROR_PREVIEW:
                frame = cv2.flip(frame,1)

            overlay_center(frame,f"STARTING IN {i}")

            cv2.imshow("Lifefourcut",frame)

            if cv2.waitKey(1000)&0xFF==ord('q'):
                raise KeyboardInterrupt


        # PHOTO LOOP

        for shot in range(NUM_SHOTS):

            end = time.time() + BETWEEN_COUNTDOWN

            while True:

                remain = int(end-time.time())+1

                if remain <=0:
                    break

                ret,frame = cap.read()

                if not ret:
                    continue

                if MIRROR_PREVIEW:
                    frame = cv2.flip(frame,1)

                overlay_center(frame,str(remain),3)

                cv2.putText(frame,
                            f"SHOT {shot+1}/{NUM_SHOTS}",
                            (20,50),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            1,(255,255,255),2)

                cv2.imshow("Lifefourcut",frame)

                if cv2.waitKey(200)&0xFF==ord('q'):
                    raise KeyboardInterrupt


            ret,frame = cap.read()

            if MIRROR_PREVIEW:
                frame = cv2.flip(frame,1)

            cv2.imshow("Lifefourcut",frame)
            cv2.waitKey(FREEZE_MS)

            rgb = cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)

            shots.append(Image.fromarray(rgb))

            print("Captured",len(shots))


        return shots

    finally:

        cap.release()
        cv2.destroyAllWindows()



# ================================
# IMAGE FIT
# ================================

def fit(img,w,h):

    scale=max(w/img.width,h/img.height)

    nw=int(img.width*scale)
    nh=int(img.height*scale)

    img=img.resize((nw,nh),Image.Resampling.LANCZOS)

    left=(nw-w)//2
    top=(nh-h)//2

    return img.crop((left,top,left+w,top+h))


# ================================
# STRIP
# ================================

def make_strip(shots, sw, sh):

    strip = Image.new("RGB", (sw, sh), BG_COLOR)

    # 프레임에 맞게 사진 위치 직접 지정
    photo_positions = [
        (80, 120, 440, 330),
        (80, 470, 440, 330),
        (80, 820, 440, 330),
        (80, 1170, 440, 330)
    ]

    for img, pos in zip(shots, photo_positions):

        x, y, w, h = pos

        fitted = fit(img, w, h)

        strip.paste(fitted, (x, y))

    return strip



# ================================
# COMPOSE
# ================================

def compose(shots):

    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)

    sw = (CANVAS_W - (2 * MARGIN + STRIP_GAP)) // 2
    sh = CANVAS_H - 2 * MARGIN

    strip = make_strip(shots, sw, sh)

    # 왼쪽 스트립
    canvas.paste(strip, (MARGIN, MARGIN))

    # 오른쪽 스트립
    canvas.paste(strip, (MARGIN + sw + STRIP_GAP, MARGIN))

    if FRAME_OVERLAY.exists():

        overlay = Image.open(FRAME_OVERLAY).convert("RGBA")
        overlay = overlay.resize((CANVAS_W, CANVAS_H))

        canvas = Image.alpha_composite(
            canvas.convert("RGBA"),
            overlay
        ).convert("RGB")

    return canvas



# ================================
# SAVE
# ================================

def save(img):

    ts=datetime.now().strftime("%Y%m%d_%H%M%S")

    path=OUTPUT_DIR/f"lifefourcut_{ts}.jpg"

    img.save(path,"JPEG",quality=95,dpi=(DPI,DPI))

    print("Saved:",path)

    return path



# ================================
# PRINT
# ================================

def print_photo(path):

    cmd=["lp",str(path),"-d",PRINTER_NAME]+LP_OPTIONS

    try:

        subprocess.run(cmd,check=True)

        print("Print sent")

    except Exception as e:

        print("Print failed",e)



# ================================
# MAIN
# ================================

def main():

    print("LifeFourCut Booth Started")

    shots=capture_shots()

    img=compose(shots)

    path=save(img)

    if AUTO_PRINT:
        print_photo(path)



if __name__=="__main__":

    try:
        main()

    except KeyboardInterrupt:
        print("Exit")

    except Exception as e:
        print("ERROR:",e)