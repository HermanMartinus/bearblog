import os

# Add tz, admin_passport, and blog context to every page
def extra(request):
    blog = getattr(request, 'blog', None)
    return {
        'tz': request.COOKIES.get('timezone', 'UTC'),
        'admin_passport': request.COOKIES.get('admin_passport') == os.getenv('ADMIN_PASSPORT'),
        'bear_root': 'http://' + os.getenv('MAIN_SITE_HOSTS').split(',')[0],
        'blog': blog
    }
