.PHONY: dev shell logs 404 migrate makemigrations

dev:
	echo http://lh.co
	uv run manage.py runserver 0:80

migrate:
	uv run manage.py migrate

makemigrations:
	uv run manage.py makemigrations

shell:
	sudo heroku run uv run manage.py shell --app bear-blog

logs:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "app\[web" | grep -Ev "(GET|POST|HEAD|OPTIONS)"

404:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "heroku\[" | grep "404"

router:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "heroku\[router" | grep -Ev "feed"
