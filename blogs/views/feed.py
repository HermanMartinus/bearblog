from django.http import HttpResponse
from django.utils import timezone

from blogs.helpers import unmark
from blogs.templatetags.custom_tags import markdown
from blogs.views.blog import not_found, resolve_address

from feedgen.feed import FeedGenerator


def feed(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    all_posts = blog.post_set.filter(publish=True, is_page=False, published_date__lte=timezone.now()).order_by('-published_date')[:10]
    all_posts = sorted(list(all_posts), key=lambda post: post.published_date)

    fg = FeedGenerator()
    fg.id(blog.useful_domain())
    fg.author({'name': blog.subdomain, 'email': 'hidden'})
    fg.title(blog.title)
    fg.subtitle(blog.meta_description or unmark(blog.content) or blog.title)
    fg.link(href=f"{blog.useful_domain()}/", rel='alternate')

    name = blog.subdomain
    if blog.user.first_name and blog.user.last_name:
        name = f"{blog.user.first_name} {blog.user.last_name}"

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{blog.useful_domain()}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': name, 'email': 'hidden'})
        fe.link(href=f"{blog.useful_domain()}/{post.slug}/")
        fe.content(markdown(post.content.replace('{{ email-signup }}', ''), blog), type="html")
        fe.published(post.published_date)
        fe.updated(post.published_date)

    if request.GET.get('type') == 'rss':
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type='application/rss+xml')
    else:
        fg.link(href=f"{blog.useful_domain()}/feed/", rel='self')
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type='application/atom+xml')
