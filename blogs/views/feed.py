from django.http.response import Http404
from django.http import HttpResponse
from django.utils import timezone

from blogs.helpers import unmark, clean_text
from blogs.views.blog import resolve_address

from feedgen.feed import FeedGenerator
import mistune


def feed(request):
    blog = resolve_address(request)

    if not blog:
        raise Http404("Blog does not exist")

    all_posts = blog.post_set.filter(publish=True, is_page=False, published_date__lte=timezone.now()).order_by('-published_date')

    fg = FeedGenerator()
    fg.id(blog.useful_domain())
    fg.author({'name': blog.subdomain, 'email': 'hidden'})
    fg.title(blog.title)
    fg.subtitle(blog.meta_description or unmark(blog.content) or blog.title)
    fg.link(href=f"{blog.useful_domain()}/", rel='alternate')

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{blog.useful_domain()}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': blog.subdomain, 'email': 'hidden'})
        fe.link(href=f"{blog.useful_domain()}/{post.slug}/")
        fe.content(clean_text(mistune.html(post.content)), type="html")
        fe.published(post.published_date)
        fe.updated(post.published_date)

    if request.GET.get('type') == 'rss':
        fg.link(href=f"{blog.useful_domain()}/feed/?type=rss", rel='self')
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type='application/rss+xml')
    else:
        fg.link(href=f"{blog.useful_domain()}/feed/", rel='self')
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type='application/atom+xml')
