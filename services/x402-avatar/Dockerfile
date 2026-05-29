FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    fonts-dejavu-core && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN apt-get update && apt-get upgrade -y --no-install-recommends && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3107
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3107", "--proxy-headers", "--forwarded-allow-ips=*"]
