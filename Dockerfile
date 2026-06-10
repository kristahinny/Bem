FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATA_DIR=/app/data
ENV PORT=8000

WORKDIR /app

COPY app ./app
COPY static ./static
COPY requirements.txt ./requirements.txt

RUN mkdir -p /app/data
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8000

CMD ["python", "app/server.py"]
