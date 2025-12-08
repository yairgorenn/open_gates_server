# Base image
FROM python:3.11-slim

# Work directory
WORKDIR /app

# Copy requirements
COPY requirements.txt ./

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all project files
COPY . .

# שינוי קריטי: לא חושפים פורט 80 קבוע, אלא משתמשים במשתנה הסביבה של Railway
# הפקודה CMD למטה תטפל בזה.

# Start Gunicorn
# שימוש בגרסת ה-Shell (ללא סוגריים מרובעים) כדי לאפשר קריאה של המשתנה $PORT
CMD gunicorn app:app --bind 0.0.0.0:$PORT --workers 1