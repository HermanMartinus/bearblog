from datetime import timedelta
from django.http.response import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Count, ExpressionWrapper, F, FloatField
from django.db.models.functions import Log
from django.utils import timezone
from django.db.models.functions import Now
from django.contrib.sites.models import Site

from blogs.models import Post, Upvote
from blogs.helpers import clean_text, sanitise_int

from feedgen.feed import FeedGenerator
from pg_utils import Seconds
from ipaddr import client_ip
import mistune

gravity = 1.2
posts_per_page = 20


@csrf_exempt
def discover(request):
    page = 0
    gravity = request.GET.get("gravity", 1.2)

    if request.GET.get("page", 0):
        page = sanitise_int(request.GET.get("page"), 7)

    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get("newest")
    top = request.GET.get("top")

    if newest:
        posts = (
            Post.objects.annotate(
                upvote_count=Count("upvote"),
            )
            .filter(
                publish=True,
                blog__reviewed=True,
                blog__blocked=False,
                show_in_feed=True,
                published_date__lte=timezone.now(),
            )
            .order_by("-published_date")
            .select_related("blog")[posts_from:posts_to]
        )
    elif top:
        posts = (
            Post.objects.annotate(
                upvote_count=Count("upvote"),
            )
            .filter(
                publish=True,
                blog__reviewed=True,
                blog__blocked=False,
                show_in_feed=True,
                published_date__lte=timezone.now(),
            )
            .order_by("-score", "-published_date")
            .select_related("blog")
            .prefetch_related("upvote_set")[posts_from:posts_to]
        )
    else:
        # Trending
        posts = (
            Post.objects.annotate(
                upvote_count=Count("upvote"),
                rating=ExpressionWrapper(
                    (
                        (Count("upvote"))
                        / ((Seconds(Now() - F("published_date"))) + 4) ** gravity
                    )
                    * 100000,
                    output_field=FloatField(),
                ),
            )
            .filter(
                publish=True,
                blog__reviewed=True,
                blog__blocked=False,
                show_in_feed=True,
                published_date__lte=timezone.now(),
            )
            .order_by("-rating", "-published_date")
            .select_related("blog")
            .prefetch_related("upvote_set")[posts_from:posts_to]
        )

    return render(request, "discover.html", {
            "site": Site.objects.get_current(),
            "posts": posts,
            "previous_page": page - 1,
            "next_page": page + 1,
            "posts_from": posts_from,
            "gravity": gravity,
            "newest": newest,
        },
    )


def feed(request):
    fg = FeedGenerator()
    fg.id("bearblog")
    fg.author({"name": "Bear Blog", "email": "hi@bearblog.dev"})

    newest = request.GET.get("newest")
    if newest:
        fg.title("Bear Blog Most Recent Posts")
        fg.subtitle("Most recent posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/?newest=True", rel="alternate")
        all_posts = (
            Post.objects.annotate(
                upvote_count=Count("upvote"),
            )
            .filter(
                publish=True,
                blog__reviewed=True,
                blog__blocked=False,
                show_in_feed=True,
                published_date__lte=timezone.now(),
            )
            .order_by("-published_date")
            .select_related("blog")[0:posts_per_page]
        )
    else:
        fg.title("Bear Blog Trending Posts")
        fg.subtitle("Trending posts on Bear Blog")
        fg.link(href="https://bearblog.dev/discover/", rel="alternate")
        all_posts = (
            Post.objects.annotate(
                upvote_count=Count("upvote"),
                rating=ExpressionWrapper(
                    (
                        (Count("upvote") - 1)
                        / ((Seconds(Now() - F("published_date"))) + 4) ** gravity
                    )
                    * 100000,
                    output_field=FloatField(),
                ),
            )
            .filter(
                publish=True,
                blog__reviewed=True,
                blog__blocked=False,
                show_in_feed=True,
                published_date__lte=timezone.now(),
            )
            .order_by("-rating", "-published_date")
            .select_related("blog")
            .prefetch_related("upvote_set")[0:posts_per_page]
        )

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{post.blog.useful_domain()}/{post.slug}/")
        fe.title(post.title)
        fe.author({"name": post.blog.subdomain, "email": "hidden"})
        fe.link(href=f"{post.blog.useful_domain()}/{post.slug}/")
        fe.content(clean_text(mistune.html(post.content)), type="html")
        fe.published(post.published_date)
        fe.updated(post.published_date)

    if request.GET.get("type") == "rss":
        fg.link(href=f"{post.blog.useful_domain()}/feed/?type=rss", rel="self")
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type="application/rss+xml")
    else:
        fg.link(href=f"{post.blog.useful_domain()}/feed/", rel="self")
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type="application/atom+xml")
