import base64
import io
import os
import uuid
from datetime import date, datetime

import cv2
import numpy as np
from dotenv import load_dotenv
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side
from openpyxl.utils import get_column_letter
from PIL import Image
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

load_dotenv()

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads", "teachers")
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", DEFAULT_UPLOAD_DIR)
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-this-secret-key")

raw_db_url = os.environ.get("DATABASE_URL", "sqlite:///instance/school_face_attendance.db")
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = raw_db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "webp"}
FACE_CONFIDENCE_THRESHOLD = int(os.environ.get("FACE_CONFIDENCE_THRESHOLD", "75"))


db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="admin", nullable=False)


class Teacher(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False, unique=True)
    department = db.Column(db.String(160), default="")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    images = db.relationship("TeacherImage", backref="teacher", cascade="all, delete-orphan")
    records = db.relationship("AttendanceRecord", backref="teacher", cascade="all, delete-orphan")


class TeacherImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)


class AttendanceRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    teacher_id = db.Column(db.Integer, db.ForeignKey("teacher.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, default=date.today)
    sign_in_time = db.Column(db.DateTime, nullable=True)
    sign_out_time = db.Column(db.DateTime, nullable=True)
    sign_in_confidence = db.Column(db.Float, nullable=True)
    sign_out_confidence = db.Column(db.Float, nullable=True)
    status_note = db.Column(db.String(255), default="")


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def teacher_folder(teacher_id):
    path = os.path.join(UPLOAD_DIR, str(teacher_id))
    os.makedirs(path, exist_ok=True)
    return path


def image_to_gray_array(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    array = np.array(image)
    bgr = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return gray


def detect_largest_face(gray):
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(cascade_path)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(80, 80))
    if len(faces) == 0:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    face = gray[y:y + h, x:x + w]
    return cv2.resize(face, (200, 200))


def decode_camera_image(data_url):
    if not data_url or "," not in data_url:
        raise ValueError("Camera image was not received correctly.")
    encoded = data_url.split(",", 1)[1]
    return base64.b64decode(encoded)


def collect_training_faces():
    faces = []
    labels = []
    label_to_teacher = {}
    teachers = Teacher.query.order_by(Teacher.name.asc()).all()
    label = 0
    for teacher in teachers:
        teacher_faces = []
        for img in teacher.images:
            path = os.path.join(teacher_folder(teacher.id), img.filename)
            if not os.path.exists(path):
                continue
            try:
                with open(path, "rb") as f:
                    gray = image_to_gray_array(f.read())
                face = detect_largest_face(gray)
                if face is not None:
                    teacher_faces.append(face)
            except Exception:
                continue
        if teacher_faces:
            label_to_teacher[label] = teacher
            for face in teacher_faces:
                faces.append(face)
                labels.append(label)
            label += 1
    return faces, labels, label_to_teacher


def recognize_teacher(image_bytes):
    captured_gray = image_to_gray_array(image_bytes)
    captured_face = detect_largest_face(captured_gray)
    if captured_face is None:
        return None, None, "No clear face detected. Please face the camera with good lighting."

    faces, labels, label_to_teacher = collect_training_faces()
    if not faces:
        return None, None, "No trained teacher images found. Admin must upload teacher photos first."

    recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    recognizer.train(faces, np.array(labels))
    predicted_label, confidence = recognizer.predict(captured_face)
    teacher = label_to_teacher.get(predicted_label)

    if teacher is None or confidence > FACE_CONFIDENCE_THRESHOLD:
        return None, float(confidence), "Face not confidently matched. Please try again or ask admin to upload clearer photos."

    return teacher, float(confidence), "Matched successfully."


def today_record_for(teacher):
    today = date.today()
    record = AttendanceRecord.query.filter_by(teacher_id=teacher.id, record_date=today).first()
    if not record:
        record = AttendanceRecord(teacher_id=teacher.id, record_date=today)
        db.session.add(record)
        db.session.flush()
    return record


def admin_required():
    return current_user.is_authenticated and current_user.role == "admin"


@app.before_request
def initialize_database():
    if not getattr(app, "_database_initialized", False):
        db.create_all()
        if not User.query.filter_by(username="admin").first():
            user = User(username="admin", password_hash=generate_password_hash("1234"), role="admin")
            db.session.add(user)
            db.session.commit()
        app._database_initialized = True


@app.route("/")
def index():
    teacher_count = Teacher.query.count()
    return render_template("index.html", teacher_count=teacher_count)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("admin_dashboard"))
        flash("Invalid username or password.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("index"))
    teachers = Teacher.query.order_by(Teacher.name.asc()).all()
    today = date.today()
    records_today = AttendanceRecord.query.filter_by(record_date=today).all()
    return render_template("admin.html", teachers=teachers, records_today=records_today)


@app.route("/admin/teachers", methods=["POST"])
@login_required
def add_teacher():
    if not admin_required():
        return redirect(url_for("index"))
    name = request.form.get("name", "").strip()
    department = request.form.get("department", "").strip()
    files = request.files.getlist("photos")
    if not name:
        flash("Teacher name is required.", "danger")
        return redirect(url_for("admin_dashboard"))
    teacher = Teacher.query.filter_by(name=name).first()
    if not teacher:
        teacher = Teacher(name=name, department=department)
        db.session.add(teacher)
        db.session.flush()
    else:
        teacher.department = department or teacher.department
    saved = 0
    for file in files:
        if file and allowed_file(file.filename):
            ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
            filename = f"{uuid.uuid4().hex}.{ext}"
            path = os.path.join(teacher_folder(teacher.id), filename)
            raw = file.read()
            face = detect_largest_face(image_to_gray_array(raw))
            if face is None:
                continue
            with open(path, "wb") as f:
                f.write(raw)
            db.session.add(TeacherImage(teacher_id=teacher.id, filename=filename))
            saved += 1
    db.session.commit()
    flash(f"Teacher saved. {saved} valid face image(s) uploaded.", "success" if saved else "warning")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/teacher/<int:teacher_id>/delete", methods=["POST"])
@login_required
def delete_teacher(teacher_id):
    if not admin_required():
        return redirect(url_for("index"))
    teacher = db.session.get(Teacher, teacher_id)
    if teacher:
        folder = teacher_folder(teacher.id)
        db.session.delete(teacher)
        db.session.commit()
        try:
            for filename in os.listdir(folder):
                os.remove(os.path.join(folder, filename))
            os.rmdir(folder)
        except Exception:
            pass
        flash("Teacher deleted.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/attendance/<action>")
def attendance_page(action):
    if action not in {"in", "out"}:
        return redirect(url_for("index"))
    return render_template("attendance.html", action=action)


@app.route("/api/attendance", methods=["POST"])
def api_attendance():
    payload = request.get_json(silent=True) or {}
    action = payload.get("action")
    if action not in {"in", "out"}:
        return jsonify({"ok": False, "message": "Invalid attendance action."}), 400
    try:
        image_bytes = decode_camera_image(payload.get("image"))
        teacher, confidence, message = recognize_teacher(image_bytes)
        if not teacher:
            return jsonify({"ok": False, "message": message, "confidence": confidence})
        record = today_record_for(teacher)
        now = datetime.now()
        if action == "in":
            if record.sign_in_time:
                return jsonify({"ok": False, "message": f"{teacher.name} already signed in today."})
            record.sign_in_time = now
            record.sign_in_confidence = confidence
            text = f"Welcome {teacher.name}. Sign in recorded at {now.strftime('%H:%M:%S')}."
        else:
            if not record.sign_in_time:
                return jsonify({"ok": False, "message": f"{teacher.name} must sign in before signing out."})
            if record.sign_out_time:
                return jsonify({"ok": False, "message": f"{teacher.name} already signed out today."})
            record.sign_out_time = now
            record.sign_out_confidence = confidence
            text = f"Goodbye {teacher.name}. Sign out recorded at {now.strftime('%H:%M:%S')}."
        db.session.commit()
        return jsonify({"ok": True, "message": text, "teacher": teacher.name, "confidence": confidence})
    except Exception as exc:
        return jsonify({"ok": False, "message": f"Processing error: {exc}"}), 500


def parse_date_or_none(value):
    if not value:
        return None
    return datetime.strptime(value, "%Y-%m-%d").date()


def date_range(start, end):
    from datetime import timedelta
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def build_report_rows(teacher_id=None, start_date="", end_date="", status="all"):
    start = parse_date_or_none(start_date)
    end = parse_date_or_none(end_date)
    if status == "not_signed_in":
        if not start and not end:
            start = end = date.today()
        elif start and not end:
            end = start
        elif end and not start:
            start = end
        teachers_query = Teacher.query.order_by(Teacher.name.asc())
        if teacher_id:
            teachers_query = teachers_query.filter(Teacher.id == teacher_id)
        rows = []
        for day in date_range(start, end):
            for teacher in teachers_query.all():
                record = AttendanceRecord.query.filter_by(teacher_id=teacher.id, record_date=day).first()
                if record is None or record.sign_in_time is None:
                    rows.append({
                        "date": day,
                        "teacher": teacher,
                        "sign_in_time": record.sign_in_time if record else None,
                        "sign_out_time": record.sign_out_time if record else None,
                        "status": "Not signed in",
                        "sign_in_confidence": record.sign_in_confidence if record else None,
                        "sign_out_confidence": record.sign_out_confidence if record else None,
                    })
        return rows

    query = AttendanceRecord.query.join(Teacher)
    if teacher_id:
        query = query.filter(AttendanceRecord.teacher_id == teacher_id)
    if start:
        query = query.filter(AttendanceRecord.record_date >= start)
    if end:
        query = query.filter(AttendanceRecord.record_date <= end)
    if status == "not_signed_out":
        query = query.filter(AttendanceRecord.sign_in_time.isnot(None), AttendanceRecord.sign_out_time.is_(None))
    elif status == "complete":
        query = query.filter(AttendanceRecord.sign_in_time.isnot(None), AttendanceRecord.sign_out_time.isnot(None))
    records = query.order_by(AttendanceRecord.record_date.desc(), Teacher.name.asc()).all()
    rows = []
    for record in records:
        if not record.sign_in_time:
            row_status = "Not signed in"
        elif not record.sign_out_time:
            row_status = "Not signed out"
        else:
            row_status = "Complete"
        rows.append({
            "date": record.record_date,
            "teacher": record.teacher,
            "sign_in_time": record.sign_in_time,
            "sign_out_time": record.sign_out_time,
            "status": row_status,
            "sign_in_confidence": record.sign_in_confidence,
            "sign_out_confidence": record.sign_out_confidence,
        })
    return rows


@app.route("/admin/reports")
@login_required
def reports():
    if not admin_required():
        return redirect(url_for("index"))
    teacher_id = request.args.get("teacher_id", type=int)
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    status = request.args.get("status", "all")
    rows = build_report_rows(teacher_id, start_date, end_date, status)
    teachers = Teacher.query.order_by(Teacher.name.asc()).all()
    return render_template("reports.html", rows=rows, teachers=teachers, filters=request.args)


@app.route("/admin/reports/export")
@login_required
def export_report():
    if not admin_required():
        return redirect(url_for("index"))
    teacher_id = request.args.get("teacher_id", type=int)
    start_date = request.args.get("start_date", "")
    end_date = request.args.get("end_date", "")
    status = request.args.get("status", "all")
    rows = build_report_rows(teacher_id, start_date, end_date, status)

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance Report"
    ws.merge_cells("A1:H1")
    ws["A1"] = "School Face Recognition Attendance Report"
    ws["A1"].font = Font(size=16, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor="1F4E78")
    ws["A1"].alignment = Alignment(horizontal="center")
    headers = ["Date", "Teacher", "Department", "Sign In", "Sign Out", "Status", "Sign In Confidence", "Sign Out Confidence"]
    ws.append([])
    ws.append(headers)
    header_fill = PatternFill("solid", fgColor="D9EAF7")
    thin = Side(border_style="thin", color="D9D9D9")
    for cell in ws[3]:
        cell.font = Font(bold=True)
        cell.fill = header_fill
        cell.border = Border(top=thin, left=thin, right=thin, bottom=thin)
        cell.alignment = Alignment(horizontal="center")
    for row in rows:
        ws.append([
            row["date"].strftime("%Y-%m-%d"),
            row["teacher"].name,
            row["teacher"].department or "-",
            row["sign_in_time"].strftime("%H:%M:%S") if row["sign_in_time"] else "-",
            row["sign_out_time"].strftime("%H:%M:%S") if row["sign_out_time"] else "-",
            row["status"],
            round(row["sign_in_confidence"], 2) if row["sign_in_confidence"] is not None else "-",
            round(row["sign_out_confidence"], 2) if row["sign_out_confidence"] is not None else "-",
        ])
    for row in ws.iter_rows(min_row=4):
        for cell in row:
            cell.border = Border(top=thin, left=thin, right=thin, bottom=thin)
            cell.alignment = Alignment(horizontal="center")
    widths = [15, 28, 22, 14, 14, 18, 20, 20]
    for idx, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = "A4"
    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    filename = f"attendance_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return send_file(output, as_attachment=True, download_name=filename, mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")



if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
