FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir "psycopg[binary]"

ENV PYTHONPATH=/app

CMD ["python", "--version"]