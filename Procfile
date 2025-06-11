release: python manage.py migrate
web: gunicorn conf.wsgi --log-file - --timeout 24 --graceful-timeout 5 --max-requests 10000