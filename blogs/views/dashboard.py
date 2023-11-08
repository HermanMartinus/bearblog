
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from django.db.models import Count
from django.contrib.auth import get_user_model

from ipaddr import client_ip
from unicodedata import lookup
import json
import os
import boto3
import time
import djqscsv

from blogs.forms import NavForm, StyleForm
from blogs.helpers import get_country, sanitise_int
from blogs.models import Blog, Post, Stylesheet, Upvote


@login_required
def nav(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST":
        form = NavForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
        else:
            form = NavForm(instance=blog)
    else:
        form = NavForm(instance=blog)

    return render(request, 'dashboard/nav.html', {
        'form': form,
        'blog': blog,
        'root': blog.useful_domain()
    })


@login_required
def styles(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST":
        form = StyleForm(
            request.POST,
            instance=blog
        )
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = StyleForm(
            instance=blog
        )

    if request.GET.get("style", False):
        style = request.GET.get("style", "default")
        blog.custom_styles = Stylesheet.objects.get(identifier=style).css
        blog.overwrite_styles = True
        if request.GET.get("preview", False):
            return render(request, 'home.html', {'blog': blog, 'preview': True})
        blog.save()
        return redirect('/dashboard/styles/')

    return render(request, 'dashboard/styles.html', {
        'blog': blog,
        'form': form,
        'stylesheets': Stylesheet.objects.all().order_by('pk')
    })


@login_required
def posts_edit(request):
    blog = get_object_or_404(Blog, user=request.user)

    posts = Post.objects.annotate(
        hit_count=Count('hit')).filter(blog=blog).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {
        'posts': posts,
        'blog': blog
    })


@login_required
def post_delete(request, pk):
    blog = get_object_or_404(Blog, user=request.user)
    post = get_object_or_404(Post, blog=blog, pk=sanitise_int(pk))
    post.delete()
    return redirect('/dashboard/posts/')


@csrf_exempt
def upload_image(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST" and blog.upgraded is True:
        file_links = []
        time_string = str(time.time()).split('.')[0]
        count = 0

        for file in request.FILES.getlist('file'):
            extention = file.name.split('.')[-1]
            if extention.lower().endswith(('png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'svg', 'webp')):

                filepath = f'{blog.subdomain}-{time_string}-{count}.{extention}'
                url = f'https://bear-images.sfo2.cdn.digitaloceanspaces.com/{filepath}'
                count = count + 1
                file_links.append(url)

                session = boto3.session.Session()
                client = session.client(
                    's3',
                    endpoint_url='https://sfo2.digitaloceanspaces.com',
                    region_name='sfo2',
                    aws_access_key_id='KKKRU7JXRF6ZOLEGJPPX',
                    aws_secret_access_key=os.getenv('SPACES_SECRET'))

                response = client.put_object(
                    Bucket='bear-images',
                    Key=filepath,
                    Body=file,
                    ContentType=file.content_type,
                    ACL='public-read',
                )

        return HttpResponse(json.dumps(sorted(file_links)), 200)


@login_required
def upgrade(request):
    blog = get_object_or_404(Blog, user=request.user)

    country = get_country(client_ip(request))
    country_name = ''
    country_emoji = ''
    promo_code = ''
    discount = 0

    country_code = country.get("country_code")

    if country_code:
        country_name = country.get('country_name', {})
        country_emoji = lookup(
            f'REGIONAL INDICATOR SYMBOL LETTER {country_code[0]}') + lookup(f'REGIONAL INDICATOR SYMBOL LETTER {country_code[1]}')

        tier_2 = ['AD', 'AG', 'AW', 'BE', 'BS', 'BZ', 'CG', 'CN', 'CW', 'CY', 'DE', 'DM', 'EE', 'ES', 'FR', 'GR', 'HK', 'IT', 'KI',
                  'KN', 'KR', 'LC', 'MO', 'MT', 'NR', 'PG', 'PT', 'PW', 'QA', 'SB', 'SG', 'SI', 'SK', 'SM', 'SX', 'TO', 'UY', 'WS', 'ZW']
        tier_3 = ['AE', 'AL', 'AR', 'AS', 'BA', 'BG', 'BH', 'BN', 'BR', 'BW', 'CD', 'CF', 'CI', 'CL', 'CM', 'CR', 'CV', 'CZ', 'DJ', 'DO',
                  'EC', 'FJ', 'GA', 'GD', 'GN', 'GQ', 'GT', 'HN', 'HR', 'HT', 'HU', 'IQ', 'JM', 'JO', 'KM', 'KW', 'LR', 'LS', 'LT', 'LV',
                  'MA', 'ME', 'MV', 'MX', 'NA', 'NE', 'OM', 'PA', 'PE', 'PL', 'PS', 'RO', 'RS', 'SA', 'SC', 'SN', 'ST', 'SV', 'SZ',
                  'TD', 'TG', 'TM', 'TT', 'VC', 'YE', 'ZA']
        tier_4 = ['AF', 'AM', 'AO', 'AZ', 'BD', 'BF', 'BI', 'BJ', 'BO', 'BT', 'BY', 'CO', 'DZ', 'EG', 'ER', 'ET', 'GE', 'GH', 'GM', 'GW', 'GY',
                  'ID', 'IN', 'KE', 'KG', 'KH', 'KZ', 'LA', 'LB', 'LK', 'LY', 'MD', 'MG', 'MK', 'ML', 'MM', 'MN', 'MR', 'MU', 'MW', 'MY', 'MZ',
                  'NG', 'NI', 'NP', 'PH', 'PK', 'PY', 'RU', 'RW', 'SL', 'SO', 'SR', 'TH', 'TJ', 'TL', 'TN', 'TR', 'TZ', 'UA', 'UG', 'UZ', 'VN', 'ZM']

        if country_code in tier_2:
            promo_code = 'PADDINGTON'
            discount = 15
        if country_code in tier_3:
            promo_code = 'YOGI'
            discount = 30
        if country_code in tier_4:
            promo_code = 'BALOO'
            discount = 50

    return render(request, "dashboard/upgrade.html", {
        "blog": blog,
        "country_name": country_name,
        "country_emoji": country_emoji,
        "discount": discount,
        "promo_code": promo_code
    })


@login_required
def opt_in_review(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == 'POST':
        spam = request.POST.get("spam", "")
        note = request.POST.get("note", "")
        if spam == 'on':
            blog.reviewer_note = note
            blog.to_review = True
            blog.save()

    return render(request, "dashboard/opt-in-review.html", {"blog": blog})


@login_required
def settings(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.GET.get("export", ""):
        return djqscsv.render_to_csv_response(blog.post_set)

    return render(request, "dashboard/account.html", {
        "blog": blog
    })


@login_required
def delete_user(request):
    if request.method == "POST":
        user = get_object_or_404(get_user_model(), pk=request.user.pk)
        user.delete()
        return redirect('/')

    return render(request, 'account/account_confirm_delete.html')


class PostDelete(DeleteView):
    model = Post
    success_url = '/dashboard/posts'
