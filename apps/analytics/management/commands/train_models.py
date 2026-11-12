from django.core.management.base import BaseCommand

from apps.analytics.services import train_risk_model


class Command(BaseCommand):
    help = 'Retrain the machine-learning models (run nightly as a Render Cron Job).'

    def handle(self, *args, **options):
        run, message = train_risk_model()
        self.stdout.write(message)
