release: python manage.py migrate
web: gunicorn conf.wsgi --log-file - --timeout 15 --graceful-timeout 5 --max-requests 1200