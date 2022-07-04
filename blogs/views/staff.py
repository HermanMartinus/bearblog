from datetime import timedelta
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from blogs.helpers import send_async_mail

from blogs.models import Blog


@staff_member_required
def review_flow(request):
    blogs = Blog.objects.filter(reviewed=False, blocked=False).annotate(
        post_count=Count("post"),
    ).prefetch_related("post_set").order_by('created_date')

    unreviewed_blogs = []
    for blog in blogs:
        one_month = timezone.now() - timedelta(days=14)
        if (blog.content == "Hello World!"
            and blog.post_count == 0
            and not blog.domain
            and not blog.custom_styles
                and blog.nav != "[Home](/)[Blog](/blog/)"):

            # Delete empty blogs over a month old
            if blog.created_date < one_month:
                blog.delete()
        else:
            unreviewed_blogs.append(blog)

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

    message = request.POST.get("message", "")

    if not request.GET.get("no-email", ""):
        send_async_mail(
            "I've just reviewed your blog",
            message,
            'Herman Martinus <herman@bearblog.dev>',
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
def delete(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.delete()
    return redirect('review_flow')
