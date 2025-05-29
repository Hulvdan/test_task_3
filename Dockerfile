FROM python:3.11-alpine

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src src
COPY alembic alembic
COPY alembic.ini .
EXPOSE 8000
