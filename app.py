from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash
import os
import sqlite3
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

app = Flask(__name__)
app.secret_key = "supersecretkey-change-me"  # change in production

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "xlsx", "zip", "png", "jpg"}

# ---------------- Database ----------------

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()

    # teachers
    c.execute(
        """CREATE TABLE IF NOT EXISTS teachers (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT,
               email TEXT UNIQUE,
               password TEXT,
               status TEXT DEFAULT 'pending'
           )"""
    )

    # folders (owned by teacher; can be nested with parent_id)
    c.execute(
        """CREATE TABLE IF NOT EXISTS folders (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               name TEXT NOT NULL,
               parent_id INTEGER,
               owner_id INTEGER NOT NULL,
               created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY(owner_id) REFERENCES teachers(id)
           )"""
    )

    # files (linked to folder_id)
    c.execute(
        """CREATE TABLE IF NOT EXISTS files (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               file_name TEXT,
               file_path TEXT,
               uploader_id INTEGER,
               folder_id INTEGER,
               subject TEXT,
               upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
               FOREIGN KEY(uploader_id) REFERENCES teachers(id),
               FOREIGN KEY(folder_id) REFERENCES folders(id)
           )"""
    )

    # admin
    c.execute(
        """CREATE TABLE IF NOT EXISTS admin (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               username TEXT UNIQUE,
               password TEXT
           )"""
    )

    # timetable (weekly recurring)
    # day_of_week: 0=Mon .. 6=Sun; times in HH:MM 24h
    c.execute(
        """CREATE TABLE IF NOT EXISTS timetable (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               day_of_week INTEGER NOT NULL,
               title TEXT NOT NULL,
               start_time TEXT NOT NULL,
               end_time TEXT NOT NULL,
               teacher TEXT,
               location TEXT,
               notes TEXT
           )"""
    )

    # default admin
    c.execute(
        "INSERT OR IGNORE INTO admin (id, username, password) VALUES (1, 'admin', 'admin123')"
    )

    conn.commit()
    conn.close()

init_db()

# ---------------- Helpers ----------------

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def require_admin():
    if not session.get("admin"):
        return redirect(url_for("login"))
    return None

def require_teacher():
    if not session.get("teacher_id"):
        return redirect(url_for("login"))
    return None

def week_range_for(date_obj):
    # return (monday_date, sunday_date) covering date_obj
    monday = date_obj - timedelta(days=(date_obj.weekday()))
    sunday = monday + timedelta(days=6)
    return monday, sunday

# ---------------- Routes: Public ----------------

@app.route("/")
def index():
    conn = get_db()
    c = conn.cursor()
    # show latest files with folder name and teacher name
    c.execute(
        """
        SELECT f.id, f.file_name, f.file_path, f.subject, f.upload_date,
               t.name AS teacher_name,
               COALESCE((SELECT name FROM folders WHERE id=f.folder_id), '') AS folder_name
        FROM files f
        LEFT JOIN teachers t ON t.id = f.uploader_id
        ORDER BY f.upload_date DESC
        """
    )
    files = c.fetchall()
    conn.close()
    return render_template("index.html", files=files)

@app.route("/uploads/<path:filename>")
def download_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename, as_attachment=True)

# ---------------- Auth ----------------

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        conn = get_db()
        c = conn.cursor()
        try:
            c.execute(
                "INSERT INTO teachers (name, email, password) VALUES (?, ?, ?)",
                (name, email, password),
            )
            conn.commit()
            flash("Registration submitted. Wait for admin approval.")
        except sqlite3.IntegrityError:
            flash("Email already registered.")
        finally:
            conn.close()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        email_or_username = request.form.get("email")
        password = request.form.get("password")
        conn = get_db()
        c = conn.cursor()
        if role == "admin":
            c.execute(
                "SELECT * FROM admin WHERE username=? AND password=?",
                (email_or_username, password),
            )
            admin = c.fetchone()
            if admin:
                session.clear()
                session["admin"] = True
                conn.close()
                return redirect(url_for("admin_dashboard"))
        else:
            c.execute(
                "SELECT * FROM teachers WHERE email=? AND password=?",
                (email_or_username, password),
            )
            t = c.fetchone()
            if t and t["status"] == "approved":
                session.clear()
                session["teacher_id"] = t["id"]
                session["teacher_name"] = t["name"]
                conn.close()
                return redirect(url_for("teacher_files"))
        conn.close()
        flash("Invalid credentials or not approved yet.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

# ---------------- Admin ----------------

@app.route("/admin")
def admin_dashboard():
    must = require_admin()
    if must:
        return must
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM teachers WHERE status='pending'")
    pending = c.fetchall()
    conn.close()
    return render_template("admin.html", teachers=pending)

@app.route("/approve/<int:teacher_id>")
def approve_teacher(teacher_id):
    must = require_admin()
    if must:
        return must
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE teachers SET status='approved' WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

# Timetable admin CRUD
@app.route("/admin/timetable", methods=["GET", "POST"])
def timetable_admin():
    must = require_admin()
    if must:
        return must
    conn = get_db()
    c = conn.cursor()
    if request.method == "POST":
        # add new entry
        day = int(request.form["day_of_week"])  # 0..6
        title = request.form["title"].strip()
        start_time = request.form["start_time"]  # HH:MM
        end_time = request.form["end_time"]
        teacher = request.form.get("teacher", "").strip()
        location = request.form.get("location", "").strip()
        notes = request.form.get("notes", "").strip()
        c.execute(
            """
            INSERT INTO timetable (day_of_week, title, start_time, end_time, teacher, location, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (day, title, start_time, end_time, teacher, location, notes),
        )
        conn.commit()
        flash("Timetable entry added.")
        return redirect(url_for("timetable_admin"))

    c.execute("SELECT * FROM timetable ORDER BY day_of_week, start_time")
    entries = c.fetchall()
    conn.close()
    return render_template("timetable_admin.html", entries=entries)

@app.route("/admin/timetable/delete/<int:entry_id>")
def timetable_delete(entry_id):
    must = require_admin()
    if must:
        return must
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM timetable WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    flash("Deleted timetable entry.")
    return redirect(url_for("timetable_admin"))

# ---------------- Timetable public ----------------

@app.route("/timetable")
def timetable_public():
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM timetable ORDER BY day_of_week, start_time")
    entries = c.fetchall()
    conn.close()

    # group by day 0..6
    week = {i: [] for i in range(7)}
    for e in entries:
        week[e["day_of_week"]].append(e)

    # dates for header
    days = []
    for i in range(7):
        d = week_start + timedelta(days=i)
        days.append({"idx": i, "date": d.strftime("%a %d %b"), "iso": d.strftime("%Y-%m-%d")})

    return render_template("timetable_public.html", week=week, days=days)

# ---------------- Teacher: folders & files ----------------

@app.route("/teacher/files")
def teacher_files():
    must = require_teacher()
    if must:
        return must
    teacher_id = session["teacher_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM folders WHERE owner_id=? ORDER BY created_at DESC", (teacher_id,))
    folders = c.fetchall()
    c.execute(
        """
        SELECT f.*, COALESCE((SELECT name FROM folders WHERE id=f.folder_id), '') AS folder_name
        FROM files f WHERE uploader_id=? ORDER BY upload_date DESC
        """,
        (teacher_id,),
    )
    files = c.fetchall()
    conn.close()
    return render_template("teacher_files.html", folders=folders, files=files)

@app.route("/folder/create", methods=["POST"])
def folder_create():
    must = require_teacher()
    if must:
        return must
    name = request.form["name"].strip()
    parent_id = request.form.get("parent_id") or None
    teacher_id = session["teacher_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "INSERT INTO folders (name, parent_id, owner_id) VALUES (?, ?, ?)",
        (name, parent_id, teacher_id),
    )
    conn.commit()
    conn.close()
    flash("Folder created.")
    return redirect(url_for("teacher_files"))

@app.route("/folder/rename/<int:folder_id>", methods=["POST"])
def folder_rename(folder_id):
    must = require_teacher()
    if must:
        return must
    new_name = request.form["name"].strip()
    teacher_id = session["teacher_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "UPDATE folders SET name=? WHERE id=? AND owner_id=?",
        (new_name, folder_id, teacher_id),
    )
    conn.commit()
    conn.close()
    flash("Folder renamed.")
    return redirect(url_for("teacher_files"))

@app.route("/folder/delete/<int:folder_id>")
def folder_delete(folder_id):
    must = require_teacher()
    if must:
        return must
    teacher_id = session["teacher_id"]
    conn = get_db()
    c = conn.cursor()
    # prevent delete if files exist inside
    c.execute("SELECT COUNT(*) AS cnt FROM files WHERE folder_id=?", (folder_id,))
    cnt = c.fetchone()[0]
    if cnt and cnt > 0:
        conn.close()
        flash("Folder not empty. Delete files first.")
        return redirect(url_for("teacher_files"))
    # allow delete if owned
    c.execute("DELETE FROM folders WHERE id=? AND owner_id=?", (folder_id, teacher_id))
    conn.commit()
    conn.close()
    flash("Folder deleted.")
    return redirect(url_for("teacher_files"))

@app.route("/upload", methods=["GET", "POST"])
def upload():
    must = require_teacher()
    if must:
        return must
    teacher_id = session["teacher_id"]

    if request.method == "POST":
        subject = request.form.get("subject", "").strip()
        folder_id = request.form.get("folder_id")
        file = request.files.get("file")
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            # save in a subfolder path: uploads/<teacher_id>/
            teacher_dir = os.path.join(app.config["UPLOAD_FOLDER"], f"t_{teacher_id}")
            os.makedirs(teacher_dir, exist_ok=True)
            save_path = os.path.join(teacher_dir, filename)
            file.save(save_path)

            # store relative path from uploads/
            rel_path = os.path.relpath(save_path, app.config["UPLOAD_FOLDER"])

            conn = get_db()
            c = conn.cursor()
            c.execute(
                "INSERT INTO files (file_name, file_path, uploader_id, folder_id, subject) VALUES (?, ?, ?, ?, ?)",
                (filename, rel_path, teacher_id, folder_id, subject),
            )
            conn.commit()
            conn.close()
            flash("File uploaded.")
            return redirect(url_for("teacher_files"))
        else:
            flash("Invalid file type.")

    # GET: show folders to choose
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM folders WHERE owner_id=? ORDER BY name", (teacher_id,))
    folders = c.fetchall()
    conn.close()
    return render_template("upload.html", folders=folders)

@app.route("/file/delete/<int:file_id>")
def file_delete(file_id):
    must = require_teacher()
    if must:
        return must
    teacher_id = session["teacher_id"]
    conn = get_db()
    c = conn.cursor()
    c.execute(
        "SELECT file_path FROM files WHERE id=? AND uploader_id=?",
        (file_id, teacher_id),
    )
    row = c.fetchone()
    if not row:
        conn.close()
        flash("File not found or not yours.")
        return redirect(url_for("teacher_files"))
    rel_path = row[0]
    abs_path = os.path.join(app.config["UPLOAD_FOLDER"], rel_path)
    # delete db row
    c.execute("DELETE FROM files WHERE id=? AND uploader_id=?", (file_id, teacher_id))
    conn.commit()
    conn.close()
    # try delete file from disk
    try:
        if os.path.exists(abs_path):
            os.remove(abs_path)
    except Exception:
        pass
    flash("File deleted.")
    return redirect(url_for("teacher_files"))

if __name__ == "__main__":
    app.run(debug=True)
