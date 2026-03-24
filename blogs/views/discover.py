from django.http.response import HttpResponse
from django.shortcuts import render, redirect
from django.db.models import Q, Max, Min
from django.utils import timezone
from django.db.models.functions import Length
from django.contrib.postgres.search import SearchQuery

from blogs.models import Post, Blog
from blogs.helpers import clean_text, random_post_link, random_blog_link
from blogs.templatetags.custom_tags import markdown, plain_title

import random
from feedgen.feed import FeedGenerator

posts_per_page = 20


def get_base_query(user=None):
    queryset = Post.objects.select_related("blog").filter(
        publish=True,
        blog__reviewed=True,
        blog__user__is_active=True,
        make_discoverable=True,
        published_date__lte=timezone.now(),
        blog__posts_in_last_12_hours__lte=3
    ).annotate(
        content_length=Length('content')
    ).filter(
        content_length__gte=100
    )

    if user and user.is_authenticated:
        queryset = queryset.filter(
            Q(hidden=False, blog__hidden=False) |
            Q(blog__user=user)
        )
    else:
        queryset = queryset.filter(hidden=False, blog__hidden=False)

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
        
        if request.POST.get("set-values", False):
            post = Post.objects.get(pk=request.POST.get("set-values"))
            post.shadow_votes = int(request.POST.get("shadow-votes"))
            post.lang = request.POST.get('post-lang')
            post.save()

            if post.blog.lang != request.POST.get('blog-lang'):
                post.blog.lang = request.POST.get('blog-lang')
                post.blog.save()

        


def discover(request):
    admin_actions(request)

    # Handle hide/unhide actions
    if request.method == 'POST':
        subdomain = request.POST.get('subdomain')
        action = request.POST.get('action')  # 'hide' or 'unhide'

        if subdomain:
            if request.user.is_authenticated:
                # Update user settings
                hide_list = request.user.settings.discovery_hide_list or []
                
                if action == 'hide' and subdomain not in hide_list:
                    hide_list.append(subdomain)
                elif action == 'unhide' and subdomain in hide_list:
                    hide_list.remove(subdomain)
                
                request.user.settings.discovery_hide_list = hide_list
                request.user.settings.save()
                
                # Redirect to same page to prevent resubmission
                return redirect(request.get_full_path())

    try:
        page = int(request.GET.get("page", 0) or 0)
    except ValueError:
        page = 0
    
    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get("newest")
    random_feed = request.GET.get("random")

    base_query = get_base_query(request.user)
    
    # Get blog objects for display
    hide_list = None
    if request.user.is_authenticated:
        hide_list_subdomains = request.user.settings.discovery_hide_list or []
        hide_list = Blog.objects.filter(subdomain__in=hide_list_subdomains)
        # Exclude hidden blogs from query
        if hide_list:
            base_query = base_query.exclude(blog__in=hide_list)

    lang = request.COOKIES.get('lang')

    if lang:
        base_query = base_query.filter(
            (Q(lang__startswith=lang) & ~Q(lang='')) |
            (Q(lang='') & Q(blog__lang__startswith=lang) & ~Q(blog__lang=''))
        )

    if random_feed:
        probe_langs = {'en', 'pt', 'es', 'zh', 'fr', 'de'}
        use_probes = not lang or lang in probe_langs

        if use_probes:
            # Fast path: random ID probes for common languages.
            agg = Post.objects.aggregate(max_id=Max('id'), min_id=Min('id'))
            results = []
            found_ids = set()
            if agg['max_id']:
                for _ in range(posts_per_page * 10):
                    rand_id = random.randint(agg['min_id'], agg['max_id'])
                    post = base_query.filter(id__gte=rand_id).first()
                    if post and post.id not in found_ids:
                        found_ids.add(post.id)
                        results.append(post)
                    if len(results) >= posts_per_page:
                        break
            posts = results
        else:
            # Slow fallback: ORDER BY random() for rare languages where probes have too low a hit rate
            posts = list(base_query.order_by('?')[:posts_per_page])
    elif newest:
        posts = base_query.order_by("-published_date")
    else:
        posts = base_query.order_by("-score")

    if not random_feed:
        posts = posts[posts_from:posts_to]

    return render(request, "discover.html", {
        "lang": lang,
        "available_languages": get_available_languages(),
        "posts": posts,
        "previous_page": page - 1,
        "next_page": page + 1,
        "posts_from": posts_from,
        "newest": newest,
        "random": random_feed,
        "hide_list": hide_list
    })


def get_available_languages():
    return ["cs", "de", "el", "en", "es", "fi", "fr", "hu", "id", "it", "ja", "ko", "nl", "pl", "pt", "ru", "sv", "tr", "uk", "zh"]


# RSS/Atom feed
def feed(request):
    # Determine feed parameters
    feed_kind = "newest" if request.GET.get("newest") else "trending"
    feed_type = 'rss' if request.GET.get("type") == "rss" else "atom"
    lang = request.GET.get("lang")
    
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
        # Sort by published date
        all_posts = base_query.order_by("-published_date")[:posts_per_page]
        
    else:
        fg.title("Bear Blog Trending Posts")
        fg.subtitle("Trending posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/", rel="alternate")
        # Sort by score and then by published date
        all_posts = base_query.order_by("-score", "-published_date")[:posts_per_page]

    # Reverse the most recent posts
    all_posts = list(all_posts)[::-1]

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{post.blog.useful_domain}/{post.slug}/")
        fe.title(plain_title(post.title))
        fe.author({"name": post.blog.subdomain, "email": "hidden"})
        fe.link(href=f"{post.blog.useful_domain}/{post.slug}/")
        post_content = post.content.replace("{{ email-signup }}", '')
        fe.content(
            clean_text(markdown(post_content, post.blog, post)),
            type="html"
        )
        fe.published(post.published_date)
        fe.updated(post.published_date)

    # Generate the feed string
    feed_str = feed_method(pretty=True)

    return HttpResponse(feed_str, content_type=f"application/xml")


def search(request):
    search_string = request.GET.get('query', "")
    posts = None

    try:
        page = int(request.GET.get("page", 0) or 0)
    except ValueError:
        page = 0

    posts_from = page * posts_per_page
    posts_to = posts_from + posts_per_page

    if search_string:
        posts = (
            get_base_query().filter(
                search_vector=SearchQuery(search_string, search_type='websearch')
            )
            .order_by('-upvotes')[posts_from:posts_to]
        )

    return render(request, "search.html", {
        "posts": posts,
        "search_string": search_string,
        "previous_page": page - 1,
        "next_page": page + 1,
    })


def random_post(request):
    url = random_post_link()
    if not url:
        return redirect('/discover/')
    return redirect(url)


def random_blog(request):
    url = random_blog_link()
    if not url:
        return redirect('/discover/')
    return redirect(url)