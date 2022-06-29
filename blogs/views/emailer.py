from curses.ascii import HT
import hashlib
import re

import djqscsv
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from blogs.helpers import validate_subscriber_email
from blogs.models import Blog, Subscriber
from blogs.views.blog import resolve_address, not_found
from blogs.views.dashboard import resolve_subdomain


@login_required
def email_list(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    if request.GET.get("delete", ""):
        Subscriber.objects.filter(blog=blog, pk=request.GET.get("delete", "")).delete()

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

    if request.POST.get("email_addresses", ""):
        email_addresses = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", request.POST.get("email_addresses", ""))

        for email in email_addresses:
            Subscriber.objects.get_or_create(blog=blog, email_address=email)

    return render(request, "dashboard/subscribers.html", {
        "blog": blog,
        "subscribers": subscribers,
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
            'root': blog.useful_domain(),
        }
    )


@csrf_exempt
def email_subscribe(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    if request.method == "POST":
        if request.POST.get("email", "") and not request.POST.get("name", False):
            email = request.POST.get("email", "")
            subscriber_dupe = Subscriber.objects.filter(blog=blog, email_address=email)
            if not subscriber_dupe:
                validate_subscriber_email(email, blog)
                return HttpResponse("You've been subscribed! ＼ʕ •ᴥ•ʔ／")
            else:
                return HttpResponse("You are already subscribed.")

    return HttpResponse("Something went wrong.")


def confirm_subscription(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    email = request.GET.get("email", "")
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    if token == request.GET.get("token", ""):
        Subscriber.objects.get_or_create(blog=blog, email_address=email)

        return HttpResponse(f'''
            <p style='text-align: center; padding-top: 30%'>
                Your subscription to
                <a href="{blog.useful_domain()}">{blog.title}</a>
                has been confirmed. ＼ʕ •ᴥ•ʔ／
            </p>
            ''')

    return HttpResponse("Something went wrong. Try subscribing again. ʕノ•ᴥ•ʔノ ︵ ┻━┻")
