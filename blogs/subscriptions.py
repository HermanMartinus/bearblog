from django.http import HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.contrib.auth.models import User
from django.conf import settings

from blogs.models import UserSettings

import requests
import os
import json
import hashlib
import hmac

@csrf_exempt
def lemon_webhook(request):
    digest = hmac.new(settings.LEMONSQUEEZY_SIGNATURE.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256).hexdigest()

    if request.META.get('HTTP_X_SIGNATURE') != digest:
        return HttpResponseForbidden('Invalid signature')

    data = json.loads(request.body, strict=False)
    print('Received webhook call')
    # Account upgrade
    if 'order_created' in request.META.get('HTTP_X_EVENT_NAME', ''):
        user = None
        try:
            user_id = str(data['meta']['custom_data']['user_id'])
            user = get_object_or_404(User, id=user_id)
            print(f'Found user with user_id {user}, upgrading account...')
        except KeyError:
            email = str(data['data']['attributes']['user_email'])
            user = User.objects.get(email=email)
            print(f'Found user with email address {email}, upgrading account...')

        if user:
            user.settings.upgraded = True
            user.settings.upgraded_date = timezone.now()
            user.settings.order_id = data['data']['id']
            user.settings.save()
            for blog in user.blogs.all():
                blog.reviewed = True
                blog.save()
            return HttpResponse(f'Upgraded {user}')

    # Account downgrade
    elif 'subscription_expired' in request.META.get('HTTP_X_EVENT_NAME', ''):
        user_settings = None
        try:
            order_id = data['data']['attributes']['order_id']
            user_settings = get_object_or_404(UserSettings, order_id=order_id)
            print('Found order_id, downgrading account...')
            if user_settings:
                user_settings.upgraded = False
                user_settings.upgraded_date = None
                user_settings.order_id = None
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

    response = requests.get(url, headers=headers)

    if response.status_code == 200:
        return response.json()
    else:
        return response.text