FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY ui ui
COPY data/sample_knowledge data/sample_knowledge
COPY data/sample_logs data/sample_logs
CMD ["uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
