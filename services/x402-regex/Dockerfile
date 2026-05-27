FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

EXPOSE 3059
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3059", "--proxy-headers", "--forwarded-allow-ips=*"]
