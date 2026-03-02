import os
import time
import requests
import sentry_sdk
from django.core.management.base import BaseCommand


# Monitors a custom domain (justsketch.me) to verify it's serving Bear Blog content.
# Checks for the bear-necessities meta tag, retries once after 5s, then falls back to
# the .bearblog.dev subdomain. If the subdomain works but the custom domain doesn't,
# waits 10s to confirm and reboots the Caddy droplet via the DigitalOcean API.

URL = "https://justsketch.me"
FALLBACK_URL = "https://justsketchme.bearblog.dev"
TARGET = "look-for-the-bear-necessities"


class Command(BaseCommand):
    help = "Monitor custom domain uptime and reboot Caddy droplet if needed"

    def check_url(self, url):
        user_agent = os.environ.get("ADMIN_USER_AGENT", "")
        try:
            response = requests.get(url, headers={"User-Agent": user_agent}, timeout=10)
            return TARGET in response.text
        except requests.RequestException:
            return False

    def reboot_droplet(self):
        do_token = os.environ["DO_TOKEN"]
        droplet_name = "bearblog"

        response = requests.get(
            f"https://api.digitalocean.com/v2/droplets?name={droplet_name}",
            headers={"Authorization": f"Bearer {do_token}"},
            timeout=10,
        )
        droplets = response.json().get("droplets", [])
        if not droplets:
            self.stderr.write(self.style.ERROR(f"Could not find droplet '{droplet_name}'"))
            return

        droplet_id = droplets[0]["id"]
        requests.post(
            f"https://api.digitalocean.com/v2/droplets/{droplet_id}/actions",
            headers={
                "Authorization": f"Bearer {do_token}",
                "Content-Type": "application/json",
            },
            json={"type": "reboot"},
            timeout=10,
        )
        sentry_sdk.capture_message(
            f"Caddy droplet rebooted: {droplet_name} (id: {droplet_id})",
            level="error",
        )
        self.stdout.write(self.style.SUCCESS(f"Reboot triggered for droplet {droplet_name} (id: {droplet_id})"))

    def handle(self, *args, **kwargs):
        if self.check_url(URL):
            self.stdout.write(f"OK: {URL}")
            return

        # Second check for redundancy
        time.sleep(5)
        if self.check_url(URL):
            self.stdout.write(f"OK: {URL} (second check)")
            return

        if self.check_url(FALLBACK_URL):
            self.stdout.write(f"Fallback OK but not {URL} — confirming before reboot...")
            time.sleep(10)
            if self.check_url(URL):
                self.stdout.write("Resolved on confirmation check — no reboot needed")
                return

            self.stdout.write(self.style.WARNING("Still misconfigured. Rebooting droplet..."))
            self.reboot_droplet()
        else:
            self.stderr.write(self.style.ERROR(f"Target not found at {URL} or {FALLBACK_URL}"))
