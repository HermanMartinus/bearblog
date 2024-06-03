# Add tz to every page for formatting date
def tz(request):
    return {'tz': request.COOKIES.get('timezone', 'UTC')}