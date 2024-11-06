.PHONY: dev shell logs 404

dev:
	echo http://lh.co
	python manage.py runserver 0:80
	
shell:
	sudo heroku run python manage.py shell --app bear-blog

logs:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "app\[web" | grep -Ev "(GET|POST|HEAD|OPTIONS)"

404:
	sudo heroku logs --tail --app bear-blog --force-colors | grep "heroku\[" | grep "404"