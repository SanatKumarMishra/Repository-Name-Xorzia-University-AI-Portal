import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash


def hash_password(password):
    return generate_password_hash(password)


def password_matches(stored_password, submitted_password):
    if not stored_password:
        return False
    if stored_password.startswith(("pbkdf2:", "scrypt:")):
        return check_password_hash(stored_password, submitted_password)
    return stored_password == submitted_password


def authenticate(username, password, role=None):
    conn = sqlite3.connect("university.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    params = [username]
    role_filter = ""

    if role:
        role_filter = "AND lower(role)=?"
        params.append(role.lower())

    cursor.execute(
        f"""
        SELECT user_id, username, password, role, linked_id
        FROM users
        WHERE username=?
        {role_filter}
        """,
        params,
    )

    result = cursor.fetchone()
    conn.close()

    if not result or not password_matches(result["password"], password):
        return None

    user = dict(result)
    user.pop("password", None)
    return user


def create_account(form):
    role = form.get("role", "").strip().lower()
    username = form.get("username", "").strip()
    password = form.get("password", "")
    name = form.get("name", "").strip()
    department = form.get("department", "").strip()

    if role not in {"student", "faculty"}:
        raise ValueError("Signup is available for student and faculty accounts only.")
    if not username or not password or not name or not department:
        raise ValueError("Please fill all required fields.")
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters.")

    conn = sqlite3.connect("university.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN")

        if role == "student":
            cursor.execute(
                """
                INSERT INTO students(name, age, gender, department, semester)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    name,
                    form.get("age") or None,
                    form.get("gender", "").strip() or None,
                    department,
                    form.get("semester") or None,
                ),
            )
            linked_id = cursor.lastrowid

            courses = cursor.execute(
                "SELECT course_id FROM courses ORDER BY course_id LIMIT 2"
            ).fetchall()
            for index, course in enumerate(courses):
                cursor.execute(
                    "INSERT INTO marks(student_id, course_id, marks) VALUES (?, ?, ?)",
                    (linked_id, course["course_id"], 82 + (index * 5)),
                )
                cursor.execute(
                    """
                    INSERT INTO attendance(student_id, course_id, attendance_percentage)
                    VALUES (?, ?, ?)
                    """,
                    (linked_id, course["course_id"], 91.0 - (index * 3)),
                )
        else:
            cursor.execute(
                """
                INSERT INTO faculty(name, department, designation, salary)
                VALUES (?, ?, ?, ?)
                """,
                (
                    name,
                    department,
                    form.get("designation", "").strip() or "Faculty",
                    0,
                ),
            )
            linked_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT INTO courses(course_name, faculty_id, credits)
                VALUES (?, ?, ?)
                """,
                (f"{department} Foundations", linked_id, 3),
            )

        cursor.execute(
            """
            INSERT INTO users(username, password, role, linked_id)
            VALUES (?, ?, ?, ?)
            """,
            (username, hash_password(password), role, linked_id),
        )
        user_id = cursor.lastrowid
        conn.commit()

        return {
            "user_id": user_id,
            "username": username,
            "role": role,
            "linked_id": linked_id,
        }
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        if "unique" in str(exc).lower():
            raise ValueError("That username is already taken.") from exc
        raise
    finally:
        conn.close()


def create_user_admin(form):
    """Create or update a user record from the admin panel.

    Expects form fields: username, password (optional for update), role, linked_id (optional).
    Role may be 'student', 'faculty', or 'admin'.
    """
    role = form.get("role", "").strip().lower()
    username = form.get("username", "").strip()
    password = form.get("password")
    linked_id = form.get("linked_id") or None

    if role not in {"student", "faculty", "admin"}:
        raise ValueError("Role must be student, faculty or admin.")
    if not username:
        raise ValueError("Username is required.")

    conn = sqlite3.connect("university.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        cursor.execute("BEGIN")
        existing = cursor.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
        if existing:
            # Update existing user
            if password:
                cursor.execute("UPDATE users SET password=?, role=?, linked_id=? WHERE username=?",
                               (hash_password(password), role, linked_id, username))
            else:
                cursor.execute("UPDATE users SET role=?, linked_id=? WHERE username=?",
                               (role, linked_id, username))
            user_id = existing["user_id"]
        else:
            if not password:
                raise ValueError("Password is required for new users.")
            cursor.execute(
                "INSERT INTO users(username, password, role, linked_id) VALUES (?, ?, ?, ?)",
                (username, hash_password(password), role, linked_id),
            )
            user_id = cursor.lastrowid

        conn.commit()
        return {"user_id": user_id, "username": username, "role": role, "linked_id": linked_id}
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        if "unique" in str(exc).lower():
            raise ValueError("That username is already taken.") from exc
        raise
    finally:
        conn.close()
