import os
import sqlite3
import csv
import io
from functools import wraps

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
import logging
import csv
from io import TextIOWrapper

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from auth import authenticate, create_account, create_user_admin, hash_password
from chatbot import ask_university_assistant
from config import load_env_file
from database import init_database

if load_dotenv:
    load_dotenv()
else:
    load_env_file()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key")

# Basic logging for error tracking
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    init_database()
except sqlite3.OperationalError as exc:
    if "readonly" not in str(exc).lower():
        raise


def get_db():
    conn = sqlite3.connect("university.db")
    conn.row_factory = sqlite3.Row
    return conn


def flash_redirect(endpoint, message=None, **values):
    if message:
        values["message"] = message
    return redirect(url_for(endpoint, **values))


def get_announcements(role):
    conn = get_db()
    rows = conn.execute(
        """
        SELECT title, body, audience, created_at
        FROM announcements
        WHERE audience IN ('all', ?)
        ORDER BY announcement_id DESC
        LIMIT 4
        """,
        (role,),
    ).fetchall()
    conn.close()
    return rows


def csv_response(filename, rows):
    output = io.StringIO()
    rows = [dict(row) for row in rows]
    if rows:
        writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def simple_pdf_response(filename, title, lines):
    safe_lines = [title, ""] + [str(line) for line in lines]
    stream = "BT /F1 18 Tf 72 760 Td (" + _pdf_escape(title) + ") Tj ET\n"
    y = 720
    for line in safe_lines[2:]:
        stream += f"BT /F1 11 Tf 72 {y} Td ({_pdf_escape(line)}) Tj ET\n"
        y -= 18
    content = stream.encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
    ]
    pdf = b"%PDF-1.4\n"
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf += f"{index} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_at = len(pdf)
    pdf += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode()
    for offset in offsets[1:]:
        pdf += f"{offset:010d} 00000 n \n".encode()
    pdf += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    return Response(
        pdf,
        mimetype="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


def _pdf_escape(value):
    return str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def current_message():
    return request.args.get("message")


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.get('/notifications')
@login_required()
def notifications():
    role = session['user']['role']
    linked_id = session['user']['linked_id']
    conn = get_db()
    notes = []

    # Student notifications: low attendance and poor marks
    if role == 'student':
        low_att = conn.execute(
            "SELECT c.course_name, a.attendance_percentage FROM attendance a JOIN courses c ON c.course_id=a.course_id WHERE a.student_id=? AND a.attendance_percentage < 75",
            (linked_id,),
        ).fetchall()
        poor_marks = conn.execute(
            "SELECT c.course_name, m.marks FROM marks m JOIN courses c ON c.course_id=m.course_id WHERE m.student_id=? AND m.marks < 50",
            (linked_id,),
        ).fetchall()
        for row in low_att:
            notes.append({"type": "low_attendance", "message": f"Low attendance in {row['course_name']}: {row['attendance_percentage']}%", "course": row['course_name']})
        for row in poor_marks:
            notes.append({"type": "poor_marks", "message": f"Low marks in {row['course_name']}: {row['marks']}", "course": row['course_name']})

    # Faculty notifications: students in assigned courses with issues
    elif role == 'faculty':
        # students with attendance <75 or marks <50 in faculty's courses
        rows = conn.execute(
            """
            SELECT c.course_id, c.course_name, s.student_id, s.name, m.marks, a.attendance_percentage
            FROM courses c
            LEFT JOIN marks m ON m.course_id = c.course_id
            LEFT JOIN students s ON s.student_id = m.student_id
            LEFT JOIN attendance a ON a.student_id = s.student_id AND a.course_id = c.course_id
            WHERE c.faculty_id = ? AND (m.marks < 50 OR a.attendance_percentage < 75)
            ORDER BY c.course_name, m.marks ASC
            """,
            (linked_id,),
        ).fetchall()
        for r in rows:
            if r['marks'] is not None and r['marks'] < 50:
                notes.append({"type": "poor_marks", "message": f"{r['name']} has low marks ({r['marks']}) in {r['course_name']}", "student_id": r['student_id']})
            if r['attendance_percentage'] is not None and r['attendance_percentage'] < 75:
                notes.append({"type": "low_attendance", "message": f"{r['name']} has low attendance ({r['attendance_percentage']}%) in {r['course_name']}", "student_id": r['student_id']})

    # Admin notifications: aggregate counts
    elif role == 'admin':
        low_att_count = conn.execute("SELECT COUNT(*) FROM attendance WHERE attendance_percentage < 75").fetchone()[0]
        low_marks_count = conn.execute("SELECT COUNT(*) FROM marks WHERE marks < 50").fetchone()[0]
        notes.append({"type": "summary", "message": f"Students with low attendance: {low_att_count}"})
        notes.append({"type": "summary", "message": f"Marks below threshold: {low_marks_count}"})

    # Include announcements and upcoming events relevant to the user
    announcements = conn.execute(
        "SELECT announcement_id, title, body, audience, created_at FROM announcements WHERE audience IN ('all', ?) ORDER BY announcement_id DESC LIMIT 5",
        (role,),
    ).fetchall()
    events = conn.execute(
        "SELECT event_id, title, body, audience, event_date FROM events WHERE audience IN ('all', ?) ORDER BY event_date LIMIT 10",
        (role,),
    ).fetchall()
    conn.close()

    return jsonify({
        "notifications": notes,
        "announcements": [dict(a) for a in announcements],
        "events": [dict(e) for e in events],
    })


@app.post('/admin/events')
@login_required('admin')
def admin_save_event():
    title = request.form.get('title', '').strip()
    body = request.form.get('body', '').strip()
    audience = request.form.get('audience', 'all')
    event_date = request.form.get('event_date', '').strip()
    if not title or not event_date:
        return flash_redirect('admin_dashboard', 'Title and event date are required.')
    conn = get_db()
    conn.execute('INSERT INTO events(title, body, audience, event_date) VALUES (?, ?, ?, ?)', (title, body, audience, event_date))
    conn.commit()
    conn.close()
    logger.info('Admin %s created event %s for %s on %s', session['user']['username'], title, audience, event_date)
    return flash_redirect('admin_dashboard', 'Event saved.')


@app.get('/events.json')
@login_required()
def events_json():
    role = session['user']['role']
    conn = get_db()
    rows = conn.execute('SELECT event_id, title, body, audience, event_date FROM events WHERE audience IN ("all", ?) ORDER BY event_date LIMIT 20', (role,)).fetchall()
    conn.close()
    return jsonify({'events': [dict(r) for r in rows]})


def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login"))
            if role and session["user"]["role"] != role:
                return redirect(url_for("dashboard"))
            return view(*args, **kwargs)

        return wrapped

    return decorator


@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    message = request.args.get('message')

    if request.method == "POST":
        role = request.form.get("role", "").strip().lower()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        user = authenticate(username, password, role)
        if user:
            session["user"] = user
            return redirect(url_for("dashboard"))

        error = "Invalid username, password, or role."

    return render_template("login.html", error=error, message=message)


@app.route("/signup", methods=["GET", "POST"])
def signup():
    error = None

    if request.method == "POST":
        try:
            user = create_account(request.form)
            session["user"] = user
            return redirect(url_for("dashboard", message="Account created. Welcome!"))
        except ValueError as exc:
            error = str(exc)
        except sqlite3.OperationalError as exc:
            error = "Signup could not save right now. Please make sure the database is writable."
            if "readonly" not in str(exc).lower():
                raise

    return render_template("signup.html", error=error)


@app.route("/dashboard")
@login_required()
def dashboard():
    role = session["user"]["role"]
    return redirect(url_for(f"{role}_dashboard"))


@app.route("/student")
@login_required("student")
def student_dashboard():
    linked_id = session["user"]["linked_id"]
    conn = get_db()
    student = conn.execute(
        "SELECT * FROM students WHERE student_id=?",
        (linked_id,),
    ).fetchone()
    marks = conn.execute(
        """
        SELECT c.course_name, c.credits, m.marks, a.attendance_percentage
        FROM courses c
        LEFT JOIN marks m ON m.course_id = c.course_id AND m.student_id = ?
        LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id = ?
        WHERE m.student_id IS NOT NULL OR a.student_id IS NOT NULL
        ORDER BY c.course_name
        """,
        (linked_id, linked_id),
    ).fetchall()
    announcements = get_announcements("student")
    conn.close()

    mark_values = [row["marks"] for row in marks if row["marks"] is not None]
    attendance_values = [row["attendance_percentage"] for row in marks if row["attendance_percentage"] is not None]
    average_marks = round(sum(mark_values) / len(mark_values), 1) if mark_values else None
    average_attendance = round(sum(attendance_values) / len(attendance_values), 1) if attendance_values else None
    best_course = max(marks, key=lambda row: row["marks"] or -1) if mark_values else None
    weakest_course = min([row for row in marks if row["marks"] is not None], key=lambda row: row["marks"]) if mark_values else None
    low_attendance = [row for row in marks if row["attendance_percentage"] is not None and row["attendance_percentage"] < 75]
    insights = {
        "average_marks": average_marks,
        "average_attendance": average_attendance,
        "best_course": best_course,
        "weakest_course": weakest_course,
        "low_attendance": low_attendance,
    }
    return render_template(
        "student.html",
        user=session["user"],
        student=student,
        marks=marks,
        insights=insights,
        announcements=announcements,
        message=current_message(),
    )


@app.route("/faculty")
@login_required("faculty")
def faculty_dashboard():
    linked_id = session["user"]["linked_id"]
    conn = get_db()
    faculty = conn.execute(
        "SELECT * FROM faculty WHERE faculty_id=?",
        (linked_id,),
    ).fetchone()
    courses = conn.execute(
        """
        SELECT c.course_id, c.course_name, c.credits, COUNT(DISTINCT m.student_id) AS enrolled
        FROM courses c
        LEFT JOIN marks m ON m.course_id = c.course_id
        WHERE c.faculty_id=?
        GROUP BY c.course_id
        ORDER BY c.course_name
        """,
        (linked_id,),
    ).fetchall()
    roster = conn.execute(
        """
        SELECT c.course_id, c.course_name, s.student_id, s.name, s.department,
               m.mark_id, m.marks, a.attendance_id, a.attendance_percentage
        FROM courses c
        LEFT JOIN marks m ON m.course_id = c.course_id
        LEFT JOIN students s ON s.student_id = m.student_id
        LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id = s.student_id
        WHERE c.faculty_id=?
        ORDER BY c.course_name, s.name
        """,
        (linked_id,),
    ).fetchall()
    course_summary = conn.execute(
        """
        SELECT c.course_name,
               ROUND(AVG(m.marks), 1) AS avg_marks,
               ROUND(AVG(a.attendance_percentage), 1) AS avg_attendance,
               SUM(CASE WHEN m.marks < 50 THEN 1 ELSE 0 END) AS at_risk_marks,
               SUM(CASE WHEN a.attendance_percentage < 75 THEN 1 ELSE 0 END) AS at_risk_attendance
        FROM courses c
        LEFT JOIN marks m ON m.course_id = c.course_id
        LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id = m.student_id
        WHERE c.faculty_id=?
        GROUP BY c.course_id
        ORDER BY c.course_name
        """,
        (linked_id,),
    ).fetchall()
    announcements = get_announcements("faculty")
    conn.close()
    return render_template(
        "faculty.html",
        user=session["user"],
        faculty=faculty,
        courses=courses,
        roster=roster,
        course_summary=course_summary,
        announcements=announcements,
        message=current_message(),
    )


@app.route("/admin")
@login_required("admin")
def admin_dashboard():
    conn = get_db()
    search = request.args.get("q", "").strip()
    department = request.args.get("department", "").strip()
    student_where = []
    student_params = []
    if search:
        student_where.append("name LIKE ?")
        student_params.append(f"%{search}%")
    if department:
        student_where.append("department=?")
        student_params.append(department)
    student_filter = "WHERE " + " AND ".join(student_where) if student_where else ""

    stats = {
        "students": conn.execute("SELECT COUNT(*) FROM students").fetchone()[0],
        "faculty": conn.execute("SELECT COUNT(*) FROM faculty").fetchone()[0],
        "courses": conn.execute("SELECT COUNT(*) FROM courses").fetchone()[0],
        "admins": conn.execute("SELECT COUNT(*) FROM administration").fetchone()[0],
    }
    students = conn.execute(f"SELECT * FROM students {student_filter} ORDER BY student_id LIMIT 50", student_params).fetchall()
    faculty = conn.execute("SELECT * FROM faculty ORDER BY faculty_id LIMIT 50").fetchall()
    courses = conn.execute(
        """
        SELECT c.course_id, c.course_name, c.credits, c.faculty_id, f.name AS faculty_name
        FROM courses c
        LEFT JOIN faculty f ON f.faculty_id = c.faculty_id
        ORDER BY c.course_id
        LIMIT 50
        """
    ).fetchall()
    departments = conn.execute("SELECT DISTINCT department FROM students WHERE department IS NOT NULL ORDER BY department").fetchall()
    announcements = get_announcements("admin")
    conn.close()
    return render_template(
        "admin.html",
        user=session["user"],
        stats=stats,
        students=students,
        faculty=faculty,
        courses=courses,
        departments=departments,
        announcements=announcements,
        filters={"q": search, "department": department},
        message=current_message(),
    )


@app.post("/api/chat")
@login_required()
def chat_api():
    data = request.get_json(silent=True) or {}
    question = (data.get("question") or "").strip()

    if not question:
        return jsonify({"error": "Please type a question first."}), 400
    if len(question) > 500:
        return jsonify({"error": "Please keep the question under 500 characters."}), 400

    try:
        result = ask_university_assistant(question, session["user"])
        # Save chat history in session for the duration of the user's session
        session.setdefault("chat_history", [])
        session["chat_history"].append({
            "question": question,
            "answer": result.get("answer"),
            "sql": result.get("sql"),
            "rows": result.get("rows"),
        })
        return jsonify({"answer": result["answer"], "rows": result["rows"], "sql": result.get("sql")})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 400
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    except Exception as exc:
        # Log unexpected exceptions for later diagnosis
        logger.exception("Unhandled error in chat_api")
        message = str(exc).lower()
        if "connection" in message or "network" in message:
            return jsonify({"error": "Groq could not be reached. Check your internet connection and API access."}), 502
        if "api key" in message or "authentication" in message:
            return jsonify({"error": "Groq API key is missing or invalid. Check GROQ_API_KEY in .env."}), 400
        return jsonify({"error": "The assistant could not answer that right now."}), 500


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.post("/faculty/records/update")
@login_required("faculty")
def update_faculty_record():
    linked_id = session["user"]["linked_id"]
    course_id = request.form.get("course_id")
    student_id = request.form.get("student_id")
    marks = request.form.get("marks")
    attendance = request.form.get("attendance")
    conn = get_db()
    owns_course = conn.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND faculty_id=?",
        (course_id, linked_id),
    ).fetchone()
    if not owns_course:
        conn.close()
        return flash_redirect("faculty_dashboard", "You can only update your assigned courses.")

    existing_mark = conn.execute(
        "SELECT mark_id FROM marks WHERE student_id=? AND course_id=?",
        (student_id, course_id),
    ).fetchone()
    if existing_mark:
        conn.execute("UPDATE marks SET marks=? WHERE mark_id=?", (marks or None, existing_mark["mark_id"]))
    else:
        conn.execute(
            "INSERT INTO marks(student_id, course_id, marks) VALUES (?, ?, ?)",
            (student_id, course_id, marks or None),
        )

    existing_attendance = conn.execute(
        "SELECT attendance_id FROM attendance WHERE student_id=? AND course_id=?",
        (student_id, course_id),
    ).fetchone()
    if existing_attendance:
        conn.execute(
            "UPDATE attendance SET attendance_percentage=? WHERE attendance_id=?",
            (attendance or None, existing_attendance["attendance_id"]),
        )
    else:
        conn.execute(
            "INSERT INTO attendance(student_id, course_id, attendance_percentage) VALUES (?, ?, ?)",
            (student_id, course_id, attendance or None),
        )
    conn.commit()
    conn.close()
    logger.info(
        "Faculty %s updated record for student %s in course %s (marks=%s, attendance=%s)",
        session["user"]["username"],
        student_id,
        course_id,
        marks,
        attendance,
    )
    return flash_redirect("faculty_dashboard", "Record updated.")


@app.get('/faculty/course/<int:course_id>/students')
@login_required('faculty')
def faculty_course_students(course_id):
    linked_id = session["user"]["linked_id"]
    conn = get_db()
    owns = conn.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND faculty_id=?",
        (course_id, linked_id),
    ).fetchone()
    if not owns:
        conn.close()
        return jsonify({"error": "You do not have access to that course."}), 403

    rows = conn.execute(
        """
        SELECT s.student_id, s.name, s.department, m.marks, a.attendance_percentage
        FROM students s
        LEFT JOIN marks m ON m.student_id = s.student_id AND m.course_id = ?
        LEFT JOIN attendance a ON a.student_id = s.student_id AND a.course_id = ?
        WHERE m.course_id IS NOT NULL OR a.course_id IS NOT NULL
        ORDER BY s.name
        """,
        (course_id, course_id),
    ).fetchall()
    conn.close()
    return jsonify({"students": [dict(r) for r in rows]})


@app.get('/faculty/course/<int:course_id>/summary')
@login_required('faculty')
def faculty_course_summary(course_id):
    linked_id = session["user"]["linked_id"]
    threshold = float(request.args.get("threshold", 50))
    conn = get_db()
    owns = conn.execute(
        "SELECT 1 FROM courses WHERE course_id=? AND faculty_id=?",
        (course_id, linked_id),
    ).fetchone()
    if not owns:
        conn.close()
        return jsonify({"error": "You do not have access to that course."}), 403

    summary = conn.execute(
        """
        SELECT
            ROUND(AVG(m.marks), 1) AS avg_marks,
            ROUND(AVG(a.attendance_percentage), 1) AS avg_attendance
        FROM marks m
        LEFT JOIN attendance a ON a.student_id = m.student_id AND a.course_id = m.course_id
        WHERE m.course_id = ?
        """,
        (course_id,),
    ).fetchone()

    low_performers = conn.execute(
        """
        SELECT s.student_id, s.name, m.marks, a.attendance_percentage
        FROM marks m
        JOIN students s ON s.student_id = m.student_id
        LEFT JOIN attendance a ON a.student_id = s.student_id AND a.course_id = m.course_id
        WHERE m.course_id = ? AND (m.marks < ? OR a.attendance_percentage < 75)
        ORDER BY m.marks ASC
        LIMIT 50
        """,
        (course_id, threshold),
    ).fetchall()

    conn.close()
    return jsonify({
        "avg_marks": summary["avg_marks"],
        "avg_attendance": summary["avg_attendance"],
        "low_performers": [dict(r) for r in low_performers],
    })


@app.post("/admin/students")
@login_required("admin")
def save_student():
    form = request.form
    conn = get_db()
    student_id = form.get("student_id")
    values = (
        form.get("name", "").strip(),
        form.get("age") or None,
        form.get("gender", "").strip() or None,
        form.get("department", "").strip(),
        form.get("semester") or None,
    )
    if student_id:
        conn.execute(
            "UPDATE students SET name=?, age=?, gender=?, department=?, semester=? WHERE student_id=?",
            values + (student_id,),
        )
        message = "Student updated."
    else:
        conn.execute(
            "INSERT INTO students(name, age, gender, department, semester) VALUES (?, ?, ?, ?, ?)",
            values,
        )
        message = "Student added."
    conn.commit()
    conn.close()
    return flash_redirect("admin_dashboard", message)


@app.post("/admin/faculty")
@login_required("admin")
def save_faculty():
    form = request.form
    conn = get_db()
    faculty_id = form.get("faculty_id")
    values = (
        form.get("name", "").strip(),
        form.get("department", "").strip(),
        form.get("designation", "").strip(),
        form.get("salary") or 0,
    )
    if faculty_id:
        conn.execute(
            "UPDATE faculty SET name=?, department=?, designation=?, salary=? WHERE faculty_id=?",
            values + (faculty_id,),
        )
        message = "Faculty updated."
    else:
        conn.execute(
            "INSERT INTO faculty(name, department, designation, salary) VALUES (?, ?, ?, ?)",
            values,
        )
        message = "Faculty added."
    conn.commit()
    conn.close()
    return flash_redirect("admin_dashboard", message)


@app.post("/admin/courses")
@login_required("admin")
def save_course():
    form = request.form
    conn = get_db()
    course_id = form.get("course_id")
    values = (
        form.get("course_name", "").strip(),
        form.get("faculty_id") or None,
        form.get("credits") or 0,
    )
    if course_id:
        conn.execute(
            "UPDATE courses SET course_name=?, faculty_id=?, credits=? WHERE course_id=?",
            values + (course_id,),
        )
        message = "Course updated."
    else:
        conn.execute(
            "INSERT INTO courses(course_name, faculty_id, credits) VALUES (?, ?, ?)",
            values,
        )
        message = "Course added."
    conn.commit()
    conn.close()
    return flash_redirect("admin_dashboard", message)


@app.post("/admin/announcements")
@login_required("admin")
def save_announcement():
    conn = get_db()
    conn.execute(
        "INSERT INTO announcements(title, body, audience) VALUES (?, ?, ?)",
        (
            request.form.get("title", "").strip(),
            request.form.get("body", "").strip(),
            request.form.get("audience", "all"),
        ),
    )
    conn.commit()
    conn.close()
    return flash_redirect("admin_dashboard", "Announcement posted.")


@app.post('/admin/assign_course')
@login_required('admin')
def admin_assign_course():
    form = request.form
    course_id = form.get('course_id')
    faculty_id = form.get('faculty_id') or None
    if not course_id:
        return flash_redirect('admin_dashboard', 'Course id required.')
    conn = get_db()
    conn.execute('UPDATE courses SET faculty_id=? WHERE course_id=?', (faculty_id, course_id))
    conn.commit()
    conn.close()
    logger.info('Admin %s assigned faculty %s to course %s', session['user']['username'], faculty_id, course_id)
    return flash_redirect('admin_dashboard', 'Course assignment updated.')


@app.get('/admin/users.json')
@login_required('admin')
def admin_users_json():
    conn = get_db()
    rows = conn.execute('SELECT user_id, username, role, linked_id FROM users ORDER BY user_id').fetchall()
    conn.close()
    return jsonify({'users': [dict(r) for r in rows]})


@app.post('/admin/users')
@login_required('admin')
def admin_save_user():
    try:
        user = create_user_admin(request.form)
        logger.info('Admin %s created/updated user %s (role=%s)', session['user']['username'], user['username'], user['role'])
        return flash_redirect('admin_dashboard', 'User saved.')
    except ValueError as exc:
        return flash_redirect('admin_dashboard', str(exc))


@app.post('/admin/users/delete/<int:user_id>')
@login_required('admin')
def admin_delete_user(user_id):
    conn = get_db()
    conn.execute('DELETE FROM users WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    logger.info('Admin %s deleted user id %s', session['user']['username'], user_id)
    return flash_redirect('admin_dashboard', 'User deleted.')


@app.post("/admin/delete/<table>/<int:record_id>")
@login_required("admin")
def delete_record(table, record_id):
    allowed = {
        "students": ("students", "student_id"),
        "faculty": ("faculty", "faculty_id"),
        "courses": ("courses", "course_id"),
    }
    if table not in allowed:
        return flash_redirect("admin_dashboard", "That record type cannot be deleted.")
    db_table, key = allowed[table]
    conn = get_db()
    conn.execute(f"DELETE FROM {db_table} WHERE {key}=?", (record_id,))
    conn.commit()
    conn.close()
    return flash_redirect("admin_dashboard", "Record deleted.")


@app.get("/exports/<kind>.csv")
@login_required()
def export_csv(kind):
    conn = get_db()
    role = session["user"]["role"]
    linked_id = session["user"]["linked_id"]
    if kind == "students" and role == "admin":
        rows = conn.execute("SELECT * FROM students ORDER BY student_id").fetchall()
    elif kind == "courses":
        rows = conn.execute(
            """
            SELECT c.course_name, c.credits, f.name AS faculty
            FROM courses c LEFT JOIN faculty f ON f.faculty_id = c.faculty_id
            ORDER BY c.course_name
            """
        ).fetchall()
    elif kind == "student_report" and role == "student":
        rows = conn.execute(
            """
            SELECT c.course_name, c.credits, m.marks, a.attendance_percentage
            FROM courses c
            LEFT JOIN marks m ON m.course_id = c.course_id AND m.student_id=?
            LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id=?
            WHERE m.student_id IS NOT NULL OR a.student_id IS NOT NULL
            ORDER BY c.course_name
            """,
            (linked_id, linked_id),
        ).fetchall()
    elif kind == "faculty_report" and role == "faculty":
        rows = conn.execute(
            """
            SELECT c.course_name, s.name AS student, m.marks, a.attendance_percentage
            FROM courses c
            LEFT JOIN marks m ON m.course_id = c.course_id
            LEFT JOIN students s ON s.student_id = m.student_id
            LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id = s.student_id
            WHERE c.faculty_id=?
            ORDER BY c.course_name, s.name
            """,
            (linked_id,),
        ).fetchall()
    else:
        conn.close()
        return jsonify({"error": "Export not available for this role."}), 403
    conn.close()
    return csv_response(f"{kind}.csv", rows)


@app.post('/admin/import/marks')
@login_required('admin')
def import_marks():
    if 'file' not in request.files:
        return flash_redirect('admin_dashboard', 'No file uploaded.')
    file = request.files['file']
    try:
        stream = TextIOWrapper(file.stream, encoding='utf-8')
        reader = csv.DictReader(stream)
        conn = get_db()
        count = 0
        for row in reader:
            student_id = row.get('student_id')
            course_id = row.get('course_id')
            marks = row.get('marks')
            if not student_id or not course_id:
                continue
            existing = conn.execute('SELECT mark_id FROM marks WHERE student_id=? AND course_id=?', (student_id, course_id)).fetchone()
            if existing:
                conn.execute('UPDATE marks SET marks=? WHERE mark_id=?', (marks or None, existing['mark_id']))
            else:
                conn.execute('INSERT INTO marks(student_id, course_id, marks) VALUES (?, ?, ?)', (student_id, course_id, marks or None))
            count += 1
        conn.commit()
        conn.close()
        logger.info('Imported %s marks from CSV by admin %s', count, session['user']['username'])
        return flash_redirect('admin_dashboard', f'Imported {count} marks.')
    except Exception as exc:
        logger.exception('Failed to import marks CSV')
        return flash_redirect('admin_dashboard', 'Failed to import marks CSV.')


@app.post('/admin/import/attendance')
@login_required('admin')
def import_attendance():
    if 'file' not in request.files:
        return flash_redirect('admin_dashboard', 'No file uploaded.')
    file = request.files['file']
    try:
        stream = TextIOWrapper(file.stream, encoding='utf-8')
        reader = csv.DictReader(stream)
        conn = get_db()
        count = 0
        for row in reader:
            student_id = row.get('student_id')
            course_id = row.get('course_id')
            attendance = row.get('attendance_percentage')
            if not student_id or not course_id:
                continue
            existing = conn.execute('SELECT attendance_id FROM attendance WHERE student_id=? AND course_id=?', (student_id, course_id)).fetchone()
            if existing:
                conn.execute('UPDATE attendance SET attendance_percentage=? WHERE attendance_id=?', (attendance or None, existing['attendance_id']))
            else:
                conn.execute('INSERT INTO attendance(student_id, course_id, attendance_percentage) VALUES (?, ?, ?)', (student_id, course_id, attendance or None))
            count += 1
        conn.commit()
        conn.close()
        logger.info('Imported %s attendance rows from CSV by admin %s', count, session['user']['username'])
        return flash_redirect('admin_dashboard', f'Imported {count} attendance rows.')
    except Exception as exc:
        logger.exception('Failed to import attendance CSV')
        return flash_redirect('admin_dashboard', 'Failed to import attendance CSV.')


@app.get('/search/students.json')
@login_required('admin')
def search_students_json():
    q = request.args.get('q', '').strip()
    department = request.args.get('department', '').strip()
    sort = request.args.get('sort', 'student_id')
    order = request.args.get('order', 'asc').lower()
    allowed_sorts = {'student_id', 'name', 'department', 'semester'}
    if sort not in allowed_sorts:
        sort = 'student_id'
    if order not in {'asc', 'desc'}:
        order = 'asc'
    where = []
    params = []
    if q:
        where.append('name LIKE ?')
        params.append(f'%{q}%')
    if department:
        where.append('department=?')
        params.append(department)
    filter_sql = 'WHERE ' + ' AND '.join(where) if where else ''
    conn = get_db()
    rows = conn.execute(f'SELECT * FROM students {filter_sql} ORDER BY {sort} {order} LIMIT 200', params).fetchall()
    conn.close()
    return jsonify({'students': [dict(r) for r in rows]})


@app.get('/exports/marks.csv')
@login_required()
def export_marks_by_course():
    course_id = request.args.get('course_id')
    if not course_id:
        return jsonify({'error': 'course_id is required'}), 400
    role = session['user']['role']
    linked_id = session['user']['linked_id']
    conn = get_db()
    # faculty may only export their courses
    if role == 'faculty':
        owns = conn.execute('SELECT 1 FROM courses WHERE course_id=? AND faculty_id=?', (course_id, linked_id)).fetchone()
        if not owns:
            conn.close()
            return jsonify({'error': 'Access denied'}), 403
    rows = conn.execute(
        '''
        SELECT s.student_id, s.name, m.marks
        FROM students s
        LEFT JOIN marks m ON m.student_id = s.student_id AND m.course_id = ?
        WHERE m.course_id IS NOT NULL
        ORDER BY s.name
        ''',
        (course_id,),
    ).fetchall()
    conn.close()
    return csv_response(f'marks-course-{course_id}.csv', rows)


@app.get("/reports/student.pdf")
@login_required("student")
def student_pdf_report():
    linked_id = session["user"]["linked_id"]
    conn = get_db()
    student = conn.execute("SELECT * FROM students WHERE student_id=?", (linked_id,)).fetchone()
    rows = conn.execute(
        """
        SELECT c.course_name, m.marks, a.attendance_percentage
        FROM courses c
        LEFT JOIN marks m ON m.course_id = c.course_id AND m.student_id=?
        LEFT JOIN attendance a ON a.course_id = c.course_id AND a.student_id=?
        WHERE m.student_id IS NOT NULL OR a.student_id IS NOT NULL
        ORDER BY c.course_name
        """,
        (linked_id, linked_id),
    ).fetchall()

    mark_values = [r["marks"] for r in rows if r["marks"] is not None]
    attendance_values = [r["attendance_percentage"] for r in rows if r["attendance_percentage"] is not None]
    average_marks = round(sum(mark_values) / len(mark_values), 1) if mark_values else None
    average_attendance = round(sum(attendance_values) / len(attendance_values), 1) if attendance_values else None
    gpa = round((average_marks / 100.0) * 4.0, 2) if average_marks is not None else None
    best_course = max([r for r in rows if r["marks"] is not None], key=lambda x: x["marks"]) if mark_values else None
    weakest_course = min([r for r in rows if r["marks"] is not None], key=lambda x: x["marks"]) if mark_values else None
    low_attendance = [r for r in rows if r["attendance_percentage"] is not None and r["attendance_percentage"] < 75]

    conn.close()

    lines = [
        f"Student: {student['name'] if student else session['user']['username']}",
        f"Department: {student['department'] if student else '-'}",
        f"Semester: {student['semester'] if student else '-'}",
        "",
    ]
    lines.append(f"Average Marks: {average_marks if average_marks is not None else '-'}")
    lines.append(f"Average Attendance: {average_attendance if average_attendance is not None else '-'}%")
    lines.append(f"Estimated GPA (4.0 scale): {gpa if gpa is not None else '-'}")
    if best_course:
        lines.append(f"Best Subject: {best_course['course_name']} ({best_course['marks']})")
    if weakest_course:
        lines.append(f"Weakest Subject: {weakest_course['course_name']} ({weakest_course['marks']})")
    if low_attendance:
        lines.append("")
        lines.append("Attendance Warnings:")
        for r in low_attendance:
            lines.append(f" - {r['course_name']}: {r['attendance_percentage']}%")

    lines.append("")
    lines.append("Detailed Scores:")
    for row in rows:
        lines.append(f"{row['course_name']}: Marks {row['marks']}, Attendance {row['attendance_percentage']}%")

    return simple_pdf_response("student-report.pdf", "Student Report Card", lines)


@app.get('/reports/faculty/<int:course_id>.pdf')
@login_required('faculty')
def faculty_course_pdf(course_id):
    linked_id = session['user']['linked_id']
    conn = get_db()
    owns = conn.execute('SELECT course_name FROM courses WHERE course_id=? AND faculty_id=?', (course_id, linked_id)).fetchone()
    if not owns:
        conn.close()
        return redirect(url_for('faculty_dashboard'))

    course_name = owns['course_name']
    rows = conn.execute(
        """
        SELECT s.student_id, s.name, m.marks, a.attendance_percentage
        FROM students s
        LEFT JOIN marks m ON m.student_id = s.student_id AND m.course_id = ?
        LEFT JOIN attendance a ON a.student_id = s.student_id AND a.course_id = ?
        WHERE m.course_id IS NOT NULL OR a.course_id IS NOT NULL
        ORDER BY s.name
        """,
        (course_id, course_id),
    ).fetchall()

    avg_marks = conn.execute('SELECT ROUND(AVG(marks),1) AS avg_marks FROM marks WHERE course_id=?', (course_id,)).fetchone()["avg_marks"]
    avg_att = conn.execute('SELECT ROUND(AVG(attendance_percentage),1) AS avg_att FROM attendance WHERE course_id=?', (course_id,)).fetchone()["avg_att"]
    conn.close()

    lines = [
        f"Course: {course_name}",
        f"Average Marks: {avg_marks if avg_marks is not None else '-'}",
        f"Average Attendance: {avg_att if avg_att is not None else '-'}%",
        "",
        "Students:",
    ]
    for r in rows:
        lines.append(f"{r['name']} (ID {r['student_id']}): Marks {r['marks']}, Attendance {r['attendance_percentage']}%")

    return simple_pdf_response(f"course-{course_id}-report.pdf", f"Course Report - {course_name}", lines)


@app.get('/reports/admin/departments.csv')
@login_required('admin')
def admin_departments_csv():
    conn = get_db()
    rows = conn.execute(
        """
        SELECT s.department,
               COUNT(s.student_id) AS student_count,
               ROUND(AVG(m.marks),1) AS avg_marks,
               ROUND(AVG(a.attendance_percentage),1) AS avg_attendance
        FROM students s
        LEFT JOIN marks m ON m.student_id = s.student_id
        LEFT JOIN attendance a ON a.student_id = s.student_id
        GROUP BY s.department
        ORDER BY s.department
        """,
    ).fetchall()
    conn.close()
    return csv_response('departments-summary.csv', rows)


if __name__ == "__main__":
    app.run(debug=True)
