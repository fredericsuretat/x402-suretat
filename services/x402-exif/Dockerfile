FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libjpeg-dev zlib1g-dev && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3093
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3093", "--proxy-headers", "--forwarded-allow-ips=*"]
