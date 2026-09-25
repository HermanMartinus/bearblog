from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt

from blogs.models import Post, Upvote
from blogs.helpers import salt_and_hash


def get_upvote_info(request, uid):
    post = get_object_or_404(Post.objects.only('upvotes'), uid=uid)
    hash_id = salt_and_hash(request, 'year')
    upvoted = post.upvote_set.filter(hash_id=hash_id).exists()

    response = JsonResponse({
        "upvoted": upvoted,
        "upvote_count": post.upvotes,
    })
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@csrf_exempt
def upvote(request):
    uid = request.POST.get("uid", "")

    response = HttpResponse('Upvoted', content_type='text/plain')
    response['X-Robots-Tag'] = 'noindex, nofollow'

    if not uid:
        return response

    hash_id = salt_and_hash(request, 'year')
    post = Post.objects.filter(uid=uid).first()
    if not post:
        return response

    try:
        Upvote.objects.get_or_create(
            post=post,
            hash_id=hash_id,
        )
    except Upvote.MultipleObjectsReturned:
        pass

    return response
