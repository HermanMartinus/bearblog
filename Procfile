release: python manage.py migrate
web: gunicorn conf.wsgi --log-file - --timeout 20 --graceful-timeout 1 --max-requests 1200