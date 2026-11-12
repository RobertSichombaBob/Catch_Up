from django.core.management.base import BaseCommand

from apps.ledger.services import create_payout_batch


class Command(BaseCommand):
    help = "Create this month's tutor payouts for approval in the admin (run on the 1st)."

    def add_arguments(self, parser):
        parser.add_argument('--minimum', default=None, help='Smallest balance to pay out, in kwacha')

    def handle(self, *args, **opts):
        created = create_payout_batch(opts['minimum'])
        self.stdout.write(f'Created {len(created)} payout(s) awaiting approval.')
