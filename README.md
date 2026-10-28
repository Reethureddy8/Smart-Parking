# SmartPark AI – Smart Parking System

An AI-powered parking management web app. It reads vehicle number plates from a webcam or an uploaded photo, assigns a free parking slot, tracks parking time and fares, and has a built-in Gemini chat assistant.

## Features

- **Automatic vehicle entry**: capture a vehicle with the webcam or upload an image. A YOLOv8 model finds the number plate and EasyOCR reads it.
- **Slot assignment and map**: the nearest free slot is assigned and highlighted on a parking-lot map (driver copy).
- **Active parking dashboard**: see parked vehicles, their slots, and live duration and fare.
- **Exit and payment**: the fare is calculated from parking time, with a QR code for payment.
- **History**: past sessions and total revenue.
- **User accounts**: register and log in.
- **AI assistant**: a chat widget powered by Google Gemini that answers questions about the system.

## Tech stack

| Layer | Tools |
|-------|-------|
| Backend | Python, Flask, SQLite |
| Computer vision | Ultralytics YOLOv8, EasyOCR, OpenCV, Pillow, NumPy |
| AI assistant | Google Gemini (`google-genai`) |
| Frontend | HTML (Jinja2 templates), Tailwind CSS, JavaScript |

## Project structure

```
Smart-Parking/
├── flask_app.py          # Flask app: routes, detection, database, chat
├── best.pt               # Trained YOLOv8 weights for plate detection
├── requirements.txt
├── run_flask_app.bat     # Windows: install dependencies and start the server
├── Open website.bat      # Windows: start the server and open the browser
├── templates/            # Jinja2 HTML pages
├── static/
│   ├── css/  js/         # Styles and front-end scripts
│   ├── parking_lot.jpg   # Parking-lot map image
│   └── uploads/          # Captured images (created at runtime, not committed)
├── 11.jpeg, 12.jpeg      # Sample vehicle images for testing
├── .env.example
└── LICENSE
```

## Getting started

### 1. Prerequisites

- Python 3.10+
- A webcam (optional, you can upload images instead)
- A Google Gemini API key (optional, only needed for the chat assistant)

### 2. Install

```bash
git clone https://github.com/Reethureddy8/Smart-Parking.git
cd Smart-Parking
python -m venv venv
# Windows: venv\Scripts\activate    macOS/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 3. Set environment variables

See `.env.example` for the variables the app uses.

```bash
# macOS / Linux
export FLASK_SECRET_KEY="any-long-random-string"
export GEMINI_API_KEY="your-gemini-api-key"
```

```powershell
# Windows PowerShell
$env:FLASK_SECRET_KEY="any-long-random-string"
$env:GEMINI_API_KEY="your-gemini-api-key"
```

### 4. Run

```bash
python flask_app.py
```

Then open <http://localhost:5000>. On Windows you can also double-click `run_flask_app.bat` or `Open website.bat`.

The first start can take a while because EasyOCR downloads its models.

## Notes

- `parking_system.db` (SQLite) is **created automatically** on first run. It is not included in the repo because it holds user data.
- `best.pt` is the trained YOLOv8 weights file used for number-plate detection. Keep it in the project root.
- Use `11.jpeg` and `12.jpeg` to test vehicle entry without a camera.

## License

This project is licensed under the [MIT License](LICENSE).
