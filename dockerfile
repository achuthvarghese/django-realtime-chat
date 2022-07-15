FROM python:3.8-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /code
COPY . /code/

RUN /usr/local/bin/python -m pip install -U pip
RUN pip install -r requirements.txt

# Setup Django Database
RUN python manage.py makemigrations
RUN python manage.py migrate
