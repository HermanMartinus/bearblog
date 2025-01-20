from django.http.response import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.utils import timezone
from django.core.cache import cache

from blogs.models import Post
from blogs.helpers import clean_text

from datetime import timedelta
from feedgen.feed import FeedGenerator
import mistune

posts_per_page = 20

CACHE_TIMEOUT = 600  # 10 minutes in seconds


def get_base_query():
    queryset = Post.objects.select_related("blog").filter(
        publish=True,
        hidden=False,
        blog__reviewed=True,
        blog__user__is_active=True,
        blog__hidden=False,
        make_discoverable=True,
        published_date__lte=timezone.now()
    )

    return queryset


def admin_actions(request):
    # admin actions
    if request.user.is_staff:
        if request.POST.get("hide-post", False):
            post = Post.objects.get(pk=request.POST.get("hide-post"))
            post.hidden = True
            post.save()
        if request.POST.get("hide-blog", False):
            post = Post.objects.get(pk=request.POST.get("hide-blog"))
            post.blog.hidden = True
            post.blog.save()
        if request.POST.get("block-blog", False):
            post = Post.objects.get(pk=request.POST.get("block-blog"))
            post.blog.user.is_active = False
            post.blog.user.save()
        
        if request.POST.get("set-votes", False):
            post = Post.objects.get(pk=request.POST.get("set-votes"))
            post.shadow_votes = int(request.POST.get("shadow-votes"))
            post.save()


@csrf_exempt
def discover(request):
    admin_actions(request)

    try:
        page = int(request.GET.get("page", 0) or 0)
    except ValueError:
        page = 0

    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get("newest")

    base_query = get_base_query()

    lang = request.COOKIES.get('lang')

    if lang:
        base_query = base_query.filter(
            (Q(lang__startswith=lang) & ~Q(lang='')) |
            (Q(lang='') & Q(blog__lang__startswith=lang) & ~Q(blog__lang=''))
        )

    if newest:
        posts = base_query.order_by("-published_date")
    else:
        posts = base_query.order_by("-score")

    posts = posts[posts_from:posts_to]

    return render(request, "discover.html", {
        "lang": lang,
        "available_languages": get_available_languages(),
        "posts": posts,
        "previous_page": page - 1,
        "next_page": page + 1,
        "posts_from": posts_from,
        "newest": newest,
    })


def get_available_languages():
    return ["cs", "de", "en", "es", "fi", "fr", "hu", "id", "it", "ja", "ko", "nl", "pl", "pt", "ru", "sv", "tr", "zh"]


# RSS/Atom feed
def feed(request):
    # Determine feed parameters
    feed_kind = "newest" if request.GET.get("newest") else "trending"
    feed_type = 'rss' if request.GET.get("type") == "rss" else "atom"
    lang = request.GET.get("lang")

    # Construct a unique cache key
    if lang:
        CACHE_KEY = f'discover_feed_{feed_kind}_{feed_type}_{lang}'
    else:
        CACHE_KEY = f'discover_feed_{feed_kind}_{feed_type}'

    # Attempt to retrieve the cached feed
    cached_feed = cache.get(CACHE_KEY)
    if cached_feed is not None:
        return HttpResponse(cached_feed, content_type=f"application/{feed_type}+xml")

    fg = FeedGenerator()
    fg.id("bearblog")
    fg.author({"name": "Bear Blog", "email": "feed@bearblog.dev"})

    if feed_type == 'rss':
        feed_method = fg.rss_str
    else:
        feed_method = fg.atom_str
    
    base_query = get_base_query()
    if lang:
        base_query = base_query.filter(
            (Q(lang__startswith=lang) & ~Q(lang='')) |
            (Q(lang='') & Q(blog__lang__startswith=lang) & ~Q(blog__lang=''))
        )
    if feed_kind == 'newest':
        fg.title("Bear Blog Most Recent Posts")
        fg.subtitle("Most recent posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/?newest=True", rel="alternate")

        all_posts = base_query.order_by("-published_date")[:posts_per_page]
        all_posts = sorted(all_posts, key=lambda post: post.published_date)
    else:
        fg.title("Bear Blog Trending Posts")
        fg.subtitle("Trending posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/", rel="alternate")

        all_posts = base_query.order_by("-score", "-published_date")[:posts_per_page]
        all_posts = sorted(all_posts, key=lambda post: post.score)  


    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{post.blog.useful_domain}/{post.slug}/")
        fe.title(post.title)
        fe.author({"name": post.blog.subdomain, "email": "hidden"})
        fe.link(href=f"{post.blog.useful_domain}/{post.slug}/")
        fe.content(
            clean_text(mistune.html(post.content.replace("{{ email-signup }}", ''))),
            type="html"
        )
        fe.published(post.published_date)
        fe.updated(post.published_date)

    # Generate the feed string and cache it
    feed_str = feed_method(pretty=True)
    cache.set(CACHE_KEY, feed_str, CACHE_TIMEOUT)
    return HttpResponse(feed_str, content_type=f"application/{feed_type}+xml")

    

def search(request):
    search_string = request.GET.get('query', "")
    posts = None

    if search_string:
        posts = (
            get_base_query().filter(
                Q(content__icontains=search_string) | Q(title__icontains=search_string)
            )
            .order_by('-upvotes', "-published_date")
            .select_related("blog")[0:20]
        )

    return render(request, "search.html", {
        "posts": posts,
        "search_string": search_string,
    })