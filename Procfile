release: uv run manage.py migrate
web: uv run gunicorn conf.wsgi --log-file - --timeout 24 --graceful-timeout 5 --max-requests 10000F
