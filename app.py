from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session
import os
import sqlite3
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"  # Change this in production

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt"}

# ---------- Database Setup ----------
def init_db():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    
    # Teachers table
    c.execute("""CREATE TABLE IF NOT EXISTS teachers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT,
                    email TEXT UNIQUE,
                    password TEXT,
                    status TEXT DEFAULT 'pending'
                )""")
    
    # Files table
    c.execute("""CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_name TEXT,
                    file_path TEXT,
                    uploader_id INTEGER,
                    subject TEXT,
                    upload_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )""")
    
    # Admin table
    c.execute("""CREATE TABLE IF NOT EXISTS admin (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE,
                    password TEXT
                )""")
    
    # Default admin account
    c.execute("INSERT OR IGNORE INTO admin (id, username, password) VALUES (1, 'admin', 'admin123')")
    
    conn.commit()
    conn.close()

init_db()

# ---------- Helper Functions ----------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# ---------- Routes ----------

# Home - Public file listing
@app.route("/")
def index():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM files ORDER BY upload_date DESC")
    files = c.fetchall()
    conn.close()
    return render_template("index.html", files=files)

# Teacher registration
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()
        try:
            c.execute("INSERT INTO teachers (name, email, password) VALUES (?, ?, ?)", (name, email, password))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return "Email already registered!"
        conn.close()
        return "Registration successful! Wait for admin approval."
    return render_template("register.html")

# Login (admin & teacher)
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form["role"]
        email_or_username = request.form["email"]
        password = request.form["password"]

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        if role == "admin":
            c.execute("SELECT * FROM admin WHERE username=? AND password=?", (email_or_username, password))
            admin = c.fetchone()
            if admin:
                session["admin"] = True
                return redirect(url_for("admin_dashboard"))
        else:
            c.execute("SELECT * FROM teachers WHERE email=? AND password=?", (email_or_username, password))
            teacher = c.fetchone()
            if teacher and teacher[4] == "approved":
                session["teacher_id"] = teacher[0]
                return redirect(url_for("upload"))
        
        conn.close()
        return "Invalid credentials or not approved yet."
    return render_template("login.html")

# Admin dashboard
@app.route("/admin", methods=["GET", "POST"])
def admin_dashboard():
    if not session.get("admin"):
        return redirect(url_for("login"))

    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT * FROM teachers WHERE status='pending'")
    pending_teachers = c.fetchall()
    conn.close()
    return render_template("admin.html", teachers=pending_teachers)

@app.route("/approve/<int:teacher_id>")
def approve_teacher(teacher_id):
    if not session.get("admin"):
        return redirect(url_for("login"))
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("UPDATE teachers SET status='approved' WHERE id=?", (teacher_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin_dashboard"))

# Teacher file upload
@app.route("/upload", methods=["GET", "POST"])
def upload():
    if not session.get("teacher_id"):
        return redirect(url_for("login"))

    if request.method == "POST":
        subject = request.form["subject"]
        file = request.files["file"]
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(file_path)

            conn = sqlite3.connect("database.db")
            c = conn.cursor()
            c.execute("INSERT INTO files (file_name, file_path, uploader_id, subject) VALUES (?, ?, ?, ?)",
                      (filename, filename, session["teacher_id"], subject))
            conn.commit()
            conn.close()
            return "File uploaded successfully!"
    return render_template("upload.html")

# File download
@app.route("/uploads/<filename>")
def download_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

if __name__ == "__main__":
    app.run(debug=True)
