FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3114
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3114", "--proxy-headers", "--forwarded-allow-ips=*"]
