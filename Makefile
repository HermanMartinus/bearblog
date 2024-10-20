.PHONY: dev prodshell

dev:
	python manage.py runserver
	
prodshell:
	sudo heroku run python manage.py shell --app bear-blog

prodlogs:
	sudo heroku logs --tail --app bear-blog | grep "app" | grep -Ev "(GET|POST|HEAD|OPTIONS)"

