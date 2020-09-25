from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from blogs.models import Blog, Hit, Post
from blogs.helpers import root
from django.db.models import Count, Sum
from django.http import HttpResponse

from ipaddr import client_ip


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)

    posts = Post.objects.annotate(
            hit_count=Count('hit')).filter(blog=blog, publish=True).order_by('-hit_count', '-published_date')

    unique_reads = posts.aggregate(Sum('hit_count'))

    return render(request, 'dashboard/analytics.html', {
        'unique_reads': unique_reads,
        'posts': posts,
        'blog': blog
    })


@login_required
def post_analytics(request, pk):
    post = get_object_or_404(Post, pk=pk)

    return HttpResponse("Work in progress  ᕦʕ •ᴥ•ʔᕤ")


def post_hit(request, pk):
    ip_address = client_ip(request)
    post = get_object_or_404(Post, pk=pk)
    post_view_dupe = post.hit_set.filter(ip_address=ip_address)

    if len(post_view_dupe) == 0:
        hit = Hit(post=post, ip_address=ip_address)
        hit.save()

    return HttpResponse("Image", 'Content-Type: image/png')