from django.contrib.admin.views.decorators import staff_member_required
from django.core.mail import send_mail
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.models import User

from blogs.models import Blog
from blogs.helpers import bulk_email


@staff_member_required
def review_flow(request):
    unreviewed_blogs = Blog.objects.filter(reviewed=False, blocked=False).order_by('created_date')

    if unreviewed_blogs:
        blog = unreviewed_blogs[0]
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

        return render(
            request,
            'review_flow.html',
            {
                'blog': blog,
                'content': blog.content or "~nothing here~",
                'posts': all_posts,
                'root': blog.useful_domain(),
                'still_to_go': len(unreviewed_blogs)
            })
    else:
        return HttpResponse("No blogs left to review! \ʕ•ᴥ•ʔ/")


@staff_member_required
def approve(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.reviewed = True
    blog.save()
    if not request.GET.get("no-email", ""):
        send_mail(
            'Hello',
            f'''
Hey, awesome to have you on board!

I hope you enjoy your "bear" blogging experience. Bear is 100% free, open-source, and community centric.

If you're keen to support the project you can do that here: https://bearblog.dev/contribute/
Supporters will receive beta access to new features such as newsletter subscriptions.

Have an awesome week!

Herman
            ''',
            'hi@bearblog.dev',
            [blog.user.email]
        )
    return redirect('review_flow')


@staff_member_required
def block(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.blocked = True
    blog.save()
    return redirect('review_flow')


@staff_member_required
def bulk_mail_users(request):
    if request.method == "POST":
        if request.POST.get("subject", "") and request.POST.get("body", ""):
            if request.POST.get("is_test", ""):
                # Sends to first registered user (assuming that's the admin)
                queryset = Blog.objects.filter(pk=1)
            else:
                queryset = Blog.objects.filter(blocked=False, reviewed=True)
            bulk_email(
                queryset,
                request.POST.get("subject", ""),
                request.POST.get("body", "")
            )
            return HttpResponse(f"Your mail has been sent to {len(queryset)} users!")
        return render(
            request,
            'staff/bulk_mail_users.html',
            {'error': 'Missing message subject or body'}
        )
    else:
        return render(
            request,
            'staff/bulk_mail_users.html',
            {}
        )


def bulk_mail_unsubscribe(request, pk):
    user = get_object_or_404(User, pk=pk)
    user.subscribed = False
    user.save()
    return HttpResponse('You have been successfully unsubscribed.')
