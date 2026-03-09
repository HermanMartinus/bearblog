from django.core.management.base import BaseCommand
from django.template.loader import render_to_string
from django.utils import timezone

from blogs.helpers import send_async_mail
from blogs.views.staff import new_upgrades, monthly_users_to_upgrade, free_users_to_nudge


class Command(BaseCommand):
    help = 'Sends scheduled emails (new upgrades, monthly nudge, contribution nudge)'

    def handle(self, *args, **kwargs):
        # Email new upgrades
        count = 0
        for user in new_upgrades().select_related('settings'):
            send_async_mail(
                "You upgraded!",
                render_to_string('emails/upgraded.html'),
                'Herman Martinus <herman@mg.bearblog.dev>',
                [user.email],
                ['Herman Martinus <herman@bearblog.dev>'],
            )
            user.settings.upgraded_email_sent = True
            user.settings.save()
            count += 1
        self.stdout.write(f"Emailed {count} new upgrades.")

        # Nudge monthly users
        count = 0
        for user_settings in monthly_users_to_upgrade():
            send_async_mail(
                "Your subscription",
                render_to_string('emails/upgrade_from_monthly.html'),
                'Herman Martinus <herman@mg.bearblog.dev>',
                [user_settings.user.email],
                ['Herman Martinus <herman@bearblog.dev>'],
            )
            user_settings.upgrade_nudge_email_sent = timezone.now()
            user_settings.save()
            count += 1
        self.stdout.write(f"Emailed {count} monthly users to upgrade.")

        # Nudge free users to contribute
        count = 0
        for user in free_users_to_nudge():
            send_async_mail(
                "Your support",
                render_to_string('emails/contribution_nudge.html'),
                'Herman Martinus <herman@mg.bearblog.dev>',
                [user.email],
                ['Herman Martinus <herman@bearblog.dev>'],
            )
            user.settings.contribution_nudge_email_sent = timezone.now()
            user.settings.save()
            count += 1
        self.stdout.write(f"Emailed {count} free users about contributing.")
