# SmartPark

Parking operations console. The entry camera reads number plates, each car is sent to the nearest suitable bay with a drawn route, an overhead lot camera spots cars without a ticket, and exits are charged by tariff with UPI QR, cash or card.

## Run it

Double-click **`Start SmartPark.bat`** (Windows). It installs dependencies on the first run, starts the server and opens the browser.

Or manually:

```bash
pip install -r requirements.txt
python run.py --open        # http://127.0.0.1:5000
```

On first launch you create the admin account. The models take about 10 s to load in the background. Until they're ready you can still type plates.

## What it does

| Area | Details |
|---|---|
| **Gate** | One screen for the whole job: type or scan a plate (or just its last 4 digits). A parked car comes up ready to check out; a new car comes up ready to check in with its bay chosen. `Enter` confirms, `Esc` clears. |
| **Entry** | Webcam, photo upload, paste or typed entry. EasyOCR reads the plate. Look-alike characters (O/0, I/1, B/8…) are fixed by fitting Indian formats (`KA 01 AB 1234`, BH series, two-line plates). Ranked candidates show confidence. Duplicate plates are blocked. |
| **Assignment** | Nearest free bay from the entrance by driving distance, matched to vehicle type (EV → EV bays, bikes → bike bays, accessible bays held back). The route is drawn on the lot map. Click any bay to override. |
| **Lot camera** | `model/best.pt` (YOLO, classes Car/Empty) scans an overhead frame and marks which bays physically hold a vehicle. It flags **cars without a ticket** and **tickets whose bay looks empty** (drove off without paying). |
| **Layout** | Bays are auto-mapped from a camera frame: rows are clustered, a van across two bays is split, and missed bays are inferred from even spacing. Admins can set bay types, close bays and move the entrance. |
| **Exit** | Search by plate, last 4 digits, ticket code or a photo. Live fare with breakdown. Pay by UPI QR (with amount), cash or card. Admins can waive. Printable receipt. |
| **Tariffs** | Per vehicle type: free grace minutes, first hour, each started hour, daily cap. |
| **Dashboard** | Live via server-sent events: free bays, occupancy, revenue, money on the meter, alerts, activity feed, vehicles-per-hour and 7-day revenue charts. |
| **Tickets** | Parked and history views, search, date filters, CSV export, move bay, void (admin), printable thermal-size tickets with QR. |
| **Assistant** | Answers from live lot data ("where is KA01AB1234?", "how much for 3 hours?", "any alerts?"). Uses Gemini when `GEMINI_API_KEY` is set, and works offline without it. |
| **Team** | Admin and operator roles, scrypt password hashing, login throttling, CSRF header check, HttpOnly session cookies. |

Keyboard: `G` gate, `O` overview, `T` tickets, `L` lot. On the Gate you can just start typing a plate. `Enter` confirms, `Esc` clears, `Space` captures with the camera and `Ctrl+V` pastes a photo.

## Try it without a camera

- **Plates:** `assets/plates/*.jpg` (Gate → Photo).
- **Lot camera:** the sample frames on the Lot camera page.

## Configuration

Copy `.env.example` to `.env`. Every setting is optional: `GEMINI_API_KEY`, `HOST` (use `0.0.0.0` so a phone at the gate can connect), `PORT`, and `SMARTPARK_DATA`. Lot name, UPI ID, currency and tariffs are set in the app under **Settings**.

## Project layout

```
smartpark/        backend (FastAPI)
  main.py         HTTP API, auth, SSE
  services.py     tickets, assignment, fares, camera reconciliation, stats
  layout.py       bay grid from detections, occupancy matching, routing
  vision.py       YOLO + EasyOCR, loaded on a background thread
  plates.py       plate cleaning / OCR correction / formatting
  pricing.py      tariff maths
  assistant.py    Gemini + offline answers
web/              front end (vanilla JS, no build step, no CDN)
model/best.pt     YOLO lot-occupancy weights
assets/           lot image, bundled layout, sample frames and plates
tools/            regenerate layout.json / sample plates
tests/            pytest: core logic + API flows
data/             SQLite DB and captured images (created at runtime)
```

Run the tests with `python -m pytest`.

## License

MIT, see `LICENSE`.
