from django.db.models import F
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

from blogs.helpers import send_async_mail
from blogs.models import UserSettings

import json
import hashlib
import hmac


PLAN_TYPES = {'monthly', 'yearly', 'lifetime'}
UPGRADE_EVENTS = {'payment.succeeded', 'subscription.activated', 'subscription.resumed'}
DOWNGRADE_EVENTS = {'subscription.canceled', 'subscription.expired', 'subscription.paused'}


def normalize_plan_type(plan_type):
    if isinstance(plan_type, str) and plan_type.lower() in PLAN_TYPES:
        return plan_type.lower()
    return None


def find_user_for_payment(data):
    user_id = data.get('user_id')
    if user_id:
        try:
            user = User.objects.filter(id=str(user_id)).first()
        except (TypeError, ValueError):
            user = None
        if user:
            return user

    email = data.get('email')
    if not isinstance(email, str) or not email:
        return None

    # Fall back on account email, linked allauth addresses, then a previous
    # payment email. Most recently active user wins.
    candidates = (
        User.objects.filter(email__iexact=email),
        User.objects.filter(emailaddress__email__iexact=email),
        User.objects.filter(settings__order_email__iexact=email),
    )
    for queryset in candidates:
        user = queryset.order_by(F('last_login').desc(nulls_last=True)).first()
        if user:
            return user
    return None


@csrf_exempt
def payment_webhook(request):
    """Handle normalized payment events from any configured provider.

    Send JSON with an ``event`` plus ``user_id``, ``email``, ``payment_id``,
    ``plan_type`` and optionally ``management_url``. Sign the raw body with
    HMAC-SHA256 and send the hex digest in the ``X-Signature`` header.
    """
    if request.method != 'POST':
        return HttpResponse('Method not allowed', status=405)

    if not settings.PAYMENT_WEBHOOK_SECRET:
        return HttpResponseForbidden('Invalid signature')

    digest = hmac.new(settings.PAYMENT_WEBHOOK_SECRET.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256).hexdigest()

    provided = request.META.get('HTTP_X_SIGNATURE', '')
    if not hmac.compare_digest(provided.encode('utf-8'), digest.encode('utf-8')):
        return HttpResponseForbidden('Invalid signature')

    try:
        data = json.loads(request.body, strict=False)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponseBadRequest('Invalid JSON')
    if not isinstance(data, dict):
        return HttpResponseBadRequest('Invalid event')

    event = data.get('event')
    if not isinstance(event, str):
        return HttpResponseBadRequest('Missing event')

    if event in UPGRADE_EVENTS:
        plan_type = normalize_plan_type(data.get('plan_type'))
        payment_id = data.get('payment_id') or data.get('subscription_id') or data.get('id')
        if not plan_type or not isinstance(payment_id, (str, int)) or not payment_id:
            return HttpResponseBadRequest('Missing payment details')

        user = find_user_for_payment(data)

        if user:
            email = data.get('email')
            if not isinstance(email, str):
                email = ''
            user.settings.upgraded = True
            user.settings.upgraded_date = timezone.now()
            user.settings.order_id = str(payment_id)[:100]
            user.settings.plan_type = plan_type
            management_url = data.get('management_url', '')
            if isinstance(management_url, str):
                user.settings.payment_management_url = management_url
            if email:
                user.settings.order_email = email
            user.settings.save()
            for blog in user.blogs.all():
                blog.reviewed = True
                blog.save()
            return HttpResponse(f'Upgraded {user}')

        # No account matched; ask the purchaser to get in touch
        email = data.get('email')
        if not isinstance(email, str):
            email = ''
        payment_id = data.get('payment_id') or data.get('subscription_id') or data.get('id')
        if email:
            send_async_mail(
                "Your Bear Blog upgrade",
                render_to_string('emails/upgrade_unmatched.html'),
                'Herman Martinus <herman@mg.bearblog.dev>',
                [email],
                ['Herman Martinus <herman@bearblog.dev>'],
            )
        return HttpResponse('No matching user found; purchaser notified')

    elif event in DOWNGRADE_EVENTS:
        payment_id = data.get('payment_id') or data.get('subscription_id') or data.get('id')
        if payment_id:
            user_settings = UserSettings.objects.filter(order_id=str(payment_id)).first()
            if user_settings:
                user_settings.upgraded = False
                user_settings.upgraded_date = None
                user_settings.order_id = None
                user_settings.plan_type = None
                user_settings.payment_management_url = ''
                user_settings.save()
                return HttpResponse(f'Downgraded {user_settings}')

    return HttpResponse('Payment event received with no action taken')
