FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=3000
ENV HOST=0.0.0.0

WORKDIR /app

COPY server.py /app/server.py
COPY public /app/public
COPY alerts/.gitkeep /app/alerts/.gitkeep

EXPOSE 3000

CMD ["python3", "server.py"]
