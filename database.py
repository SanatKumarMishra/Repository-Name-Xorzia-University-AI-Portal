import sqlite3

conn = sqlite3.connect("university.db")

cursor = conn.cursor()

# STUDENTS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS students (
    student_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    age INTEGER,
    gender TEXT,
    department TEXT,
    semester INTEGER
)
""")

# FACULTY TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS faculty (
    faculty_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    department TEXT,
    designation TEXT,
    salary INTEGER
)
""")

# COURSES TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS courses (
    course_id INTEGER PRIMARY KEY AUTOINCREMENT,
    course_name TEXT,
    faculty_id INTEGER,
    credits INTEGER
)
""")

# MARKS TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS marks (
    mark_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    course_id INTEGER,
    marks INTEGER
)
""")

# ATTENDANCE TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER,
    course_id INTEGER,
    attendance_percentage REAL
)
""")

# ADMINISTRATION TABLE
cursor.execute("""
CREATE TABLE IF NOT EXISTS administration (
    admin_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    role TEXT,
    salary INTEGER
)
""")

# INSERT STUDENTS
cursor.execute("""
INSERT INTO students
(name, age, gender, department, semester)
VALUES
('Rahul Sharma', 20, 'Male', 'CSE', 4),
('Priya Singh', 21, 'Female', 'ECE', 6),
('Aman Verma', 19, 'Male', 'CSE', 2)
""")

# INSERT FACULTY
cursor.execute("""
INSERT INTO faculty
(name, department, designation, salary)
VALUES
('Dr. Mehta', 'CSE', 'Professor', 120000),
('Dr. Sharma', 'ECE', 'Associate Professor', 95000)
""")

# INSERT COURSES
cursor.execute("""
INSERT INTO courses
(course_name, faculty_id, credits)
VALUES
('Data Structures', 1, 4),
('Digital Electronics', 2, 3)
""")

# INSERT MARKS
cursor.execute("""
INSERT INTO marks
(student_id, course_id, marks)
VALUES
(1, 1, 88),
(2, 2, 91),
(3, 1, 76)
""")

# INSERT ATTENDANCE
cursor.execute("""
INSERT INTO attendance
(student_id, course_id, attendance_percentage)
VALUES
(1, 1, 92.5),
(2, 2, 88.0),
(3, 1, 79.5)
""")

# INSERT ADMINISTRATION
cursor.execute("""
INSERT INTO administration
(name, role, salary)
VALUES
('Mr. Sinha', 'Registrar', 110000),
('Mrs. Kapoor', 'Accountant', 75000)
""")

conn.commit()

print("🎓 University Database Created Successfully")