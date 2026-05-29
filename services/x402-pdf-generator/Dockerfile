FROM python:3.12-alpine
WORKDIR /app
COPY requirements.txt .
RUN apk upgrade --no-cache
RUN apk add --no-cache gcc musl-dev libffi-dev cairo-dev pango-dev gdk-pixbuf-dev fontconfig-dev shared-mime-info font-noto
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt
COPY main.py .
EXPOSE 3040
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3040", "--proxy-headers", "--forwarded-allow-ips=*"]
