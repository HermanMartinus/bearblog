
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth import get_user_model
from django.utils.text import slugify

from ipaddr import client_ip
from unicodedata import lookup
import djqscsv

from blogs.forms import NavForm, StyleForm
from blogs.helpers import get_country, is_protected
from blogs.models import Blog, Post, Stylesheet


@login_required
def nav(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

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
        'blog': blog
    })


@login_required
def styles(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == "POST":
        stylesheet = request.POST.get("stylesheet")
        if stylesheet:
            blog.custom_styles = Stylesheet.objects.get(identifier=stylesheet).css
            blog.overwrite_styles = True
            blog.save()
            return redirect('styles', id=blog.subdomain)
        else:
            form = StyleForm(request.POST, instance=blog)
            if form.is_valid():
                form.save()
    else:
        form = StyleForm(instance=blog)

    if request.GET.get("preview"):
        stylesheet = request.GET.get("stylesheet")
        if stylesheet:
            blog.custom_styles = Stylesheet.objects.get(identifier=stylesheet).css
            blog.overwrite_styles = True
            return render(request, 'home.html', {'blog': blog, 'preview': True})

    

    return render(request, 'dashboard/styles.html', {
        'blog': blog,
        'form': form,
        'stylesheets': Stylesheet.objects.all().order_by('pk')
    })



@login_required
def blog_delete(request, id):
    if request.method == "POST":
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)
        blog.delete()
    return redirect('account')


@login_required
def posts_edit(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    posts = Post.objects.filter(blog=blog, is_page=False).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {
        'pages': False,
        'blog': blog,
        'posts': posts
    })

@login_required
def pages_edit(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    posts = Post.objects.filter(blog=blog, is_page=True).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {
        'pages': True,
        'blog': blog,
        'posts': posts
    })


@login_required
def post_delete(request, id, uid):
    if request.method == "POST":
        if request.user.is_superuser:
            blog = get_object_or_404(Blog, subdomain=id)
        else:
            blog = get_object_or_404(Blog, user=request.user, subdomain=id)

        post = get_object_or_404(Post, blog=blog, uid=uid)
        is_page = post.is_page
        post.delete()
        if is_page:
            return redirect('pages_edit', id=blog.subdomain)
    return redirect('posts_edit', id=blog.subdomain)


@login_required
def upgrade(request):
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

        "country_name": country_name,
        "country_emoji": country_emoji,
        "discount": discount,
        "promo_code": promo_code
    })


@login_required
def opt_in_review(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == 'POST':
        spam = request.POST.get("spam", "")
        note = request.POST.get("note", "")
        if spam == 'on':
            blog.reviewer_note = note
            blog.to_review = True
            blog.save()

    return render(request, "dashboard/opt-in-review.html", {"blog": blog})


@login_required
def settings(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)
    
    error_messages = []
    
    if request.method == "POST":
        subdomain = request.POST.get('subdomain')
        lang = request.POST.get('lang', 'en')

        if subdomain:
            subdomain = slugify(subdomain.split('.')[0]).replace('_', '-')
            if not Blog.objects.filter(subdomain=subdomain).exclude(pk=blog.pk).exists() and not is_protected(subdomain):
                blog.subdomain = subdomain
                blog.lang = lang
                blog.save()
                return redirect('settings', id=blog.subdomain)
            else:
                error_messages.append(f'The subdomain "{subdomain}" is reserved')



    if request.GET.get("export", ""):
        return djqscsv.render_to_csv_response(blog.posts)
    

    return render(request, "dashboard/settings.html", {
        "blog": blog,
        "error_messages": error_messages
    })


@login_required
def delete_user(request):
    if request.method == "POST":
        user = get_object_or_404(get_user_model(), pk=request.user.pk)
        user.delete()
        return redirect('/')

    return render(request, 'account/account_confirm_delete.html')
