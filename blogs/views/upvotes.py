from time import time

import requests
from requests.exceptions import RequestException

from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.core.signing import BadSignature, TimestampSigner, b62_decode

from blogs.models import Post, Upvote
from blogs.helpers import salt_and_hash, trusted_client_ip


upvote_signer = TimestampSigner(salt='upvote')

# Tokens are minted per page load, so this only needs to outlast a reading session
UPVOTE_TOKEN_MAX_AGE = 60 * 60 * 12
UPVOTE_TOKEN_MIN_AGE = 3


def valid_upvote_token_age(token, uid, hash_id):
    try:
        value = upvote_signer.unsign(token, max_age=UPVOTE_TOKEN_MAX_AGE)
        if value != f"{uid}:{hash_id}":
            return None
        timestamp = token.rsplit(upvote_signer.sep, 2)[-2]
        return time() - b62_decode(timestamp)
    except BadSignature:
        return None


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

    marked_reason = ''
    if request.POST.get("title", False):
        marked_reason = 'Honeypot filled'
    elif 'timezone' not in request.COOKIES:
        marked_reason = 'Timezone cookie'
    elif _request_from_tor(request):
        marked_reason = 'Tor exit'

    hash_id = salt_and_hash(request, 'year')
    if not marked_reason:
        token_age = valid_upvote_token_age(request.POST.get("token", ""), uid, hash_id)
        if token_age is None:
            marked_reason = 'Invalid token'
        elif token_age < UPVOTE_TOKEN_MIN_AGE:
            marked_reason = 'Quick submission'

    post = Post.objects.filter(uid=uid).first()
    if not post:
        print("Not upvoting: Unknown post", uid)
        return response

    try:
        upvote, created = Upvote.objects.get_or_create(
            post=post,
            hash_id=hash_id,
            defaults={
                'marked': bool(marked_reason),
                'marked_reason': marked_reason,
            },
        )

        if created:
            print("Upvoting:", post, marked_reason)
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

    return trusted_client_ip(request) in exit_ips
