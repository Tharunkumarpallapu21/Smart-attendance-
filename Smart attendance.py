# SMART ATTENDANCE SYSTEM - SINGLE FILE VERSION
# Flask + HTML/CSS/JS (inlined into the file)

from flask import Flask, request, redirect, session, send_file, jsonify, make_response
import sqlite3
import qrcode
import io
import datetime
import os
from geopy.distance import geodesic
import random
import string
import csv

app = Flask(__name__)
app.secret_key = "supersecretkey"

COLLEGE_COORDS = (13.5000, 79.5000)
MAX_DISTANCE_KM = 0.5
DB_PATH = "students.db"
qr_expiry_seconds = 600
qr_store = {}
otp_store = {}

@app.route("/")
def home():
    if "user" in session:
        return redirect("/dashboard")
    return login_page()

@app.route("/login", methods=["POST"])
def login():
    regno = request.form["regno"]
    password = request.form["password"]
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT * FROM students WHERE RegNo = ?", (regno,))
    user = cur.fetchone()
    if user and password == user["Password"]:
        session["user"] = user["RegNo"]
        session["name"] = user["Name"]
        return redirect("/dashboard")
    return login_page("Invalid credentials")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect("/")
    return dashboard_page(session["name"])

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/generate_qr", methods=["POST"])
def generate_qr():
    subject = request.form["subject"]
    period = request.form["period"]
    timestamp = datetime.datetime.now()
    key = f"{subject}|{period}"
    qr_data = f"{subject}|{period}|{timestamp.isoformat()}"
    qr_store[key] = (timestamp, qr_data)
    img = qrcode.make(qr_data)
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/scan", methods=["POST"])
def scan():
    regno = session.get("user")
    qr_data = request.form["qr_data"]
    lat = float(request.form["latitude"])
    lon = float(request.form["longitude"])
    scanned_coords = (lat, lon)
    if geodesic(COLLEGE_COORDS, scanned_coords).km > MAX_DISTANCE_KM:
        return "Outside authorized location"
    subject, period, timestamp_str = qr_data.split("|")
    key = f"{subject}|{period}"
    if key not in qr_store:
        return "QR not recognized"
    stored_time, _ = qr_store[key]
    if (datetime.datetime.now() - stored_time).total_seconds() > qr_expiry_seconds:
        return "QR expired"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("INSERT INTO attendance(RegNo, Subject, Period, Date, Time) VALUES (?, ?, ?, ?, ?)",
                (regno, subject, period, datetime.date.today().isoformat(), datetime.datetime.now().time()))
    conn.commit()
    return "Attendance marked successfully"

@app.route("/request_otp", methods=["POST"])
def request_otp():
    regno = request.form["regno"]
    otp = ''.join(random.choices(string.digits, k=6))
    otp_store[regno] = otp
    return jsonify({"otp": otp})

@app.route("/verify_otp", methods=["POST"])
def verify_otp():
    regno = request.form["regno"]
    otp = request.form["otp"]
    subject = request.form["subject"]
    period = request.form["period"]
    if otp_store.get(regno) == otp:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute("INSERT INTO attendance(RegNo, Subject, Period, Date, Time) VALUES (?, ?, ?, ?, ?)",
                    (regno, subject, period, datetime.date.today().isoformat(), datetime.datetime.now().time()))
        conn.commit()
        return "OTP verified. Attendance marked."
    return "Invalid OTP"

@app.route("/export_attendance")
def export_attendance():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT * FROM attendance")
    rows = cur.fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "RegNo", "Subject", "Period", "Date", "Time"])
    for row in rows:
        writer.writerow(row)
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode()), mimetype="text/csv", as_attachment=True, download_name="attendance.csv")

def login_page(error=""):
    return f'''
    <html><head><title>Login</title>
    <style>
    body {{ font-family: sans-serif; background: #f0f2f5; display:flex;justify-content:center;align-items:center;height:100vh; }}
    form {{ background: #fff; padding: 30px; border-radius: 10px; box-shadow: 0 0 10px rgba(0,0,0,.1); }}
    input {{ display:block; width:100%; margin-bottom:10px; padding:8px; }}
    .error {{ color: red; }}
    </style>
    </head>
    <body>
    <form method="POST" action="/login">
        <h2>Smart Attendance Login</h2>
        <p class="error">{error}</p>
        <input name="regno" placeholder="Register Number" required>
        <input name="password" type="password" placeholder="Password" required>
        <button type="submit">Login</button>
    </form>
    </body></html>
    '''

def dashboard_page(name):
    return f'''
    <html><head><title>Dashboard</title>
    <style>
    body {{ font-family: sans-serif; background: #e8f0fe; padding: 20px; }}
    input, button {{ padding: 8px; margin: 5px; }}
    .section {{ background: white; padding: 15px; margin: 10px 0; border-radius: 8px; box-shadow: 0 2px 5px rgba(0,0,0,.1); }}
    </style></head><body>
    <h2>Welcome, {name} | <a href="/logout">Logout</a></h2>

    <div class="section">
        <h3>Generate QR Code (Faculty)</h3>
        <form method="POST" action="/generate_qr" target="qr_frame">
            Subject: <input name="subject"> Period: <input name="period">
            <button type="submit">Generate</button>
        </form>
        <iframe name="qr_frame" style="border:none;height:200px;"></iframe>
    </div>

    <div class="section">
        <h3>Mark Attendance via QR</h3>
        <form onsubmit="submitScan(event)">
            QR Data: <input id="qr_data" required><br>
            Latitude: <input id="lat" required> Longitude: <input id="lon" required><br>
            <button type="submit">Submit</button>
        </form>
        <p id="scan_result"></p>
    </div>

    <div class="section">
        <h3>OTP Fallback</h3>
        <form onsubmit="sendOTP(event)">
            RegNo: <input id="otp_reg" required>
            <button>Request OTP</button>
        </form>
        <form onsubmit="verifyOTP(event)">
            RegNo: <input id="otp_reg2" required>
            OTP: <input id="otp_val" required>
            Subject: <input id="otp_sub"> Period: <input id="otp_period">
            <button>Verify OTP</button>
        </form>
        <p id="otp_result"></p>
    </div>

    <div class="section">
        <h3>Export Attendance</h3>
        <a href="/export_attendance"><button>Export CSV</button></a>
    </div>

    <script>
    function submitScan(e) {{
        e.preventDefault();
        fetch('/scan', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
            body: `qr_data=${{qr_data.value}}&latitude=${{lat.value}}&longitude=${{lon.value}}`
        }}).then(r => r.text()).then(d => scan_result.innerText = d);
    }}
    function sendOTP(e) {{
        e.preventDefault();
        fetch('/request_otp', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
            body: `regno=${{otp_reg.value}}`
        }}).then(r => r.json()).then(d => otp_result.innerText = "OTP: " + d.otp);
    }}
    function verifyOTP(e) {{
        e.preventDefault();
        fetch('/verify_otp', {{
            method: 'POST',
            headers: {{ 'Content-Type': 'application/x-www-form-urlencoded' }},
            body: `regno=${{otp_reg2.value}}&otp=${{otp_val.value}}&subject=${{otp_sub.value}}&period=${{otp_period.value}}`
        }}).then(r => r.text()).then(d => otp_result.innerText = d);
    }}
    </script></body></html>
    '''

if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        conn = sqlite3.connect(DB_PATH)
        conn.execute("CREATE TABLE students (RegNo TEXT PRIMARY KEY, Name TEXT, Password TEXT);")
        conn.execute("CREATE TABLE attendance (ID INTEGER PRIMARY KEY AUTOINCREMENT, RegNo TEXT, Subject TEXT, Period TEXT, Date TEXT, Time TEXT);")
        conn.commit()
    app.run(debug=True)
