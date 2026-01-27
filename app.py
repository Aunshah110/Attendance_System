from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify, make_response, abort, Response
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import pandas as pd
import re, csv, io
from datetime import datetime, time, date
from werkzeug.utils import secure_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer,Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from slugify import slugify
from io import BytesIO
from reportlab.lib.units import inch

app = Flask(__name__)
app.secret_key = 'app123'
app.secret_key = os.urandom(24)

conn = psycopg2.connect(
    host="localhost",
    database="attendance_db",
    user="attendance_user",
    password="uni@123"
)

def get_db_connection():
    return psycopg2.connect(
        "host=localhost dbname=attendance_db user=attendance_user password=uni@123"
    )

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Enable UUID extension
    cursor.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create tables with PostgreSQL-compatible syntax
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS batches (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS semesters (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sections (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            batch_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            UNIQUE (name, batch_id, department_id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id)
            );
    ''')

    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            batch_id INTEGER,
            department_id INTEGER, 
            section_id INTEGER,              
            batch_status TEXT,
            admission_date TEXT,
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
            );
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            semester_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            section_id INTEGER,  
            FOREIGN KEY (semester_id) REFERENCES semesters(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (section_id) REFERENCES sections(id)
        );

    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_allocations (
            id SERIAL PRIMARY KEY,
            course_id INTEGER,
            teacher_id TEXT,
            batch_id INTEGER,
            department_id INTEGER,
            section_id INTEGER,
            semester_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (teacher_id) REFERENCES users(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (section_id) REFERENCES sections(id),
            FOREIGN KEY (semester_id) REFERENCES semesters(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            student_id TEXT NOT NULL,
            course_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            semester_id INTEGER NOT NULL,
            section_id INTEGER,
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL,
            class_type TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (section_id) REFERENCES sections(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (semester_id) REFERENCES semesters(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timetable (
            id SERIAL PRIMARY KEY,
            course_id INTEGER,
            batch_id INTEGER,
            department_id INTEGER,
            semester_id INTEGER,
            section_id INTEGER,
            day TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            class_type TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (section_id) REFERENCES sections(id),
            FOREIGN KEY (semester_id) REFERENCES semesters(id)
        )
    ''')
    
    conn.commit()
    conn.close()

def admin_exists():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE role = %s', ('admin',))
    admin = cursor.fetchone()
    conn.close()
    return admin is not None

@app.context_processor
def utility_processor():
    return dict(admin_exists=admin_exists)


@app.route('/')
def home():
    if 'user_id' in session:
        # Redirect to the user's dashboard if already logged in
        return redirect(url_for(f"{session['role']}_dashboard"))
    return render_template('home.html')

@app.route('/about')
def about():
    """Team information page"""
    return render_template('about.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Prevent logging in again if already logged in
    if 'user_id' in session:
        flash('Please Logout from the current dashboard!', 'warning')
        return redirect(url_for(f"{session['role']}_dashboard"))

    if request.method == 'POST':
        # Convert input email to lowercase
        email = request.form['email'].strip().lower()
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()

        # Ensure DB email is compared in lowercase too
        cursor.execute('SELECT * FROM users WHERE LOWER(email) = %s', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['name'] = user[1]           # column index 1 = name
            session['role'] = user[4].lower()   # normalize role
            session['logged_in'] = True         # login flag

            flash('Login successful!', 'success')

            # Redirect to correct dashboard
            if session['role'] == 'admin':
                return redirect(url_for('admin_dashboard'))
            elif session['role'] == 'teacher':
                return redirect(url_for('teacher_dashboard'))
            elif session['role'] == 'student':
                return redirect(url_for('student_dashboard'))
            else:
                flash('Unknown role!', 'danger')
                return redirect(url_for('login'))
        else:
            flash('Invalid email or password', 'warning')

    return render_template('login.html')


# Logout route
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('home'))


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            # Check login first
            if not session.get('logged_in'):
                flash('You must log in first.', 'warning')
                return redirect(url_for('login'))

            current_role = session.get('role')

            # Check if user's role is allowed
            if current_role not in [r.lower() for r in roles]:
                flash('Access Denied! Please use your own dashboard.', 'warning')
                return redirect(url_for(f"{current_role}_dashboard"))

            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.route('/admin', endpoint='admin_dashboard')
@role_required('admin')
def admin_dashboard():
    return render_template('admin.html')

@app.route('/teacher', endpoint='teacher_dashboard')
@role_required('teacher')
def teacher_dashboard():
    return render_template('teacher.html')

@app.route('/student', endpoint='student_dashboard')
@role_required('student')
def student_dashboard():
    return render_template('student.html')



@app.route('/admin/manage_sections', methods=['GET', 'POST'])
@role_required('admin')
def manage_sections():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ---------------- ADD SECTION ----------------
        if request.method == 'POST' and 'add_section' in request.form:
            section_name = request.form['section_name'].strip()
            batch_id = request.form['batch_id']
            department_id = request.form['department_id']

            cursor.execute('''
                INSERT INTO sections (name, batch_id, department_id)
                VALUES (%s, %s, %s)
            ''', (section_name, batch_id, department_id))

            conn.commit()
            flash('Section added successfully!', 'success')

        # ---------------- DELETE SECTION ----------------
        elif request.method == 'POST' and 'delete_section' in request.form:
            section_id = request.form['section_id']

            # Optional safety: detach users first (avoid FK failure)
            cursor.execute('UPDATE users SET section_id=NULL WHERE section_id=%s', (section_id,))

            cursor.execute('DELETE FROM sections WHERE id=%s', (section_id,))
            conn.commit()
            flash('Section deleted successfully.', 'success')

    except Exception as e:
        conn.rollback()
        print(e)
        flash(str(e), 'danger')

    # ---------------- FETCH DATA FOR PAGE ----------------

    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()

    cursor.execute('''
        SELECT
            s.id,
            s.name AS section_name,
            b.name AS batch_name,
            d.name AS department_name
        FROM sections s
        JOIN batches b ON s.batch_id = b.id
        JOIN departments d ON s.department_id = d.id
        ORDER BY b.name, d.name, s.name
    ''')
    rows = cursor.fetchall()

    sections = []
    for r in rows:
        sections.append({
            'id': r[0],
            'section_name': r[1],
            'batch_name': r[2],
            'department_name': r[3]
        })

    conn.close()

    return render_template(
        'manage_sections.html',
        batches=batches,
        departments=departments,
        sections=sections
    )

@app.route('/admin/check_sections')
@role_required('admin', 'teacher')
def check_sections():
    batch_id = request.args.get('batch_id')
    department_id = request.args.get('department_id')

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT id, name FROM sections
        WHERE batch_id=%s AND department_id=%s
        ORDER BY name
    ''', (batch_id, department_id))
    rows = cursor.fetchall()
    conn.close()

    return jsonify(rows)

@app.route('/admin/manage_users', methods=['GET', 'POST'])
@role_required('admin')
def manage_users():

    if request.method == 'POST':
        user_id = request.form['user_id']
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']

        batch_id = None
        department_id = None
        section_id = None
        batch_status = None
        admission_date = None

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if role == 'student':
                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                batch_status = request.form['batch_status']

                # Determine section
                if request.form.get('section_id'):
                    section_id = request.form['section_id']
                else:
                    # No section → NULL in DB
                    section_id = None

                if batch_status == 'new':
                    admission_date = request.form['admission_date']

            cursor.execute('''
                INSERT INTO users
                (id, name, email, password, role,
                 batch_id, department_id, section_id,
                 batch_status, admission_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (
                user_id, name, email, password, role,
                batch_id, department_id, section_id,
                batch_status, admission_date
            ))

            conn.commit()
            flash('User registered successfully!', 'success')

        except Exception as e:
            conn.rollback()
            flash(str(e), 'danger')

        finally:
            conn.close()

        return redirect(url_for('manage_users'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()
    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()
    conn.close()

    return render_template('manage_users.html', batches=batches, departments=departments)


@app.route('/admin/import_users', methods=['POST'])
@role_required('admin')
def import_users():

    if 'csv_file' not in request.files:
        flash('No file uploaded.', 'danger')
        return redirect(url_for('manage_users'))

    file = request.files['csv_file']
    if file.filename == '' or not file.filename.endswith('.csv'):
        flash('Invalid CSV file.', 'danger')
        return redirect(url_for('manage_users'))

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = list(csv.DictReader(stream))

        conn = get_db_connection()
        cursor = conn.cursor()

        # ------------------ PRE-VALIDATION ------------------

        for row in csv_input:
            role = (row.get('role') or '').strip()

            raw_password = (row.get('password') or '').strip()
            if len(raw_password) < 8:
                raise Exception(
                    f"Password must be at least 8 characters for user ID {row.get('user_id')}"
                )

            if role == 'student':
                batch_id = (row.get('batch_id') or '').strip()
                department_id = (row.get('department_id') or '').strip()
                section_name = (row.get('section_name') or '').strip() or None

                # fetch batch & dept names
                cursor.execute('SELECT name FROM batches WHERE id=%s', (batch_id,))
                batch_res = cursor.fetchone()
                batch_name = batch_res[0] if batch_res else f"Unknown(ID:{batch_id})"

                cursor.execute('SELECT name FROM departments WHERE id=%s', (department_id,))
                dept_res = cursor.fetchone()
                dept_name = dept_res[0] if dept_res else f"Unknown(ID:{department_id})"

                cursor.execute('''
                    SELECT id FROM sections
                    WHERE batch_id=%s AND department_id=%s
                ''', (batch_id, department_id))
                sections = cursor.fetchall()

                if sections and not section_name:
                    raise Exception(
                        f"Section exists for {batch_name} & {dept_name}, "
                        f"but CSV has empty section_name."
                    )

                if not sections and section_name:
                    raise Exception(
                        f"No sections exist for {batch_name} & {dept_name}, "
                        f"but CSV provided section '{section_name}'."
                    )

        # ------------------ ACTUAL INSERT ------------------

        for row in csv_input:
            user_id = (row.get('user_id') or '').strip()
            name = (row.get('name') or '').strip()
            email = (row.get('email') or '').strip()
            password = generate_password_hash((row.get('password') or '').strip())
            role = (row.get('role') or '').strip()

            batch_id = None
            department_id = None
            section_id = None
            batch_status = None
            admission_date = None

            if role == 'student':
                batch_id = (row.get('batch_id') or '').strip()
                department_id = (row.get('department_id') or '').strip()
                batch_status = (row.get('batch_status') or '').strip()
                section_name = (row.get('section_name') or '').strip() or None

                if section_name:
                    cursor.execute('''
                        SELECT id FROM sections
                        WHERE name=%s AND batch_id=%s AND department_id=%s
                    ''', (section_name, batch_id, department_id))
                    res = cursor.fetchone()

                    cursor.execute('SELECT name FROM batches WHERE id=%s', (batch_id,))
                    batch_res = cursor.fetchone()
                    batch_name = batch_res[0] if batch_res else f"Unknown(ID:{batch_id})"

                    cursor.execute('SELECT name FROM departments WHERE id=%s', (department_id,))
                    dept_res = cursor.fetchone()
                    dept_name = dept_res[0] if dept_res else f"Unknown(ID:{department_id})"

                    if not res:
                        raise Exception(
                            f"Invalid '{section_name}' for {batch_name} & {dept_name}"
                        )
                    section_id = res[0]

                if batch_status == 'new':
                    admission_date = (row.get('admission_date') or '').strip()

            cursor.execute('''
                INSERT INTO users
                (id, name, email, password, role,
                 batch_id, department_id, section_id,
                 batch_status, admission_date)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ''', (
                user_id, name, email, password, role,
                batch_id, department_id, section_id,
                batch_status, admission_date
            ))

        conn.commit()
        flash('Users imported successfully!', 'success')

    except Exception as e:
        conn.rollback()
        print(e)
        flash(str(e), 'danger')

    finally:
        conn.close()

    return redirect(url_for('manage_users'))


@app.route('/get_courses', methods=['POST'])
@role_required("admin", "teacher")
def get_courses():
    data = request.get_json()

    batch_id = data.get('batch_id')
    department_id = data.get('department_id')
    semester_id = data.get('semester_id')
    section_id = data.get('section_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # ✔ If section is selected → fetch section-specific courses
    if section_id:
        cursor.execute("""
            SELECT id, name
            FROM courses
            WHERE batch_id = %s
              AND department_id = %s
              AND semester_id = %s
              AND section_id = %s
            ORDER BY name
        """, (batch_id, department_id, semester_id, section_id))

    # ✔ If no section exists for batch+dept → fetch only NULL section courses
    else:
        cursor.execute("""
            SELECT id, name
            FROM courses
            WHERE batch_id = %s
              AND department_id = %s
              AND semester_id = %s
              AND section_id IS NULL
            ORDER BY name
        """, (batch_id, department_id, semester_id))

    rows = cursor.fetchall()
    conn.close()

    return jsonify([
        {"id": r[0], "name": r[1]}
        for r in rows
    ])


@app.route('/admin/allocate_course', methods=['GET', 'POST'])
@role_required('admin')
def allocate_course():

    if request.method == 'POST':

        course_id = request.form.get('course_id')
        teacher_id = request.form.get('teacher_id')
        batch_id = request.form.get('batch_id')
        department_id = request.form.get('department_id')
        section_id = request.form.get('section_id') or None
        semester_id = request.form.get('semester_id')
        start_date = request.form.get('start_date')
        end_date = request.form.get('end_date')
        force_update = request.form.get('force_update')

        if not all([course_id, teacher_id, batch_id, department_id, semester_id, start_date, end_date]):
            flash("All fields are required.", "danger")
            return redirect(url_for('allocate_course'))

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if force_update:

                cursor.execute("""
                    UPDATE course_allocations
                    SET teacher_id=%s, start_date=%s, end_date=%s
                    WHERE course_id=%s
                      AND batch_id=%s
                      AND department_id=%s
                      AND semester_id=%s
                      AND (section_id=%s OR (%s IS NULL AND section_id IS NULL))
                """, (
                    teacher_id, start_date, end_date,
                    course_id, batch_id, department_id, semester_id,
                    section_id, section_id
                ))

                flash("Course allocation updated successfully!", "success")

            else:
                cursor.execute("""
                    INSERT INTO course_allocations
                    (course_id, teacher_id, batch_id, department_id, section_id, semester_id, start_date, end_date)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (
                    course_id, teacher_id, batch_id, department_id,
                    section_id, semester_id, start_date, end_date
                ))

                flash("Course allocated successfully!", "success")

            conn.commit()

        except Exception as e:
            conn.rollback()
            flash("Allocation failed. Please try again.", "danger")
            print("ALLOCATE ERROR:", e)

        finally:
            cursor.close()
            conn.close()

        return redirect(url_for('allocate_course'))

    # ---------- GET ----------
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT id, name FROM courses')
    courses = cursor.fetchall()

    cursor.execute("SELECT id, name FROM users WHERE role='teacher'")
    teachers = cursor.fetchall()

    cursor.execute('SELECT id, name FROM batches')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments')
    departments = cursor.fetchall()

    cursor.execute('SELECT id, name FROM semesters')
    semesters = cursor.fetchall()

    conn.close()

    return render_template(
        'allocate_course.html',
        courses=courses,
        teachers=teachers,
        batches=batches,
        departments=departments,
        semesters=semesters
    )


@app.route('/admin/check_course_allocation')
@role_required('admin')
def check_course_allocation():

    course_id = request.args.get('course_id')
    batch_id = request.args.get('batch_id')
    department_id = request.args.get('department_id')
    semester_id = request.args.get('semester_id')
    section_id = request.args.get('section_id')

    conn = get_db_connection()
    cur = conn.cursor()

    if section_id:
        cur.execute("""
            SELECT u.name
            FROM course_allocations ca
            JOIN users u ON ca.teacher_id = u.id
            WHERE ca.course_id=%s
              AND ca.batch_id=%s
              AND ca.department_id=%s
              AND ca.semester_id=%s
              AND ca.section_id=%s
            LIMIT 1
        """, (course_id, batch_id, department_id, semester_id, section_id))
    else:
        cur.execute("""
            SELECT u.name
            FROM course_allocations ca
            JOIN users u ON ca.teacher_id = u.id
            WHERE ca.course_id=%s
              AND ca.batch_id=%s
              AND ca.department_id=%s
              AND ca.semester_id=%s
              AND ca.section_id IS NULL
            LIMIT 1
        """, (course_id, batch_id, department_id, semester_id))

    row = cur.fetchone()
    conn.close()

    if row:
        return jsonify({"exists": True, "teacher": row[0]})
    else:
        return jsonify({"exists": False})



@app.route('/admin/view_students', methods=['GET', 'POST'])
@role_required("admin", "teacher")
def view_students():

    selected_batch = None
    selected_department = None
    selected_section = None

    students = []
    sections_available = False
    sections = []
    show_table = False
    form_submitted = False

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # -----------------------------
        # Dropdown Data
        # -----------------------------
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()

        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()

        # -----------------------------
        # Form Submit
        # -----------------------------
        if request.method == 'POST':
            form_submitted = True
            selected_batch = request.form.get('batch_id')
            selected_department = request.form.get('department_id')
            selected_section = request.form.get('section')

            # -----------------------------------------
            # Detect if this batch+dept has sections
            # -----------------------------------------
            cursor.execute('''
                SELECT DISTINCT section_id
                FROM users
                WHERE role = 'student'
                  AND batch_id = %s
                  AND department_id = %s
                  AND section_id IS NOT NULL
            ''', (selected_batch, selected_department))

            section_rows = cursor.fetchall()

            if section_rows:
                sections_available = True
                sections = sorted([r[0] for r in section_rows if r[0]])

            # -----------------------------------------
            # RULE 1: Sections exist but not selected
            # → DO NOT SHOW TABLE
            # -----------------------------------------
            if sections_available and not selected_section:
                show_table = False

            # -----------------------------------------
            # RULE 2: Sections exist AND selected
            # -----------------------------------------
            elif sections_available and selected_section:
                show_table = True

                cursor.execute('''
                    SELECT users.id,
                           users.name,
                           batches.name,
                           departments.name,
                           sections.name
                    FROM users
                    JOIN batches ON users.batch_id = batches.id
                    JOIN departments ON users.department_id = departments.id
                    JOIN sections ON users.section_id = sections.id
                    WHERE users.role = 'student'
                      AND users.batch_id = %s
                      AND users.department_id = %s
                      AND users.section_id = %s
                    ORDER BY CAST(SUBSTRING(users.id FROM '(\\d+)$') AS INTEGER)
                ''', (selected_batch, selected_department, selected_section))

                students = cursor.fetchall()

            # -----------------------------------------
            # RULE 3: No sections exist → show directly
            # -----------------------------------------
            else:
                show_table = True

                cursor.execute('''
                    SELECT users.id,
                           users.name,
                           batches.name,
                           departments.name,
                           NULL
                    FROM users
                    JOIN batches ON users.batch_id = batches.id
                    JOIN departments ON users.department_id = departments.id
                    WHERE users.role = 'student'
                      AND users.batch_id = %s
                      AND users.department_id = %s
                    ORDER BY CAST(SUBSTRING(users.id FROM '(\\d+)$') AS INTEGER)
                ''', (selected_batch, selected_department))

                students = cursor.fetchall()

    except Exception as e:
        print("VIEW STUDENTS ERROR:", e)
        students = []
        sections_available = False
        sections = []
        show_table = False

    finally:
        conn.close()

    return render_template(
    'view_students.html',
    batches=batches,
    departments=departments,
    students=students,
    sections_available=sections_available,
    sections=sections,
    form_submitted=form_submitted,
    selected_batch=selected_batch,
    selected_department=selected_department,
    selected_section=selected_section,
    show_table=show_table,
    user_role=session.get('role') 
    )

@app.route('/admin/update_student/<student_id>', methods=['GET', 'POST'])
@role_required("admin")
def update_student(student_id):

    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        batch_id = request.form['batch_id']
        department_id = request.form['department_id']
        section_id = request.form.get('section_id') or None

        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')

        conn = get_db_connection()
        cursor = conn.cursor()

        try:
            if new_password:
                hashed_password = generate_password_hash(new_password)
                cursor.execute('''
                    UPDATE users
                    SET name=%s,
                        email=%s,
                        batch_id=%s,
                        department_id=%s,
                        section_id=%s,
                        password=%s
                    WHERE id=%s
                ''', (name, email, batch_id, department_id, section_id, hashed_password, student_id))
            else:
                cursor.execute('''
                    UPDATE users
                    SET name=%s,
                        email=%s,
                        batch_id=%s,
                        department_id=%s,
                        section_id=%s
                    WHERE id=%s
                ''', (name, email, batch_id, department_id, section_id, student_id))

            conn.commit()
            flash('Student updated successfully!', 'success')
            return redirect(url_for('view_students'))

        except Exception as e:
            conn.rollback()
            flash('Error updating student!', 'error')
            return redirect(url_for('update_student', student_id=student_id))

        finally:
            conn.close()

    # -------- GET DATA --------
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('SELECT * FROM users WHERE id=%s', (student_id,))
    student = cursor.fetchone()

    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()

    # preload sections for student's current batch+dept
    cursor.execute('''
        SELECT id, name FROM sections
        WHERE batch_id=%s AND department_id=%s
        ORDER BY name
    ''', (student[5], student[6]))
    sections = cursor.fetchall()

    conn.close()

    return render_template(
        'update_student.html',
        student=student,
        batches=batches,
        departments=departments,
        sections=sections
    )

@app.route('/admin/delete_student/<student_id>', methods=['POST'])
@role_required("admin")
def delete_student(student_id):
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        # Delete dependent records first
        cursor.execute(
            "DELETE FROM attendance WHERE student_id = %s",
            (student_id,)
        )

        # Delete student
        cursor.execute(
            "DELETE FROM users WHERE id = %s",
            (student_id,)
        )
        conn.commit()

        flash("Student deleted successfully!", "success")

    except Exception as e:
        if conn:
            conn.rollback()
        flash("Failed to delete student.", "danger")
        app.logger.exception(e)

    finally:
        if conn:
            conn.close()

    return redirect(url_for('view_students'))
    


@app.route('/admin/generate_reports', methods=['GET', 'POST'])
@role_required("admin")
def admin_generate_reports():

    conn = get_db_connection()
    cursor = conn.cursor()

    report_data = []
    form_submitted = False

    selected_batch = None
    selected_department = None
    selected_section = None
    selected_semester = None

    batch_name = dept_name = semester_name = section_name = None

    try:
        # ------------------ DROPDOWNS ------------------
        cursor.execute('SELECT id, name FROM batches ORDER BY name')
        batches = cursor.fetchall()

        cursor.execute('SELECT id, name FROM departments ORDER BY name')
        departments = cursor.fetchall()

        cursor.execute('SELECT id, name FROM semesters ORDER BY id')
        semesters = cursor.fetchall()

        # ------------------ FORM SUBMIT ------------------
        if request.method == 'POST':
            form_submitted = True

            # EXPORT
            if 'export_csv' in request.form or 'export_pdf' in request.form:
                batch_id = session.get('report_batch_id')
                department_id = session.get('report_department_id')
                semester_id = session.get('report_semester_id')
                section_id = session.get('report_section_id')
            else:
                batch_id = request.form.get('batch_id')
                department_id = request.form.get('department_id')
                semester_id = request.form.get('semester_id')
                section_id = request.form.get('section_id') or None

                session['report_batch_id'] = batch_id
                session['report_department_id'] = department_id
                session['report_semester_id'] = semester_id
                session['report_section_id'] = section_id

            selected_batch = batch_id
            selected_department = department_id
            selected_section = section_id
            selected_semester = semester_id

            if not (batch_id and department_id and semester_id):
                flash("Please select Batch, Department and Semester.", "warning")
                return redirect(url_for('admin_generate_reports'))

            # ------------------ NAMES ------------------
            cursor.execute('SELECT name FROM batches WHERE id=%s', (batch_id,))
            batch_name = cursor.fetchone()[0]

            cursor.execute('SELECT name FROM departments WHERE id=%s', (department_id,))
            dept_name = cursor.fetchone()[0]

            cursor.execute('SELECT name FROM semesters WHERE id=%s', (semester_id,))
            semester_name = cursor.fetchone()[0]

            if section_id:
                cursor.execute('SELECT name FROM sections WHERE id=%s', (section_id,))
                r = cursor.fetchone()
                section_name = r[0] if r else None

            # ------------------ REPORT QUERY ------------------

            base_query = '''
                SELECT u.id, u.name,
                       COUNT(a.id) AS total_days,
                       COALESCE(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END),0) AS present_days,
                       CASE WHEN COUNT(a.id)=0 THEN 0.00
                            ELSE ROUND(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END)*100.0/COUNT(a.id),2)
                       END AS percentage
                FROM users u
                LEFT JOIN attendance a ON u.id = a.student_id
                LEFT JOIN courses c ON a.course_id = c.id
                WHERE u.role='student'
                  AND u.batch_id=%s
                  AND u.department_id=%s
                  AND c.semester_id=%s
            '''

            params = [batch_id, department_id, semester_id]

            if section_id:
                base_query += ' AND u.section_id = %s '
                params.append(section_id)

            base_query += '''
                GROUP BY u.id, u.name
                ORDER BY CAST(SUBSTRING(u.id FROM '(\\d+)$') AS INTEGER)
            '''

            cursor.execute(base_query, tuple(params))
            report_data = cursor.fetchall()

            title = f"{batch_name}-{dept_name}"
            if section_name:
                title += f"-{section_name}"
            title += f"-{semester_name}"


            if 'export_csv' in request.form:
                return export_csv(report_data, title)

            if 'export_pdf' in request.form:
                return export_pdf(report_data, title)

        return render_template(
            'admin_generate_reports.html',
            batches=batches,
            departments=departments,
            semesters=semesters,
            report_data=report_data,
            form_submitted=form_submitted,
            selected_batch=selected_batch,
            selected_department=selected_department,
            selected_section=selected_section,
            selected_semester=selected_semester,
            batch_name=batch_name,
            dept_name=dept_name,
            semester_name=semester_name,
            section_name=section_name
        )

    except Exception as e:
        flash(f"Error: {str(e)}", "danger")
        return redirect(url_for('admin_generate_reports'))

    finally:
        cursor.close()
        conn.close()


@app.route('/teacher/generate_reports', methods=['GET', 'POST'])
@role_required("teacher")
def teacher_generate_reports():

    teacher_id = session.get('user_id')
    if not teacher_id:
        flash('Please login first', 'danger')
        return redirect(url_for('login'))

    conn = get_db_connection()
    cursor = conn.cursor()

    # -------------------------------
    # Template vars
    # -------------------------------
    batches = []
    departments = []
    semesters = []
    courses = []
    report_data = None

    selected_batch = None
    selected_department = None
    selected_section = None
    selected_semester = None
    selected_course = None

    batch_name = ''
    dept_name = ''
    semester_name = ''
    course_name = ''
    section_name = ''


    try:
        # -------------------------------
        # Load master dropdown data
        # -------------------------------
        cursor.execute('SELECT * FROM batches ORDER BY name')
        batches = cursor.fetchall()

        cursor.execute('SELECT * FROM departments ORDER BY name')
        departments = cursor.fetchall()

        cursor.execute('SELECT * FROM semesters ORDER BY name')
        semesters = cursor.fetchall()

        
        section_name = None
        if selected_section:
            cursor.execute('SELECT name FROM sections WHERE id=%s', (selected_section,))
            r = cursor.fetchone()
            section_name = r[0] if r else None

        # -------------------------------
        # Read filters (GET first)
        # -------------------------------
        selected_batch = request.args.get('batch_id') or None
        selected_department = request.args.get('department_id') or None
        selected_section = request.args.get('section_id') or None
        selected_semester = request.args.get('semester_id') or None

        # -------------------------------
        # POST overrides filters
        # -------------------------------
        if request.method == 'POST':
            selected_batch = request.form.get('batch_id')
            selected_department = request.form.get('department_id')
            selected_section = request.form.get('section_id') or None
            selected_semester = request.form.get('semester_id')
            selected_course = request.form.get('course_id')

        if selected_batch:
            cursor.execute('SELECT name FROM batches WHERE id=%s', (selected_batch,))
            r = cursor.fetchone()
            batch_name = r[0] if r else ''

        if selected_department:
            cursor.execute('SELECT name FROM departments WHERE id=%s', (selected_department,))
            r = cursor.fetchone()
            dept_name = r[0] if r else ''

        if selected_semester:
            cursor.execute('SELECT name FROM semesters WHERE id=%s', (selected_semester,))
            r = cursor.fetchone()
            semester_name = r[0] if r else ''

        if selected_course:
            cursor.execute('SELECT name FROM courses WHERE id=%s', (selected_course,))
            r = cursor.fetchone()
            course_name = r[0] if r else ''

        if selected_section:
            cursor.execute('SELECT name FROM sections WHERE id=%s', (selected_section,))
            r = cursor.fetchone()
            section_name = r[0] if r else ''

        # -------------------------------
        # Load courses if filters ready
        # -------------------------------
        if selected_batch and selected_department and selected_semester:

            if selected_section:
                cursor.execute('''
                    SELECT DISTINCT c.id, c.name
                    FROM course_allocations ca
                    JOIN courses c ON ca.course_id = c.id
                    WHERE ca.teacher_id = %s
                      AND ca.batch_id = %s
                      AND ca.department_id = %s
                      AND ca.section_id = %s
                      AND ca.semester_id = %s
                    ORDER BY c.name
                ''', (teacher_id, selected_batch, selected_department, selected_section, selected_semester))
            else:
                cursor.execute('''
                    SELECT DISTINCT c.id, c.name
                    FROM course_allocations ca
                    JOIN courses c ON ca.course_id = c.id
                    WHERE ca.teacher_id = %s
                      AND ca.batch_id = %s
                      AND ca.department_id = %s
                      AND ca.section_id IS NULL
                      AND ca.semester_id = %s
                    ORDER BY c.name
                ''', (teacher_id, selected_batch, selected_department, selected_semester))

            courses = cursor.fetchall()

        # -------------------------------
        # POST: Generate / Export
        # -------------------------------
        if request.method == 'POST':

            if not selected_course:
                flash('All fields are required!', 'danger')
                return redirect(url_for('teacher_generate_reports'))

            # Save for export
            session['report_batch_id'] = selected_batch
            session['report_department_id'] = selected_department
            session['report_section_id'] = selected_section
            session['report_semester_id'] = selected_semester
            session['report_course_id'] = selected_course

            # -------------------------------
            # Security: verify allocation
            # -------------------------------
            if selected_section:
                cursor.execute('''
                    SELECT 1 FROM course_allocations
                    WHERE teacher_id=%s AND course_id=%s
                      AND batch_id=%s AND department_id=%s
                      AND section_id=%s AND semester_id=%s
                ''', (teacher_id, selected_course, selected_batch, selected_department, selected_section, selected_semester))
            else:
                cursor.execute('''
                    SELECT 1 FROM course_allocations
                    WHERE teacher_id=%s AND course_id=%s
                      AND batch_id=%s AND department_id=%s
                      AND section_id IS NULL AND semester_id=%s
                ''', (teacher_id, selected_course, selected_batch, selected_department, selected_semester))

            if not cursor.fetchone():
                flash('Unauthorized course access.', 'danger')
                return redirect(url_for('teacher_generate_reports'))


            # -------------------------------
            # Attendance report query
            # -------------------------------
            if selected_section:
                cursor.execute('''
                    SELECT u.id, u.name,
                           COUNT(a.id),
                           COALESCE(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END),0),
                           CASE WHEN COUNT(a.id)=0 THEN 0
                                ELSE ROUND(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END)*100.0/COUNT(a.id),2)
                           END
                    FROM users u
                    LEFT JOIN attendance a ON u.id=a.student_id AND a.course_id=%s
                    WHERE u.role='student'
                      AND u.batch_id=%s AND u.department_id=%s AND u.section_id=%s
                    GROUP BY u.id, u.name
                    ORDER BY CAST(SUBSTRING(u.id FROM '(\\d+)$') AS INTEGER)
                ''', (selected_course, selected_batch, selected_department, selected_section))
            else:
                cursor.execute('''
                    SELECT u.id, u.name,
                           COUNT(a.id),
                           COALESCE(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END),0),
                           CASE WHEN COUNT(a.id)=0 THEN 0
                                ELSE ROUND(SUM(CASE WHEN a.status='present' THEN 1 ELSE 0 END)*100.0/COUNT(a.id),2)
                           END
                    FROM users u
                    LEFT JOIN attendance a ON u.id=a.student_id AND a.course_id=%s
                    WHERE u.role='student'
                      AND u.batch_id=%s AND u.department_id=%s AND u.section_id IS NULL
                    GROUP BY u.id, u.name
                    ORDER BY CAST(SUBSTRING(u.id FROM '(\\d+)$') AS INTEGER)
                ''', (selected_course, selected_batch, selected_department))

            report_data = cursor.fetchall()
            title = f"Attendance Report for {batch_name}, Department: {dept_name}"
            if section_name:
                title += f", {section_name}"
            title += f", {semester_name}, Course: {course_name}"


            if 'export_csv' in request.form:
                return export_csv(report_data, title)

            if 'export_pdf' in request.form:
                return export_pdf(report_data, title)

        # -------------------------------
        # Final render
        # -------------------------------
        return render_template(
            'teacher_generate_reports.html',
            batches=batches,
            departments=departments,
            semesters=semesters,
            courses=courses,
            batch_name=batch_name,
            dept_name=dept_name,
            semester_name=semester_name,
            course_name=course_name,
            section_name=section_name,
            report_data=report_data,
            selected_batch=selected_batch,
            selected_department=selected_department,
            selected_section=selected_section,
            selected_semester=selected_semester,
            selected_course=selected_course
        )

    except Exception as e:
        flash(f'Error: {str(e)}', 'danger')
        return render_template(
            'teacher_generate_reports.html',
            batches=batches,
            departments=departments,
            semesters=semesters,
            courses=courses,
            selected_batch=selected_batch,
            selected_department=selected_department,
            selected_section=selected_section,
            selected_semester=selected_semester,
            selected_course=selected_course
        )

    finally:
        try:
            cursor.close()
        except:
            pass
        conn.close()



def export_csv(data, title):
    try:
        # Create a StringIO buffer for CSV data
        output = io.StringIO()
        writer = csv.writer(output)

        
        
        # Write header
        writer.writerow(['Student ID', 'Name', 'Total Days', 'Present Days', 'Percentage (%)'])
        
        # Write data rows
        for row in data:
            writer.writerow(row)
        
        # Create a Flask response with CSV data
        response = Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f"attachment;filename={slugify(title)}.csv",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )
        return response
        
    except Exception as e:
        flash(f'CSV export failed: {str(e)}', 'error')
        return redirect(url_for('admin_generate_reports'))

def export_pdf(data, title):
    try:
        # Create a buffer for PDF data
        buffer = io.BytesIO()
        
        # Create PDF document
        doc = SimpleDocTemplate(buffer, pagesize=letter)
        elements = []
        styles = getSampleStyleSheet()

        try:
            # Add Logo (adjust width/height as needed)
            logo = Image('static/uni_logo.png', width=1*inch, height=1*inch)
            logo.hAlign = 'CENTER'
            elements.append(logo)
        except Exception as e:
            # If logo not found, continue without it
            pass

        # University Title
        uni_title = Paragraph(
            "<para align='center'><b>BENAZIR BHUTTO SHAHEED UNIVERSITY OF TECHNOLOGY AND SKILL DEVELOPMENT KHAIRPUR</b></para>",
            styles['Title']
        )
        elements.append(uni_title)
        elements.append(Spacer(1, 0.2 * inch))
        
        # Add title
        elements.append(Paragraph(title, styles['Title']))
        elements.append(Spacer(1, 12))
        
        # Create table data
        table_data = [['Student ID', 'Name', 'Total Days', 'Present Days', 'Percentage (%)']]
        for row in data:
            table_data.append([str(item) for item in row])
        
        # Create table
        table = Table(table_data)
        table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#00BFF')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 10),
            ('BOTTOMPADDING', (0,0), (-1,0), 12),
            ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#F8F9FA')),
            ('GRID', (0,0), (-1,-1), 1, colors.HexColor('#DEE2E6'))
        ]))
        
        elements.append(table)
        doc.build(elements)
        
        # Create Flask response
        buffer.seek(0)
        response = Response(
            buffer.getvalue(),
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f"attachment;filename={slugify(title)}.pdf",
                "Content-Type": "application/pdf"
            }
        )
        return response
        
    except Exception as e:
        flash(f'PDF export failed: {str(e)}', 'error')
        return redirect(url_for('admin_generate_reports'))


@app.route('/register_admin', methods=['GET', 'POST'])
def register_admin():
    # Check if an admin already exists
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE role = %s', ('admin',))
    admin_exists = cursor.fetchone()
    conn.close()

    if admin_exists:
        flash('An admin already exists. Please log in.', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        user_id = request.form['user_id']
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO users (id, name, email, password, role)
            VALUES (%s, %s, %s, %s, %s)
        ''', (user_id, name, email, password, 'admin'))  # 'admin' as a string value
        conn.commit()
        conn.close()
        flash('Admin registered successfully! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register_admin.html')


@app.route('/admin/create_course', methods=['GET', 'POST'])
@role_required('admin')
def create_course():

    if request.method == 'POST':
        data = request.get_json()

        name = data.get('name', '').strip().lower()
        semester_id = data.get('semester_id')
        department_id = data.get('department_id')
        batch_id = data.get('batch_id')
        section_id = data.get('section_id') or None

        if not all([name, semester_id, department_id, batch_id]):
            return jsonify({'status': 'error', 'msg': 'Missing required fields'}), 400

        conn = get_db_connection()
        cursor = conn.cursor()

        # DUPLICATE CHECK (case-insensitive)
        if section_id:
            cursor.execute("""
                SELECT 1 FROM courses
                WHERE LOWER(TRIM(name))=%s
                  AND semester_id=%s
                  AND department_id=%s
                  AND batch_id=%s
                  AND section_id=%s
            """, (name, semester_id, department_id, batch_id, section_id))
        else:
            cursor.execute("""
                SELECT 1 FROM courses
                WHERE LOWER(TRIM(name))=%s
                  AND semester_id=%s
                  AND department_id=%s
                  AND batch_id=%s
                  AND section_id IS NULL
            """, (name, semester_id, department_id, batch_id))

        if cursor.fetchone():
            conn.close()
            return jsonify({'status': 'warning', 'msg': 'Course already exists for this selection'})

        # INSERT
        cursor.execute("""
            INSERT INTO courses (name, semester_id, department_id, batch_id, section_id)
            VALUES (%s,%s,%s,%s,%s)
        """, (name, semester_id, department_id, batch_id, section_id))

        conn.commit()
        conn.close()

        return jsonify({'status': 'success', 'msg': 'Course created successfully!'})

    # ---------- GET ----------
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name FROM semesters ORDER BY id')
    semesters = cursor.fetchall()
    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()
    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()
    conn.close()

    return render_template(
        'create_course.html',
        semesters=semesters,
        departments=departments,
        batches=batches
    )

@app.route('/admin/manage_courses', methods=['GET', 'POST'])
@role_required("admin")
def manage_courses():

    conn = get_db_connection()
    cursor = conn.cursor()

    # ---------- DROPDOWNS ----------
    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()

    cursor.execute('SELECT id, name FROM semesters ORDER BY id')
    semesters = cursor.fetchall()

    courses = []
    selected_batch = selected_department = selected_semester = selected_section = None
    form_submitted = False

    if request.method == 'POST':
        form_submitted = True
        selected_batch = request.form.get('batch_id')
        selected_department = request.form.get('department_id')
        selected_semester = request.form.get('semester_id')
        selected_section = request.form.get('section_id') or None

        # ---------- FETCH COURSES ----------
        if selected_section:
            cursor.execute("""
                SELECT id, name
                FROM courses
                WHERE batch_id=%s
                  AND department_id=%s
                  AND semester_id=%s
                  AND section_id=%s
                ORDER BY name
            """, (selected_batch, selected_department, selected_semester, selected_section))
        else:
            cursor.execute("""
                SELECT id, name
                FROM courses
                WHERE batch_id=%s
                  AND department_id=%s
                  AND semester_id=%s
                  AND section_id IS NULL
                ORDER BY name
            """, (selected_batch, selected_department, selected_semester))

        courses = cursor.fetchall()

    conn.close()

    return render_template(
        'manage_courses.html',
        batches=batches,
        departments=departments,
        semesters=semesters,
        courses=courses,
        form_submitted=form_submitted,
        selected_batch=selected_batch,
        selected_department=selected_department,
        selected_semester=selected_semester,
        selected_section=selected_section
    )


@app.route('/admin/delete_course/<int:course_id>', methods=['POST'])
@role_required("admin")
def delete_course(course_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # First delete any course allocations for this course
        cursor.execute('DELETE FROM course_allocations WHERE course_id = %s', (course_id,))
        
        # Then delete any timetable entries for this course
        cursor.execute('DELETE FROM timetable WHERE course_id = %s', (course_id,))
        
        # Then delete any attendance records for this course
        cursor.execute('DELETE FROM attendance WHERE course_id = %s', (course_id,))
        
        # Finally delete the course itself
        cursor.execute('DELETE FROM courses WHERE id = %s', (course_id,))
        
        conn.commit()
        flash('Course and all related data deleted successfully!', 'success')
        
    except Exception as e:
        conn.rollback()
        flash(f'Error deleting course: {str(e)}', 'error')
        
    finally:
        conn.close()
    
    return redirect(url_for('manage_courses'))


@app.route('/teacher/mark_attendance', methods=['GET', 'POST'])
@role_required("teacher")
def mark_attendance():
    teacher_id = session.get('user_id')
    conn = get_db_connection()
    cursor = conn.cursor()

    # -------------------------------
    # Static dropdowns
    # -------------------------------
    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()

    cursor.execute('SELECT id, name FROM semesters ORDER BY name')
    semesters = cursor.fetchall()

    # -------------------------------
    # POST → Mark Attendance
    # -------------------------------
    if request.method == 'POST':

        try:
            batch_id = request.form.get('batch_id')
            department_id = request.form.get('department_id')
            semester_id = request.form.get('semester_id')
            section_id = request.form.get('section_id') or None
            course_id = request.form.get('course_id')
            attendance_date = request.form.get('date')
            start_time = request.form.get('start_time')
            end_time = request.form.get('end_time')
            class_type = request.form.get('class_type')

            # 🔐 Validate allocation with section
            cursor.execute("""
                SELECT 1
                FROM course_allocations ca
                WHERE ca.teacher_id = %s
                  AND ca.course_id = %s
                  AND ca.batch_id = %s
                  AND ca.department_id = %s
                  AND ca.semester_id = %s
                  AND (ca.section_id=%s OR (%s IS NULL AND ca.section_id IS NULL))
            """, (teacher_id, course_id, batch_id, department_id, semester_id, section_id, section_id))

            if not cursor.fetchone():
                return flash("Unauthorized or invalid course allocation.", "warning")

            # selected_date = date.fromisoformat(attendance_date)
            # if selected_date != date.today():
            #     return flash("Attendance can only be marked for today's date.", "warning")

            if not any(k.startswith('attendance_') for k in request.form):
                return flash("No attendance data submitted.", "warning")

            # DUPLICATE CHECK
            cursor.execute("""
                SELECT 1 FROM attendance
                WHERE batch_id=%s AND department_id=%s AND semester_id=%s
                  AND course_id=%s AND date=%s AND start_time=%s AND end_time=%s
                  AND (section_id=%s OR (%s IS NULL AND section_id IS NULL))
                LIMIT 1
            """, (batch_id, department_id, semester_id, course_id,
                  attendance_date, start_time, end_time, section_id, section_id))

            if cursor.fetchone():
                return flash("Attendance already marked for this class.", "warning")

            # PRACTICAL BLOCK → get all slots of that day
            practical_slots = []
            if class_type == "Practical":
                cursor.execute("""
                    SELECT start_time, end_time
                    FROM timetable
                    WHERE batch_id=%s AND department_id=%s AND semester_id=%s
                      AND course_id=%s
                      AND (section_id=%s OR (%s IS NULL AND section_id IS NULL))
                      AND TRIM(day) = TO_CHAR(%s::date, 'FMDay')
                      AND class_type='Pr'
                    ORDER BY start_time
                """, (batch_id, department_id, semester_id, course_id, section_id, section_id, attendance_date))
                practical_slots = cursor.fetchall()

            # INSERT ATTENDANCE
            for key, value in request.form.items():
                if key.startswith('attendance_'):
                    student_id = key.split('_')[1]

                    if class_type == "Practical" and practical_slots:
                        for st, et in practical_slots:
                            cursor.execute("""
                                INSERT INTO attendance
                                (student_id, course_id, batch_id, department_id, semester_id,
                                 section_id, date, start_time, end_time, status, class_type)
                                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                            """, (student_id, course_id, batch_id, department_id, semester_id,
                                  section_id, attendance_date, st, et, value, "Practical"))
                    else:
                        cursor.execute("""
                            INSERT INTO attendance
                            (student_id, course_id, batch_id, department_id, semester_id,
                             section_id, date, start_time, end_time, status, class_type)
                            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """, (student_id, course_id, batch_id, department_id, semester_id,
                              section_id, attendance_date, start_time, end_time, value, class_type))

            conn.commit()
            flash("Attendance marked successfully!", "success")
            return redirect(url_for('mark_attendance'))

        except Exception as e:
            conn.rollback()
            flash(str(e), "error")
            return redirect(url_for('mark_attendance'))

        finally:
            conn.close()


            return redirect(url_for('mark_attendance'))

    # -------------------------------
    # GET → Selection flow
    # -------------------------------
    batch_id = request.args.get('batch_id')
    department_id = request.args.get('department_id')
    semester_id = request.args.get('semester_id')
    section_id = request.args.get('section_id')
    course_id = request.args.get('course_id')

    courses = []
    students = []

    if batch_id and department_id and semester_id:
        cursor.execute("""
            SELECT c.id, c.name
            FROM courses c
            JOIN course_allocations ca ON ca.course_id = c.id
            WHERE ca.teacher_id=%s
              AND ca.batch_id=%s
              AND ca.department_id=%s
              AND ca.semester_id=%s
              AND (ca.section_id=%s OR (%s IS NULL AND ca.section_id IS NULL))
            ORDER BY c.name
        """, (teacher_id, batch_id, department_id, semester_id, section_id, section_id))
        courses = cursor.fetchall()

        if course_id not in {str(c[0]) for c in courses}:
            course_id = None

    if course_id:
        cursor.execute("""
            SELECT id, name FROM users
            WHERE role='student'
              AND batch_id=%s AND department_id=%s
              AND (section_id=%s OR (%s IS NULL AND section_id IS NULL))
            ORDER BY CAST(SUBSTRING(id FROM '(\\d+)$') AS INTEGER)
        """, (batch_id, department_id, section_id, section_id))
        students = cursor.fetchall()

    conn.close()

    return render_template(
        'mark_attendance.html',
        batches=batches,
        departments=departments,
        semesters=semesters,
        courses=courses,
        students=students,
        selected_batch=batch_id,
        selected_department=department_id,
        selected_semester=semester_id,
        selected_section=section_id,
        selected_course=course_id
    )


@app.route('/api/timetable_lookup')
@role_required("teacher")
def timetable_lookup():
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        batch_id = request.args.get("batch_id")
        department_id = request.args.get("department_id")
        semester_id = request.args.get("semester_id")
        course_id = request.args.get("course_id")
        section_id = request.args.get("section_id")
        date_str = request.args.get("date")

        if not all([batch_id, department_id, semester_id, course_id, date_str]):
            return jsonify({"error": "Missing parameters"}), 400

        # Convert empty section_id → None
        section_id = int(section_id) if section_id and section_id.strip() != "" else None

        # Convert date → weekday
        day_name = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A")

        # Build query depending on section presence
        if section_id is None:
            cursor.execute("""
                SELECT id, start_time, end_time, class_type
                FROM timetable
                WHERE batch_id=%s
                  AND department_id=%s
                  AND semester_id=%s
                  AND course_id=%s
                  AND section_id IS NULL
                  AND day=%s
                ORDER BY start_time
            """, (batch_id, department_id, semester_id, course_id, day_name))
        else:
            cursor.execute("""
                SELECT id, start_time, end_time, class_type
                FROM timetable
                WHERE batch_id=%s
                  AND department_id=%s
                  AND semester_id=%s
                  AND course_id=%s
                  AND section_id=%s
                  AND day=%s
                ORDER BY start_time
            """, (batch_id, department_id, semester_id, course_id, section_id, day_name))

        rows = cursor.fetchall()

        classes = [
            {
                "entry_id": r[0],
                "start_time": r[1],
                "end_time": r[2],
                "class_type": r[3]
            }
            for r in rows
        ]

        return jsonify({
            "day": day_name,
            "total_classes": len(classes),
            "classes": classes
        })

    finally:
        conn.close()

# Add this near the top of your Flask application file

def convert_to_12h(time_str):
    try:
        # Handle both 'HH:MM' and 'HH:MM:SS' formats
        time_obj = datetime.strptime(time_str, '%H:%M') if len(time_str) <= 5 else datetime.strptime(time_str, '%H:%M:%S')
        return time_obj.strftime('%I:%M %p')
    except ValueError:
        return time_str

# Register the filter with Jinja2
app.jinja_env.filters['convert_to_12h'] = convert_to_12h

@app.route('/admin/timetable', methods=['GET', 'POST'])
@role_required("admin")
def timetable():

    courses = []
    batches = []
    departments = []
    semesters = []
    timetable_data = []

    selected_batch = None
    selected_department = None
    selected_semester = None
    selected_section = None
    form_submitted = False

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute('SELECT * FROM courses')
        courses = cursor.fetchall()
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()

        if request.method == 'POST':

            form_submitted = True
            # ============================
            # GENERATE TIMETABLE
            # ============================
            if 'generate_table' in request.form:

                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                semester_id = request.form['semester_id']
                section_id = request.form.get('section_id')

                selected_batch = batch_id
                selected_department = department_id
                selected_semester = semester_id
                selected_section = section_id

                section_filter = "AND t.section_id = %s" if section_id else "AND t.section_id IS NULL"
                params = [batch_id, department_id, semester_id]
                if section_id:
                    params.append(section_id)

                cursor.execute(f'''
                    SELECT DISTINCT start_time, end_time 
                    FROM timetable t
                    WHERE t.batch_id=%s AND t.department_id=%s AND t.semester_id=%s
                    {section_filter}
                    ORDER BY start_time
                ''', params)
                time_slots = cursor.fetchall()

                timetable_by_day = {d: {} for d in ['Monday','Tuesday','Wednesday','Thursday','Friday']}

                cursor.execute(f'''
                    SELECT c.name, t.day, t.start_time, t.end_time, u.name, t.class_type, t.id
                    FROM timetable t
                    JOIN courses c ON t.course_id = c.id
                    LEFT JOIN course_allocations ca 
                        ON ca.course_id=t.course_id AND ca.batch_id=t.batch_id 
                        AND ca.department_id=t.department_id AND ca.semester_id=t.semester_id
                    LEFT JOIN users u ON ca.teacher_id=u.id AND u.role='teacher'
                    WHERE t.batch_id=%s AND t.department_id=%s AND t.semester_id=%s
                    {section_filter}
                    ORDER BY t.start_time
                ''', params)

                for e in cursor.fetchall():
                    day = e[1]
                    key = f"{e[2]}-{e[3]}"
                    timetable_by_day[day][key] = {
                        'course': e[0],
                        'teacher': e[4],
                        'class_type': e[5],
                        'entry_id': e[6]
                    }

                timetable_data = []
                for s, e in time_slots:
                    key = f"{s}-{e}"
                    row = {'start_time': s, 'end_time': e, 'days': {}}
                    for d in timetable_by_day:
                        row['days'][d] = timetable_by_day[d].get(key)
                    timetable_data.append(row)

                    # ADD ENTRY
            # ============================
            else:
                course_id = request.form['course_id']
                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                semester_id = request.form['semester_id']
                day = request.form['day']
                start_time = request.form['start_time']
                end_time = request.form['end_time']
                class_type = request.form['class_type']

                section_id = request.form.get('section_id')

                # convert empty string to None
                if not section_id:
                    section_id = None


                if start_time >= end_time:
                    flash('End time must be greater than Start time!', 'danger')
                    return redirect(url_for('timetable'))

                cursor.execute('''
                    SELECT 1 FROM timetable
                    WHERE batch_id=%s AND department_id=%s AND semester_id=%s
                      AND (section_id IS NOT DISTINCT FROM %s)
                      AND day=%s AND start_time=%s AND end_time=%s AND class_type=%s
                ''', (batch_id, department_id, semester_id, section_id,
                      day, start_time, end_time, class_type))

                if cursor.fetchone():
                    flash('Duplicate timetable entry already exists!', 'warning')
                    return redirect(url_for('timetable'))

                cursor.execute('''
                    INSERT INTO timetable 
                    (course_id,batch_id,department_id,semester_id,section_id,day,start_time,end_time,class_type)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ''', (course_id, batch_id, department_id, semester_id, section_id,
                      day, start_time, end_time, class_type))
                conn.commit()
                flash('Timetable entry added successfully!', 'success')

    finally:
        conn.close()

    return render_template(
        'timetable.html',
        courses=courses,
        batches=batches,
        departments=departments,
        semesters=semesters,
        timetable_data=timetable_data,
        selected_batch=selected_batch,
        selected_department=selected_department,
        selected_semester=selected_semester,
        selected_section=selected_section,
        form_submitted=form_submitted
    )

@app.route('/admin/edit_timetable/<int:timetable_id>', methods=['GET', 'POST'])
@role_required("admin")
def edit_timetable(timetable_id):

    conn = get_db_connection()
    cursor = conn.cursor()

    # ================= FETCH CURRENT ENTRY =================
    cursor.execute('SELECT * FROM timetable WHERE id=%s', (timetable_id,))
    entry = cursor.fetchone()

    if not entry:
        conn.close()
        flash('Timetable entry not found!', 'danger')
        return redirect(url_for('timetable'))

    # ================= DROPDOWNS =================
    cursor.execute('SELECT id, name FROM courses ORDER BY name')
    courses = cursor.fetchall()

    cursor.execute('SELECT id, name FROM batches ORDER BY name')
    batches = cursor.fetchall()

    cursor.execute('SELECT id, name FROM departments ORDER BY name')
    departments = cursor.fetchall()

    cursor.execute('SELECT id, name FROM semesters ORDER BY name')
    semesters = cursor.fetchall()

    # ================= UPDATE =================
    if request.method == 'POST':

        course_id = request.form['course_id']
        batch_id = request.form['batch_id']
        department_id = request.form['department_id']
        semester_id = request.form['semester_id']

        section_id = request.form.get('section_id')
        if not section_id:
            section_id = None   # ✅ critical fix

        day = request.form['day']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        class_type = request.form['class_type']

        # -------- TIME VALIDATION --------
        if start_time >= end_time:
            flash('End time must be greater than Start time!', 'danger')
            return redirect(url_for('edit_timetable', timetable_id=timetable_id))

        # -------- DUPLICATE CHECK (EXCEPT ITSELF) --------
        cursor.execute('''
            SELECT 1 FROM timetable
            WHERE batch_id=%s
              AND department_id=%s
              AND semester_id=%s
              AND (section_id IS NOT DISTINCT FROM %s)
              AND day=%s
              AND start_time=%s
              AND end_time=%s
              AND class_type=%s
              AND id <> %s
        ''', (
            batch_id, department_id, semester_id, section_id,
            day, start_time, end_time, class_type, timetable_id
        ))

        if cursor.fetchone():
            flash('This timetable entry already exists for selected values!', 'warning')
            return redirect(url_for('edit_timetable', timetable_id=timetable_id))

        # -------- UPDATE --------
        cursor.execute('''
            UPDATE timetable
            SET course_id=%s,
                batch_id=%s,
                department_id=%s,
                semester_id=%s,
                section_id=%s,
                day=%s,
                start_time=%s,
                end_time=%s,
                class_type=%s
            WHERE id=%s
        ''', (
            course_id, batch_id, department_id, semester_id, section_id,
            day, start_time, end_time, class_type, timetable_id
        ))

        conn.commit()
        conn.close()

        flash('Timetable entry updated successfully!', 'success')
        return redirect(url_for('timetable'))

    conn.close()

    return render_template(
        'edit_timetable.html',
        entry=entry,
        courses=courses,
        batches=batches,
        departments=departments,
        semesters=semesters
    )


@app.route('/admin/delete_timetable/<int:timetable_id>')
@role_required("admin")
def delete_timetable(timetable_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM timetable WHERE id = %s', (timetable_id,))
    conn.commit()
    conn.close()
    flash('Timetable entry deleted successfully!', 'success')
    return redirect(url_for('timetable'))

@app.route('/timetable/view', methods=['GET', 'POST'])
@role_required("student", "teacher")
def view_timetable():

    conn = get_db_connection()
    cursor = conn.cursor()

    batches = []
    departments = []
    semesters = []
    timetable_data = []

    selected_batch = None
    selected_department = None
    selected_section = None
    selected_semester = None

    batch_name = None
    department_name = None
    section_name = None
    form_submitted = False

    try:
        cursor.execute('SELECT id, name FROM batches ORDER BY name')
        batches = cursor.fetchall()

        cursor.execute('SELECT id, name FROM departments ORDER BY name')
        departments = cursor.fetchall()

        cursor.execute('SELECT id, name FROM semesters ORDER BY id')
        semesters = cursor.fetchall()

        # ================= STUDENT AUTO LOCK =================
        if session['role'] == 'student':
            cursor.execute("""
                SELECT u.batch_id, u.department_id, u.section_id,
                       b.name, d.name, s.name
                FROM users u
                JOIN batches b ON b.id = u.batch_id
                JOIN departments d ON d.id = u.department_id
                LEFT JOIN sections s ON s.id = u.section_id
                WHERE u.id = %s AND u.role='student'
                LIMIT 1
            """, (session['user_id'],))

            r = cursor.fetchone()
            if not r:
                flash("Student profile not found.", "danger")
                return redirect(url_for('home'))

            selected_batch = str(r[0])
            selected_department = str(r[1])
            selected_section = str(r[2]) if r[2] else None

            batch_name = r[3]
            department_name = r[4]
            section_name = r[5]

        # ================= FORM SUBMIT =================
        if request.method == 'POST' and 'generate_table' in request.form:
            form_submitted = True
            selected_semester = request.form.get('semester_id')

            if session['role'] == 'teacher':
                selected_batch = request.form.get('batch_id')
                selected_department = request.form.get('department_id')
                selected_section = request.form.get('section_id') or None

            if not (selected_batch and selected_department and selected_semester):
                flash("Please select all required fields.", "warning")

            else:
                # --------- TIME SLOTS ----------
                if selected_section:
                    cursor.execute('''
                        SELECT DISTINCT start_time, end_time
                        FROM timetable
                        WHERE batch_id=%s AND department_id=%s
                          AND semester_id=%s AND section_id=%s
                        ORDER BY start_time
                    ''', (selected_batch, selected_department, selected_semester, selected_section))
                else:
                    cursor.execute('''
                        SELECT DISTINCT start_time, end_time
                        FROM timetable
                        WHERE batch_id=%s AND department_id=%s
                          AND semester_id=%s AND section_id IS NULL
                        ORDER BY start_time
                    ''', (selected_batch, selected_department, selected_semester))

                time_slots = cursor.fetchall()

                timetable_by_day = {d: {} for d in ['Monday','Tuesday','Wednesday','Thursday','Friday']}

                # --------- MAIN DATA ----------
                if selected_section:
                    cursor.execute('''
                        SELECT c.name, t.day, t.start_time, t.end_time,
                               u.name, t.class_type
                        FROM timetable t
                        JOIN courses c ON c.id=t.course_id
                        LEFT JOIN course_allocations ca
                          ON ca.course_id=t.course_id
                         AND ca.batch_id=t.batch_id
                         AND ca.department_id=t.department_id
                         AND ca.semester_id=t.semester_id
                        LEFT JOIN users u ON u.id=ca.teacher_id AND u.role='teacher'
                        WHERE t.batch_id=%s AND t.department_id=%s
                          AND t.semester_id=%s AND t.section_id=%s
                        ORDER BY t.start_time
                    ''', (selected_batch, selected_department, selected_semester, selected_section))
                else:
                    cursor.execute('''
                        SELECT c.name, t.day, t.start_time, t.end_time,
                               u.name, t.class_type
                        FROM timetable t
                        JOIN courses c ON c.id=t.course_id
                        LEFT JOIN course_allocations ca
                          ON ca.course_id=t.course_id
                         AND ca.batch_id=t.batch_id
                         AND ca.department_id=t.department_id
                         AND ca.semester_id=t.semester_id
                        LEFT JOIN users u ON u.id=ca.teacher_id AND u.role='teacher'
                        WHERE t.batch_id=%s AND t.department_id=%s
                          AND t.semester_id=%s AND t.section_id IS NULL
                        ORDER BY t.start_time
                    ''', (selected_batch, selected_department, selected_semester))

                rows = cursor.fetchall()

                for c, day, st, et, teacher, ct in rows:
                    key = f"{st}-{et}"
                    timetable_by_day[day][key] = {
                        'course': c,
                        'teacher': teacher,
                        'class_type': ct
                    }

                for st, et in time_slots:
                    key = f"{st}-{et}"
                    timetable_data.append({
                        'start_time': st,
                        'end_time': et,
                        'days': {d: timetable_by_day[d].get(key) for d in timetable_by_day}
                    })

    except Exception as e:
        flash(f"Timetable error: {str(e)}", "danger")

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'timetable_view.html',
        batches=batches,
        departments=departments,
        semesters=semesters,
        timetable_data=timetable_data,
        form_submitted=form_submitted,
        selected_batch=selected_batch,
        selected_department=selected_department,
        selected_section=selected_section,
        selected_semester=selected_semester,
        batch_name=batch_name,
        department_name=department_name,
        section_name=section_name,
        user_role=session['role']
    )

    

@app.route('/student/view_attendance', methods=['GET', 'POST'])
@role_required("student")
def view_attendance():

    student_id = session.get('user_id')
    if not student_id:
        return "Unauthorized", 401

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # ================= STUDENT PROFILE =================
        cursor.execute("""
            SELECT u.id, u.name,
                   b.name AS batch_name,
                   d.name AS dept_name,
                   s.name AS section_name,
                   u.batch_id, u.department_id, u.section_id
            FROM users u
            LEFT JOIN batches b ON u.batch_id = b.id
            LEFT JOIN departments d ON u.department_id = d.id
            LEFT JOIN sections s ON u.section_id = s.id
            WHERE u.id = %s AND u.role = 'student'
            LIMIT 1
        """, (student_id,))
        student = cursor.fetchone()

        if not student:
            return "Student record not found", 404

        (
            stu_id, stu_name,
            batch_name, dept_name, section_name,
            batch_id, dept_id, section_id
        ) = student

        # ================= SEMESTERS =================
        cursor.execute("SELECT id, name FROM semesters ORDER BY name")
        semesters = cursor.fetchall()

        courses = []
        attendance_data = []
        selected_semester = None
        selected_course = None

        # ================= FORM =================
        if request.method == 'POST':

            selected_semester = request.form.get('semester_id')
            selected_course = request.form.get('course_id')

            # ---------- COURSES (FILTERED BY SECTION IF EXISTS) ----------
            if selected_semester:

                if section_id:
                    cursor.execute("""
                        SELECT id, name
                        FROM courses
                        WHERE semester_id = %s
                          AND batch_id = %s
                          AND department_id = %s
                          AND section_id = %s
                        ORDER BY name
                    """, (selected_semester, batch_id, dept_id, section_id))
                else:
                    cursor.execute("""
                        SELECT id, name
                        FROM courses
                        WHERE semester_id = %s
                          AND batch_id = %s
                          AND department_id = %s
                          AND section_id IS NULL
                        ORDER BY name
                    """, (selected_semester, batch_id, dept_id))

                courses = cursor.fetchall()

            # ---------- ATTENDANCE ----------
            if selected_course and selected_semester:

                if section_id:
                    cursor.execute("""
                        SELECT a.date, a.status, c.name, a.class_type, a.start_time, a.end_time
                        FROM attendance a
                        JOIN courses c ON a.course_id = c.id
                        WHERE a.student_id = %s
                          AND a.course_id = %s
                          AND c.batch_id = %s
                          AND c.department_id = %s
                          AND c.section_id = %s
                          AND c.semester_id = %s
                        ORDER BY a.date DESC
                    """, (student_id, selected_course, batch_id, dept_id, section_id, selected_semester))
                else:
                    cursor.execute("""
                        SELECT a.date, a.status, c.name, a.class_type, a.start_time, a.end_time
                        FROM attendance a
                        JOIN courses c ON a.course_id = c.id
                        WHERE a.student_id = %s
                          AND a.course_id = %s
                          AND c.batch_id = %s
                          AND c.department_id = %s
                          AND c.section_id IS NULL
                          AND c.semester_id = %s
                        ORDER BY a.date DESC
                    """, (student_id, selected_course, batch_id, dept_id, selected_semester))

                raw_data = cursor.fetchall()

                for r in raw_data:
                    def fmt(t):
                        if not t:
                            return ""
                        if isinstance(t, time):
                            return t.strftime("%I:%M %p")
                        # if string like '13:30:00' or '13:30'
                        try:
                            return datetime.strptime(t[:5], "%H:%M").strftime("%I:%M %p")
                        except:
                            return t  # fallback (never crash)

                    start = fmt(r[4])
                    end = fmt(r[5])

                    attendance_data.append((r[0], r[1], r[2], r[3], start, end))

    finally:
        cursor.close()
        conn.close()

    return render_template(
        'view_attendance.html',
        student=student,
        semesters=semesters,
        courses=courses,
        attendance_data=attendance_data,
        selected_semester=selected_semester,
        selected_course=selected_course
    )



# Manage Batches
@app.route('/admin/manage_batches', methods=['GET', 'POST'])
@role_required("admin")
def manage_batches():
    if request.method == 'POST':

        # ADD BATCH
        if 'add_batch' in request.form:
            batch_name = request.form['batch_name']
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute(
                'INSERT INTO batches (name) VALUES (%s)',
                (batch_name,)
            )
            conn.commit()
            conn.close()
            flash('Batch added successfully!', 'success')

        # DELETE BATCH (WITH FK HANDLING)
        elif 'delete_batch' in request.form:
            batch_id = request.form['batch_id']
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # Delete attendance linked to courses of this batch
                cursor.execute("""
                    DELETE FROM attendance
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE batch_id = %s
                    )
                """, (batch_id,))

                # Delete timetable entries linked to courses of this batch
                cursor.execute("""
                    DELETE FROM timetable
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE batch_id = %s
                    )
                """, (batch_id,))

                # Delete course allocations linked to courses of this batch
                cursor.execute("""
                    DELETE FROM course_allocations
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE batch_id = %s
                    )
                """, (batch_id,))

                # Delete courses of this batch
                cursor.execute(
                    'DELETE FROM courses WHERE batch_id = %s',
                    (batch_id,)
                )

                # Finally delete the batch
                cursor.execute(
                    'DELETE FROM batches WHERE id = %s',
                    (batch_id,)
                )

                conn.commit()
                flash(
                    'Batch deleted successfully!',
                    'success'
                )
            except Exception as e:
                conn.rollback()
                flash(
                    f'Error deleting batch: {str(e)}',
                    'error'
                )
            finally:
                conn.close()

        return redirect(url_for('manage_batches'))

    # FETCH BATCHES
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    conn.close()

    return render_template('manage_batches.html', batches=batches)


# Manage Departments
@app.route('/admin/manage_departments', methods=['GET', 'POST'])
@role_required("admin")
def manage_departments():
    if request.method == 'POST':
        if 'add_department' in request.form:
            department_name = request.form['department_name']
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO departments (name) VALUES (%s)', (department_name,))
            conn.commit()
            conn.close()
            flash('Department added successfully!', 'success')
        elif 'delete_department' in request.form:
            department_id = request.form['department_id']
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                # Delete attendance linked to courses of this batch
                cursor.execute("""
                    DELETE FROM attendance
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE department_id = %s
                    )
                """, (department_id,))

                # Delete timetable entries linked to courses of this batch
                cursor.execute("""
                    DELETE FROM timetable
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE department_id = %s
                    )
                """, (department_id,))

                # Delete course allocations linked to courses of this batch
                cursor.execute("""
                    DELETE FROM course_allocations
                    WHERE course_id IN (
                        SELECT id FROM courses WHERE department_id = %s
                    )
                """, (department_id,))

                # Delete courses of this batch
                cursor.execute(
                    'DELETE FROM courses WHERE department_id = %s',
                    (department_id,))

                # Finally delete the batch
                cursor.execute(
                    'DELETE FROM departments WHERE id = %s',
                    (department_id,))
                

                conn.commit()
                flash('Department deleted successfully!', 'success')

            except Exception as e:
                conn.rollback()
                flash(
                    f'Error deleting Department: {str(e)}',
                    'error'
                )
            finally:
                conn.close()

        return redirect(url_for('manage_departments'))

    # Fetch all departments
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    conn.close()
    return render_template('manage_departments.html', departments=departments)

# Manage Teachers
@app.route('/admin/manage_teachers', methods=['GET', 'POST'])
@role_required("admin")
def manage_teachers():
    if request.method == 'POST':
        if 'edit_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            # Redirect to an edit page (to be implemented)
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))
        elif 'delete_teacher' in request.form:
            teacher_id = request.form['teacher_id']
            conn = get_db_connection()
            cursor = conn.cursor()

            try:
                
                cursor.execute("""
                    DELETE FROM course_allocations
                    WHERE teacher_id=%s
                """, (teacher_id,))

                cursor.execute(
                    'DELETE FROM users WHERE id = %s AND role=%s',
                    (teacher_id,"teacher")
                )

                conn.commit()
                flash('Teacher deleted successfully!', 'success')
            except Exception as e:
                conn.rollback()
                flash(
                    f'Error deleting Teacher: {str(e)}',
                    'error'
                )
            finally:
                conn.close()

        return redirect(url_for('manage_teachers'))

    # Fetch all teachers
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT id, name, email FROM users WHERE role = %s', ("teacher",))
    teachers = cursor.fetchall()
    conn.close()
    return render_template('manage_teachers.html', teachers=teachers)


@app.route('/admin/edit_teacher/<teacher_id>', methods=['GET', 'POST'])
@role_required("admin")
def edit_teacher(teacher_id):
    if request.method == 'POST':
        # Update teacher data
        name = request.form['name']
        email = request.form['email']
        new_password = request.form['new_password']
        confirm_password = request.form['confirm_password']

        # Validate password if provided
        if new_password:
            if len(new_password) < 8:
                flash('Password must be at least 8 characters long!', 'error')
                return redirect(url_for('edit_teacher', teacher_id=teacher_id))
            if new_password != confirm_password:
                flash('Passwords do not match!', 'error')
                return redirect(url_for('edit_teacher', teacher_id=teacher_id))

        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            if new_password:
                # Update with password
                hashed_password = generate_password_hash(new_password)
                cursor.execute('''
                    UPDATE users
                    SET name = %s, email = %s, password = %s
                    WHERE id = %s AND role = 'teacher'
                ''', (name, email, hashed_password, teacher_id))
            else:
                # Update without password
                cursor.execute('''
                    UPDATE users
                    SET name = %s, email = %s
                    WHERE id = %s AND role = 'teacher'
                ''', (name, email, teacher_id))
                
            conn.commit()
            flash('Teacher updated successfully!', 'success')
            return redirect(url_for('manage_teachers'))
        except Exception as e:
            conn.rollback()
            flash(f'Error updating teacher: {str(e)}', 'error')
            return redirect(url_for('edit_teacher', teacher_id=teacher_id))
        finally:
            conn.close()

    # Fetch the teacher's current data
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT id, name, email FROM users WHERE id = %s AND role = %s', (teacher_id, 'teacher'))
        teacher = cursor.fetchone()
        
        if not teacher:
            flash('Teacher not found!', 'error')
            return redirect(url_for('manage_teachers'))

        return render_template('edit_teacher.html', teacher=teacher)
    except Exception as e:
        flash(f'Error fetching teacher data: {str(e)}', 'error')
        return redirect(url_for('manage_teachers'))
    finally:
        conn.close()


@app.route('/admin/manage_attendance', methods=['GET', 'POST'])
@role_required("admin")
def manage_attendance():
    conn = get_db_connection()
    cursor = conn.cursor()

    form_submitted = False

    try:
        cursor.execute('SELECT id, name FROM batches ORDER BY name')
        batches = cursor.fetchall()

        cursor.execute('SELECT id, name FROM departments ORDER BY name')
        departments = cursor.fetchall()

        cursor.execute('SELECT id, name FROM semesters ORDER BY name')
        semesters = cursor.fetchall()

        attendance_data = []

        selected_batch = selected_department = selected_semester = selected_course = selected_section = ''
        search_id = search_date = ''

        if request.method == 'POST':
            form_submitted = True
            selected_batch = request.form.get('batch_id')
            selected_department = request.form.get('department_id')
            selected_semester = request.form.get('semester_id')
            selected_course = request.form.get('course_id')
            selected_section = request.form.get('section_id') or None

            search_id = request.form.get('search_id', '').strip()
            search_date = request.form.get('search_date', '').strip()

            if not (selected_batch and selected_department and selected_semester and selected_course):
                flash("Please select all required fields.", "warning")
            else:
                query = '''
                    SELECT a.id, u.id, u.name, a.date,
                           a.start_time, a.end_time,
                           c.name, a.status
                    FROM attendance a
                    JOIN users u ON a.student_id = u.id
                    JOIN courses c ON a.course_id = c.id
                    WHERE u.batch_id = %s
                      AND u.department_id = %s
                      AND a.course_id = %s
                      AND c.semester_id = %s
                '''
                params = [selected_batch, selected_department, selected_course, selected_semester]

                if selected_section:
                    query += ' AND u.section_id = %s'
                    params.append(selected_section)

                if search_id:
                    query += ' AND (u.id::text ILIKE %s OR u.name ILIKE %s)'
                    params.extend([f'%{search_id}%', f'%{search_id}%'])

                if search_date:
                    query += ' AND a.date = %s'
                    params.append(search_date)

                query += ' ORDER BY a.date DESC, u.id'

                cursor.execute(query, params)
                results = cursor.fetchall()

                def convert_time(t):
                    if not t:
                        return ''
                    if isinstance(t, str):
                        try:
                            return datetime.strptime(t[:5], "%H:%M").strftime("%I:%M %p")
                        except:
                            return t
                    return t.strftime("%I:%M %p")


                def format_date(d):
                    if not d:
                        return ''
                    if isinstance(d, str):
                        try:
                            return datetime.strptime(d, "%Y-%m-%d").strftime("%d-%m-%Y")
                        except:
                            return d
                    return d.strftime("%d-%m-%Y")


                attendance_data = [
                    (
                        r[0], r[1], r[2],
                        format_date(r[3]),
                        convert_time(r[4]),
                        convert_time(r[5]),
                        r[6], r[7]
                    )
                    for r in results
                ]

        return render_template(
            'manage_attendance.html',
            batches=batches,
            departments=departments,
            semesters=semesters,
            attendance_data=attendance_data,
            selected_batch=selected_batch,
            selected_department=selected_department,
            selected_semester=selected_semester,
            selected_course=selected_course,
            selected_section=selected_section,
            search_id=search_id,
            search_date=search_date,
            form_submitted=form_submitted 
        )

    except Exception as e:
        flash(f'Error fetching attendance data: {str(e)}', 'danger')
        return redirect(url_for('manage_attendance'))

    finally:
        conn.close()



@app.route('/admin/update_attendance/<int:attendance_id>', methods=['GET', 'POST'])
@role_required("admin")
def update_attendance(attendance_id):
    if request.method == 'POST':
        status = request.form['status']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE attendance
            SET status = %s
            WHERE id = %s
        ''', (status, attendance_id))
        conn.commit()
        conn.close()
        flash('Attendance updated successfully!', 'success')
        return redirect(url_for('manage_attendance'))

    # Fetch the current attendance record
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM attendance WHERE id = %s', (attendance_id,))
    attendance_record = cursor.fetchone()
    conn.close()

    return render_template('update_attendance.html', attendance_record=attendance_record)

@app.route('/admin/delete_attendance/<int:attendance_id>', methods=['POST'])
@role_required("admin")
def delete_attendance(attendance_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM attendance WHERE id = %s', (attendance_id,))
    conn.commit()
    conn.close()
    flash('Attendance deleted successfully!', 'success')
    return redirect(url_for('manage_attendance'))
 
def generate_timetable_pdf(timetable_data, batch_name, department_name, semester_name):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch
    )

    styles = getSampleStyleSheet()

    # Custom style for table content
    table_content_style = ParagraphStyle(
        name='TableContent',
        parent=styles['Normal'],
        fontSize=8,   # smaller font size
        alignment=1,  # center alignment
        leading=10,   # line spacing
    )

    elements = []

        # ---------- Logo + University Title ----------
    try:
        # Add Logo (adjust width/height as needed)
        logo = Image('static/uni_logo.png', width=1*inch, height=1*inch)
        logo.hAlign = 'CENTER'
        elements.append(logo)
    except Exception as e:
        # If logo not found, continue without it
        pass

    # University Title
    uni_title = Paragraph(
        "<para align='center'><b>BENAZIR BHUTTO SHAHEED UNIVERSITY OF TECHNOLOGY AND SKILL DEVELOPMENT KHAIRPUR</b></para>",
        styles['Title']
    )
    elements.append(uni_title)
    elements.append(Spacer(1, 0.2 * inch))

    # Title
    title = Paragraph(
        f"<para align='center'><b>Timetable for {batch_name}, {department_name}, {semester_name}</b></para>",
        styles['Title']
    )
    elements.append(title)
    elements.append(Spacer(1, 0.3 * inch))  # Spacer below title

    # Convert time to 12-hour format
    def format_time(time_str):
        try:
            hour, minute = map(int, time_str.split(':'))
            period = 'AM' if hour < 12 else 'PM'
            hour = hour % 12
            hour = 12 if hour == 0 else hour
            return f"{hour}:{minute:02d} {period}"
        except:
            return time_str

    # Prepare data for table
    headers = ["Time", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    data = []

    # Wrap headers with Paragraphs too (so they don't overflow)
    header_row = [Paragraph(h, table_content_style) for h in headers]
    data.append(header_row)

    for entry in timetable_data:
        time_slot = f"{format_time(entry['start_time'])} - {format_time(entry['end_time'])}"
        row = [Paragraph(time_slot, table_content_style)]

        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
            if entry['days'][day]:
                course_info = f"{entry['days'][day]['course']}"
                if entry['days'][day]['teacher']:
                    course_info += f"<br/>{entry['days'][day]['teacher']}"
                if entry['days'][day]['class_type']:
                    course_info += f"<br/>({entry['days'][day]['class_type']})"
                row.append(Paragraph(course_info, table_content_style))
            else:
                row.append(Paragraph("", table_content_style))
        data.append(row)

    # Create Table
    table = Table(data)

    # Calculate available width
    available_width = letter[0] - doc.leftMargin - doc.rightMargin

    # Set dynamic column widths
    num_cols = len(headers)
    col_width = available_width / num_cols
    table._argW = [col_width] * num_cols

    # Table Style
    style = TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#4472C4')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),

        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#F2F2F2')),
        ('ROWBACKGROUNDS', (1, 1), (-1, -1), [colors.white, colors.HexColor('#E9E9E9')]),

        ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ('BOX', (0, 0), (-1, -1), 1, colors.black),

        ('LEFTPADDING', (0, 0), (-1, -1), 2),
        ('RIGHTPADDING', (0, 0), (-1, -1), 2),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ])

    table.setStyle(style)

    elements.append(table)

    # Build PDF
    doc.build(elements)
    buffer.seek(0)
    return buffer

@app.route('/download_timetable_pdf')
def download_timetable_pdf():
    batch_id = request.args.get('batch_id')
    department_id = request.args.get('department_id')
    semester_id = request.args.get('semester_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        if not batch_id or not department_id or not semester_id:
            # assuming you store logged-in user id in session
            teacher_id = session.get('user_id')

            if teacher_id:
                cursor.execute("""
                    SELECT DISTINCT 
                        t.batch_id, 
                        t.department_id, 
                        t.semester_id
                    FROM timetable t
                    JOIN course_allocations ca 
                        ON ca.course_id = t.course_id
                        AND ca.batch_id = t.batch_id
                        AND ca.department_id = t.department_id
                        AND ca.semester_id = t.semester_id
                    WHERE ca.teacher_id = %s
                    LIMIT 1
                """, (teacher_id,))

                row = cursor.fetchone()
                if row:
                    batch_id, department_id, semester_id = row

        # Get names safely
        cursor.execute('SELECT name FROM batches WHERE id = %s', (batch_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invalid batch_id")
        batch_name = row[0]

        cursor.execute('SELECT name FROM departments WHERE id = %s', (department_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invalid department_id")
        department_name = row[0]

        cursor.execute('SELECT name FROM semesters WHERE id = %s', (semester_id,))
        row = cursor.fetchone()
        if not row:
            raise ValueError("Invalid semester_id")
        semester_name = row[0]


        # Get all timetable slots - FIXED: Added start_time to SELECT for ORDER BY
        cursor.execute('''
            SELECT DISTINCT start_time, end_time 
            FROM timetable 
            WHERE batch_id = %s AND department_id = %s AND semester_id = %s
            ORDER BY start_time
        ''', (batch_id, department_id, semester_id))
        time_slots = cursor.fetchall()

        # Organize timetable data
        timetable_by_day = {day: {} for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']}

        cursor.execute('''
            SELECT c.name, t.day, t.start_time, t.end_time, u.name, t.class_type
            FROM timetable t
            JOIN courses c ON t.course_id = c.id
            LEFT JOIN course_allocations ca ON ca.course_id = t.course_id
                AND ca.batch_id = t.batch_id
                AND ca.department_id = t.department_id
                AND ca.semester_id = t.semester_id
            LEFT JOIN users u ON ca.teacher_id = u.id
            WHERE t.batch_id = %s AND t.department_id = %s AND t.semester_id = %s
            ORDER BY t.start_time
        ''', (batch_id, department_id, semester_id))

        for course_name, day, start_time, end_time, teacher_name, class_type in cursor.fetchall():
            time_key = f"{start_time}-{end_time}"
            timetable_by_day[day][time_key] = {
                'course': course_name,
                'teacher': teacher_name,
                'class_type': class_type
            }

        # Build timetable data
        timetable_data = []
        for start_time, end_time in time_slots:
            time_key = f"{start_time}-{end_time}"
            row = {
                'start_time': start_time,
                'end_time': end_time,
                'days': {}
            }
            for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']:
                row['days'][day] = timetable_by_day[day].get(time_key, None)
            timetable_data.append(row)

        # Generate and send PDF
        pdf_buffer = generate_timetable_pdf(timetable_data, batch_name, department_name, semester_name)
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=f"Timetable_{batch_name}_{department_name}_{semester_name}.pdf",
            mimetype='application/pdf'
        )
        
    except Exception as e:
        flash(f'Error generating timetable PDF: {str(e)}', 'error')
        return redirect(url_for('timetable'))
        
    finally:
        conn.close()

@app.template_filter('convert_to_12h')
def convert_to_12h(time_str):
    try:
        hour, minute = map(int, time_str.split(':'))
        period = 'AM' if hour < 12 else 'PM'
        hour = hour % 12
        hour = 12 if hour == 0 else hour
        return f"{hour}:{minute:02d} {period}"
    except:
        return time_str


if __name__ == '__main__':
    #init_db()
    #app.run(debug=True)
    app.run(host="0.0.0.0", port=5000, debug=True)
