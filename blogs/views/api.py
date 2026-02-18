import json
import time

from django.core.cache import cache
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt

from blogs.helpers import unique_slug
from blogs.models import Blog, Post

RATE_LIMIT_REQUESTS = 10
RATE_LIMIT_WINDOW = 10  # seconds


def _authenticate(request):
    """Resolve Bearer token to a blog. Returns (blog, None) or (None, JsonResponse error)."""
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return None, JsonResponse({'error': 'Missing or invalid Authorization header'}, status=401)

    token = auth_header[7:].strip()
    if not token:
        return None, JsonResponse({'error': 'Missing token'}, status=401)

    try:
        blog = Blog.objects.get(auth_token=token, user__is_active=True)
    except Blog.DoesNotExist:
        return None, JsonResponse({'error': 'Invalid token'}, status=401)

    if not blog.user.settings.upgraded:
        return None, JsonResponse({'error': 'API access requires an upgraded account'}, status=403)

    window = int(time.time() / RATE_LIMIT_WINDOW)
    cache_key = f'api_ratelimit:{token}:{window}'
    try:
        count = cache.incr(cache_key)
    except ValueError:
        cache.add(cache_key, 0, timeout=RATE_LIMIT_WINDOW * 2)
        count = cache.incr(cache_key)

    if count > RATE_LIMIT_REQUESTS:
        retry_after = RATE_LIMIT_WINDOW - (int(time.time()) % RATE_LIMIT_WINDOW)
        return None, JsonResponse(
            {'error': f'Rate limit exceeded. Maximum {RATE_LIMIT_REQUESTS} requests per {RATE_LIMIT_WINDOW} seconds.'},
            status=429,
            headers={'Retry-After': str(retry_after)},
        )

    return blog, None


def _post_to_summary(post):
    return {
        'uid': post.uid,
        'title': post.title,
        'slug': post.slug,
        'publish': post.publish,
        'published_date': post.published_date.isoformat() if post.published_date else None,
        'tags': json.loads(post.all_tags) if post.all_tags else [],
        'is_page': post.is_page,
    }


def _post_to_dict(post):
    return {
        'uid': post.uid,
        'title': post.title,
        'slug': post.slug,
        'content': post.content,
        'publish': post.publish,
        'published_date': post.published_date.isoformat() if post.published_date else None,
        'tags': json.loads(post.all_tags) if post.all_tags else [],
        'meta_description': post.meta_description,
        'meta_image': post.meta_image,
        'is_page': post.is_page,
        'make_discoverable': post.make_discoverable,
        'canonical_url': post.canonical_url,
    }


def _validate_post_data(data):
    """Returns (True, None) if valid, (False, JsonResponse) if invalid."""
    for field in ('publish', 'is_page', 'make_discoverable'):
        if field in data and not isinstance(data[field], bool):
            return False, JsonResponse({'error': f"'{field}' must be a boolean"}, status=400)

    tags = data.get('tags', [])
    if not isinstance(tags, list) or not all(isinstance(t, str) for t in tags):
        return False, JsonResponse({'error': "'tags' must be an array of strings"}, status=400)

    if len(data.get('title', '')) > 200:
        return False, JsonResponse({'error': "'title' must be 200 characters or fewer"}, status=400)

    return True, None


def _apply_post_data(post, data):
    """Apply writable fields from a parsed JSON dict onto a Post instance."""
    post.title = data.get('title', '')
    post.content = data.get('content', '')
    post.publish = data.get('publish', True)
    post.is_page = data.get('is_page', False)
    post.make_discoverable = data.get('make_discoverable', True)
    post.meta_description = data.get('meta_description', '')
    post.meta_image = data.get('meta_image', '')
    post.canonical_url = data.get('canonical_url', '')
    post.all_tags = json.dumps(data.get('tags', []))

    if data.get('published_date'):
        parsed = parse_datetime(data['published_date'])
        if parsed:
            post.published_date = parsed

    if post.publish and not post.first_published_at:
        post.first_published_at = timezone.now()


@csrf_exempt
def posts_list(request):
    blog, error = _authenticate(request)
    if error:
        return error

    if request.method == 'GET':
        posts = blog.posts.all().order_by('-published_date')
        return JsonResponse({'posts': [_post_to_summary(p) for p in posts]})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        valid, err = _validate_post_data(data)
        if not valid:
            return err

        post = Post(blog=blog, published_date=timezone.now())
        _apply_post_data(post, data)
        post.save()  # generates uid + pk

        post.slug = unique_slug(blog, post, data.get('slug', ''))
        post.save()

        blog.save()
        return JsonResponse(_post_to_dict(post), status=201)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
def post_detail(request, uid):
    blog, error = _authenticate(request)
    if error:
        return error

    try:
        post = blog.posts.get(uid=uid)
    except Post.DoesNotExist:
        return JsonResponse({'error': 'Post not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse(_post_to_dict(post))

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)

        valid, err = _validate_post_data(data)
        if not valid:
            return err

        _apply_post_data(post, data)
        post.slug = unique_slug(blog, post, data.get('slug', ''))
        post.save()

        blog.save()
        return JsonResponse(_post_to_dict(post))

    if request.method == 'DELETE':
        post.delete()
        blog.save()
        return JsonResponse({'deleted': True})

    return JsonResponse({'error': 'Method not allowed'}, status=405)
