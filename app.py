from flask import Flask, render_template, request, redirect, url_for, session, flash, send_file, jsonify, make_response, abort
import psycopg2
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
import os
import pandas as pd
import re
# from reportlab.lib.pagesizes import letter
from io import BytesIO

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
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL,
            batch_id INTEGER,
            department_id INTEGER,
            batch_status TEXT,
            admission_date TEXT,
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS courses (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            semester_id INTEGER NOT NULL,
            department_id INTEGER NOT NULL,
            batch_id INTEGER NOT NULL,
            FOREIGN KEY (semester_id) REFERENCES semesters(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id)
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS course_allocations (
            id SERIAL PRIMARY KEY,
            course_id INTEGER,
            teacher_id TEXT,
            batch_id INTEGER,
            department_id INTEGER,
            semester_id INTEGER,
            start_date TEXT,
            end_date TEXT,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (teacher_id) REFERENCES users(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
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
            date TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            status TEXT NOT NULL,
            class_type TEXT NOT NULL,
            FOREIGN KEY (student_id) REFERENCES users(id),
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
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
            day TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            class_type TEXT NOT NULL,
            FOREIGN KEY (course_id) REFERENCES courses(id),
            FOREIGN KEY (batch_id) REFERENCES batches(id),
            FOREIGN KEY (department_id) REFERENCES departments(id),
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


@app.route('/login', methods=['GET', 'POST'])
def login():
    # Prevent logging in again if already logged in
    if 'user_id' in session:
        flash('Please Logout from the current dashboard!', 'warning')
        return redirect(url_for(f"{session['role']}_dashboard"))

    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = %s', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user[3], password):
            session['user_id'] = user[0]
            session['name'] = user[1]       # column index 1 = name
            session['role'] = user[4].lower()  # normalize role
            session['logged_in'] = True      # 👈 add login flag

            flash('Login successful!', 'success')

            # Redirect to the correct dashboard
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
            flash('Invalid email or password', 'error')

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

@app.route('/admin/manage_users', methods=['GET', 'POST'])
@role_required('admin')
def manage_users():
    if request.method == 'POST':
        user_id = request.form['user_id']
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        
        # Initialize optional fields
        batch_id = None
        department_id = None
        batch_status = None
        admission_date = None
        
        if role == 'student':
            batch_id = request.form['batch_id']
            department_id = request.form['department_id']
            batch_status = request.form['batch_status']
            
            if batch_status == 'new':
                admission_date = request.form['admission_date']

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (id, name, email, password, role, batch_id, department_id, batch_status, admission_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (user_id, name, email, password, role, batch_id, department_id, batch_status, admission_date))
            conn.commit()
            flash('User registered successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error registering user: {str(e)}', 'danger')
        finally:
            conn.close()
        return redirect(url_for('manage_users'))

    # Fetch batches and departments for dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
    except Exception as e:
        flash(f'Error fetching data: {str(e)}', 'danger')
        batches = []
        departments = []
    finally:
        conn.close()
    
    return render_template('manage_users.html', batches=batches, departments=departments)


@app.route('/admin/import_users', methods=['POST'])
@role_required('admin')
def import_users():
    if 'csv_file' not in request.files:
        flash('No file part in the request.', 'danger')
        return redirect(url_for('manage_users'))
    
    file = request.files['csv_file']
    
    if file.filename == '':
        flash('No selected file.', 'danger')
        return redirect(url_for('manage_users'))
    
    if not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('manage_users'))

    try:
        stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream)

        conn = get_db_connection()
        cursor = conn.cursor()

        for row in csv_input:
            user_id = row.get('user_id', 'N/A')
            name = row.get('name', 'N/A')
            email = row.get('email', 'N/A')
            password = generate_password_hash(row.get('password', 'N/A'))
            role = row.get('role', 'N/A')
            batch_id = row.get('batch_id', 'N/A') if role == 'student' else None
            department_id = row.get('department_id', 'N/A') if role == 'student' else None
            batch_status = row.get('batch_status', 'N/A') if role == 'student' else None
            admission_date = row.get('admission_date', 'N/A') if batch_status == 'new' else None

            cursor.execute('''
                INSERT INTO users (id, name, email, password, role, batch_id, department_id, batch_status, admission_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (user_id, name, email, password, role, batch_id, department_id, batch_status, admission_date))

        conn.commit()
        flash('Records imported successfully!', 'success')
    except Exception as e:
        if 'conn' in locals():
            conn.rollback()
        print(e)
        flash('Error importing records. Please check your CSV format.', 'danger')
    finally:
        if 'conn' in locals():
            conn.close()

    return redirect(url_for('manage_users'))

@app.route('/get_courses', methods=['POST'])
def get_courses():
    data = request.get_json()
    batch_id = data['batch_id']
    department_id = data['department_id']
    semester_id = data['semester_id']

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM courses 
        WHERE batch_id = %s AND department_id = %s AND semester_id = %s
    ''', (batch_id, department_id, semester_id))
    filtered_courses = cursor.fetchall()
    conn.close()

    # Return filtered courses as JSON
    return jsonify(filtered_courses)

@app.route('/admin/allocate_courses', methods=['GET', 'POST'])
@role_required('admin')
def allocate_courses():
    if request.method == 'POST':
        course_id = request.form['course_id']
        teacher_id = request.form['teacher_id']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO course_allocations (course_id, teacher_id)
            VALUES (%s, %s) RETURNING id
        ''', (course_id, teacher_id))
        # Get the inserted ID if needed
        inserted_id = cursor.fetchone()[0]
        conn.commit()
        conn.close()
        return redirect(url_for('admin_dashboard'))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM courses')
    courses = cursor.fetchall()
    cursor.execute('SELECT * FROM users WHERE role = %s', ('teacher',))
    teachers = cursor.fetchall()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()
    conn.close()

    return render_template(
        'allocate_courses.html',
        courses=courses,
        teachers=teachers,
        batches=batches,
        departments=departments,
        semesters=semesters
    )


@app.route('/admin/view_students', methods=['GET', 'POST'])
@role_required("admin", "teacher")
def view_students():
    selected_batch = None
    selected_department = None
    selected_batch_name = None
    selected_department_name = None
    students = []

    # Fetch all batches and departments for the dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()

    if request.method == 'POST':
        selected_batch = request.form['batch_id']
        selected_department = request.form['department_id']

        # Fetch batch name
        cursor.execute('SELECT name FROM batches WHERE id = %s', (selected_batch,))
        batch_row = cursor.fetchone()
        if batch_row:
            selected_batch_name = batch_row[0]

        # Fetch department name
        cursor.execute('SELECT name FROM departments WHERE id = %s', (selected_department,))
        dept_row = cursor.fetchone()
        if dept_row:
            selected_department_name = dept_row[0]

        # Fetch students for the selected batch and department, sorted by the last number in their ID
        # PostgreSQL uses SUBSTRING instead of SUBSTR and has different syntax
        cursor.execute('''
            SELECT users.id, users.name, users.email, batches.name, departments.name
            FROM users
            JOIN batches ON users.batch_id = batches.id
            JOIN departments ON users.department_id = departments.id
            WHERE users.role = 'student' AND batches.id = %s AND departments.id = %s
            ORDER BY CAST(SUBSTRING(users.id FROM '(\\d+)$') AS INTEGER)
        ''', (selected_batch, selected_department))
        students = cursor.fetchall()

    conn.close()

    # Get the user's role from the session
    user_role = session.get('role')

    return render_template(
        'view_students.html',
        batches=batches,
        departments=departments,
        students=students,
        selected_batch=selected_batch,
        selected_department=selected_department,
        selected_batch_name=selected_batch_name,
        selected_department_name=selected_department_name,
        user_role=user_role
    )


@app.route('/admin/update_student/<student_id>', methods=['GET', 'POST'])
@role_required("admin")
def update_student(student_id):
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        batch_id = request.form['batch_id']
        department_id = request.form['department_id']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE users
            SET name = %s, email = %s, batch_id = %s, department_id = %s
            WHERE id = %s
        ''', (name, email, batch_id, department_id, student_id))
        conn.commit()
        conn.close()
        flash('Student updated successfully!', 'success')
        return redirect(url_for('view_students'))

    # Fetch the student's current data
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE id = %s', (student_id,))
    student = cursor.fetchone()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    conn.close()

    return render_template('update_student.html', student=student, batches=batches, departments=departments)


@app.route('/admin/delete_student/<student_id>', methods=['POST'])
@role_required("admin")
def delete_student(student_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM users WHERE id = %s', (student_id,))
        conn.commit()
        conn.close()
        return jsonify({'success': True, 'message': 'Student deleted successfully!'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

from werkzeug.utils import secure_filename
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
import io
import csv
from slugify import slugify
from flask import Response, flash, redirect, url_for, session

@app.route('/admin/generate_reports', methods=['GET', 'POST'])
@role_required("admin")
def admin_generate_reports():
    if request.method == 'POST':
        # Check if this is an export request
        if 'export_csv' in request.form or 'export_pdf' in request.form:
            # Get the filter parameters from session
            batch_id = session.get('report_batch_id')
            department_id = session.get('report_department_id')
            semester_id = session.get('report_semester_id')
            
            if not all([batch_id, department_id, semester_id]):
                flash('Please generate a report first before exporting', 'error')
                return redirect(url_for('admin_generate_reports'))
        else:
            # Regular report generation
            batch_id = request.form['batch_id']
            department_id = request.form['department_id']
            semester_id = request.form['semester_id']
            
            # Store filters in session for export
            session['report_batch_id'] = batch_id
            session['report_department_id'] = department_id
            session['report_semester_id'] = semester_id
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        try:
            # Get batch, department, semester names for report title
            cursor.execute('SELECT name FROM batches WHERE id = %s', (batch_id,))
            batch_result = cursor.fetchone()
            if not batch_result:
                flash('Batch not found!', 'error')
                return redirect(url_for('admin_generate_reports'))
            batch_name = batch_result[0]
            
            cursor.execute('SELECT name FROM departments WHERE id = %s', (department_id,))
            dept_result = cursor.fetchone()
            if not dept_result:
                flash('Department not found!', 'error')
                return redirect(url_for('admin_generate_reports'))
            dept_name = dept_result[0]
            
            cursor.execute('SELECT name FROM semesters WHERE id = %s', (semester_id,))
            semester_result = cursor.fetchone()
            if not semester_result:
                flash('Semester not found!', 'error')
                return redirect(url_for('admin_generate_reports'))
            semester_name = semester_result[0]
            
            # Get all students in batch/department
            cursor.execute('''
            SELECT u.id, u.name, 
            COUNT(a.id) AS total_days,
            COALESCE(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), 0) AS present_days,
            CASE 
               WHEN COUNT(a.id) = 0 THEN 0.00
               ELSE ROUND(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id), 2)
            END AS percentage
            FROM users u
            LEFT JOIN attendance a ON u.id = a.student_id
            LEFT JOIN courses c ON a.course_id = c.id
            WHERE u.role = 'student' 
            AND u.batch_id = %s 
            AND u.department_id = %s
            AND c.semester_id = %s
            GROUP BY u.id, u.name
            ORDER BY CAST(SUBSTRING(u.id FROM '(\\d+)$') AS INTEGER)
            ''', (batch_id, department_id, semester_id))
            
            report_data = cursor.fetchall()
            
            if 'export_csv' in request.form:
                return export_csv(report_data, f"Reports for {batch_name}, Department {dept_name}, {semester_name}")
            elif 'export_pdf' in request.form:
                return export_pdf(report_data, f"Reports for {batch_name}, Department {dept_name}, {semester_name}")
            
            return render_template('admin_generate_reports.html', 
                                report_data=report_data,
                                batch_name=batch_name,
                                dept_name=dept_name,
                                semester_name=semester_name,
                                batches=session.get('batches'),
                                departments=session.get('departments'),
                                semesters=session.get('semesters'))
            
        except Exception as e:
            flash(f'Error generating report: {str(e)}', 'error')
            return redirect(url_for('admin_generate_reports'))
        
        finally:
            conn.close()
    
    # Fetch dropdown options
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()
        
        # Store in session for later use
        session['batches'] = batches
        session['departments'] = departments
        session['semesters'] = semesters
        
        return render_template('admin_generate_reports.html', 
                            batches=batches,
                            departments=departments,
                            semesters=semesters)
    except Exception as e:
        flash(f'Error fetching dropdown data: {str(e)}', 'error')
        return render_template('admin_generate_reports.html')
    finally:
        conn.close()

@app.route('/teacher/generate_reports', methods=['GET', 'POST'])
@role_required("teacher")
def teacher_generate_reports():
    teacher_id = session.get('user_id')
    if not teacher_id:
        flash('Please login first', 'error')
        return redirect(url_for('login'))
    
    # Fetch dropdown options - PostgreSQL connection
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Get batches
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        
        # Get departments
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
        
        # Get semesters
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()
        
        # Store in session for later use
        session['batches'] = batches
        session['departments'] = departments
        session['semesters'] = semesters

        if request.method == 'POST':
            # Check if this is an AJAX request for course filtering
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                batch_id = request.form.get('batch_id')
                department_id = request.form.get('department_id')
                semester_id = request.form.get('semester_id')
                
                # Get courses allocated to this teacher for the selected criteria
                cursor.execute('''
                    SELECT DISTINCT c.id, c.name 
                    FROM course_allocations ca
                    JOIN courses c ON ca.course_id = c.id
                    JOIN timetable t ON c.id = t.course_id
                    WHERE ca.teacher_id = %s
                    AND t.batch_id = %s
                    AND c.department_id = %s
                    AND c.semester_id = %s
                ''', (teacher_id, batch_id, department_id, semester_id))
                courses = cursor.fetchall()
                
                return jsonify(courses)
            
            # Check if this is an export request
            if 'export_csv' in request.form or 'export_pdf' in request.form:
                # Get the filter parameters from session
                batch_id = session.get('report_batch_id')
                department_id = session.get('report_department_id')
                semester_id = session.get('report_semester_id')
                course_id = session.get('report_course_id')
                
                if not all([batch_id, department_id, semester_id, course_id]):
                    flash('Please generate a report first before exporting', 'error')
                    return redirect(url_for('teacher_generate_reports'))
            else:
                # Regular report generation
                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                semester_id = request.form['semester_id']
                course_id = request.form['course_id']
                
                # Store filters in session for export
                session['report_batch_id'] = batch_id
                session['report_department_id'] = department_id
                session['report_semester_id'] = semester_id
                session['report_course_id'] = course_id
            
            # Verify teacher is allocated to this course
            cursor.execute('''
                SELECT 1 FROM course_allocations 
                WHERE teacher_id = %s AND course_id = %s
            ''', (teacher_id, course_id))
            if not cursor.fetchone():
                flash('You are not allocated to this course!', 'error')
                return redirect(url_for('teacher_generate_reports'))
            
            # Get names for report title
            cursor.execute('SELECT name FROM batches WHERE id = %s', (batch_id,))
            batch_result = cursor.fetchone()
            batch_name = batch_result[0] if batch_result else "Unknown Batch"
            
            cursor.execute('SELECT name FROM departments WHERE id = %s', (department_id,))
            dept_result = cursor.fetchone()
            dept_name = dept_result[0] if dept_result else "Unknown Department"
            
            cursor.execute('SELECT name FROM semesters WHERE id = %s', (semester_id,))
            semester_result = cursor.fetchone()
            semester_name = semester_result[0] if semester_result else "Unknown Semester"
            
            cursor.execute('SELECT name FROM courses WHERE id = %s', (course_id,))
            course_result = cursor.fetchone()
            course_name = course_result[0] if course_result else "Unknown Course"
            
            # Get attendance data - PostgreSQL compatible
            cursor.execute('''
            SELECT u.id, u.name, 
            COUNT(a.id) AS total_days,
            COALESCE(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END), 0) AS present_days,
            CASE 
               WHEN COUNT(a.id) = 0 THEN 0.00
               ELSE ROUND(SUM(CASE WHEN a.status = 'present' THEN 1 ELSE 0 END) * 100.0 / COUNT(a.id), 2)
            END AS percentage
            FROM users u
            LEFT JOIN attendance a ON u.id = a.student_id
            WHERE u.role = 'student' 
            AND u.batch_id = %s 
            AND u.department_id = %s
            AND a.course_id = %s
            GROUP BY u.id, u.name
            ORDER BY CAST(SUBSTRING(u.id FROM '(\\d+)$') AS INTEGER)
            ''', (batch_id, department_id, course_id))
            report_data = cursor.fetchall()
            
            if 'export_csv' in request.form:
                title = f"Reports for {batch_name}, Department {dept_name}, {semester_name}, Course {course_name}"
                return export_csv(report_data, title)
            elif 'export_pdf' in request.form:
                title = f"Reports for {batch_name}, Department {dept_name}, {semester_name}, Course {course_name}"
                return export_pdf(report_data, title)
            
            return render_template('teacher_generate_reports.html', 
                                report_data=report_data,
                                batch_name=batch_name,
                                dept_name=dept_name,
                                semester_name=semester_name,
                                course_name=course_name,
                                batches=batches,
                                departments=departments,
                                semesters=semesters)
        
        # Get initial courses for the teacher (empty selection)
        cursor.execute('''
            SELECT c.id, c.name 
            FROM course_allocations ca
            JOIN courses c ON ca.course_id = c.id
            WHERE ca.teacher_id = %s
            LIMIT 0
        ''', (teacher_id,))
        courses = cursor.fetchall()
        
        return render_template('teacher_generate_reports.html', 
                            batches=batches,
                            departments=departments,
                            semesters=semesters,
                            courses=courses)
    
    except Exception as e:
        flash(f'Error: {str(e)}', 'error')
        return render_template('teacher_generate_reports.html')
    finally:
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



@app.route('/view_attendance1', methods=['GET', 'POST'])
def view_attendance1():
    student_id = request.args.get('student_id')
    course_id = request.args.get('course_id')

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch courses for the selected student
    cursor.execute('''
        SELECT courses.id, courses.name
        FROM attendance
        JOIN courses ON attendance.course_id = courses.id
        WHERE attendance.student_id = %s
        GROUP BY courses.id
    ''', (student_id,))
    courses = cursor.fetchall()

    # Fetch attendance data for the selected student and course
    attendance_data = []
    if request.method == 'POST':
        course_id = request.form['course_id']
        cursor.execute('''
            SELECT date, status
            FROM attendance
            WHERE student_id = %s AND course_id = %s
        ''', (student_id, course_id))
        attendance_data = cursor.fetchall()

    conn.close()
    return render_template('view_attendance1.html', student_id=student_id, courses=courses, attendance_data=attendance_data, selected_course=course_id)



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
        name = request.form['name']
        semester_id = request.form['semester_id']
        department_id = request.form['department_id']
        batch_id = request.form['batch_id']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO courses (name, semester_id, department_id, batch_id)
            VALUES (%s, %s, %s, %s)
        ''', (name, semester_id, department_id, batch_id))
        conn.commit()
        conn.close()
        flash('Course created successfully!', 'success')
        return redirect(url_for('create_course'))

    # Fetch semesters, departments, and batches for dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    conn.close()
    
    return render_template('create_course.html', 
                         semesters=semesters, 
                         departments=departments,
                         batches=batches)


@app.route('/admin/manage_courses', methods=['GET', 'POST'])
@role_required("admin")
def manage_courses():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch dropdown data for both GET and POST
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()

    courses = []
    selected_batch = selected_department = selected_semester = None

    if request.method == 'POST':
        selected_batch = request.form['batch_id']
        selected_department = request.form['department_id']
        selected_semester = request.form['semester_id']

        # Fetch filtered courses
        cursor.execute('''
            SELECT id, name
            FROM courses 
            WHERE batch_id = %s AND department_id = %s AND semester_id = %s
        ''', (selected_batch, selected_department, selected_semester))
        courses = cursor.fetchall()

    conn.close()

    return render_template('manage_courses.html',
                           batches=batches,
                           departments=departments,
                           semesters=semesters,
                           courses=courses,
                           selected_batch=selected_batch,
                           selected_department=selected_department,
                           selected_semester=selected_semester)


@app.route('/admin/delete_course/<int:course_id>')
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


@app.route('/admin/allocate_course', methods=['GET', 'POST'])
@role_required("admin")
def allocate_course():
    if request.method == 'POST':
        course_id = request.form['course_id']
        teacher_id = request.form['teacher_id']
        batch_id = request.form['batch_id']
        department_id = request.form['department_id']
        semester_id = request.form['semester_id']
        start_date = request.form['start_date']
        end_date = request.form['end_date']

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO course_allocations 
            (course_id, teacher_id, batch_id, department_id, semester_id, start_date, end_date)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (course_id, teacher_id, batch_id, department_id, semester_id, start_date, end_date))
        conn.commit()
        conn.close()
        flash('Course allocated successfully with dates!', 'success')
        return redirect(url_for('allocate_course'))

    # Fetch data for dropdowns
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM courses')
    courses = cursor.fetchall()
    cursor.execute('SELECT * FROM users WHERE role = %s', ('teacher',))
    teachers = cursor.fetchall()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()
    conn.close()

    return render_template('allocate_course.html', 
                         courses=courses, 
                         teachers=teachers, 
                         batches=batches,
                         departments=departments,
                         semesters=semesters)


@app.route('/teacher/mark_attendance', methods=['GET', 'POST'])
@role_required("teacher")
def mark_attendance():
    teacher_id = session.get('user_id')
    conn = get_db_connection()  # Changed to PostgreSQL connection
    cursor = conn.cursor()

    # Fetch static dropdown options
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()

    # Handle POST request
    if request.method == 'POST':
        try:
            batch_id = request.form['batch_id']
            department_id = request.form['department_id']
            semester_id = request.form['semester_id']
            course_id = request.form['course_id']
            date = request.form['date']
            start_time = request.form['start_time']
            end_time = request.form['end_time']
            class_type = request.form['class_type']

            # Process attendance for each student
            for key, value in request.form.items():
                if key.startswith('attendance_'):
                    student_id = key.split('_')[1]
                    status = value
                    cursor.execute('''
                        INSERT INTO attendance 
                        (student_id, course_id, batch_id, department_id, semester_id, date, start_time, end_time, status, class_type)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ''', (student_id, course_id, batch_id, department_id, semester_id, date, start_time, end_time, status, class_type))

            conn.commit()
            flash('Attendance marked successfully!', 'success')
        except Exception as e:
            conn.rollback()
            flash(f'Error: {str(e)}', 'error')
        finally:
            conn.close()
        return redirect(url_for('mark_attendance'))

    # Handle GET request
    batch_id = request.args.get('batch_id')
    department_id = request.args.get('department_id')
    semester_id = request.args.get('semester_id')
    courses = []
    students = []

    if batch_id and department_id and semester_id:
        # Fetch courses allocated to this teacher
        cursor.execute('''
            SELECT c.id, c.name 
            FROM courses c 
            JOIN course_allocations ca ON c.id = ca.course_id
            WHERE c.department_id = %s AND c.semester_id = %s AND ca.teacher_id = %s
        ''', (department_id, semester_id, teacher_id))
        courses = cursor.fetchall()

        # Fetch students if course selected
        course_id = request.args.get('course_id')
        if course_id:
            cursor.execute('''
                SELECT id, name 
                FROM users 
                WHERE role = 'student' AND batch_id = %s AND department_id = %s
                ORDER BY CAST(SUBSTRING(id FROM '(\\d+)$') AS INTEGER)
            ''', (batch_id, department_id))
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
        selected_course=request.args.get('course_id')
    )

    
# Add this near the top of your Flask application file
from datetime import datetime

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
    # Initialize all template variables at the start
    courses = []
    batches = []
    departments = []
    semesters = []
    timetable_data = []
    selected_batch = None
    selected_department = None
    selected_semester = None

    # Connect to database once
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Always fetch dropdown data
        cursor.execute('SELECT * FROM courses')
        courses = cursor.fetchall()
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()

        if request.method == 'POST':
            if 'generate_table' in request.form:
                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                semester_id = request.form['semester_id']
                selected_batch = batch_id
                selected_department = department_id
                selected_semester = semester_id

                # Get all possible time slots first
                cursor.execute('''
                    SELECT DISTINCT start_time, end_time 
                    FROM timetable 
                    WHERE batch_id = %s AND department_id = %s AND semester_id = %s
                    ORDER BY start_time
                ''', (batch_id, department_id, semester_id))
                time_slots = cursor.fetchall()
                
                # Get timetable data organized by day
                timetable_by_day = {
                    'Monday': {},
                    'Tuesday': {},
                    'Wednesday': {},
                    'Thursday': {},
                    'Friday': {}
                }
                cursor.execute('''
                SELECT c.name, t.day, t.start_time, t.end_time, u.name as teacher_name, t.class_type, t.id as entry_id
                FROM timetable t
                JOIN courses c ON t.course_id = c.id
                LEFT JOIN course_allocations ca ON ca.course_id = t.course_id 
                AND ca.batch_id = t.batch_id 
                AND ca.department_id = t.department_id 
                AND ca.semester_id = t.semester_id
                LEFT JOIN users u ON ca.teacher_id = u.id AND u.role = 'teacher'
                WHERE t.batch_id = %s AND t.department_id = %s AND t.semester_id = %s
                ORDER BY t.start_time
                ''', (batch_id, department_id, semester_id))    

                for entry in cursor.fetchall():
                    day = entry[1]
                    time_key = f"{entry[2]}-{entry[3]}"
                    timetable_by_day[day][time_key] = {
                    'course': entry[0],
                    'teacher': entry[4],
                    'class_type': entry[5],
                    'entry_id': entry[6]  # Add entry_id to the data
                }   

                
                # Prepare data for template
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

            else:
                # Add new timetable entry with class_type
                course_id = request.form['course_id']
                batch_id = request.form['batch_id']
                department_id = request.form['department_id']
                semester_id = request.form['semester_id']
                day = request.form['day']
                start_time = request.form['start_time']
                end_time = request.form['end_time']
                class_type = request.form['class_type']  # New field

                cursor.execute('''
                    INSERT INTO timetable (course_id, batch_id, department_id, semester_id, 
                                         day, start_time, end_time, class_type)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ''', (course_id, batch_id, department_id, semester_id, 
                      day, start_time, end_time, class_type))
                conn.commit()
                flash('Timetable entry added successfully!', 'success')

    finally:
        conn.close()

    return render_template('timetable.html', 
                         courses=courses, 
                         batches=batches, 
                         departments=departments, 
                         semesters=semesters, 
                         timetable_data=timetable_data,
                         selected_batch=selected_batch, 
                         selected_department=selected_department, 
                         selected_semester=selected_semester)


@app.route('/admin/edit_timetable/<int:timetable_id>', methods=['GET', 'POST'])
@role_required("admin")
def edit_timetable(timetable_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Fetch the current timetable entry
    cursor.execute('''
        SELECT * FROM timetable WHERE id = %s
    ''', (timetable_id,))
    entry = cursor.fetchone()
    
    # Fetch dropdown data
    cursor.execute('SELECT * FROM courses')
    courses = cursor.fetchall()
    cursor.execute('SELECT * FROM batches')
    batches = cursor.fetchall()
    cursor.execute('SELECT * FROM departments')
    departments = cursor.fetchall()
    cursor.execute('SELECT * FROM semesters')
    semesters = cursor.fetchall()
    
    if request.method == 'POST':
        # Update the timetable entry
        course_id = request.form['course_id']
        batch_id = request.form['batch_id']
        department_id = request.form['department_id']
        semester_id = request.form['semester_id']
        day = request.form['day']
        start_time = request.form['start_time']
        end_time = request.form['end_time']
        class_type = request.form['class_type']
        
        cursor.execute('''
            UPDATE timetable 
            SET course_id = %s, batch_id = %s, department_id = %s, semester_id = %s,
                day = %s, start_time = %s, end_time = %s, class_type = %s
            WHERE id = %s
        ''', (course_id, batch_id, department_id, semester_id, 
              day, start_time, end_time, class_type, timetable_id))
        conn.commit()
        conn.close()
        # flash('Timetable entry updated successfully!', 'success')
        return redirect(url_for('timetable'))
    
    conn.close()
    return render_template('edit_timetable.html', 
                         entry=entry,
                         courses=courses,
                         batches=batches,
                         departments=departments,
                         semesters=semesters)

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
    # Role guard: allow teacher and student
    if 'role' not in session or session['role'] not in ['teacher', 'student']:
        flash('Unauthorized: Teachers and Students only.', 'danger')
        return redirect(url_for('home'))  # Changed from 'dashboard' to 'home'

    # Initialize template vars
    batches = []
    departments = []
    semesters = []
    timetable_data = []
    selected_batch = None
    selected_department = None
    selected_semester = None

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Populate dropdowns
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()

        if request.method == 'POST' and 'generate_table' in request.form:
            batch_id = request.form['batch_id']
            department_id = request.form['department_id']
            semester_id = request.form['semester_id']
            selected_batch = batch_id
            selected_department = department_id
            selected_semester = semester_id

            # 1) All time slots for the chosen B/D/S - FIXED ORDER BY
            cursor.execute('''
                SELECT DISTINCT start_time, end_time
                FROM timetable
                WHERE batch_id = %s AND department_id = %s AND semester_id = %s
                ORDER BY start_time
            ''', (batch_id, department_id, semester_id))
            time_slots = cursor.fetchall()

            # 2) Fetch entries grouped by day - FIXED ORDER BY
            timetable_by_day = {d: {} for d in ['Monday','Tuesday','Wednesday','Thursday','Friday']}

            cursor.execute('''
                SELECT c.name, t.day, t.start_time, t.end_time,
                       u.name AS teacher_name, t.class_type, t.id AS entry_id
                FROM timetable t
                JOIN courses c ON t.course_id = c.id
                LEFT JOIN course_allocations ca ON ca.course_id = t.course_id
                     AND ca.batch_id = t.batch_id
                     AND ca.department_id = t.department_id
                     AND ca.semester_id = t.semester_id
                LEFT JOIN users u ON ca.teacher_id = u.id AND u.role = 'teacher'
                WHERE t.batch_id = %s AND t.department_id = %s AND t.semester_id = %s
                ORDER BY t.start_time
            ''', (batch_id, department_id, semester_id))

            for course_name, day, start_time, end_time, teacher_name, class_type, entry_id in cursor.fetchall():
                time_key = f"{start_time}-{end_time}"
                timetable_by_day[day][time_key] = {
                    'course': course_name,
                    'teacher': teacher_name,
                    'class_type': class_type,
                    'entry_id': entry_id,
                }

            # 3) Flatten into rows for template
            for start_time, end_time in time_slots:
                time_key = f"{start_time}-{end_time}"
                row = {
                    'start_time': start_time,
                    'end_time': end_time,
                    'days': {d: timetable_by_day[d].get(time_key) for d in ['Monday','Tuesday','Wednesday','Thursday','Friday']}
                }
                timetable_data.append(row)

    except Exception as e:
        flash(f'Error loading timetable: {str(e)}', 'error')
        
    finally:
        conn.close()

    return render_template(
        'timetable_view.html',
        batches=batches,
        departments=departments,
        semesters=semesters,
        timetable_data=timetable_data,
        selected_batch=selected_batch,
        selected_department=selected_department,
        selected_semester=selected_semester,
    )

@app.route('/student/view_attendance', methods=['GET', 'POST'])
@role_required("student")
def view_attendance():
    student_id = session.get('user_id')  # Get logged-in student's ID

    if not student_id:
        return "No student logged in (session empty)", 400

    conn = get_db_connection()
    cursor = conn.cursor()

    # Fetch student details with LEFT JOIN (to avoid null join issues)
    cursor.execute('''
        SELECT users.id, users.name, 
               batches.name AS batch_name, 
               departments.name AS dept_name,
               users.batch_id, users.department_id
        FROM users
        LEFT JOIN batches ON users.batch_id = batches.id
        LEFT JOIN departments ON users.department_id = departments.id
        WHERE users.id = %s
    ''', (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        return f"Student not found for user_id={student_id}", 404

    # Unpack values
    stu_id, stu_name, batch_name, dept_name, batch_id, dept_id = student

    # Fetch all semesters
    cursor.execute('SELECT id, name FROM semesters ORDER BY name')
    semesters = cursor.fetchall()

    courses = []
    attendance_data = []
    selected_semester = None
    selected_course = None

    if request.method == 'POST':
        selected_semester = request.form.get('semester_id')
        selected_course = request.form.get('course_id')

        if selected_semester:
            # Filter courses by semester + student's batch + department
            cursor.execute('''
                SELECT id, name
                FROM courses
                WHERE semester_id = %s AND batch_id = %s AND department_id = %s
                ORDER BY name
            ''', (selected_semester, batch_id, dept_id))
            courses = cursor.fetchall()

        if selected_course:
            # Fetch attendance
            cursor.execute('''
                SELECT date, status, courses.name, class_type, start_time, end_time
                FROM attendance
                JOIN courses ON attendance.course_id = courses.id
                WHERE attendance.student_id = %s AND attendance.course_id = %s
                ORDER BY date DESC
            ''', (student_id, selected_course))
            raw_data = cursor.fetchall()

            # Format times
            attendance_data = []
            for entry in raw_data:
                start = datetime.strptime(entry[4], "%H:%M").strftime("%I:%M %p") if entry[4] else ""
                end = datetime.strptime(entry[5], "%H:%M").strftime("%I:%M %p") if entry[5] else ""
                attendance_data.append((entry[0], entry[1], entry[2], entry[3], start, end))

    conn.close()

    return render_template('view_attendance.html',
                           student=student,
                           semesters=semesters,
                           courses=courses,
                           attendance_data=attendance_data,
                           selected_semester=selected_semester,
                           selected_course=selected_course)


# Manage Batches
@app.route('/admin/manage_batches', methods=['GET', 'POST'])
@role_required("admin")
def manage_batches():
    if request.method == 'POST':
        if 'add_batch' in request.form:
            batch_name = request.form['batch_name']
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('INSERT INTO batches (name) VALUES (%s)', (batch_name,))
            conn.commit()
            conn.close()
            flash('Batch added successfully!', 'success')
        elif 'delete_batch' in request.form:
            batch_id = request.form['batch_id']
            conn = get_db_connection()
            cursor = conn.cursor()
            cursor.execute('DELETE FROM batches WHERE id = %s', (batch_id,))
            conn.commit()
            conn.close()
            flash('Batch deleted successfully!', 'success')
        return redirect(url_for('manage_batches'))

    # Fetch all batches
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
            cursor.execute('DELETE FROM departments WHERE id = %s', (department_id,))
            conn.commit()
            conn.close()
            flash('Department deleted successfully!', 'success')
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
            cursor.execute('DELETE FROM users WHERE id = %s AND role = %s', (teacher_id, "teacher"))
            conn.commit()
            conn.close()
            flash('Teacher deleted successfully!', 'success')
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

    try:
        # Fetch dropdown data
        cursor.execute('SELECT * FROM batches')
        batches = cursor.fetchall()
        cursor.execute('SELECT * FROM courses')
        courses = cursor.fetchall()
        cursor.execute('SELECT * FROM semesters')
        semesters = cursor.fetchall()
        cursor.execute('SELECT * FROM departments')
        departments = cursor.fetchall()

        attendance_data = []
        selected_batch = selected_course = selected_semester = selected_department = ''
        search_id = search_date = ''

        if request.method == 'POST':
            selected_batch = request.form.get('batch_id', '')
            selected_course = request.form.get('course_id', '')
            selected_semester = request.form.get('semester_id', '')
            selected_department = request.form.get('department_id', '')
            search_id = request.form.get('search_id', '').strip()
            search_date = request.form.get('search_date', '').strip()

            query = '''
                SELECT attendance.id, users.id, users.name, attendance.date,
                       attendance.start_time, attendance.end_time,
                       courses.name, attendance.status
                FROM attendance
                JOIN users ON attendance.student_id = users.id
                JOIN courses ON attendance.course_id = courses.id
                WHERE users.batch_id = %s
                  AND attendance.course_id = %s
                  AND courses.semester_id = %s
                  AND users.department_id = %s
            '''
            params = [selected_batch, selected_course, selected_semester, selected_department]

            if search_id:
                query += ' AND users.id LIKE %s'
                params.append(f'%{search_id}%')

            if search_date:
                query += ' AND attendance.date = %s'
                params.append(search_date)

            cursor.execute(query, params)
            results = cursor.fetchall()

            # Convert time to 12-hour format and sort by ID
            def convert_time(t):
                return datetime.strptime(t, "%H:%M").strftime("%I:%M %p") if t else ''

            def extract_numeric_id(sid):
                match = re.search(r'(\d+)$', sid)
                return int(match.group()) if match else float('inf')

            attendance_data = sorted([
                (
                    r[0], r[1], r[2], r[3],
                    convert_time(r[4]), convert_time(r[5]),
                    r[6], r[7]
                )
                for r in results
            ], key=lambda x: extract_numeric_id(x[1]))

        return render_template('manage_attendance.html',
                               batches=batches, courses=courses,
                               semesters=semesters, departments=departments,
                               attendance_data=attendance_data,
                               selected_batch=selected_batch,
                               selected_course=selected_course,
                               selected_semester=selected_semester,
                               selected_department=selected_department,
                               search_id=search_id,
                               search_date=search_date)
    except Exception as e:
        flash(f'Error fetching attendance data: {str(e)}', 'error')
        return render_template('manage_attendance.html',
                               batches=[], courses=[],
                               semesters=[], departments=[],
                               attendance_data=[],
                               selected_batch='',
                               selected_course='',
                               selected_semester='',
                               selected_department='',
                               search_id='',
                               search_date='')
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

@app.route('/admin/delete_attendance/<int:attendance_id>')
@role_required("admin")
def delete_attendance(attendance_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM attendance WHERE id = %s', (attendance_id,))
    conn.commit()
    conn.close()
    flash('Attendance deleted successfully!', 'success')
    return redirect(url_for('manage_attendance'))
 
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch

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
        # Get names
        cursor.execute('SELECT name FROM batches WHERE id = %s', (batch_id,))
        batch_name = cursor.fetchone()[0]
        cursor.execute('SELECT name FROM departments WHERE id = %s', (department_id,))
        department_name = cursor.fetchone()[0]
        cursor.execute('SELECT name FROM semesters WHERE id = %s', (semester_id,))
        semester_name = cursor.fetchone()[0]

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
    app.run(host="0.0.0.0", port=5000)
