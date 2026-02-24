#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
lifefourcut booth - macOS offline friendly

- modes: mock(샘플/색블록), webcam(HDMI-UVC/웹캠)
- 두 줄(스트립) × 4컷 자동 촬영
- 흐름 (webcam 모드):
  1) 미러링 프리뷰 + "Press SPACE to start (q to quit)"
  2) SPACE 누르면 "Photo session starts in 3 seconds" 카운트다운
  3) 이후 10초 카운트다운 후 촬영 -> 총 4번 반복
- 4x6in(1200x1800@300dpi) 캔버스에 두 스트립 배치
- 외부 프레임 PNG(투명) 위에 사진만 채워 넣는 구조
- 각 스트립 맨 아래 footer 에는 날짜만 표시(옵션, --date)
- 중앙 절취선(하얀 선)만 표시
"""

import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime
from typing import List, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ========= 경로 =========c
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR   = PROJECT_ROOT / "outputs"
ASSETS_DIR   = PROJECT_ROOT / "assets"
OUTPUT_DIR.mkdir(exist_ok=True)

# ========= 레이아웃 =========
DPI = 300
CANVAS_W, CANVAS_H = 1200, 1800   # 4x6in @300dpi
MARGIN    = 40
STRIP_GAP = 0
BORDER    = 10
NUM_SHOTS = 4
BG_COLOR  = (255, 255, 255)

# 프레임 오버레이 파일(투명 PNG) - 예: navy KSEA 4 CUTS 프레임
DEFAULT_FRAME_OVERLAY = ASSETS_DIR / "frame_overlay.png"

# 프레임 디자인 만들 때 쓴 값과 맞춰야 하는 파라미터
FOOTER_H     = 220   # 각 스트립 맨 아래 footer 영역 높이
OUTER_THICK  = 18    # 왼/오른쪽 테두리 두께 (프레임 기준)

# 날짜 포맷 (예: 11.21.2025)
DATE_FMT       = "%m.%d.%Y"
ADD_DATE_TEXT  = False    # --date 옵션으로 켜기
CUT_GUIDES     = True     # 가운데 절취선 on/off

# ========= 촬영(웹캠) 설정 =========
MODE = "mock"          # "mock" | "webcam"
CAM_INDEX = 0
CAPTURE_WIDTH  = 1920
CAPTURE_HEIGHT = 1080

COUNTDOWN_SEC  = 3     # 세션 시작 전 카운트다운 (3초)
BETWEEN_SEC    = 10    # 각 샷 사이 카운트다운(= 10초 후 촬영)

MIRROR_PREVIEW = True
FREEZE_MS      = 300   # 촬영 후 화면 정지 시간(ms)

# ========= 인쇄 옵션 =========
AUTO_PRINT   = False
PRINTER_NAME = "SELPHY"
LP_OPTIONS   = [
    "-o", "media=Postcard",
    "-o", "borderless=true",
    "-o", "fit-to-page=false",
    "-o", "scaling=100"
]
PRINT_RETRY = 1

# ========= 유틸 =========
def _measure_text(draw: ImageDraw.ImageDraw, txt: str, font=None) -> int:
    """Pillow draw 객체로 문자열 픽셀 폭 측정"""
    try:
        return int(draw.textlength(txt, font=font))
    except Exception:
        bbox = draw.textbbox((0, 0), txt, font=font)
        return bbox[2] - bbox[0]

def _init_camera(idx: int):
    cap = cv2.VideoCapture(idx)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)
    if not cap.isOpened():
        raise RuntimeError("카메라를 열 수 없습니다. (HDMI-UVC/웹캠 인식 실패)")
    return cap

def _overlay_big_count(frame, text: str):
    """화면 가운데에 큰 숫자 카운트다운 표시"""
    h, w = frame.shape[:2]
    scale, thick = 3, 6
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = (w - tw) // 2
    y = h // 2 + th // 2
    # 흰색 외곽
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale,
                (255, 255, 255), thick * 2, cv2.LINE_AA)
    # 검정 글자
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale,
                (0, 0, 0), thick, cv2.LINE_AA)
    return frame

def _overlay_message(frame, text: str):
    """한 줄 메시지를 화면 가운데에 크게 표시"""
    h, w = frame.shape[:2]
    scale, thick = 1.2, 3
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
    x = (w - tw) // 2
    y = h // 2 + th // 2
    # 흰색 외곽
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale,
                (255, 255, 255), thick * 2, cv2.LINE_AA)
    # 검정 글자
    cv2.putText(frame, text, (x, y),
                cv2.FONT_HERSHEY_SIMPLEX, scale,
                (0, 0, 0), thick, cv2.LINE_AA)
    return frame

# ========= MOCK =========
def capture_shots_mock(num_shots: int) -> List[Image.Image]:
    """mock 모드: assets/mock1.jpg~mock4.jpg 또는 색 블록 사용"""
    shots: List[Image.Image] = []
    for i in range(1, num_shots + 1):
        p = ASSETS_DIR / f"mock{i}.jpg"
        if p.exists():
            img = Image.open(p).convert("RGB")
        else:
            colors = [
                (200, 120, 120),
                (120, 200, 140),
                (130, 140, 220),
                (220, 180, 120),
            ]
            img = Image.new("RGB", (1600, 1066), colors[(i - 1) % len(colors)])
        shots.append(img)
    return shots

# ========= WEBCAM =========
def capture_shots_webcam(num_shots: int, start_cd: int, gap: int) -> List[Image.Image]:
    """
    촬영 흐름:
      1) 라이브 미러링 프리뷰 + 'Press SPACE to start (q to quit)'
      2) SPACE 누르면 'Photo session starts in 3 seconds' 카운트다운
      3) 이후 gap(기본 10초) 카운트다운 + 촬영을 num_shots 번 반복
    """
    shots: List[Image.Image] = []
    cap = _init_camera(CAM_INDEX)
    cv2.namedWindow("Lifefourcut", cv2.WINDOW_NORMAL)

    try:
        # ---------- 0. 시작 대기: SPACE 누를 때까지 프리뷰 ----------
        while True:
            ok, frame = cap.read()
            if not ok:
                frame = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
            if MIRROR_PREVIEW:
                frame = cv2.flip(frame, 1)

            msg = "Press SPACE to start (q to quit)"
            h, w = frame.shape[:2]
            scale, thick = 0.8, 2
            (tw, th), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, scale, thick)
            x = (w - tw) // 2
            y = h - 40
            cv2.putText(frame, msg, (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, scale,
                        (255, 255, 255), thick, cv2.LINE_AA)

            cv2.imshow("Lifefourcut", frame)
            key = cv2.waitKey(30) & 0xFF
            if key == ord(' '):   # SPACE = 촬영 시작
                break
            if key == ord('q'):
                raise KeyboardInterrupt

        # ---------- 1. 세션 시작 3초 카운트다운 ----------
        for t in range(start_cd, 0, -1):
            ok, frame = cap.read()
            if not ok:
                frame = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
            if MIRROR_PREVIEW:
                frame = cv2.flip(frame, 1)

            text = f"Photo session starts in {t} s"
            frame = _overlay_message(frame, text)
            cv2.imshow("Lifefourcut", frame)
            if cv2.waitKey(1000) & 0xFF == ord('q'):
                raise KeyboardInterrupt

        # ---------- 2. 각 샷: gap 초 카운트다운 + 촬영 ----------
        for i in range(num_shots):
            end_time = time.time() + gap
            while True:
                remain = int(end_time - time.time()) + 1
                if remain <= 0:
                    break

                ok, live = cap.read()
                if not ok:
                    live = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
                if MIRROR_PREVIEW:
                    live = cv2.flip(live, 1)

                live = _overlay_big_count(live.copy(), str(remain))
                label = f"Shot {i+1}/{num_shots}"
                cv2.putText(live, label, (20, 40),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0,
                            (255, 255, 255), 2, cv2.LINE_AA)

                cv2.imshow("Lifefourcut", live)
                if cv2.waitKey(200) & 0xFF == ord('q'):
                    raise KeyboardInterrupt

            # 실제 촬영
            ok, frame = cap.read()
            if not ok:
                frame = np.zeros((CAPTURE_HEIGHT, CAPTURE_WIDTH, 3), dtype=np.uint8)
            if MIRROR_PREVIEW:
                frame = cv2.flip(frame, 1)

            cv2.imshow("Lifefourcut", frame)
            cv2.waitKey(FREEZE_MS)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            shots.append(Image.fromarray(rgb))
            print(f"{len(shots)}/{num_shots} shot taken")

        return shots

    finally:
        cap.release()
        cv2.destroyAllWindows()

# ========= 합성 =========
def fit_into_box(img: Image.Image, w: int, h: int) -> Image.Image:
    """여백 없이 꽉 채우기(cover). 중앙 기준 크롭."""
    im = img.copy()
    scale = max(w / im.width, h / im.height)
    new_w, new_h = int(im.width * scale), int(im.height * scale)
    im = im.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = (new_w - w) // 2
    top  = (new_h - h) // 2
    return im.crop((left, top, left + w, top + h))

def make_strip(shots: List[Image.Image], strip_w: int, strip_h: int) -> Image.Image:
    """
    스트립 내부에는 사진만 채워 넣고, 테두리/배경은 오버레이 PNG가 담당.
    마지막 아래 FOOTER_H 만큼은 비워 둔다.
    """
    strip = Image.new("RGB", (strip_w, strip_h), BG_COLOR)

    usable_h = strip_h - FOOTER_H - 2 * OUTER_THICK
    slot_h   = (usable_h - (NUM_SHOTS - 1) * BORDER) // NUM_SHOTS
    slot_w   = strip_w - 2 * (OUTER_THICK + BORDER)

    y = OUTER_THICK
    for s in shots:
        box = fit_into_box(s, slot_w, slot_h)
        strip.paste(box, (OUTER_THICK + BORDER, y))
        y += slot_h + BORDER

    return strip

def _draw_date_footer(canvas: Image.Image) -> Image.Image:
    """각 스트립 footer 영역에 '날짜'만 표시."""
    if not ADD_DATE_TEXT:
        return canvas

    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("Arial.ttf", 34)
    except Exception:
        font = ImageFont.load_default()

    strip_w  = (CANVAS_W - (2 * MARGIN + STRIP_GAP)) // 2
    strip_h  = CANVAS_H - 2 * MARGIN
    footer_top = MARGIN + strip_h - FOOTER_H
    # footer 안에서 살짝 아래쪽에 표시
    date_y = footer_top + int(FOOTER_H * 0.75)

    date_str = datetime.now().strftime(DATE_FMT)

    for k in range(2):
        cx = MARGIN + k * (strip_w + STRIP_GAP) + strip_w // 2
        dw = _measure_text(draw, date_str, font=font)
        draw.text((cx - dw // 2, date_y),
                  date_str, fill=(255, 255, 255), font=font)

    return canvas

def compose_canvas(shots: List[Image.Image],
                   frame_overlay: Optional[Path]) -> Image.Image:
    canvas = Image.new("RGB", (CANVAS_W, CANVAS_H), BG_COLOR)

    strip_w = (CANVAS_W - (2 * MARGIN + STRIP_GAP)) // 2
    strip_h = CANVAS_H - 2 * MARGIN

    strip = make_strip(shots, strip_w, strip_h)

    x1 = MARGIN
    x2 = x1 + strip_w + STRIP_GAP
    y0 = MARGIN
    canvas.paste(strip, (x1, y0))
    canvas.paste(strip, (x2, y0))

    # 프레임 오버레이(투명 PNG) 합성
    if frame_overlay and Path(frame_overlay).exists():
        ov = Image.open(frame_overlay).convert("RGBA").resize(
            (CANVAS_W, CANVAS_H), Image.Resampling.LANCZOS
        )
        canvas = Image.alpha_composite(canvas.convert("RGBA"), ov).convert("RGB")

    # 항상 가운데 절취선(흰색)만
    if CUT_GUIDES:
        draw = ImageDraw.Draw(canvas)
        mid_x = x1 + strip_w
        draw.line([(mid_x, y0 - 10), (mid_x, y0 + strip_h + 10)],
                  fill=(255, 255, 255), width=3)

    # footer 날짜 텍스트
    canvas = _draw_date_footer(canvas)
    return canvas

# ========= 저장/인쇄 =========
def save_jpeg(img: Image.Image, dpi: int = DPI) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = OUTPUT_DIR / f"lifefourcut_{ts}.jpg"
    img.save(out, "JPEG", quality=95, dpi=(dpi, dpi))
    print("Saved:", out)
    return out

def print_with_lp(path: Path, printer: Optional[str] = PRINTER_NAME,
                  options: Optional[list] = None, retry: int = PRINT_RETRY):
    if options is None:
        options = LP_OPTIONS
    cmd = ["lp", str(path)]
    if printer:
        cmd += ["-d", printer]
    cmd += options
    for i in range(retry + 1):
        try:
            print("Print cmd:", " ".join(cmd))
            subprocess.run(cmd, check=True)
            print("-> queued to printer")
            return
        except subprocess.CalledProcessError as e:
            print(f"[warn] print failed {i+1}: {e}")
            time.sleep(0.8)
    print("[info] printing skipped; file saved only.")

# ========= 실행부 =========
def parse_args():
    import argparse
    p = argparse.ArgumentParser(description="lifefourcut booth")
    p.add_argument("--mode", choices=["mock", "webcam"], default=MODE)
    p.add_argument("--shots", type=int, default=NUM_SHOTS)
    p.add_argument("--countdown", type=int, default=COUNTDOWN_SEC,
                   help="세션 시작 전 카운트다운(초)")
    p.add_argument("--between", type=int, default=BETWEEN_SEC,
                   help="각 샷 사이 카운트다운(초, 끝나면 촬영)")
    p.add_argument("--cam-index", type=int, default=CAM_INDEX)
    p.add_argument("--width", type=int, default=CAPTURE_WIDTH)
    p.add_argument("--height", type=int, default=CAPTURE_HEIGHT)
    p.add_argument("--no-print", action="store_true")
    p.add_argument("--printer", type=str, default=PRINTER_NAME)
    p.add_argument("--date", action="store_true",
                   help="footer에 로컬 날짜 텍스트 표시")
    p.add_argument("--no-guides", action="store_true",
                   help="가운데 절취선 숨김")
    p.add_argument("--overlay", type=str, default=str(DEFAULT_FRAME_OVERLAY),
                   help="오버레이 PNG 경로(투명). 기본: assets/frame_overlay.png")
    return p.parse_args()

def main():
    global NUM_SHOTS, COUNTDOWN_SEC, BETWEEN_SEC
    global CAM_INDEX, CAPTURE_WIDTH, CAPTURE_HEIGHT
    global ADD_DATE_TEXT, CUT_GUIDES

    args = parse_args()
    NUM_SHOTS     = max(1, args.shots)
    COUNTDOWN_SEC = max(0, args.countdown)
    BETWEEN_SEC   = max(0, args.between)
    CAM_INDEX     = args.cam_index
    CAPTURE_WIDTH, CAPTURE_HEIGHT = args.width, args.height
    ADD_DATE_TEXT = bool(args.date)
    CUT_GUIDES    = not bool(args.no_guides)

    frame_overlay = Path(args.overlay) if args.overlay else None

    print(f"[mode] {args.mode} | shots={NUM_SHOTS} | "
          f"start_cd={COUNTDOWN_SEC}s | between={BETWEEN_SEC}s")
    print(f"[paths] root={PROJECT_ROOT} | outputs={OUTPUT_DIR}")
    print(f"[overlay] {frame_overlay} | exists={frame_overlay.exists() if frame_overlay else None}")
    print(f"[print] {'OFF' if args.no_print or not AUTO_PRINT else 'ON'} | "
          f"printer={args.printer or '(default)'}")

    if args.mode == "mock":
        shots = capture_shots_mock(NUM_SHOTS)
    else:
        shots = capture_shots_webcam(NUM_SHOTS, COUNTDOWN_SEC, BETWEEN_SEC)

    final_img = compose_canvas(shots, frame_overlay)
    out_path  = save_jpeg(final_img, DPI)

    if not args.no_print and AUTO_PRINT:
        print_with_lp(out_path, args.printer, LP_OPTIONS, PRINT_RETRY)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[abort] user cancelled")
        sys.exit(1)
    except Exception as e:
        print(f"[error] {e}")
        sys.exit(2)
