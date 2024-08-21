from django.http.response import HttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q
from django.utils import timezone
from django.contrib.sites.models import Site
from django.core.cache import cache

from blogs.models import Post
from blogs.helpers import clean_text

from feedgen.feed import FeedGenerator
import mistune

posts_per_page = 20

CACHE_TIMEOUT = 300  # 5 minutes in seconds

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
        if request.POST.get("pin-post", False):
            post = Post.objects.get(pk=request.POST.get("pin-post"))
            post.pinned = not post.pinned
            post.save()
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

    # Use the base query function excluding pinned posts
    base_query = get_base_query()

    lang = request.COOKIES.get('lang')

    if lang:
        base_query = base_query.filter(
            (Q(lang__icontains=lang) & ~Q(lang='')) |
            (Q(lang='') & Q(blog__lang__icontains=lang) & ~Q(blog__lang=''))
        )

    if newest:
        posts = base_query.order_by("-published_date")
    else:
        posts = base_query.order_by("-score", "-published_date")

    posts = posts[posts_from:posts_to]

    return render(request, "discover.html", {
        "site": Site.objects.get_current(),
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
            all_posts = get_base_query().order_by("-published_date")[0:posts_per_page]
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
            all_posts = get_base_query().order_by("-score", "-published_date")[0:posts_per_page]
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
            .select_related("blog")[0:20]
        )

    return render(request, "search.html", {
        "site": Site.objects.get_current(),
        "posts": posts,
        "search_string": search_string,
    })