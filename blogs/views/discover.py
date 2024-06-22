from django.http.response import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, Q
from django.utils import timezone
from django.contrib.sites.models import Site
from django.db.models.functions import Length
from django.core.cache import cache

from blogs.models import Post, Upvote
from blogs.helpers import clean_text, sanitise_int

from feedgen.feed import FeedGenerator
import mistune

gravity = 1.2
posts_per_page = 20

CACHE_TIMEOUT = 300  # 5 minutes in seconds

def get_base_query():
    """Returns the base query for fetching posts, with caching."""
    
    queryset = Post.objects.annotate(content_length=Length('content')).filter(
        publish=True,
        content_length__gt=200,
        hidden=False,
        blog__reviewed=True,
        blog__user__is_active=True,
        blog__hidden=False,
        make_discoverable=True,
        published_date__lte=timezone.now()
    )

    return queryset

@csrf_exempt
def discover(request):
    # admin actions
    if request.user.is_staff:
        if request.POST.get("hide-post", False):
            post = Post.objects.get(pk=request.POST.get("hide-post"))
            post.hidden = True
            post.save()
        if request.POST.get("boost-post", False):
            post = Post.objects.get(pk=request.POST.get("boost-post"))
            for i in range(0, 5):
                upvote = Upvote(post=post, hash_id=f"boost-{i}")
                upvote.save()
        if request.POST.get("pin-post", False):
            post = Post.objects.get(pk=request.POST.get("pin-post"))
            post.pinned = not post.pinned
            post.save()
        if request.POST.get("deprioritise-blog", False):
            post = Post.objects.get(pk=request.POST.get("deprioritise-blog"))
            post.blog.deprioritise = True
            post.blog.save()
        if request.POST.get("hide-blog", False):
            post = Post.objects.get(pk=request.POST.get("hide-blog"))
            post.blog.hidden = True
            post.blog.save()
        if request.POST.get("block-blog", False):
            post = Post.objects.get(pk=request.POST.get("block-blog"))
            post.blog.user.is_active = False
            post.blog.user.save()

    page = 0
    gravity = float(request.GET.get("gravity", 1.2))

    if request.GET.get("page", 0):
        page = sanitise_int(request.GET.get("page"), 7)

    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get("newest")

    pinned_posts = Post.objects.filter(pinned=True).order_by('-published_date')

    # Use the base query function excluding pinned posts
    base_query = get_base_query().exclude(id__in=pinned_posts)

    if newest:
        other_posts = base_query.order_by("-published_date")
    else:
        other_posts = base_query.order_by("-score", "-published_date")

    other_posts = other_posts.select_related("blog")[posts_from:posts_to]

    posts = list(pinned_posts) + list(other_posts)

    return render(request, "discover.html", {
        "site": Site.objects.get_current(),
        "posts": posts,
        "previous_page": page - 1,
        "next_page": page + 1,
        "posts_from": posts_from,
        "gravity": gravity,
        "newest": newest,
    })


def feed(request):
    fg = FeedGenerator()
    fg.id("bearblog")
    fg.author({"name": "Bear Blog", "email": "feed@bearblog.dev"})

    newest = request.GET.get("newest")
    if newest:
        fg.title("Bear Blog Most Recent Posts")
        fg.subtitle("Most recent posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/?newest=True", rel="alternate")
        
        CACHE_KEY = 'discover_newest_feed'
        cached_queryset = cache.get(CACHE_KEY)
    
        if cached_queryset is None:
            all_posts = get_base_query().order_by("-published_date").select_related("blog")[0:posts_per_page]
            all_posts = sorted(list(all_posts), key=lambda post: post.published_date)
            cache.set(CACHE_KEY, all_posts, CACHE_TIMEOUT)
        else:
            all_posts = cached_queryset
    else:
        fg.title("Bear Blog Trending Posts")
        fg.subtitle("Trending posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/", rel="alternate")

        CACHE_KEY = 'discover_trending_feed'
        cached_queryset = cache.get(CACHE_KEY)
    
        if cached_queryset is None:
            all_posts = get_base_query().order_by("-score", "-published_date").select_related("blog")[0:posts_per_page]
            all_posts = sorted(list(all_posts), key=lambda post: post.score)
            cache.set(CACHE_KEY, all_posts, CACHE_TIMEOUT)
        else:
            all_posts = cached_queryset

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{post.blog.useful_domain}/{post.slug}/")
        fe.title(post.title)
        fe.author({"name": post.blog.subdomain, "email": "hidden"})
        fe.link(href=f"{post.blog.useful_domain}/{post.slug}/")
        fe.content(clean_text(mistune.html(post.content.replace("{{ email-signup }}", ''))), type="html")
        fe.published(post.published_date)
        fe.updated(post.published_date)

    if request.GET.get("type") == "rss":
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type="application/rss+xml")
    else:
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type="application/atom+xml")
    

def search(request):
    search_string = request.GET.get('query', "")
    posts = None

    if search_string:
        posts = (
            get_base_query().filter(
                Q(content__icontains=search_string) | Q(title__icontains=search_string)
            )
            .order_by('-upvotes', "-published_date")
            .select_related("blog")[0:50]
        )

    return render(request, "search.html", {
        "site": Site.objects.get_current(),
        "posts": posts,
        "search_string": search_string,
    })