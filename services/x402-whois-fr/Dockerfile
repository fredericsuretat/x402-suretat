FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN apk upgrade --no-cache
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3038
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3038", "--proxy-headers", "--forwarded-allow-ips=*"]
