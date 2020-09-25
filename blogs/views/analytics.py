from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required

from blogs.models import Blog, Post
from blogs.helpers import root
from django.db.models import Count
from django.http import HttpResponse


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)

    posts = Post.objects.annotate(
            hit_count=Count('hit')).filter(blog=blog).order_by('-hit_count')

    return render(request, 'dashboard/analytics.html', {
        'posts': posts,
        'blog': blog
    })


@login_required
def post_analytics(request, pk):
    post = get_object_or_404(Post, pk=pk)

    return HttpResponse("Work in progress  ᕦʕ •ᴥ•ʔᕤ")
