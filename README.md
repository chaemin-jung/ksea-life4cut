좋아 — 바로 복붙해서 써도 되는 **깔끔한 GitHub README** 만들어줄게.
(너 프로젝트: photobooth / life4cut 기준으로 맞춰서 작성함)

---

# 📸 Life4Cut Photobooth

A production-ready, offline photobooth system built with Python, OpenCV, and Flask.
Designed for events, this application captures photos, applies custom frames, and prints instantly.

---

## 🚀 Features

* 📷 Live camera preview (real-time streaming)
* ⏱️ Automated countdown (10-second capture flow)
* 🧩 Frame selection system
* 🖼️ 4-photo composition (Life4Cut style)
* 🖨️ Instant printing support (Canon SELPHY, etc.)
* 🔌 Works fully offline (no internet required)

---

## 🛠️ Tech Stack

* Python
* OpenCV
* Flask
* PIL (Pillow)

---

## 📂 Project Structure

```
life4cut/
├── booth.py            # Main photo capture logic
├── server.py           # Flask server
├── outputs/            # Saved images
├── web/
│   ├── index.html      # UI
│   └── assets/         # Frame overlays
```

---

## ⚙️ Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/life4cut.git
cd life4cut
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the server

```bash
python server.py
```

### 4. Open in browser

```
http://localhost:5000
```

---

## 🎮 How It Works

1. Select a frame
2. Start session
3. 10-second countdown begins
4. Capture 4 photos automatically
5. Images are combined into a 4x6 layout
6. Final image is saved and printed

---

## 🖨️ Printing (Optional)

To enable printing, configure your system printer and uncomment the print command in the code:

```python
subprocess.run(["lp", file_path])
```

---

## ⚠️ Known Issues

* Camera may freeze if device is not detected properly
* Long loading time may cause preview to fail
* Ensure correct camera index (`cv2.VideoCapture(0)`)

---

## 💡 Future Improvements

* Touchscreen UI optimization (iPad/tablet support)
* Cloud backup for photos
* QR code sharing
* Multi-frame templates

---

## 👤 Author

Built by [Your Name]

---

## 📄 License

MIT License
