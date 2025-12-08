# Base image
FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway exposes dynamic port — just declare it
EXPOSE 8080

# Run gunicorn instead of Flask dev server
CMD ["gunicorn", "-b", "0.0.0.0:${PORT}", "app:app"]
