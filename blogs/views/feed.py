from django.core.exceptions import MultipleObjectsReturned
from django.http import HttpResponse
from django.utils import timezone
from django.core.cache import cache
from django.utils.text import slugify

from blogs.helpers import salt_and_hash, unmark
from blogs.models import Blog, RssSubscriber
from blogs.templatetags.custom_tags import markdown
from blogs.views.blog import not_found, resolve_address

from feedgen.feed import FeedGenerator
import re


def clean_string(s):
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)


def feed(request):
    tag = request.GET.get('q')

    if "rss" in request.GET.get('type', 'atom') or "rss" in request.path:
        feed_type = "rss"
    else:
        feed_type = "atom"

    CACHE_KEY = f'{request.get_host()}_{feed_type}_feed'
    if tag:
        CACHE_KEY += "_" + slugify(tag).replace('-', '_')

    cached_feed = cache.get(CACHE_KEY)

    if cached_feed is None:
        blog = resolve_address(request)
        if not blog:
            return not_found(request)
        try:
            feed = generate_feed(blog, feed_type, tag)
            cache.set(CACHE_KEY, feed, timeout=None)
            print(f'Feed cache miss for {CACHE_KEY}')
        except Exception as e:
            print(f'Error generating feed for {CACHE_KEY}: {e}')

        
    else:
        feed = cached_feed
        print(f'Feed cache hit for {CACHE_KEY}')


    # TODO: Have this happen async or more performantly
    # log_feed_subscriber(request)
 
    # return HttpResponse("<html><body><h1>Hello</h1></body></html>", content_type='text/html')
    return HttpResponse(feed, content_type='application/xml')


def log_feed_subscriber(request):
    try:
        hash_id = salt_and_hash(request)
        blog = resolve_address(request)
        RssSubscriber.objects.get_or_create(blog=blog, hash_id=hash_id)
    except MultipleObjectsReturned:
        pass


def generate_feed(blog, feed_type="atom", tag=None):
    all_posts = blog.posts.filter(publish=True, is_page=False, published_date__lte=timezone.now())

    if tag:
        all_posts = all_posts.filter(all_tags__icontains=tag)

    all_posts = all_posts.order_by('-published_date')[:10]
    # Reverse the most recent posts
    all_posts = list(all_posts)[::-1] 

    fg = FeedGenerator()
    fg.id(blog.useful_domain)
    fg.author({'name': blog.subdomain, 'email': 'hidden'})
    fg.title(blog.title)
    fg.subtitle(blog.meta_description or unmark(blog.content)[:157] + '...' or blog.title)
    fg.link(href=f"{blog.useful_domain}/", rel='alternate')

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{blog.useful_domain}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': blog.subdomain, 'email': 'hidden'})
        fe.link(href=f"{blog.useful_domain}/{post.slug}/")
        if post.meta_description:
            fe.summary(post.meta_description)
        try:
            fe.content(markdown(post.content.replace('{{ email-signup }}', ''), post), type="html")
        except ValueError:
            fe.content(markdown(clean_string(post.content.replace('{{ email-signup }}', '')), post), type="html")
        fe.published(post.published_date)
        fe.updated(post.last_modified)
        
        for tag in post.tags:
            fe.category(term=tag)

    if feed_type == "atom":
        fg.link(href=f"{blog.useful_domain}/atom/", rel='self')
        return fg.atom_str(pretty=True)
    elif feed_type == "rss":
        fg.link(href=f"{blog.useful_domain}/rss/", rel='self')
        return fg.rss_str(pretty=True)
