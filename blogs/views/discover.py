
from django.shortcuts import get_object_or_404, render
from django.db.models import Count, ExpressionWrapper, F, FloatField
from django.utils import timezone
from django.db.models.functions import Now

from django.contrib.sites.models import Site
from blogs.models import Post, Upvote

from pg_utils import Seconds
from ipaddr import client_ip


def discover(request):
    http_host = request.META['HTTP_HOST']

    get_object_or_404(Site, domain=http_host)

    ip_address = client_ip(request)

    if request.method == "POST":
        pk = request.POST.get("pk", "")
        post = get_object_or_404(Post, pk=pk)
        posts_upvote_dupe = post.upvote_set.filter(ip_address=ip_address)
        if len(posts_upvote_dupe) == 0:
            upvote = Upvote(post=post, ip_address=ip_address)
            upvote.save()

    posts_per_page = 20
    page = 0
    gravity = 1.2
    if request.GET.get('page'):
        page = int(request.GET.get('page'))

    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get('newest')
    if newest:
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
        ).filter(publish=True, blog__reviewed=True, show_in_feed=True, published_date__lte=timezone.now()
                 ).order_by('-published_date'
                            ).select_related('blog')[posts_from:posts_to]
    else:
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
            score=ExpressionWrapper(
                ((Count('upvote')-1) / ((Seconds(Now() - F('published_date')))+4)**gravity)*100000,
                output_field=FloatField()
            ),
        ).filter(publish=True, blog__reviewed=True, show_in_feed=True, published_date__lte=timezone.now()
                 ).order_by('-score', '-published_date'
                            ).select_related('blog').prefetch_related('upvote_set')[posts_from:posts_to]

    upvoted_posts = []
    for post in posts:
        for upvote in post.upvote_set.all():
            if upvote.ip_address == ip_address:
                upvoted_posts.append(post.pk)

    return render(request, 'discover.html', {
        'site': Site.objects.get_current(),
        'posts': posts,
        'next_page': page+1,
        'posts_from': posts_from,
        'gravity': gravity,
        'newest': newest,
        'upvoted_posts': upvoted_posts
    })
