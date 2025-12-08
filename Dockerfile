# Base image
FROM python:3.11-slim

# Work directory
WORKDIR /app

# Make Python print logs immediately
ENV PYTHONUNBUFFERED=1

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . .

# Railway sets PORT automatically — expose it
EXPOSE 8000

# Run Flask app using the environment PORT given by Railway
CMD ["python", "app.py"]
