# ========================================
# Multi-stage Dockerfile for FastAPI Backend
# Python 3.10 + OpenAI + OCR + PDF Processing
# ========================================

FROM python:3.10-slim AS base

# Set working directory
WORKDIR /app

# Install system dependencies for OCR and PDF processing
# - poppler-utils: Required for pdf2image (PDF to image conversion)
# - tesseract-ocr: Fallback OCR engine with multi-language support
# - tesseract-ocr-hin: Hindi language data
# - tesseract-ocr-eng: English language data (default)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    tesseract-ocr \
    tesseract-ocr-hin \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p vendors uploads temp_uploads data

# Expose port (FastAPI runs on 8001 in production)
EXPOSE 8001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8001/health')" || exit 1

# Run with uvicorn (4 workers for production)
# Use gunicorn config for better production management
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "4"]
