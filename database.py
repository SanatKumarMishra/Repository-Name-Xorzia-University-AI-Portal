import sqlite3
from werkzeug.security import generate_password_hash

DB_PATH = "university.db"


def init_database(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users(
        user_id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        linked_id INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS students(
        student_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        age INTEGER,
        gender TEXT,
        department TEXT,
        semester INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS faculty(
        faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        department TEXT,
        designation TEXT,
        salary INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS courses(
        course_id INTEGER PRIMARY KEY AUTOINCREMENT,
        course_name TEXT,
        faculty_id INTEGER,
        credits INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS marks(
        mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        course_id INTEGER,
        marks INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS attendance(
        attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        course_id INTEGER,
        attendance_percentage REAL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS administration(
        admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        role TEXT,
        salary INTEGER
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS announcements(
        announcement_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT NOT NULL,
        audience TEXT NOT NULL DEFAULT 'all',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS events(
        event_id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body TEXT,
        audience TEXT NOT NULL DEFAULT 'all',
        event_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
        """)
    
    seed_users = [
        (1, "admin", "admin123", "admin", 1),
        (2, "student", "student123", "student", 1),
        (3, "faculty", "faculty123", "faculty", 1),
        (101, "rahul", "rahul123", "student", 101),
        (102, "priya", "priya123", "student", 102),
        (103, "mehta", "mehta123", "faculty", 101),
        (104, "nisha", "nisha123", "faculty", 102),
    ]

    hashed_users = seed_users

    cursor.executemany(
        """
        INSERT OR IGNORE INTO users
        (user_id, username, password, role, linked_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        hashed_users,
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO students
        (student_id, name, age, gender, department, semester)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, "Rahul Sharma", 20, "Male", "CSE", 4),
            (2, "Priya Singh", 21, "Female", "ECE", 6),
            (3, "Aman Verma", 19, "Male", "CSE", 2),
            (101, "Rohan Das", 20, "Male", "CSE", 4),
            (102, "Isha Menon", 21, "Female", "ECE", 6),
            (103, "Kabir Malhotra", 19, "Male", "CSE", 2),
            (104, "Sara Khan", 22, "Female", "Medicine", 8),
            (105, "Neha Kapoor", 20, "Female", "Nursing", 4),
            (106, "Arjun Rao", 23, "Male", "Pharmacy", 7),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO faculty
        (faculty_id, name, department, designation, salary)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "Dr. Mehta", "CSE", "Professor", 120000),
            (2, "Dr. Sharma", "ECE", "Associate Professor", 95000),
            (101, "Dr. Leena Menon", "CSE", "Professor", 120000),
            (102, "Dr. Nisha Rao", "Medicine", "Professor", 135000),
            (103, "Dr. Vikram Sen", "Nursing", "Assistant Professor", 88000),
            (104, "Dr. Kavya Iyer", "Pharmacy", "Associate Professor", 98000),
            (105, "Dr. Arvind Bose", "ECE", "Professor", 115000),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO events
        (event_id, title, body, audience, event_date)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, "Midterm Exams", "Midterm exam week starts next month.", "all", "2026-07-15"),
            (2, "Department Meeting", "CSE department meeting for faculty.", "faculty", "2026-07-01"),
        ],
    )

    cursor.executemany(
        """
        UPDATE students
        SET name=?, age=?, gender=?, department=?, semester=?
        WHERE student_id=?
        """,
        [
            ("Rohan Das", 20, "Male", "CSE", 4, 101),
            ("Isha Menon", 21, "Female", "ECE", 6, 102),
            ("Kabir Malhotra", 19, "Male", "CSE", 2, 103),
            ("Sara Khan", 22, "Female", "Medicine", 8, 104),
            ("Neha Kapoor", 20, "Female", "Nursing", 4, 105),
            ("Arjun Rao", 23, "Male", "Pharmacy", 7, 106),
        ],
    )

    cursor.executemany(
        """
        UPDATE faculty
        SET name=?, department=?, designation=?, salary=?
        WHERE faculty_id=?
        """,
        [
            ("Dr. Leena Menon", "CSE", "Professor", 120000, 101),
            ("Dr. Nisha Rao", "Medicine", "Professor", 135000, 102),
            ("Dr. Vikram Sen", "Nursing", "Assistant Professor", 88000, 103),
            ("Dr. Kavya Iyer", "Pharmacy", "Associate Professor", 98000, 104),
            ("Dr. Arvind Bose", "ECE", "Professor", 115000, 105),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO courses
        (course_id, course_name, faculty_id, credits)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, "Data Structures", 1, 4),
            (2, "Digital Electronics", 2, 3),
            (101, "Advanced Data Structures", 101, 4),
            (102, "Database Management Systems", 101, 4),
            (103, "Digital Electronics", 105, 3),
            (104, "Human Anatomy", 102, 5),
            (105, "Clinical Nursing", 103, 4),
            (106, "Pharmacology", 104, 4),
            (107, "Medical Ethics", 102, 2),
        ],
    )

    cursor.executemany(
        """
        UPDATE courses
        SET course_name=?, faculty_id=?, credits=?
        WHERE course_id=?
        """,
        [
            ("Advanced Data Structures", 101, 4, 101),
            ("Database Management Systems", 101, 4, 102),
            ("Digital Electronics", 105, 3, 103),
            ("Human Anatomy", 102, 5, 104),
            ("Clinical Nursing", 103, 4, 105),
            ("Pharmacology", 104, 4, 106),
            ("Medical Ethics", 102, 2, 107),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO marks
        (mark_id, student_id, course_id, marks)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, 1, 1, 88),
            (2, 2, 2, 91),
            (3, 3, 1, 76),
            (101, 101, 101, 88),
            (102, 101, 102, 84),
            (103, 102, 103, 91),
            (104, 103, 101, 76),
            (105, 103, 102, 81),
            (106, 104, 104, 89),
            (107, 104, 107, 93),
            (108, 105, 105, 86),
            (109, 106, 106, 78),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO attendance
        (attendance_id, student_id, course_id, attendance_percentage)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, 1, 1, 92.5),
            (2, 2, 2, 88.0),
            (3, 3, 1, 79.5),
            (101, 101, 101, 92.5),
            (102, 101, 102, 89.0),
            (103, 102, 103, 88.0),
            (104, 103, 101, 79.5),
            (105, 103, 102, 83.0),
            (106, 104, 104, 95.0),
            (107, 104, 107, 90.5),
            (108, 105, 105, 87.0),
            (109, 106, 106, 82.0),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO administration
        (admin_id, name, role, salary)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, "Mr. Sinha", "Registrar", 110000),
            (2, "Mrs. Kapoor", "Accountant", 75000),
            (101, "Mr. Sinha", "Registrar", 110000),
            (102, "Mrs. Kapoor", "Accountant", 75000),
            (103, "Anita Desai", "Admissions Officer", 68000),
            (104, "Rohan Malhotra", "Examination Controller", 90000),
            (105, "Fatima Sheikh", "Library Director", 72000),
        ],
    )

    cursor.executemany(
        """
        INSERT OR IGNORE INTO announcements
        (announcement_id, title, body, audience)
        VALUES (?, ?, ?, ?)
        """,
        [
            (1, "Semester review", "Check your marks and attendance before the final review window closes.", "student"),
            (2, "Faculty update", "Please update pending marks and attendance records for assigned courses.", "faculty"),
            (3, "Admin notice", "Use the management panel to keep student, faculty, and course records current.", "admin"),
        ],
    )

    # Remove exact duplicate rows left by earlier seed scripts.
    cursor.execute("DELETE FROM marks WHERE mark_id IN (4, 5, 6)")
    cursor.execute("DELETE FROM attendance WHERE attendance_id IN (4, 5, 6)")
    cursor.execute("DELETE FROM courses WHERE course_id IN (3, 4)")
    cursor.execute("DELETE FROM faculty WHERE faculty_id IN (3, 4)")
    cursor.execute("DELETE FROM students WHERE student_id IN (4, 5, 6)")
    cursor.execute("DELETE FROM administration WHERE admin_id IN (3, 4)")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_database()
    print("Database created successfully.")
