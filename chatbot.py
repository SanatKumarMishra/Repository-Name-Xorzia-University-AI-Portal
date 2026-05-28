import sqlite3

# CONNECT DATABASE
conn = sqlite3.connect("university.db")
cursor = conn.cursor()

print("\n🎓 University AI Assistant Started\n")

while True:

    question = input("Ask Question: ").lower()

    try:

        # SALARY QUERY
        if "salary" in question and "dr. mehta" in question:

            cursor.execute("""
            SELECT salary
            FROM faculty
            WHERE name='Dr. Mehta'
            """)

            result = cursor.fetchone()

            print("\nAnswer:")
            print(f"Dr. Mehta salary is ₹{result[0]}")

        # SHOW STUDENTS
        elif "show all students" in question:

            cursor.execute("""
            SELECT * FROM students
            """)

            results = cursor.fetchall()

            print("\nStudents:")

            for row in results:
                print(row)

        # ATTENDANCE
        elif "attendance" in question and "rahul" in question:

            cursor.execute("""
            SELECT attendance_percentage
            FROM attendance
            WHERE student_id=1
            """)

            result = cursor.fetchone()

            print("\nAnswer:")
            print(f"Rahul Sharma attendance is {result[0]}%")

        # DATA STRUCTURES FACULTY
        elif "data structures" in question:

            cursor.execute("""
            SELECT faculty.name
            FROM faculty
            JOIN courses
            ON faculty.faculty_id = courses.faculty_id
            WHERE courses.course_name='Data Structures'
            """)

            result = cursor.fetchone()

            print("\nAnswer:")
            print(f"Data Structures is taught by {result[0]}")

        else:

            print("\nSorry, question not understood.")

    except Exception as e:

        print("\nError:")
        print(e)