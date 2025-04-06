FROM python:3.8-slim

# Install system dependencies
RUN apt-get update && apt-get install -y ffmpeg git && apt-get clean

# Create app directories
WORKDIR /app
RUN mkdir -p uploads outputs

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install werkzeug==2.2.3  # fix for url_quote issue

# Copy app code
COPY . .

# Expose port Railway uses
EXPOSE 5000

# Run server
CMD ["python", "app.py"]
