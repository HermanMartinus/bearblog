.PHONY: dev prodshell

dev:
	python manage.py runserver
	
shell:
	sudo heroku run python manage.py shell --app bear-blog

logs:
	sudo heroku logs --tail --app bear-blog | grep "app" | grep -Ev "(GET|POST|HEAD|OPTIONS)"

