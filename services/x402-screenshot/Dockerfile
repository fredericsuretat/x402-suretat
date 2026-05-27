FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium --with-deps

COPY main.py .

EXPOSE 3075
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3075", "--proxy-headers", "--forwarded-allow-ips=*"]
