import os
import sqlite3

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

from config import load_env_file

try:
    from groq import Groq
except ImportError:
    Groq = None

if load_dotenv:
    load_dotenv()
else:
    load_env_file()

DB_PATH = "university.db"
MAX_QUESTION_LENGTH = 500
MAX_RESULT_ROWS = 25
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")


def _get_client():
    if Groq is None:
        raise RuntimeError("The groq package is not installed.")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is missing in .env.")

    return Groq(api_key=api_key)


def _clean_sql(sql_query):
    sql_query = sql_query.replace("```sql", "").replace("```", "").strip()
    sql_query = sql_query.rstrip(";").strip()

    if ";" in sql_query:
        raise ValueError("Only one read-only question can be answered at a time.")

    first_word = sql_query.split(None, 1)[0].lower() if sql_query else ""
    if first_word not in {"select", "with"}:
        raise ValueError("Only read-only SELECT questions are allowed.")

    blocked_words = {
        "insert",
        "update",
        "delete",
        "drop",
        "alter",
        "create",
        "replace",
        "pragma",
        "attach",
        "detach",
    }
    lowered = f" {sql_query.lower()} "
    if any(f" {word} " in lowered for word in blocked_words):
        raise ValueError("That question generated unsafe SQL.")

    return sql_query


def _query_database(sql_query, user=None):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    role = (user or {}).get("role", "guest")
    linked_id = (user or {}).get("linked_id")
    lowered = sql_query.lower()

    # Simple role-based restrictions to avoid leaking private data.
    if role == "student":
        # Students may only query their own profile/marks/attendance.
        if any(x in lowered for x in ("students", "marks", "attendance")):
            if not linked_id or str(linked_id) not in lowered:
                raise ValueError(
                    "Students may only query their own records. Please include your student_id filter in the question."
                )

    if role == "faculty":
        # Faculty may only query marks/attendance for courses they teach.
        if any(x in lowered for x in ("marks", "attendance", "students")):
            cursor.execute("SELECT course_id FROM courses WHERE faculty_id=?", (linked_id,))
            allowed = {str(r[0]) for r in cursor.fetchall()}
            if not allowed:
                raise ValueError("You are not assigned to any courses.")
            # If SQL references numeric course ids, ensure they're within allowed set.
            import re

            found_nums = set(re.findall(r"\b(\d+)\b", lowered))
            if found_nums and not (found_nums & allowed):
                raise ValueError("Faculty queries must be scoped to your assigned course IDs.")

    cursor.execute(sql_query)
    rows = [dict(row) for row in cursor.fetchmany(MAX_RESULT_ROWS)]
    conn.close()
    return rows


def ask_university_assistant(question, user=None):
    question = (question or "").strip()
    if not question:
        raise ValueError("Please enter a question.")
    if len(question) > MAX_QUESTION_LENGTH:
        raise ValueError("Please keep the question under 500 characters.")

    client = _get_client()
    user = user or {}
    role = user.get("role", "guest")
    linked_id = user.get("linked_id")

    access_policy = "The user may ask general questions about university data."
    if role == "student":
        access_policy = (
            f"The user is a student with student_id {linked_id}. "
            "For students, only reveal their own profile, marks, and attendance. "
            "They may also ask general course and faculty questions."
        )
    elif role == "faculty":
        access_policy = (
            f"The user is faculty with faculty_id {linked_id}. "
            "For faculty, only reveal detailed marks or attendance for students in courses assigned to this faculty. "
            "They may ask general course, student count, and department questions."
        )
    elif role == "admin":
        access_policy = "The user is an admin and can query all university data."

    prompt = f"""
You are an expert SQLite SQL generator.

DATABASE SCHEMA:

students(student_id, name, age, gender, department, semester)

faculty(faculty_id, name, department, designation, salary)

courses(course_id, course_name, faculty_id, credits)

marks(mark_id, student_id, course_id, marks)

attendance(attendance_id, student_id, course_id, attendance_percentage)

administration(admin_id, name, role, salary)

Convert the user's question into ONLY executable SQLite SQL.
Use only SELECT statements.
Use DISTINCT when selecting names or repeated rows.
Prefer joins when a question asks for names instead of IDs.
Limit broad result sets to {MAX_RESULT_ROWS} rows.
Access policy:
{access_policy}
If the user asks something unrelated to the schema, return:
SELECT 'I can answer questions about students, faculty, courses, marks, attendance, and administration.' AS message

User Question:
{question}

Return ONLY SQL.
"""

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )

    sql_query = _clean_sql(response.choices[0].message.content)
    rows = _query_database(sql_query, user)

    answer_prompt = f"""
You are a university assistant.

User Question:
{question}

Database Result:
{rows}

Generate a professional and natural language answer.

Do not mention SQL.
Do not mention database.
Answer directly.
"""

    answer_response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[{"role": "user", "content": answer_prompt}],
        temperature=0,
    )

    return {
        "answer": answer_response.choices[0].message.content,
        "sql": sql_query,
        "rows": rows,
    }


if __name__ == "__main__":
    print("\nUniversity AI Assistant Started\n")
    while True:
        question = input("Ask Question: ")
        try:
            result = ask_university_assistant(question)
            print("\nAnswer:")
            print(result["answer"])
        except Exception as exc:
            print("\nError:")
            print(exc)
