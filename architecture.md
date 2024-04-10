# Bear Architecture
Bear is a Django-based blogging platform that allows users to create and manage their own blogs. The project is hosted on Heroku and utilizes various technologies and services to provide a robust and scalable architecture.

## Django
Bear is built using the Django web framework, which follows the Model-View-Controller (MVC) architectural pattern. Django provides a powerful ORM (Object-Relational Mapping) for database management, an admin interface for easy data manipulation, and a templating engine for rendering dynamic HTML pages.

## Database
The project uses Heroku Postgres as the primary database. Heroku Postgres is a managed PostgreSQL database service that provides scalability, reliability, and automatic backups. The database connection is managed through the dj-database-url library, which allows seamless integration with Heroku's database configuration.

## Dependencies
Bear relies on various Python packages and libraries to extend its functionality. These dependencies are listed in the requirements.txt file and include packages for authentication (django-allauth), debugging (django-debug-toolbar), CSV export (django-queryset-csv), Markdown parsing (mistune), and more. The dependencies are installed and managed using virtualenv.

## Templates
Django's templating engine is used to render dynamic HTML pages. The project's templates are located in the templates directory and follow Django's template language syntax. The templates are organized into subdirectories based on their respective apps or functionalities.
Static Files
Static files such as CSS, JavaScript, and images are served using WhiteNoise, a Django middleware that allows serving static files efficiently. The static files are collected and stored in the staticfiles directory during the deployment process.

## Deployment
## Heroku
Bear is deployed on Heroku, a cloud platform that provides easy deployment and scaling of web applications. Heroku's platform takes care of server management, load balancing, and automatic scaling based on the application's resource requirements.

## Digital Ocean Spaces
Images are uploaded to a Spaces S3 bucket on Digital Ocean. Their CDN is used to retrieve uploaded images. 

## Procfile
The Procfile file specifies the commands that need to be executed when the application starts on Heroku. It includes a release command to run database migrations and a web command to start the Gunicorn web server.

## Runtime
The runtime.txt file specifies the Python version used by the project. Bear uses Python 3.9.13.

## Networking and Security
## DNS and SSL
Bear uses Cloudflare as its DNS provider and for issuing SSL certificates for the .bearblog.dev domains. Cloudflare provides fast and secure DNS resolution and automatic SSL certificate management.

## Reverse Proxy (custom domains)
A reverse proxy is set up on a Digital Ocean droplet using Caddy. The reverse proxy handles custom domain routing and SSL termination. It forwards incoming requests to the Heroku application based on the host header. The Caddy configuration file (Caddyfile) specifies the proxy rules and SSL settings.

## Additional Services
## Email
Bear uses Mailgun for email delivery. The email backend is configured to use Mailgun's SMTP service, and the necessary credentials are stored securely in environment variables.

## Logging and Monitoring
The project utilizes Heroku's built-in logging and monitoring capabilities to track application performance, errors, and resource usage. Additionally, custom logging is implemented using Django's logging framework, with error logs being sent to a Slack channel for real-time notifications.

---
# Staging server

Bear Staging runs on a droplet with Caddy as the web server.
The Django application is served by Gunicorn.
The database is backed up using a cron job and with Litestream.
Django, Caddy, and Litestream run as systemd services.

### Caddy:

config: /etc/caddy/Caddyfile
logs: /var/log/caddy/access.log

### Django

script & config: /root/deploy/run.sh

### Services:

Caddy: /etc/systemd/system/caddy.service
Bear: /etc/systemd/system/bearblog.service
Litestream: /etc/systemd/system/litestream.service

Restart service: systemctl restart bearblog

### DB backups run in a crontab:

Backup is running in a cron job: crontab -e
 
script: /root/deploy/backup.sh
local backups: /root/backups/
remote backups: https://sqlite.sfo3.digitaloceanspaces.com/backups/

### Litestream:

config: /etc/litestream.yml 
