import os
from urllib.parse import urlsplit, urlunsplit

from allauth.account import app_settings
from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):
    """Force auth email links onto the canonical host.

    The site accepts any Host (ALLOWED_HOSTS = ['*'], USE_X_FORWARDED_HOST)
    to serve custom domains, so allauth would otherwise build password reset
    and email confirmation links from an attacker-supplied X-Forwarded-Host.
    Pin the origin to MAIN_SITE_HOSTS[0] regardless of the request host.
    """

    def _force_canonical(self, url):
        canonical_host = os.getenv('MAIN_SITE_HOSTS').split(',')[0].strip()
        parts = urlsplit(url)
        return urlunsplit((
            app_settings.DEFAULT_HTTP_PROTOCOL,
            canonical_host,
            parts.path,
            parts.query,
            parts.fragment,
        ))

    def get_reset_password_from_key_url(self, key):
        return self._force_canonical(super().get_reset_password_from_key_url(key))

    def get_email_confirmation_url(self, request, emailconfirmation):
        return self._force_canonical(
            super().get_email_confirmation_url(request, emailconfirmation)
        )
