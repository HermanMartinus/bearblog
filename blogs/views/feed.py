from django.core.exceptions import MultipleObjectsReturned
from django.http import HttpResponse, HttpResponseServerError
from django.utils import timezone
from django.core.cache import cache

from blogs.helpers import salt_and_hash, unmark
from blogs.models import RssSubscriber
from blogs.templatetags.custom_tags import markdown
from blogs.views.blog import not_found, resolve_address

from feedgen.feed import FeedGenerator
import re
import logging

logger = logging.getLogger(__name__)

CACHE_TIMEOUT = 3600  # 1 hour in seconds

def clean_string(s):
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', s)

def feed(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    tag = request.GET.get('q')
    
    CACHE_KEY = f'{blog.subdomain}_all_posts'
    cached_queryset = cache.get(CACHE_KEY)

    if cached_queryset is None:
        all_posts = blog.posts.filter(publish=True, is_page=False, published_date__lte=timezone.now())
        cache.set(CACHE_KEY, all_posts, CACHE_TIMEOUT)
    else:
        all_posts = cached_queryset

    if tag:
        all_posts = all_posts.filter(all_tags__icontains=tag)

    all_posts = all_posts.order_by('-published_date')[:10]
    all_posts = sorted(list(all_posts), key=lambda post: post.published_date)

    all_posts = all_posts

    fg = FeedGenerator()
    fg.id(blog.useful_domain)
    fg.author({'name': blog.subdomain, 'email': 'hidden'})
    fg.title(blog.title)
    fg.subtitle(blog.meta_description or unmark(blog.content)[:157] + '...' or blog.title)
    fg.link(href=f"{blog.useful_domain}/", rel='alternate')
    

    name = blog.subdomain
    if blog.user.first_name and blog.user.last_name:
        name = f"{blog.user.first_name} {blog.user.last_name}"

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{blog.useful_domain}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': name, 'email': 'hidden'})
        fe.link(href=f"{blog.useful_domain}/{post.slug}/")
        if post.meta_description:
            fe.summary(post.meta_description)
        try:
            fe.content(markdown(post.content.replace('{{ email-signup }}', ''), post), type="html")
        except ValueError:
            fe.content(markdown(clean_string(post.content.replace('{{ email-signup }}', '')), post), type="html")
        fe.published(post.published_date)
        fe.updated(post.last_modified)

    # Log feed request
    try:
        hash_id = salt_and_hash(request)
        RssSubscriber.objects.get_or_create(blog=blog, hash_id=hash_id)
    except MultipleObjectsReturned:
        pass

    try:
        if request.GET.get('type') == 'rss':
            rssfeed = fg.rss_str(pretty=True)
            return HttpResponse(rssfeed, content_type='application/rss+xml')
        else:
            fg.link(href=f"{blog.useful_domain}/feed/", rel='self')
            atomfeed = fg.atom_str(pretty=True)
            return HttpResponse(atomfeed, content_type='application/atom+xml')
    except ValueError as e:
        # logger.error(f'Error generating feed for {blog}', exc_info=True)
        return HttpResponseServerError("An error occurred while generating the feed.")
