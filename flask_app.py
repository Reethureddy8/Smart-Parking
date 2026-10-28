from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response, stream_with_context
from google import genai
from google.genai import types
import cv2
import numpy as np
import os
from datetime import datetime, timedelta
import sqlite3
import hashlib
import uuid
import base64
from io import BytesIO
from PIL import Image
import easyocr
from ultralytics import YOLO
import re

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-only-change-me')

# Configuration
UPLOAD_FOLDER = 'static/uploads'
PARKING_LOT_IMAGE = 'static/parking_lot.jpg'
MODEL_PATH = 'best.pt'
HOURLY_RATE = 20.0  # Price per hour

# AI System Context
SYSTEM_PROMPT = """
You are the AI Assistant for the SmartPark AI System. Your role is to help users navigate and understand this specific application.

### Project Overview
SmartPark AI is an advanced automated parking management system designed to streamline vehicle entry, monitoring, and exit processes using Computer Vision and Artificial Intelligence.

### Key Features
1. **Automated Entry**: Uses a webcam or file upload to capture vehicle images. AI (YOLO + EasyOCR) automatically detects the license plate and assigns the nearest available parking slot.
2. **Real-time Monitoring**: The 'Active Parking' dashboard shows all currently parked vehicles, their slot numbers, and live duration/fare calculations.
3. **Smart Navigation**: Generates a navigation map (Driver Copy) highlighting the assigned slot and path.
4. **Exit & Payment**: Calculates total fare based on duration. Generates a QR code for seamless digital payment before exit.
5. **History & Analytics**: specific 'History' page tracks all past sessions and total revenue.

### Technical Architecture
- **Backend**: Python, Flask, SQLite (Database).
- **AI/CV**: Ultralytics YOLOv8 (Object Detection), EasyOCR (License Plate Recognition), OpenCV (Image Processing).
- **Frontend**: HTML5, Tailwind CSS (Midnight Enterprise Theme), JavaScript.
- **Hardware Support**: Webcams for live feed.

### Business Rules
- **Hourly Rate**: $20.00 per hour.
- **Billing**: Calculated per minute but displayed in hours/minutes.
- **Slot Assignment**: Auto-assigned based on availability logic.

### Guidelines
- Answer questions ONLY related to this Smart Parking System.
- Be concise, professional, and helpful.
- If asked about code, explain the Python/Flask structure or the YOLO integration.
"""

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize EasyOCR reader for license plate recognition
reader = easyocr.Reader(['en'], gpu=False)

# Load YOLO model
try:
    yolo_model = YOLO(MODEL_PATH)
except:
    yolo_model = None
    print("YOLO model not found. Using dummy detection.")

# Add custom Jinja2 filter for base64 encoding
@app.template_filter('b64encode')
def b64encode_filter(data):
    """Custom filter to encode binary data to base64"""
    if data:
        return base64.b64encode(data).decode('utf-8')
    return ''


# Database initialization
def init_database():
    """Initialize SQLite database"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    # Users table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Parking records table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS parking_records (
            id TEXT PRIMARY KEY,
            license_plate TEXT NOT NULL,
            entry_time TIMESTAMP NOT NULL,
            exit_time TIMESTAMP,
            slot_number INTEGER NOT NULL,
            status TEXT DEFAULT 'active',
            fare REAL DEFAULT 0,
            vehicle_image BLOB,
            parking_image BLOB,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def hash_password(password):
    """Hash password using SHA-256"""
    return hashlib.sha256(password.encode()).hexdigest()

def authenticate_user(username, password):
    """Authenticate user login"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    password_hash = hash_password(password)
    cursor.execute('SELECT id, username FROM users WHERE username = ? AND password_hash = ?', 
                   (username, password_hash))
    
    user = cursor.fetchone()
    conn.close()
    
    return user

def register_user(username, email, password):
    """Register new user"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    try:
        password_hash = hash_password(password)
        cursor.execute('INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)',
                       (username, email, password_hash))
        conn.commit()
        conn.close()
        return True, "Registration successful!"
    except sqlite3.IntegrityError:
        conn.close()
        return False, "Username or email already exists!"

def detect_license_plate(image):
    """Detect and extract license plate text from image using EasyOCR"""
    try:
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        
        # Apply preprocessing
        gray = cv2.bilateralFilter(gray, 11, 17, 17)
        
        # Detect text using EasyOCR
        results = reader.readtext(gray)
        
        # Filter and find license plate pattern
        license_plate = None
        max_confidence = 0
        
        for (bbox, text, confidence) in results:
            # Clean text
            text = text.upper().replace(' ', '')
            
            # Look for license plate patterns (adjust regex based on your region)
            # Example patterns: ABC1234, AB12CD3456, etc.
            if re.match(r'^[A-Z0-9]{4,10}$', text) and confidence > max_confidence:
                license_plate = text
                max_confidence = confidence
        
        if license_plate:
            return license_plate, max_confidence
        else:
            # If no pattern matched, return the text with highest confidence
            if results:
                best_result = max(results, key=lambda x: x[2])
                return best_result[1].upper().replace(' ', ''), best_result[2]
            return None, 0
            
    except Exception as e:
        print(f"License plate detection error: {e}")
        return None, 0

def detect_parking_slots(image):
    """Detect parking slots using YOLO model"""
    if yolo_model is not None:
        try:
            results = yolo_model(image, conf=0.4)
            
            empty_slots = []
            occupied_slots = []
            
            for result in results:
                boxes = result.boxes
                if boxes is not None:
                    for box in boxes:
                        x1, y1, x2, y2 = box.xyxy[0].cpu().numpy().astype(int)
                        conf = float(box.conf[0].cpu().numpy())
                        cls = int(box.cls[0].cpu().numpy())
                        
                        if cls == 0:  # Empty slot
                            empty_slots.append((x1, y1, x2, y2, "empty", conf))
                        else:  # Occupied slot
                            occupied_slots.append((x1, y1, x2, y2, "occupied", conf))
            
            return occupied_slots, empty_slots
        except Exception as e:
            print(f"Detection error: {e}")
            return create_dummy_detection(image)
    else:
        return create_dummy_detection(image)

def create_dummy_detection(image):
    """Create dummy parking slot detection for demo purposes"""
    height, width = image.shape[:2]
    empty_slots = []
    occupied_slots = []
    
    slot_width, slot_height = 80, 120
    slots_per_row = 6
    rows = 3
    
    for row in range(rows):
        for col in range(slots_per_row):
            x1 = 50 + col * (slot_width + 30)
            y1 = 50 + row * (slot_height + 40)
            x2 = x1 + slot_width
            y2 = y1 + slot_height
            
            if x2 < width and y2 < height:
                if (row * slots_per_row + col) % 3 == 0:
                    occupied_slots.append((x1, y1, x2, y2, "occupied", 0.95))
                else:
                    empty_slots.append((x1, y1, x2, y2, "empty", 0.90))
    
    return empty_slots, occupied_slots

def get_occupied_slots():
    """Get currently occupied slot numbers from database"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT slot_number FROM parking_records WHERE status = "active"')
    occupied = [row[0] for row in cursor.fetchall()]
    
    conn.close()
    return occupied

def create_parking_entry(license_plate, slot_number, vehicle_image_data, parking_image_data):
    """Create a new parking entry"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    record_id = str(uuid.uuid4())
    entry_time = datetime.now()
    
    try:
        cursor.execute('''
            INSERT INTO parking_records 
            (id, license_plate, entry_time, slot_number, status, vehicle_image, parking_image)
            VALUES (?, ?, ?, ?, 'active', ?, ?)
        ''', (record_id, license_plate, entry_time, slot_number, vehicle_image_data, parking_image_data))
        
        conn.commit()
        conn.close()
        return True, record_id
    except Exception as e:
        conn.close()
        return False, str(e)

def complete_parking(record_id):
    """Complete parking and calculate fare"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    cursor.execute('SELECT entry_time FROM parking_records WHERE id = ?', (record_id,))
    result = cursor.fetchone()
    
    if result:
        entry_time = datetime.strptime(result[0], '%Y-%m-%d %H:%M:%S.%f')
        exit_time = datetime.now()
        
        # Calculate duration in hours
        duration = (exit_time - entry_time).total_seconds() / 3600
        fare = round(duration * HOURLY_RATE, 2)
        
        cursor.execute('''
            UPDATE parking_records 
            SET exit_time = ?, status = 'completed', fare = ?
            WHERE id = ?
        ''', (exit_time, fare, record_id))
        
        conn.commit()
        conn.close()
        
        return True, fare, duration
    
    conn.close()
    return False, 0, 0

def get_active_parking_records():
    """Get all active parking records"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, license_plate, entry_time, slot_number, vehicle_image, parking_image
        FROM parking_records WHERE status = 'active'
        ORDER BY entry_time DESC
    ''')
    
    records = cursor.fetchall()
    conn.close()
    
    return records

def get_parking_history():
    """Get completed parking records"""
    conn = sqlite3.connect('parking_system.db')
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, license_plate, entry_time, exit_time, slot_number, fare
        FROM parking_records WHERE status = 'completed'
        ORDER BY exit_time DESC
        LIMIT 50
    ''')
    
    records = cursor.fetchall()
    conn.close()
    
    return records

def draw_parking_visualization(image, empty_slots, occupied_slots, assigned_slot=None, license_plate=None):
    """Draw professional parking lot visualization (Input RGB, Output BGR)"""
    # Convert to BGR for OpenCV drawing and correct output format
    display_img = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)
    overlay = display_img.copy()
    
    # Professional BGR Palette
    # Format: (Blue, Green, Red)
    COLORS = {
        'empty': (100, 255, 100),    # Bright Green
        'occupied': (50, 50, 255),   # Bright Red
        'assigned': (255, 255, 0),   # Cyan/Aqua
        'text': (255, 255, 255),     # White
        'bad': (0, 0, 255)           # Red
    }
    
    # Draw empty slots
    for i, slot in enumerate(empty_slots):
        x1, y1, x2, y2, _, conf = slot
        slot_num = i + 1
        
        is_assigned = (assigned_slot == slot_num)
        
        if is_assigned:
            color = COLORS['assigned']
            thickness = 2
            # Glower effect for assigned
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
            cv2.addWeighted(overlay, 0.3, display_img, 0.7, 0, display_img)
            overlay = display_img.copy() # Reset overlay
        else:
            color = COLORS['empty']
            thickness = 1
            # Subtle fill
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
            
        cv2.rectangle(display_img, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)
        
        # Professional Label (Small box in corner)
        label = str(slot_num)
        (w, h), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 1)
        
        # Draw label background
        cv2.rectangle(display_img, (x1, y1), (x1 + w + 10, y1 + h + 10), color, -1)
        cv2.putText(display_img, label, (x1 + 5, y1 + h + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,0,0) if is_assigned else (0,0,0), 1, cv2.LINE_AA)
        
        if is_assigned and license_plate:
            # Draw License Plate Label below
            lp_label = license_plate
            (lw, lh), _ = cv2.getTextSize(lp_label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cx = (x1 + x2) // 2
            lx = cx - lw // 2
            ly = y2 + 15
            
            cv2.rectangle(display_img, (lx - 4, ly - lh - 4), (lx + lw + 4, ly + 4), (0,0,0), -1)
            cv2.putText(display_img, lp_label, (lx, ly), cv2.FONT_HERSHEY_SIMPLEX, 0.5, COLORS['assigned'], 1, cv2.LINE_AA)

    # Draw occupied slots
    for slot in occupied_slots:
        x1, y1, x2, y2, _, conf = slot
        color = COLORS['occupied']
        
        # Border
        cv2.rectangle(display_img, (x1, y1), (x2, y2), color, 1, cv2.LINE_AA)
        # Low opacity fill
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        
    # Apply standard overlay blend
    cv2.addWeighted(overlay, 0.15, display_img, 0.85, 0, display_img)
    
    return display_img

def image_to_base64(image):
    """Convert image to base64 string"""
    _, buffer = cv2.imencode('.jpg', image)
    return base64.b64encode(buffer).decode('utf-8')

def base64_to_image(base64_string):
    """Convert base64 string to image"""
    img_data = base64.b64decode(base64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

# Routes
@app.route('/')
def index():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('index.html', username=session.get('username'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        
        user = authenticate_user(username, password)
        if user:
            session['user_id'] = user[0]
            session['username'] = user[1]
            return jsonify({'success': True, 'message': 'Login successful!'})
        else:
            return jsonify({'success': False, 'message': 'Invalid credentials!'})
    
    return render_template('login.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    
    success, message = register_user(username, email, password)
    return jsonify({'success': success, 'message': message})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/vehicle-entry')
def vehicle_entry():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('vehicle_entry.html')

@app.route('/process-vehicle', methods=['POST'])
def process_vehicle():
    """Process vehicle entry - detect license plate and assign parking"""
    try:
        # Get image from request
        if 'image' not in request.files:
            return jsonify({'success': False, 'message': 'No image provided'})
        
        file = request.files['image']
        
        # Read image
        image_bytes = file.read()
        nparr = np.frombuffer(image_bytes, np.uint8)
        vehicle_image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        # Detect license plate
        license_plate, confidence = detect_license_plate(vehicle_image)
        
        if not license_plate:
            return jsonify({'success': False, 'message': 'Could not detect license plate. Please try again.'})
        
        # Load parking lot image
        if not os.path.exists(PARKING_LOT_IMAGE):
            return jsonify({'success': False, 'message': 'Parking lot image not found'})
        
        parking_image = cv2.imread(PARKING_LOT_IMAGE)
        parking_image_rgb = cv2.cvtColor(parking_image, cv2.COLOR_BGR2RGB)
        
        # Detect parking slots
        empty_slots, occupied_slots = detect_parking_slots(parking_image_rgb)
        
        if not empty_slots:
            return jsonify({'success': False, 'message': 'No parking slots available'})
        
        # Get occupied slots from database
        db_occupied = get_occupied_slots()
        
        # Find first available slot (not in database)
        assigned_slot = None
        for i, slot in enumerate(empty_slots):
            slot_num = i + 1
            if slot_num not in db_occupied:
                assigned_slot = slot_num
                break
        
        if not assigned_slot:
            return jsonify({'success': False, 'message': 'No parking slots available'})
        
        # Draw parking visualization
        parking_viz = draw_parking_visualization(parking_image_rgb, empty_slots, occupied_slots, 
                                                 assigned_slot, license_plate)
        
        # Convert images to base64
        # Note: vehicle_image is BGR, parking_viz is BGR (from new draw function).
        # image_to_base64 uses imencode which expects BGR. So NO conversion needed here.
        vehicle_img_base64 = image_to_base64(vehicle_image)
        parking_img_base64 = image_to_base64(parking_viz)
        
        # Save to database
        success, record_id = create_parking_entry(
            license_plate, 
            assigned_slot,
            image_bytes,
            cv2.imencode('.jpg', parking_viz)[1].tobytes()
        )
        
        if success:
            return jsonify({
                'success': True,
                'license_plate': license_plate,
                'confidence': round(confidence * 100, 2),
                'slot_number': assigned_slot,
                'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'vehicle_image': vehicle_img_base64,
                'parking_image': parking_img_base64,
                'record_id': record_id
            })
        else:
            return jsonify({'success': False, 'message': f'Database error: {record_id}'})
            
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error: {str(e)}'})

@app.route('/active-parking')
def active_parking():
    """View all active parking records with calculated duration and fare"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    raw_records = get_active_parking_records()
    
    # Enrich records with calculated data
    enriched_records = []
    for record in raw_records:
        record_id, license_plate, entry_time_str, slot_number, vehicle_image, parking_image = record
        
        # Parse entry time
        entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S.%f')
        now = datetime.now()
        
        # Calculate duration
        duration_seconds = (now - entry_time).total_seconds()
        duration_hours = int(duration_seconds // 3600)
        duration_minutes = int((duration_seconds % 3600) // 60)
        total_hours = duration_seconds / 3600
        
        # Calculate fare
        estimated_fare = total_hours * HOURLY_RATE
        
        # Encode images to base64
        vehicle_img_b64 = base64.b64encode(vehicle_image).decode('utf-8') if vehicle_image else None
        parking_img_b64 = base64.b64encode(parking_image).decode('utf-8') if parking_image else None
        
        enriched_records.append({
            'id': record_id,
            'license_plate': license_plate,
            'entry_time': entry_time_str,
            'slot_number': slot_number,
            'duration_hours': duration_hours,
            'duration_minutes': duration_minutes,
            'estimated_fare': estimated_fare,
            'vehicle_image': vehicle_img_b64,
            'parking_image': parking_img_b64
        })
    
    return render_template('active_parking.html', records=enriched_records)

@app.route('/exit-vehicle/<record_id>', methods=['POST'])
def exit_vehicle(record_id):
    """Process vehicle exit and calculate fare"""
    from flask import flash
    
    success, fare, duration = complete_parking(record_id)
    
    if success:
        flash(f'✅ Vehicle exit processed! Duration: {duration:.2f} hours | Fare: ${fare}', 'success')
    else:
        flash('❌ Error processing exit. Record not found.', 'error')
    
    # Redirect back to active parking page
    return redirect(url_for('active_parking'))

@app.route('/history')
def history():
    """View parking history with calculated durations"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    raw_records = get_parking_history()
    
    # Enrich records with calculated data
    enriched_records = []
    total_revenue = 0
    
    for record in raw_records:
        record_id, license_plate, entry_time_str, exit_time_str, slot_number, fare = record
        
        # Parse times
        entry_time = datetime.strptime(entry_time_str, '%Y-%m-%d %H:%M:%S.%f')
        exit_time = datetime.strptime(exit_time_str, '%Y-%m-%d %H:%M:%S.%f')
        
        # Calculate duration
        duration_seconds = (exit_time - entry_time).total_seconds()
        duration_hours = int(duration_seconds // 3600)
        duration_minutes = int((duration_seconds % 3600) // 60)
        
        total_revenue += fare
        
        enriched_records.append({
            'id': record_id,
            'license_plate': license_plate,
            'entry_time': entry_time_str,
            'exit_time': exit_time_str,
            'slot_number': slot_number,
            'duration_hours': duration_hours,
            'duration_minutes': duration_minutes,
            'fare': fare
        })
    
    return render_template('history.html', records=enriched_records, total_revenue=f"{total_revenue:.2f}")

@app.route('/webcam-capture')
def webcam_capture():
    """Webcam capture page"""
    if 'user_id' not in session:
        return redirect(url_for('login'))
    return render_template('webcam_capture.html')

@app.route('/chat', methods=['POST'])
def chat():
    """Handle chat requests with Gemini AI"""
    data = request.get_json()
    user_input = data.get('message', '')
    
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        return jsonify({'error': 'GEMINI_API_KEY not set on server'})

    def generate():
        try:
            client = genai.Client(api_key=api_key)
            
            contents = [
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=user_input),
                    ],
                ),
            ]
            
            generate_content_config = types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                thinking_config=types.ThinkingConfig(
                    thinking_level="HIGH",
                ),
                response_mime_type="text/plain",
            )

            for chunk in client.models.generate_content_stream(
                model="gemini-3-flash-preview",
                contents=contents,
                config=generate_content_config,
            ):
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            yield f"Error: {str(e)}"

    return Response(stream_with_context(generate()), mimetype='text/plain')

if __name__ == '__main__':
    init_database()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
