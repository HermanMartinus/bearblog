from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.core.signing import BadSignature, TimestampSigner

from blogs.models import Post, Upvote
from blogs.helpers import salt_and_hash


upvote_signer = TimestampSigner(salt='upvote')

# Tokens are minted per page load, so this only needs to outlast a reading session
# Form is prepopulates with uid which is invalid, then gets swapped out with a valid one
UPVOTE_TOKEN_MAX_AGE = 60 * 60 * 12


def valid_upvote_token(token, uid, hash_id):
    # Binding the hash to the token means a token minted for one visitor is
    # useless to another, so rotating IPs costs a fetch per upvote
    try:
        return upvote_signer.unsign(token, max_age=UPVOTE_TOKEN_MAX_AGE) == f"{uid}:{hash_id}"
    except BadSignature:
        return False


def get_upvote_info(request, uid):
    post = get_object_or_404(Post.objects.only('upvotes'), uid=uid)
    hash_id = salt_and_hash(request, 'year')
    upvoted = post.upvote_set.filter(hash_id=hash_id).exists()

    response = JsonResponse({
        "upvoted": upvoted,
        "upvote_count": post.upvotes,
        "token": upvote_signer.sign(f"{uid}:{hash_id}"),
    })
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@csrf_exempt
def upvote(request):
    uid = request.POST.get("uid", "")

    response = HttpResponse('Upvoted', content_type='text/plain')
    response['X-Robots-Tag'] = 'noindex, nofollow'

    if not uid:
        print("Not upvoting: Missing uid")
        return response

    if request.POST.get("title", False):
        print("Not upvoting: Honeypot filled")
        return response

    hash_id = salt_and_hash(request, 'year')
    if not valid_upvote_token(request.POST.get("token", ""), uid, hash_id):
        print("Not upvoting: Invalid token")
        return response

    post = Post.objects.filter(uid=uid).first()
    if not post:
        print("Not upvoting: Unknown post", uid)
        return response

    try:
        upvote, created = Upvote.objects.get_or_create(post=post, hash_id=hash_id)

        if created:
            print("Upvoting", post)
        else:
            print("Not upvoting: Duplicate upvote")
    except Upvote.MultipleObjectsReturned:
        print("Not upvoting: Duplicate upvote")

    return response
