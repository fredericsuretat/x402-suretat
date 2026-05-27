FROM python:3.12-slim

RUN apt-get update && apt-get install -y libpango-1.0-0 libpangocairo-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info fonts-dejavu-core && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 3040
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3040", "--proxy-headers", "--forwarded-allow-ips=*"]
