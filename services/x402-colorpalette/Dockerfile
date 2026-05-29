FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN apk upgrade --no-cache
RUN apk add --no-cache jpeg-dev zlib-dev freetype-dev
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3060
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3060", "--proxy-headers", "--forwarded-allow-ips=*"]
