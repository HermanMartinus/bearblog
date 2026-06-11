from django.db.models import F
from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

from blogs.helpers import send_async_mail
from blogs.models import UserSettings

import requests
import os
import json
import hashlib
import hmac
import sentry_sdk


def normalize_plan_type(variant_name):
    if not variant_name:
        return None
    name = variant_name.lower()
    if name.startswith('monthly'):
        return 'monthly'
    elif name.startswith('yearly'):
        return 'yearly'
    elif name.startswith('lifetime'):
        return 'lifetime'
    return None

def find_user_for_order(data):
    # Prefer the user_id passed through checkout custom data
    user_id = (data.get('meta', {}).get('custom_data') or {}).get('user_id')
    if user_id:
        try:
            user = User.objects.filter(id=str(user_id)).first()
        except ValueError:
            user = None
        if user:
            print(f'Found user with user_id {user}, upgrading account...')
            return user

    email = data['data']['attributes'].get('user_email')
    if not email:
        return None

    # Fall back on account email, then linked allauth addresses, then the
    # email used on a previous order. Most recently active user wins.
    candidates = (
        User.objects.filter(email__iexact=email),
        User.objects.filter(emailaddress__email__iexact=email),
        User.objects.filter(settings__order_email__iexact=email),
    )
    for queryset in candidates:
        user = queryset.order_by(F('last_login').desc(nulls_last=True)).first()
        if user:
            print(f'Found user with email address {email}, upgrading account...')
            return user
    return None


@csrf_exempt
def lemon_webhook(request):
    digest = hmac.new(settings.LEMONSQUEEZY_SIGNATURE.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256).hexdigest()

    if request.META.get('HTTP_X_SIGNATURE') != digest:
        return HttpResponseForbidden('Invalid signature')

    data = json.loads(request.body, strict=False)
    print('Received webhook call')
    
    # Account upgrade
    if request.META.get('HTTP_X_EVENT_NAME') in ('order_created', 'subscription_resumed', 'subscription_unpaused'):
        user = find_user_for_order(data)

        if user:
            user.settings.upgraded = True
            user.settings.upgraded_date = timezone.now()
            variant_name = None
            if 'order_id' in data['data']['attributes']:
                # If subscription object get order_id and variant_name
                user.settings.order_id = data['data']['attributes']['order_id']
                variant_name = data['data']['attributes'].get('variant_name')
            else:
                # If order object get id and variant_name from first_order_item
                user.settings.order_id = data['data']['id']
                variant_name = data['data']['attributes'].get('first_order_item', {}).get('variant_name')
            user.settings.plan_type = normalize_plan_type(variant_name)
            if 'user_email' in data['data']['attributes']:
                user.settings.order_email = data['data']['attributes']['user_email']
            user.settings.save()
            for blog in user.blogs.all():
                blog.reviewed = True
                blog.save()
            return HttpResponse(f'Upgraded {user}')

        # No account matched; ask the purchaser to get in touch
        email = data['data']['attributes'].get('user_email')
        order_number = data['data']['attributes'].get('order_number') or data['data'].get('id')
        print(f'Could not match order {order_number} to a user (email: {email})')
        if email:
            send_async_mail(
                "Your Bear Blog upgrade",
                render_to_string('emails/upgrade_unmatched.html'),
                'Herman Martinus <herman@mg.bearblog.dev>',
                [email],
                ['Herman Martinus <herman@bearblog.dev>'],
            )
        sentry_sdk.capture_message(f'Lemon Squeezy order {order_number} could not be matched to a user (email: {email})')
        return HttpResponse('No matching user found; purchaser notified')

    # Account downgrade
    # This only happens on order id, not on email to prevent old sub overwriting new one
    elif request.META.get('HTTP_X_EVENT_NAME') in ('subscription_expired', 'subscription_paused'):
        user_settings = None
        try:
            order_id = data['data']['attributes']['order_id']
            user_settings = get_object_or_404(UserSettings, order_id=order_id)
            print('Found order_id, downgrading account...')
            if user_settings:
                user_settings.upgraded = False
                user_settings.upgraded_date = None
                user_settings.order_id = None
                user_settings.plan_type = None
                user_settings.save()
                return HttpResponse(f'Downgraded {user_settings}')
        except KeyError:
            print('Could not find order_id')

    print('Completed')
    return HttpResponse('Valid webhook call with no action taken')


def get_subscriptions(order_id=None, user_email=None):
    print('Getting subscription status')
    url = "https://api.lemonsqueezy.com/v1/subscriptions"

    if order_id:
        url += f"?filter[order_id]={order_id}"

    if user_email:
        url += f"?filter[user_email]={user_email}"

    headers = {
        'Accept': 'application/vnd.api+json',
        'Content-Type': 'application/vnd.api+json',
        'Authorization': f'Bearer {os.getenv("LEMON_SQUEEZY_KEY")}'
    }

    response = requests.get(url, headers=headers, timeout=10)

    if response.status_code == 200:
        return response.json()
    else:
        return response.text