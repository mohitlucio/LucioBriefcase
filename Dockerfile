FROM python:3.11-slim

WORKDIR /app

# Install curl for HTTP/2 download fallback used by some scrapers
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CLOUD=1
ENV PYTHONUNBUFFERED=1
ENV PORT=7860
EXPOSE 7860

CMD ["python", "backend/server.py"]
