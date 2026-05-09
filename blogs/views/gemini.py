from django.shortcuts import render, get_object_or_404
from django.http import HttpResponse
from blogs.models import Blog, Post
from django.utils.text import slugify
import re

def remove_html_tags(text):
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def gemini_content(request, blog_slug, post_slug):
    blog = get_object_or_404(Blog, slug=blog_slug)
    post = get_object_or_404(Post, blog=blog, slug=post_slug)
    
    # Convert HTML to GemText
    title = post.title
    content = post.content
    
    # Remove HTML tags
    clean_content = remove_html_tags(content)
    
    # Convert line breaks
    clean_content = clean_content.replace('\r\n', '\n').replace('\r', '\n')
    
    # Basic formatting - convert headings
    lines = clean_content.split('\n')
    formatted_lines = []
    for line in lines:
    if line.startswith('# '):
        formatted_lines.append(f"# {line[2:]}")
    elif line.startswith('## '):
        formatted_lines.append(f"## {line[3:]}")
    elif line.startswith('### '):
        formatted_lines.append(f"### {line[4:]}")
    elif line.startswith('> '):
        formatted_lines.append(f"> {line[2:]}")
    elif line.startswith('- '):
        formatted_lines.append(f"* {line[2:]}")
    else:
        formatted_lines.append(line)
    
    gemtext_content = "\n".join(formatted_lines)
    
    # Create the full GemText document
    gemtext = f"# {title}\n\n"
    gemtext += f"Published: {post.published_date.strftime('%Y-%m-%d')}\n\n"
    gemtext += gemtext_content
    
    # Add links at the end
    gemtext += f"\n=> /{blog.slug} Home\n"
    
    response = HttpResponse(gemtext, content_type='text/gemini')
    response['Content-Disposition'] = f'inline; filename="{post.slug}.gmi"'
    return response

def gemini_blog(request, blog_slug):
    blog = get_object_or_404(Blog, slug=blog_slug)
    posts = Post.objects.filter(blog=blog, is_page=False).order_by('-published_date')
    
    gemtext = f"# {blog.title}\n\n"
    if blog.content:
        gemtext += f"{remove_html_tags(blog.content)}\n\n"
    
    gemtext += "## Posts\n\n"
    for post in posts:
        gemtext += f"=> /{blog.slug}/{post.slug} {post.title}\n"
    
    gemtext += f"\n=> /{blog.slug} Home\n"
    
    response = HttpResponse(gemtext, content_type='text/gemini')
    response['Content-Disposition'] = f'inline; filename="{blog.slug}.gmi"'
    return response