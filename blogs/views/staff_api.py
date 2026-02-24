import json
import os
from functools import wraps

from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from blogs.models import Blog, Post
from blogs.views.discover import get_base_query


def api_auth(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        key = request.headers.get('X-API-Key')
        if not key or key != os.getenv('STAFF_API_KEY'):
            return JsonResponse({'error': 'Unauthorized'}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def blog_data(b):
    return {
        'subdomain': b.subdomain,
        'domain': b.domain,
        'title': b.title,
        'hidden': b.hidden,
        'flagged': b.flagged,
        'reviewed': b.reviewed,
        'reviewer_note': b.reviewer_note,
        'dodginess_score': b.dodginess_score,
        'permanent_ignore': b.permanent_ignore,
        'to_review': b.to_review,
        'created_date': b.created_date.isoformat(),
        'last_posted': b.last_posted.isoformat() if b.last_posted else None,
        'posts_in_last_12_hours': b.posts_in_last_12_hours,
        'user': {
            'email': b.user.email,
            'name': f"{b.user.first_name} {b.user.last_name}".strip() or b.subdomain,
        },
    }


def post_data(p, full_content=False):
    return {
        'pk': p.pk,
        'title': p.title,
        'slug': p.slug,
        'blog': p.blog.subdomain,
        'url': f"{p.blog.useful_domain}/{p.slug}/",
        'published_date': p.published_date.isoformat(),
        'hidden': p.hidden,
        'make_discoverable': p.make_discoverable,
        'score': p.score,
        'upvotes': p.upvotes,
        'shadow_votes': p.shadow_votes,
        'content': p.content if full_content else p.content[:300],
    }


BLOG_UPDATABLE = {'hidden', 'flagged', 'reviewed', 'reviewer_note', 'permanent_ignore', 'to_review'}
POST_UPDATABLE = {'hidden', 'make_discoverable', 'shadow_votes'}


@csrf_exempt
@api_auth
def blog(request, subdomain):
    try:
        b = Blog.objects.select_related('user').get(subdomain=subdomain)
    except Blog.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse(blog_data(b))

    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        try:
            for field, value in data.items():
                if field in BLOG_UPDATABLE:
                    setattr(b, field, value)
            b.save()
        except (TypeError, ValueError, ValidationError) as e:
            return JsonResponse({'error': f'Invalid value: {e}'}, status=400)
        return JsonResponse(blog_data(b))

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@csrf_exempt
@api_auth
def post(request, pk):
    try:
        p = Post.objects.select_related('blog__user').get(pk=pk)
    except Post.DoesNotExist:
        return JsonResponse({'error': 'Not found'}, status=404)

    if request.method == 'GET':
        return JsonResponse(post_data(p, full_content=True))

    if request.method == 'PATCH':
        try:
            data = json.loads(request.body)
        except (json.JSONDecodeError, ValueError):
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
        try:
            for field, value in data.items():
                if field in POST_UPDATABLE:
                    setattr(p, field, value)
            p.save()
        except (TypeError, ValueError, ValidationError) as e:
            return JsonResponse({'error': f'Invalid value: {e}'}, status=400)
        return JsonResponse(post_data(p, full_content=True))

    return JsonResponse({'error': 'Method not allowed'}, status=405)


@api_auth
def most_recent_posts(request):
    qs = get_base_query().order_by('-published_date')[:160]
    return JsonResponse({'posts': [post_data(p) for p in qs]})
