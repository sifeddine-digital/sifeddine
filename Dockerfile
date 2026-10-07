FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV DATABASE_PATH=/data/los.sqlite3 SESSION_COOKIE_SECURE=1
VOLUME /data
EXPOSE 8000
CMD ["gunicorn", "-w", "2", "--preload", "--timeout", "120", "-b", "0.0.0.0:8000", "wsgi:app"]
