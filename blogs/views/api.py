import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.utils.text import slugify

from blogs.models import Blog, Post


def _get_blog_from_token(request):
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Token "):
        return None
    token = auth[6:].strip()
    if not token:
        return None
    try:
        return Blog.objects.get(api_token=token)
    except Blog.DoesNotExist:
        return None


@csrf_exempt
@require_http_methods(["POST", "PUT", "PATCH"])
def post_api(request, slug=None):
    blog = _get_blog_from_token(request)
    if blog is None:
        return JsonResponse({"error": "Invalid or missing API token."}, status=401)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if request.method == "POST":
        title = data.get("title", "").strip()
        if not title:
            return JsonResponse({"error": "'title' is required."}, status=400)

        content = data.get("content", "")
        published = bool(data.get("published", False))
        post_slug = data.get("slug") or slugify(title)

        if Post.objects.filter(blog=blog, slug=post_slug).exists():
            return JsonResponse({"error": "A post with this slug already exists."}, status=409)

        post = Post.objects.create(
            blog=blog,
            title=title,
            slug=post_slug,
            content=content,
            published=published,
            publish_date=timezone.now() if published else None,
        )
        return JsonResponse({"slug": post.slug, "title": post.title, "published": post.published}, status=201)

    # PUT / PATCH
    if not slug:
        return JsonResponse({"error": "'slug' is required in the URL for updates."}, status=400)

    try:
        post = Post.objects.get(blog=blog, slug=slug)
    except Post.DoesNotExist:
        return JsonResponse({"error": "Post not found."}, status=404)

    if "title" in data:
        post.title = data["title"].strip()
    if "content" in data:
        post.content = data["content"]
    if "published" in data:
        newly_published = bool(data["published"])
        if newly_published and not post.published and post.publish_date is None:
            post.publish_date = timezone.now()
        post.published = newly_published
    if "slug" in data:
        new_slug = data["slug"].strip()
        if new_slug and new_slug != post.slug:
            if Post.objects.filter(blog=blog, slug=new_slug).exists():
                return JsonResponse({"error": "A post with this slug already exists."}, status=409)
            post.slug = new_slug

    post.save()
    return JsonResponse({"slug": post.slug, "title": post.title, "published": post.published}, status=200)
