from taggit.models import Tag

from django.contrib.postgres.search import TrigramSimilarity
from django.core.mail import send_mail
from django.core.paginator import EmptyPage, Paginator, PageNotAnInteger
from django.db.models import Count
from django.db.models.functions import Greatest
from django.shortcuts import get_object_or_404, render

from .forms import CommentForm, EmailPostForm, SearchForm
from .models import Post


def post_detail(request, year, month, day, post, similar_posts_number=4):
    """Displays a Post page with comments and a list of similar Posts.

    Args:
        request (HttpRequest):

        year (int):
            Year of Post Published.
        month (int):
            Month of Post Published.
        day (int):
            Day of Post Published.
        post (str):
            Post slug.
        similar_posts_number (int):
            Number of similar posts on a page.

    Returns:
         An HttpResponse.
    """

    post = get_object_or_404(Post, slug=post, status='PUBLISHED',
                             publish__year=year, publish__month=month,
                             publish__day=day)

    comments = post.comments.filter(active=True)
    new_comment = None
    comment_form = None

    if request.method == 'POST':
        comment_form = CommentForm(data=request.POST)
        if comment_form.is_valid():
            # Create a comment.
            new_comment = comment_form.save(commit=False)
            # Bind a comment to the current post.
            new_comment.post = post
            new_comment.save()
        else:
            comment_form = CommentForm()

    # Forming a similar posts list.
    post_tags_ids = post.tags.values_list('id', flat=True)

    similar_posts = (Post.published.filter(tags__in=post_tags_ids)
                     .exclude(id=post.id)
                     .annotate(same_tags=Count('tags'))
                     .order_by('-same_tags', '-publish')
                     )[:similar_posts_number]

    return render(request, 'blog/post/detail.html',
                  {'post': post,
                   'comments': comments,
                   'new_comment': new_comment,
                   'comment_form': comment_form,
                   'similar_posts': similar_posts})


def post_list(request, tag_slug=None, posts_on_page=3):
    """Displays the main blog page with paginated Post's.

    Args:
        request (HttpRequest):

        posts_on_page (int):
            Post number on one page.
        tag_slug (str):
            Tag for Post filtering.

    Returns:
         An HttpResponse.
    """
    published_posts = Post.published.all()
    tag = None
    if tag_slug:
        tag = get_object_or_404(Tag, slug=tag_slug)
        published_posts = published_posts.filter(tags__in=[tag])

    paginator = Paginator(published_posts, posts_on_page)
    page = request.GET.get('page')
    try:
        posts = paginator.page(page)
    except PageNotAnInteger:
        posts = paginator.page(1)
    except EmptyPage:
        # If the page number passed in the request is greater than the number
        # of existing page numbers.
        posts = paginator.page(paginator.num_pages)
    return render(request, 'blog/post/list.html',
                  {'page': page, 'posts': posts, 'tag': tag})


def post_search(request):
    """Search posts by a query in title or body.

    Args:
        request (HttpRequest):
            Request with search query passed with the GET method.
    Returns:
         An HttpResponse with search results.
    """
    form = SearchForm()
    query = None
    results = []
    if 'query' in request.GET:
        form = SearchForm(request.GET)
    if form.is_valid():
        query = form.cleaned_data['query']
        threshold = 0.003
        # Annotate table strings by SearchVectors and filter by relevance.
        # Using SearchRank for comment ranking.
        results = (Post.objects
                   .annotate(
                        similarity=Greatest(
                            TrigramSimilarity('title', query),
                            TrigramSimilarity('body', query)
                        )
                    )
                   .filter(similarity__gte=threshold)
                   .order_by('-similarity'))
    return render(request, 'blog/post/search_results.html',
                  {'form': form, 'query': query, 'results': results})


def post_share_by_email(request, post_id):
    """Displays a share Post by email page.

    Args:
        request (HttpRequest):

        post_id (int):
            The primary key of the post.

    Returns:
         HttpResponse with a page about the status of the email sending.
    """
    # Get a Post object by id. In theory get_object_or_404 uses Django ORM
    # (objects.get), they are equivalent anyway.
    post = get_object_or_404(Post, id=post_id, status='PUBLISHED')
    sent = False
    sent_failed = False
    if request.method == 'POST':
        # Pass data from request to form for validate.
        form = EmailPostForm(request.POST)
        # List of validation errors contain in forms.errors.
        if form.is_valid():
            # Contain only valid fields.
            cd = form.cleaned_data

            # Sending email.
            # get_absolute_url() returns the path relative from the application
            post_url = request.build_absolute_uri(post.get_absolute_url())

            subject = (f"{cd['name']} ({cd['email']}) recommends you reading "
                       f"{post.title}")

            message = (f'Read "{post.title}" at {post_url}\n\n'
                       f"{cd['name']}'s comments:{cd['comments']}")

            from_email = 'django.framework.email.test@gmail.com'
            try:
                send_mail(subject, message, from_email, [cd['destination']])
                sent = True
            except Exception:
                sent_failed = True
    else:
        form = EmailPostForm()
    return render(request, 'blog/post/share.html',
                  {'post': post, 'form': form, 'sent': sent,
                   'sent_failed': sent_failed})
