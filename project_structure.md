# Project structure

Bear runs on a droplet with Caddy as the web server. The Django application is served by Gunicorn. The database is backed up using a cron job and with Litestream. Django, Caddy, and Litestream run as systemd services.

## Caddy:

config: /etc/caddy/Caddyfile
logs: /var/log/caddy/access.log

## Django

script & config: /root/deploy/run.sh

## Services:

Caddy: /etc/systemd/system/caddy.service
Bear: /etc/systemd/system/bearblog.service
Litestream: /etc/systemd/system/litestream.service

Restart service: systemctl restart bearblog

## DB backups run in a crontab:

Backup is running in a cron job: crontab -e
 
script: /root/deploy/backup.sh
local backups: /root/backups/
remote backups: https://sqlite.sfo3.digitaloceanspaces.com/backups/

## Litestream:

config: /etc/litestream.yml 
