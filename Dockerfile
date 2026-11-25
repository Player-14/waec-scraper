FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Automatically install all required system dependencies for Chromium
RUN playwright install-deps chromium
RUN playwright install chromium

COPY . .

CMD ["python", "scraper.py"]