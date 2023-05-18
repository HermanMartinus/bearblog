
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.contrib.auth import get_user_model, login

from blogs.models import Blog


def signup(request):

    if request.POST.get('date') or request.POST.get('name'):
        raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")

    if request.user.is_authenticated:
        return redirect('dashboard')
    error_messages = []

    title = request.POST.get('title', '')
    subdomain = slugify(request.POST.get('subdomain', ''))
    content = request.POST.get('content', '')
    email = request.POST.get('email', '')
    password = request.POST.get('password', '')

    # Check password valid
    if password and len(password) < 6:
        error_messages.append('Password is too short')
        password = ''

    # Check subdomain unique
    if subdomain and Blog.objects.filter(subdomain=subdomain).count():
        error_messages.append('This subdomain has already been taken')
        subdomain = ''

    # Check email unique and valid
    if email and Blog.objects.filter(user__email__iexact=email).count():
        error_messages.append('There is already a blog with this email address')
        email = ''

    if title and subdomain and content and email and password:
        print('Create new blog!')

        User = get_user_model()
        user = User.objects.create_user(username=email, email=email, password=password)
        user.backend = 'django.contrib.auth.backends.ModelBackend'

        Blog.objects.create(title=title, subdomain=subdomain, content=content, user=user)

        # Log in the user
        login(request, user)

        return redirect('dashboard')

    if title and subdomain and content and (not email or not password):
        return render(request, 'signup_flow/step_2.html', {
            'error_messages': error_messages,
            'title': title,
            'subdomain': subdomain,
            'content': content,
            'email': email,
            'password': password
        })

    return render(request, 'signup_flow/step_1.html', {
        'error_messages': error_messages,
        'title': title,
        'subdomain': subdomain,
        'content': content
    })
