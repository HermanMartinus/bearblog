from time import time

import requests
from requests.exceptions import RequestException

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

    if _request_from_tor(request):
        print("Not upvoting: Tor exit")
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


_tor_exit_cache = {'ips': frozenset(), 'expires': 0}
TOR_EXIT_LIST_URL = 'https://check.torproject.org/torbulkexitlist'


def _tor_exit_ips():
    if time() < _tor_exit_cache['expires']:
        return _tor_exit_cache['ips']
    try:
        response = requests.get(TOR_EXIT_LIST_URL, timeout=3)
        response.raise_for_status()
        ips = frozenset(response.text.split())
        ttl = 60 * 60
    except RequestException:
        # Fail open: keep whatever we had, retry soon rather than block everyone
        ips = _tor_exit_cache['ips']
        ttl = 60
    _tor_exit_cache['ips'] = ips
    _tor_exit_cache['expires'] = time() + ttl
    return ips


def _request_from_tor(request):
    exit_ips = _tor_exit_ips()
    if not exit_ips:
        return False

    candidates = {request.META.get('HTTP_CF_CONNECTING_IP', '').strip()}
    candidates.update(
        part.strip() for part in request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')
    )
    candidates.discard('')

    return any(ip in exit_ips for ip in candidates)
