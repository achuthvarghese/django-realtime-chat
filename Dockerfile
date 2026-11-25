FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /code

COPY requirements.txt requirements-dev.txt /code/
RUN pip install -r requirements-dev.txt

COPY . /code/

EXPOSE 8000

# Migrations are applied at start-up, not at build time, so the database
# lives in a volume rather than in the image.
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
