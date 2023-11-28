from django.http import HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.conf import settings
import requests

from blogs.models import Blog

import os
import json
import hashlib
import hmac

@csrf_exempt
def lemon_webhook(request):
    digest = hmac.new(settings.LEMONSQUEEZY_SIGNATURE.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256).hexdigest()

    if request.META.get('HTTP_X_SIGNATURE') != digest:
        raise Http404('Blog not found')

    data = json.loads(request.body, strict=False)

    # Blog upgrade
    if 'order_created' in request.META.get('HTTP_X_EVENT_NAME', ''):
        blog = None
        try:
            subdomain = str(data['meta']['custom_data']['blog'])
            blog = get_object_or_404(Blog, subdomain=subdomain)
            print(f'Found subdomain {subdomain}, upgrading blog...')
        except KeyError:
            email = str(data['data']['attributes']['user_email'])
            blog = Blog.objects.get(user__email=email)
            print(f'Found email address {email}, upgrading blog...')

        if blog:
            blog.reviewed = True
            blog.upgraded = True
            blog.upgraded_date = timezone.now()
            blog.order_id = data['data']['id']
            blog.save()
            return HttpResponse(f'Upgraded {blog}')

    # Blog downgrade
    elif 'subscription_expired' in request.META.get('HTTP_X_EVENT_NAME', ''):
        blog = None
        try:
            blog = get_object_or_404(Blog, order_id=data['data']['attributes']['order_id'])
            print('Found order_id, downgrading blog...')
            if blog:
                blog.upgraded = False
                blog.upgraded_date = None
                blog.order_id = None
                blog.save()
                return HttpResponse(f'Downgraded {blog}')
        except KeyError:
            print('Could not find order_id')

    return HttpResponse('Valid webhook call with no action taken')


def get_subscriptions(order_id=None, user_email=None):
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