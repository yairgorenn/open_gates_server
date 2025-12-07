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

# Expose port 80 (Railway will route traffic here)
EXPOSE 80

# Start Gunicorn on port 80
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:80", "--workers", "1"]
