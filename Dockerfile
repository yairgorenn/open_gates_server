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

# ---- שינוי קריטי 2: הפעלת מצב Debug ----
# הוספתי --log-level debug וגם הדפסה מפורשת של שגיאות
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --log-level debug --access-logfile - --error-logfile -