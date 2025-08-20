from django.http import HttpResponse
from django.utils import timezone

from blogs.helpers import unmark
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

    blog = resolve_address(request)
    if not blog:
        return not_found(request)
    try:
        feed = generate_feed(blog, feed_type, tag)
    except Exception as e:
        print(f'Feeds: Error generating feed for {blog.subdomain}: {e}')
        feed = ''
        raise e
    
    response = HttpResponse(feed, content_type='application/xml')
    response['Cache-Tag'] = blog.subdomain
    return response


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
        fe.title(clean_string(post.title))
        fe.author({'name': blog.subdomain, 'email': 'hidden'})
        fe.link(href=f"{blog.useful_domain}/{post.slug}/")
        if post.meta_description:
            fe.summary(clean_string(post.meta_description))
        
        post_content = post.content.replace('{{ email-signup }}', '')
        # post_content = post.content.replace('{{ email_signup }}', '')

        fe.content(clean_string(markdown(post_content, blog, post)), type="html")
        
        fe.published(post.published_date)
        fe.updated(post.last_modified)
        
        for tag in post.tags:
            fe.category(term=tag)

    if feed_type == "atom":
        fg.link(href=f"{blog.useful_domain}/feed/", rel='self')
        return fg.atom_str(pretty=True)
    elif feed_type == "rss":
        fg.link(href=f"{blog.useful_domain}/feed/?type=rss", rel='self', type='application/rss+xml')
        fg.link(href=f"{blog.useful_domain}", rel='self')
        return fg.rss_str(pretty=True)
