from django.shortcuts import get_object_or_404, redirect
from django.contrib.sites.models import Site
from django.http import HttpResponse
from blogs.models import Blog

from blogs.helpers import unmark, clean_text, root as get_root
from blogs.views.blog import resolve_address

from feedgen.feed import FeedGenerator
import tldextract


def feed(request):
    address_info = resolve_address(request)
    if not address_info:
        return redirect('/')

    blog = address_info['blog']
    root = address_info['root']

    all_posts = blog.post_set.filter(publish=True, is_page=False).order_by('-published_date')

    fg = FeedGenerator()
    fg.id(f'http://{root}/')
    fg.author({'name': blog.subdomain, 'email': blog.user.email})
    fg.title(blog.title)
    if blog.content:
        fg.subtitle(clean_text(unmark(blog.content)[:160]))
    else:
        fg.subtitle(blog.title)
    fg.link(href=f"http://{root}/", rel='alternate')

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"http://{root}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': blog.subdomain, 'email': blog.user.email})
        fe.link(href=f"http://{root}/{post.slug}/")
        fe.content(clean_text(unmark(post.content)))
        fe.published(post.published_date)

    if request.GET.get('type') == 'rss':
        fg.link(href=f"http://{root}/feed/?type=rss", rel='self')
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type='application/rss+xml')
    else:
        fg.link(href=f"http://{root}/feed/", rel='self')
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type='application/atom+xml')
