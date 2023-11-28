from curses.ascii import HT
import hashlib
import re

import djqscsv
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from blogs.helpers import send_async_mail
from blogs.models import Blog, Subscriber
from blogs.views.blog import resolve_address, not_found


@login_required
def email_list(request):
    blog = get_object_or_404(Blog, user=request.user)

    if not blog.upgraded:
        return redirect('/dashboard/upgrade/')

    subscribers = Subscriber.objects.filter(blog=blog)

    if request.GET.get("export-csv", ""):
        subscribers = subscribers.values('email_address', 'subscribed_date')
        return djqscsv.render_to_csv_response(subscribers)

    if request.GET.get("export-txt", ""):
        subscribers = subscribers.values('email_address')
        file_data = ""
        for subscriber in subscribers:
            file_data += subscriber['email_address'] + "\n"
        response = HttpResponse(file_data, content_type='application/text charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="emails.txt"'
        return response

    email_addresses_text = ""
    if request.POST.get("email_addresses", ""):
        email_addresses = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", request.POST.get("email_addresses", ""))

        subscribers_list = list(subscribers.values_list('email_address', flat=True))
        removed = list(set(subscribers_list) - set(email_addresses))
        added = list(set(email_addresses) - set(subscribers_list))
        for email in added:
            Subscriber.objects.get_or_create(blog=blog, email_address=email)
        for email in removed:
            Subscriber.objects.filter(blog=blog, email_address=email).delete()

        for email in email_addresses:
            email_addresses_text += f'''{email}
'''

    return render(request, "dashboard/subscribers.html", {
        "blog": blog,
        "subscribers": subscribers,
        "email_addresses_text": email_addresses_text
    })


def subscribe(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    return render(
        request,
        'subscribe.html',
        {
            'blog': blog,
            'root': blog.useful_domain,
        }
    )


@csrf_exempt
def email_subscribe(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    if request.method == "POST":
        if request.POST.get("email", "") and not request.POST.get("name", False):
            recent_subscriptions = Subscriber.objects.filter(subscribed_date__gt=timezone.now()-timezone.timedelta(minutes=2)).count()
            if recent_subscriptions > 10:
                return HttpResponse("Too many recent subscriptions timeout")
            email = request.POST.get("email", "")
            subscriber_dupe = Subscriber.objects.filter(blog=blog, email_address=email).count()
            if subscriber_dupe < 1:
                validate_subscriber_email(email, blog)
                return HttpResponse("You've been subscribed! ＼ʕ •ᴥ•ʔ／")
            else:
                return HttpResponse("You are already subscribed.")

    return HttpResponse("Something went wrong.")


def confirm_subscription(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    email = request.GET.get("email", "").replace(' ', '+')
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    if token == request.GET.get("token", ""):
        Subscriber.objects.get_or_create(blog=blog, email_address=email)

        return HttpResponse(f'''
            <p style='text-align: center; padding-top: 10%'>
                Your subscription to
                <a href="{blog.useful_domain}">{blog.title}</a>
                has been confirmed. ＼ʕ •ᴥ•ʔ／
            </p>
            ''')

    return HttpResponse("Something went wrong. Try subscribing again. ʕノ•ᴥ•ʔノ ︵ ┻━┻")


def validate_subscriber_email(email, blog):
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    confirmation_link = f'{blog.useful_domain}/confirm-subscription/?token={token}&email={email}'

    html_message = f'''
        You've decided to subscribe to {blog.title} ({blog.useful_domain}). That's awesome!
        <br>
        <br>
        Follow this <a href="{confirmation_link}">link</a> to confirm your subscription.
        <br>
        <br>
        Made with <a href="https://bearblog.dev">Bear ʕ•ᴥ•ʔ</a>
    '''
    text_message = f'''
        You've decided to subscribe to {blog.title} ({blog.useful_domain}). That's awesome!

        Follow this link to confirm your subscription: {confirmation_link}

        Made with Bear ʕ•ᴥ•ʔ
    '''
    send_async_mail(
        f'Confirm your subscription to {blog.title}',
        html_message,
        'Bear ʕ•ᴥ•ʔ <no_reply@bearblog.dev>',
        [email],
    )