import nh3
from django.utils.text import slugify

ALLOWED_TAGS = {
    'a', 'abbr', 'aside', 'b', 'blockquote', 'br', 'caption', 'code', 'dd', 'del', 'details',
    'div', 'dl', 'dt', 'em', 'figcaption', 'figure', 'h2', 'h3', 'h4', 'h5', 'hr', 'i', 'img',
    'kbd', 'li', 'mark', 'ol', 'p', 'pre', 'section', 'small', 'span', 'strong', 'sub',
    'summary', 'sup', 'table', 'tbody', 'td', 'tfoot', 'th', 'thead', 'tr', 'u', 'ul',
}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title', 'target'},
    'img': {'src', 'alt', 'title', 'width', 'height', 'loading'},
    'td': {'colspan', 'rowspan'},
    'th': {'colspan', 'rowspan', 'scope'},
    'ol': {'start', 'type'},
    '*': {'class', 'id'},
}


def sanitize_html(html):
    """Strip scripts, event handlers, iframes and unsafe links from lesson HTML.
    Lesson content is rendered as HTML, so it must always pass through here."""
    return nh3.clean(
        html or '',
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes={'http', 'https', 'mailto'},
        link_rel='noopener noreferrer',
    )


def unique_slugify(instance, value, slug_field='slug', max_length=80, queryset=None):
    base = slugify(value)[:max_length].strip('-') or 'item'
    if queryset is None:
        queryset = instance.__class__._default_manager.all()
    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)
    slug, n = base, 2
    while queryset.filter(**{slug_field: slug}).exists():
        suffix = f'-{n}'
        slug = f'{base[:max_length - len(suffix)]}{suffix}'
        n += 1
    return slug
