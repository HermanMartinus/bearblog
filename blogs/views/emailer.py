import hashlib
import re

import djqscsv
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from blogs.helpers import validate_subscriber_email, get_nav
from blogs.models import Blog, Subscriber, Emailer
from blogs.forms import NotifyForm
from blogs.views.blog import resolve_address, not_found
from blogs.views.dashboard import resolve_subdomain


@login_required
def subscribers(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    if request.GET.get("delete", ""):
        Subscriber.objects.filter(blog=blog, pk=request.GET.get("delete", "")).delete()

    subscribers = Subscriber.objects.filter(blog=blog)

    if request.GET.get("export", ""):
        subscribers = subscribers.values('email_address', 'subscribed_date')
        return djqscsv.render_to_csv_response(subscribers)

    if request.POST.get("email_addresses", ""):
        email_addresses = re.findall(r"[a-z0-9\.\-+_]+@[a-z0-9\.\-+_]+\.[a-z]+", request.POST.get("email_addresses", ""))

        for email in email_addresses:
            Subscriber.objects.get_or_create(blog=blog, email_address=email)

    return render(request, "dashboard/subscribers.html", {
        "blog": blog,
        "subscribers": subscribers,
    })


@login_required
def notification_settings(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    Emailer.objects.get_or_create(blog=blog)

    if request.method == "POST":
        form = NotifyForm(request.POST, instance=blog.emailer)
        if form.is_valid():
            emailer_info = form.save(commit=False)
            emailer_info.save()
            return redirect("/dashboard/subscribers/")
    else:
        form = NotifyForm(instance=blog.emailer)

    return render(request, "dashboard/notification_settings.html", {
        "blog": blog,
        "form": form
    })


def subscribe(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    subscribe_message = ""
    if request.method == "POST":
        if request.POST.get("email", "") and not request.POST.get("name", ""):
            email = request.POST.get("email", "")
            subscriber_dupe = Subscriber.objects.filter(blog=blog, email_address=email)
            if not subscriber_dupe:
                validate_subscriber_email(email, blog)
                subscribe_message = "Check your email to confirm your subscription."
            else:
                subscribe_message = "You are already subscribed."

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    return render(
        request,
        'subscribe.html',
        {
            'blog': blog,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'subscribe_message': subscribe_message
        }
    )


def confirm_subscription(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    email = request.GET.get("email", "")
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    if token == request.GET.get("token", ""):
        Subscriber.objects.get_or_create(blog=blog, email_address=email)

        return HttpResponse(f"<p>You've been subscribed to <a href='{blog.useful_domain()}'>{blog.title}</a>. ＼ʕ •ᴥ•ʔ／</p>")

    return HttpResponse("Something went wrong. Try subscribing again. ʕノ•ᴥ•ʔノ ︵ ┻━┻")
