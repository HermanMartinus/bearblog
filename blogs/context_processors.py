import os

# Add tz and admin_passport to every page
def extra(request):
    return {
        'tz': request.COOKIES.get('timezone', 'UTC'),
        'admin_passport': request.COOKIES.get('admin_passport') == os.getenv('ADMIN_PASSPORT'),
        'bear_root': 'http://' + os.getenv('MAIN_SITE_HOSTS').split(',')[0]
    }
