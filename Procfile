release: python manage.py migrate
web: gunicorn conf.wsgi --log-file - --timeout 24 --graceful-timeout 5 --max-requests 10000 --bind 0.0.0.0:7000
