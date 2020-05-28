#!/bin/bash

# Collect static files
echo "Collect static files"
python manage.py collectstatic --noinput --clear

echo "Apply database migrations"
python manage.py migrate

echo "Starting server"
gunicorn -w 1 --bind 0.0.0.0:8080 textblog.wsgi --log-file -
