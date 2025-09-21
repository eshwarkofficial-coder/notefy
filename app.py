from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, Response
import os
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from supabase import create_client, Client
from dotenv import load_dotenv
import io


load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "supersecretkey-change-me")

UPLOAD_FOLDER = "upload"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTENSIONS = {"pdf", "docx", "pptx", "txt", "xlsx", "zip", "png", "jpg"}


SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("Please set SUPABASE_URL and SUPABASE_KEY in your .env file")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


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



def upload_file_to_storage(file_bytes, file_path: str, bucket_name: str = "notefy-files"):
    
    try:
        print("Length of file_bytes in bytes:", len(file_bytes))
        response = supabase.storage.from_(bucket_name).upload(
            path=file_path,
            file=file_bytes,  
            file_options={"content-type": "application/octet-stream"}
        )
        return True
    except Exception as e:
        print(f"Storage upload error: {e}")
        return False




@app.route("/")
def index():
    try:
        response = supabase.table('files').select('*').order('upload_date', desc=True).execute()
        files = response.data if response.data else []
        print("Fetched files:", files)
        
        folder_rows = supabase.table('folders').select('id', 'name').execute().data
        folder_map = {folder['id']: folder['name'] for folder in folder_rows}


        for f in files:
            f['folder_name'] = folder_map.get(f['folder_id'], "Unsorted")
        print("Fetched files:", files)

        return render_template("index.html", files=files)
    except Exception as e:
        flash("Error loading files.")
        return render_template("index.html", files=[])

@app.route("/upload/<path:filename>")
def download_file(filename):
    bucket_name = "notefy-files"
    try:
        
        file_bytes = supabase.storage.from_(bucket_name).download(filename)
        if file_bytes is None:
            flash("File not found in cloud storage.")
            return redirect(url_for("index"))
        
        
        return Response(
            file_bytes,
            mimetype="application/octet-stream",
            headers={"Content-Disposition": f"attachment;filename={filename.split('/')[-1]}"}
        )
    except Exception as e:
        flash("Error fetching file.")
        return redirect(url_for("index"))


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        try:
            supabase.table('teachers').insert({
                'name': name,
                'email': email,
                'password': password,
                'status': 'pending'
            }).execute()
            
            flash("Registration submitted. Wait for admin approval.")
        except Exception as e:
            if "duplicate" in str(e).lower():
                flash("Email already registered.")
            else:
                flash("Registration failed. Please try again.")
        
        return redirect(url_for("login"))
    
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        role = request.form.get("role")
        email_or_username = request.form.get("email")
        password = request.form.get("password")

        try:
            if role == "admin":
                response = supabase.table('admin').select('*').eq('username', email_or_username).eq('password', password).execute()
                if response.data:
                    session.clear()
                    session["admin"] = True
                    return redirect(url_for("admin_dashboard"))
            else:
                response = supabase.table('teachers').select('*').eq('email', email_or_username).eq('password', password).execute()
                teacher = response.data[0] if response.data else None
                
                if teacher and teacher["status"] == "approved":
                    session.clear()
                    session["teacher_id"] = teacher["id"]
                    session["teacher_name"] = teacher["name"]
                    return redirect(url_for("teacher_files"))
        except Exception as e:
            print(f"Login error: {e}")

        flash("Invalid credentials or not approved yet.")
    
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))

@app.route("/admin")
def admin_dashboard():
    must = require_admin()
    if must:
        return must

    try:
        response = supabase.table('teachers').select('*').eq('status', 'pending').execute()
        pending = response.data if response.data else []
        return render_template("admin.html", teachers=pending)
    except Exception as e:
        flash("Error loading pending teachers.")
        return render_template("admin.html", teachers=[])

@app.route("/approve/<int:teacher_id>")
def approve_teacher(teacher_id):
    must = require_admin()
    if must:
        return must

    try:
        supabase.table('teachers').update({'status': 'approved'}).eq('id', teacher_id).execute()
        flash("Teacher approved successfully.")
    except Exception as e:
        flash("Error approving teacher.")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/timetable", methods=["GET", "POST"])
def timetable_admin():
    must = require_admin()
    if must:
        return must

    if request.method == "POST":
        try:
            data = {
                'day_of_week': int(request.form["day_of_week"]),
                'title': request.form["title"].strip(),
                'start_time': request.form["start_time"],
                'end_time': request.form["end_time"],
                'teacher': request.form.get("teacher", "").strip(),
                'location': request.form.get("location", "").strip(),
                'notes': request.form.get("notes", "").strip()
            }
            
            supabase.table('timetable').insert(data).execute()
            flash("Timetable entry added.")
        except Exception as e:
            flash("Error adding timetable entry.")
        
        return redirect(url_for("timetable_admin"))

    try:
        response = supabase.table('timetable').select('*').order('day_of_week').order('start_time').execute()
        entries = response.data if response.data else []
        return render_template("timetable_admin.html", entries=entries)
    except Exception as e:
        flash("Error loading timetable.")
        return render_template("timetable_admin.html", entries=[])

@app.route("/admin/timetable/delete/<int:entry_id>")
def timetable_delete(entry_id):
    must = require_admin()
    if must:
        return must

    try:
        supabase.table('timetable').delete().eq('id', entry_id).execute()
        flash("Deleted timetable entry.")
    except Exception as e:
        flash("Error deleting timetable entry.")
    
    return redirect(url_for("timetable_admin"))

@app.route("/timetable")
def timetable_public():
    today = datetime.now()
    week_start = today - timedelta(days=today.weekday())

    try:
        response = supabase.table('timetable').select('*').order('day_of_week').order('start_time').execute()
        entries = response.data if response.data else []

       
        week = {i: [] for i in range(7)}
        for e in entries:
            week[e["day_of_week"]].append(e)

        
        days = []
        for i in range(7):
            d = week_start + timedelta(days=i)
            days.append({"idx": i, "date": d.strftime("%a %d %b"), "iso": d.strftime("%Y-%m-%d")})

        return render_template("timetable_public.html", week=week, days=days)
    except Exception as e:
        flash("Error loading timetable.")
        return render_template("timetable_public.html", week={i: [] for i in range(7)}, days=[])

@app.route("/teacher/files")
def teacher_files():
    must = require_teacher()
    if must:
        return must

    teacher_id = session["teacher_id"]

    try:
        
        folders_response = supabase.table('folders').select('*').eq('owner_id', teacher_id).order('created_at', desc=True).execute()
        folders = folders_response.data if folders_response.data else []

        
        files_response = supabase.table('files').select('''
            *,
            folders:folder_id(name)
        ''').eq('uploader_id', teacher_id).order('upload_date', desc=True).execute()
        files = files_response.data if files_response.data else []

        return render_template("teacher_files.html", folders=folders, files=files)
    except Exception as e:
        flash("Error loading files and folders.")
        return render_template("teacher_files.html", folders=[], files=[])

@app.route("/folder/create", methods=["POST"])
def folder_create():
    must = require_teacher()
    if must:
        return must

    name = request.form["name"].strip()
    parent_id = request.form.get("parent_id") or None
    teacher_id = session["teacher_id"]

    try:
        data = {'name': name, 'owner_id': teacher_id}
        if parent_id:
            data['parent_id'] = int(parent_id)
            
        supabase.table('folders').insert(data).execute()
        flash("Folder created.")
    except Exception as e:
        flash("Error creating folder.")

    return redirect(url_for("teacher_files"))

@app.route("/folder/rename/<int:folder_id>", methods=["POST"])
def folder_rename(folder_id):
    must = require_teacher()
    if must:
        return must

    new_name = request.form["name"].strip()
    teacher_id = session["teacher_id"]

    try:
        supabase.table('folders').update({'name': new_name}).eq('id', folder_id).eq('owner_id', teacher_id).execute()
        flash("Folder renamed.")
    except Exception as e:
        flash("Error renaming folder.")

    return redirect(url_for("teacher_files"))

@app.route("/folder/delete/<int:folder_id>")
def folder_delete(folder_id):
    must = require_teacher()
    if must:
        return must

    teacher_id = session["teacher_id"]

    try:
        
        files_response = supabase.table('files').select('id').eq('folder_id', folder_id).execute()
        if files_response.data:
            flash("Folder not empty. Delete files first.")
            return redirect(url_for("teacher_files"))

        supabase.table('folders').delete().eq('id', folder_id).eq('owner_id', teacher_id).execute()
        flash("Folder deleted.")
    except Exception as e:
        flash("Error deleting folder.")

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
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_filename = f"{timestamp}_{filename}"
            file_path = f"teacher_{teacher_id}/{unique_filename}"

            
            file_bytes = file.read()
            file.seek(0)  

                        
            teacher_dir = os.path.join(app.config["UPLOAD_FOLDER"], f"t_{teacher_id}")
            os.makedirs(teacher_dir, exist_ok=True)
            local_path = os.path.join(teacher_dir, unique_filename)
            file.save(local_path)

            
            storage_success = upload_file_to_storage(file_bytes, file_path)

            
            try:
                
                data = {
                    'file_name': filename,
                    'file_path': file_path if storage_success else f"t_{teacher_id}/{unique_filename}",
                    'uploader_id': teacher_id,
                    'subject': subject
                }
                if folder_id:
                    data['folder_id'] = int(folder_id)
                    
                supabase.table('files').insert(data).execute()
                
                if storage_success:
                    flash("File uploaded successfully to cloud storage.")
                else:
                    flash("File uploaded locally (cloud storage unavailable).")
                    
            except Exception as e:
                flash("Error saving file information.")
        else:
            flash("Invalid file type or no file selected.")

        return redirect(url_for("teacher_files"))

   
    try:
        folders_response = supabase.table('folders').select('*').eq('owner_id', teacher_id).order('name').execute()
        folders = folders_response.data if folders_response.data else []
        return render_template("upload.html", folders=folders)
    except Exception as e:
        return render_template("upload.html", folders=[])

@app.route("/file/delete/<int:file_id>")
def file_delete(file_id):
    must = require_teacher()
    if must:
        return must

    teacher_id = session["teacher_id"]

    try:
        
        file_response = supabase.table('files').select('*').eq('id', file_id).eq('uploader_id', teacher_id).execute()
        
        if not file_response.data:
            flash("File not found or access denied.")
            return redirect(url_for("teacher_files"))

        file_info = file_response.data[0]
        file_path = file_info['file_path']

        
        supabase.table('files').delete().eq('id', file_id).eq('uploader_id', teacher_id).execute()

        
        try:
            supabase.storage.from_('notefy-files').remove([file_path])
        except Exception:
            pass  

        
        try:
            local_path = os.path.join(app.config["UPLOAD_FOLDER"], file_path)
            if os.path.exists(local_path):
                os.remove(local_path)
        except Exception:
            pass

        flash("File deleted successfully.")
    except Exception as e:
        flash("Error deleting file.")

    return redirect(url_for("teacher_files"))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("FLASK_ENV") == "development")
