import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create the owner account from DJANGO_SUPERUSER_EMAIL and DJANGO_SUPERUSER_PASSWORD, once.'

    def handle(self, *args, **options):
        email = os.environ.get('DJANGO_SUPERUSER_EMAIL', '').strip().lower()
        password = os.environ.get('DJANGO_SUPERUSER_PASSWORD', '')
        if not email or not password:
            self.stdout.write('DJANGO_SUPERUSER_EMAIL/PASSWORD not set; skipped.')
            return
        User = get_user_model()
        if User.objects.filter(email__iexact=email).exists():
            self.stdout.write(f'{email} already exists.')
            return
        User.objects.create_superuser(email=email, password=password, first_name='Owner', role=User.Role.ADMIN)
        self.stdout.write(self.style.SUCCESS(f'Created administrator {email}.'))
