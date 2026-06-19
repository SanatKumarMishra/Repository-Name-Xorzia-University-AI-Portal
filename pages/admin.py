import streamlit as st
import sqlite3

st.title("🛠️ Admin Dashboard")

conn = sqlite3.connect("university.db")
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM students")
students = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM faculty")
faculty = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM courses")
courses = cursor.fetchone()[0]

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("👨‍🎓 Students", students)

with col2:
    st.metric("👨‍🏫 Faculty", faculty)

with col3:
    st.metric("📚 Courses", courses)