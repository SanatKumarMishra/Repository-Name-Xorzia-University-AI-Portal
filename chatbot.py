import sqlite3
from groq import Groq

# ----------------------------
# GROQ API KEY
# ----------------------------
client = Groq(
    api_key="Insert_Groq_API_Key_Here"
)

# ----------------------------
# DATABASE CONNECTION
# ----------------------------
conn = sqlite3.connect("university.db")
cursor = conn.cursor()

print("\n🎓 University AI Assistant Started\n")

while True:

    question = input("Ask Question: ")

    # Prompt for SQL generation
    prompt = f"""
You are an expert SQLite SQL generator.

DATABASE SCHEMA:

students(student_id, name, age, gender, department, semester)

faculty(faculty_id, name, department, designation, salary)

courses(course_id, course_name, faculty_id, credits)

marks(mark_id, student_id, course_id, marks)

attendance(attendance_id, student_id, course_id, attendance_percentage)

administration(admin_id, name, role, salary)

Convert the user's question into ONLY a valid SQLite query.

User Question:
{question}

Return ONLY SQL.
"""

    try:

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0
        )

        sql_query = response.choices[0].message.content.strip()

        # cleanup
        sql_query = sql_query.replace("```sql", "")
        sql_query = sql_query.replace("```", "")
        sql_query = sql_query.strip()

        print("\nGenerated SQL:")
        print(sql_query)

        cursor.execute(sql_query)

        rows = cursor.fetchall()

        print("\nAnswer:")

        if len(rows) == 0:
            print("No records found.")

        else:
            for row in rows:
                print(row)

    except Exception as e:
        print("\nError:")
        print(e)