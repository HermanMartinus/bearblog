from django.core.exceptions import MultipleObjectsReturned
from django.http import HttpResponse
from django.utils import timezone
from django.core.cache import cache
from django.utils.text import slugify

from blogs.helpers import salt_and_hash, unmark
from blogs.models import RssSubscriber
from blogs.templatetags.custom_tags import markdown
from blogs.views.blog import not_found, resolve_address

from feedgen.feed import FeedGenerator
import re

def clean_string(s):
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)


def feed(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    tag = request.GET.get('q')

    if "rss" in request.GET.get('type', 'atom') or "rss" in request.path:
        feed_type = "rss"
    else:
        feed_type = "atom"

    
    log_feed_subscriber(request, blog)

    try:
        if feed_type == "atom":
            return atom(blog, tag)
        elif feed_type == "rss":
            return rss(blog, tag)
    
    except ValueError as e:
        return HttpResponse(f"An error occurred while generating the feed: {e}")


def atom(blog, tag=None):
    CACHE_KEY = f'{blog.subdomain}_atom_feed'
    if tag:
        CACHE_KEY += "_" + slugify(tag).replace('-', '_')

    cached_feed = cache.get(CACHE_KEY)

    if cached_feed is None:
        atom_feed = generate_feed(blog, "atom", tag)
        cache.set(CACHE_KEY, atom_feed, timeout=None)
    else:
        atom_feed = cached_feed

    return HttpResponse(atom_feed, content_type='application/atom+xml')


def rss(blog, tag=None):
    CACHE_KEY = f'{blog.subdomain}_rss_feed'
    if tag:
        CACHE_KEY += "_" + slugify(tag).replace('-', '_')

    cached_feed = cache.get(CACHE_KEY)

    if cached_feed is None:
        rss_feed = generate_feed(blog, "rss")
        cache.set(CACHE_KEY, rss_feed, timeout=None)
    else:
        rss_feed = cached_feed

    return HttpResponse(rss_feed, content_type='application/rss+xml')


def log_feed_subscriber(request, blog):
    try:
        hash_id = salt_and_hash(request)
        RssSubscriber.objects.get_or_create(blog=blog, hash_id=hash_id)
    except MultipleObjectsReturned:
        pass


def generate_feed(blog, feed_type="atom", tag=None):
    all_posts = blog.posts.filter(publish=True, is_page=False, published_date__lte=timezone.now())
    if tag:
        all_posts = all_posts.filter(all_tags__icontains=tag)
    all_posts = all_posts.order_by('-published_date')[:10]
    all_posts = sorted(list(all_posts), key=lambda post: post.published_date)

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
