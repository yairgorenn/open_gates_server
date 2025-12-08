# Base image
FROM python:3.11-slim

# Work directory
WORKDIR /app

# ---- שינוי קריטי 1: חשיפת שגיאות מיידית ----
# זה יגרום לפייתון להדפיס שגיאות מיד ללוג ולא לשמור אותן
ENV PYTHONUNBUFFERED=1

# Copy requirements
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# --- השינוי: הרצה ישירה דרך פייתון ---
# זה מבטיח שהפורט ייקרא נכון דרך הקוד שלך ב-app.py
CMD ["python", "app.py", "--port=80"]