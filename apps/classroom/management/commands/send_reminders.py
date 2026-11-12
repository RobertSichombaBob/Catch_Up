"""Run every 15 minutes (Render Cron Job): session reminders an hour before,
and daily renewal reminders for subscriptions about to end."""
from django.conf import settings
from django.core.management.base import BaseCommand
from django.urls import reverse
from django.utils import timezone

from apps.classroom.services import send_session_reminders
from apps.courses.models import Enrollment
from apps.notifications.models import Notification
from apps.notifications.services import notify


class Command(BaseCommand):
    help = 'Send session reminders and subscription renewal reminders.'

    def handle(self, *args, **options):
        sent = send_session_reminders()
        now = timezone.now()
        renewals = 0
        soon = Enrollment.objects.filter(is_active=True, access_until__gt=now,
                                         access_until__lte=now + timezone.timedelta(days=3)).select_related('course',
                                                                                                           'user')
        for e in soon:
            title = f'Renew {e.course.title}: {e.days_left} day{"s" if e.days_left != 1 else ""} left'
            if Notification.objects.filter(user=e.user, title=title,
                                           created_at__gte=now - timezone.timedelta(hours=20)).exists():
                continue
            url = reverse('payments:checkout', args=[e.course.slug])
            notify(e.user, title=title, body=f'Your access ends on {timezone.localtime(e.access_until):%d %B}. '
                                             f'Renew for K{e.course.price:.0f} to keep learning without a break.',
                   url=url)
            for link in e.user.parent_links.select_related('parent'):
                notify(link.parent, title=f'{e.user.first_name}: {title}', body='You can renew for them from your '
                                                                                 'dashboard.', url=url)
            renewals += 1
        self.stdout.write(f'{sent} session reminder(s), {renewals} renewal reminder(s). '
                          f'Access period is {settings.ACCESS_PERIOD_DAYS} days.')
