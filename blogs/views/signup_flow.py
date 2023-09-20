
import os
from django.http import Http404
from django.shortcuts import render, redirect
from django.utils.text import slugify
from django.contrib.auth import get_user_model, login
from django.core.validators import validate_email
from blogs.helpers import random_error_message

from blogs.models import Blog

from akismet import Akismet


def signup(request):
    title = request.POST.get('title', '')
    subdomain = slugify(request.POST.get('subdomain', ''))
    content = request.POST.get('content', '')
    email = request.POST.get('email', '')
    password = request.POST.get('password', '')

    error_messages = []

    if request.user.is_authenticated:
        return redirect('dashboard')

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

    # If all fields are present do spam check and create account
    if title and subdomain and content and email and password:
        # Simple honeypot pre-db check
        if honeypot_check(request) or spam_check(title, content, email, request.META['REMOTE_ADDR'], request.META['HTTP_USER_AGENT']):
            error_messages.append(random_error_message())
            return render(request, 'signup_flow/step_1.html', {
                'error_messages': error_messages,
                'dodgy': True})

        User = get_user_model()
        user = User.objects.filter(email=email).first()
        if not user:
            user = User.objects.create_user(username=email, email=email, password=password)

        user.backend = 'django.contrib.auth.backends.ModelBackend'

        if not Blog.objects.filter(user=user).exists():
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


def honeypot_check(request):
    if request.POST.get('date'):
        return True
    if request.POST.get('name'):
        return True
    if request.POST.get('email', '').endswith('@cleardex.io'):
        return True

    title = request.POST.get('title', '').lower()
    spam_keywords = ['court records', 'labbia', 'insurance', 'seo', 'gamble', 'gambling', 'crypto', 'marketing', 'bangalore']

    for keyword in spam_keywords:
        if keyword in title:
            return True

    return False


def spam_check(title, content, email, user_ip, user_agent):
    akismet_api = Akismet(os.getenv('AKISMET_KEY'), 'https://bearblog.dev')

    is_spam = akismet_api.check(
        user_ip=user_ip,
        user_agent=user_agent,
        comment_author=title,
        comment_author_email=email,
        comment_content=content,
        comment_type='signup',
    )

    if is_spam > 0:
        return True
    return False
