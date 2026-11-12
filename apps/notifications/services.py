import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from .models import Notification

logger = logging.getLogger(__name__)


def absolute(url):
    url = str(url or '')
    if url.startswith('http://') or url.startswith('https://'):
        return url
    return settings.SITE_URL + (url if url.startswith('/') else '/' + url)


def send_templated_email(to, subject, template, context):
    """Send an HTML email with a plain-text part. Returns True on success.
    A mail server problem is logged and never breaks the page the user is on."""
    ctx = {'site_name': settings.SITE_NAME, 'site_url': settings.SITE_URL,
           'support_email': settings.SUPPORT_EMAIL, **context}
    try:
        html = render_to_string(f'{template}.html', ctx)
        try:
            text = render_to_string(f'{template}.txt', ctx)
        except Exception:  # noqa: BLE001  (no .txt version: derive one)
            text = strip_tags(html)
        msg = EmailMultiAlternatives(subject, text, settings.DEFAULT_FROM_EMAIL, [to])
        msg.attach_alternative(html, 'text/html')
        msg.send()
        return True
    except Exception:  # noqa: BLE001
        logger.exception('Could not send "%s" email to %s', template, to)
        return False


def notify(user, title, body='', url='', send_email=True, email_template='emails/notification', context=None):
    """Create an in-app notification and, if the user allows it, email it."""
    url = str(url or '')
    note = Notification.objects.create(user=user, title=title[:160], body=body, url=url[:300])
    if send_email and user.email_notifications and user.email:
        ctx = {'user': user, 'title': title, 'body': body, 'action_url': absolute(url) if url else '',
               **(context or {})}
        note.emailed = send_templated_email(user.email, title, email_template, ctx)
        note.save(update_fields=['emailed'])
    return note


