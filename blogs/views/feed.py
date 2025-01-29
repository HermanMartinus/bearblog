from django.core.exceptions import MultipleObjectsReturned
from django.http import HttpResponse
from django.http.response import Http404
from django.utils import timezone
from django.core.cache import cache
from django.utils.text import slugify
from django.db.models import Q

from blogs.helpers import salt_and_hash, unmark
from blogs.models import Blog, RssSubscriber
from blogs.templatetags.custom_tags import markdown
from blogs.views.blog import not_found, resolve_address

from feedgen.feed import FeedGenerator
import os
import re
import tldextract


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
            print(f'Feeds: Cache miss for {CACHE_KEY}')
        except Exception as e:
            print(f'Feeds: Error generating feed for {CACHE_KEY}: {e}')

    else:
        feed = cached_feed
        print(f'Feeds: Cache hit for {CACHE_KEY}')


    # TODO: Have this happen async or more performantly
    log_feed_subscriber(request)
 
    return HttpResponse(feed, content_type='application/xml')


def quick_resolve(request):
    # Gets only the id of the blog with no checking if active
    http_host = request.get_host()
    sites = os.getenv('MAIN_SITE_HOSTS').split(',')
    
    if any(site in http_host for site in sites):
        # Subdomained blog
        subdomain = tldextract.extract(http_host).subdomain
        blog = Blog.objects.filter(subdomain__iexact=subdomain).only('id').first()
    else:
        # Custom domain blog - handle both www and non-www
        domain_no_www = http_host.replace('www.', '')
        blog = Blog.objects.filter(
            Q(domain__iexact=domain_no_www) |
            Q(domain__iexact=f'www.{domain_no_www}')
        ).only('id').first()

    if blog:
        return blog

    raise Http404()
 
    
def log_feed_subscriber(request):
    try:
        hash_id = salt_and_hash(request)
        blog = quick_resolve(request)

        RssSubscriber.objects.only('id').get_or_create(blog=blog, hash_id=hash_id)
    except Exception as e:
        print(f'Feeds: Error logging feed subscriber: {e}')
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
