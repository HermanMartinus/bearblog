.PHONY: dev shell logs 404 migrate makemigrations

dev:
	echo http://lh.co
	python manage.py runserver 0:80

migrate:
	python manage.py migrate

makemigrations:
	python manage.py makemigrations

shell:
	sudo heroku run python manage.py shell --app bear-blog

logs:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "app\[web" | grep -Ev "(GET|POST|HEAD|OPTIONS)"

404:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "heroku\[" | grep "404"

router:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "heroku\[router" | grep -Ev "feed"