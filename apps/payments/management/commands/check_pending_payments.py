from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.payments.models import Payment
from apps.payments.services import refresh_payment


class Command(BaseCommand):
    help = 'Re-check payments still waiting for approval (safety net; run every 10 minutes).'

    def handle(self, *args, **options):
        waiting = Payment.objects.filter(status=Payment.Status.PENDING,
                                         created_at__gte=timezone.now() - timedelta(days=2))
        n = 0
        for payment in waiting:
            refresh_payment(payment, force=True)
            n += 1
        self.stdout.write(f'Checked {n} pending payment(s).')
