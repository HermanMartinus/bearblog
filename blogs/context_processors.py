import os

# Add tz and admin_passport to every page
def extra(request):
    return {
        'tz': request.COOKIES.get('timezone', 'UTC'),
        'bear_root': 'http://' + os.getenv('MAIN_SITE_HOSTS').split(',')[0]
    }
