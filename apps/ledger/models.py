"""Money owed to tutors and to the platform.

Every completed payment is split into ledger entries in the same database
transaction that unlocks the course, so the books and the enrolments can
never disagree. Amounts are whole ngwee (K1 = 100 ngwee), never floats.
Entries are never edited or deleted: a refund adds reversing entries.
"""
import uuid

from django.conf import settings
from django.db import models


class LedgerEntry(models.Model):
    class Account(models.TextChoices):
        TUTOR = 'tutor', 'Tutor earnings'
        PLATFORM = 'platform', 'Platform revenue'
        FEES = 'fees', 'Payment provider fees'

    class Kind(models.TextChoices):
        SALE = 'sale', 'Sale'
        REFUND = 'refund', 'Refund'
        PAYOUT = 'payout', 'Payout to tutor'

    payment = models.ForeignKey('payments.Payment', null=True, blank=True, on_delete=models.PROTECT,
                                related_name='ledger_entries')
    account = models.CharField(max_length=10, choices=Account.choices)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SALE)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                              related_name='ledger_entries')
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.PROTECT, related_name='+')
    amount_ngwee = models.BigIntegerField(help_text='Positive adds to the account, negative takes away')
    tutor_share_percent = models.PositiveSmallIntegerField(default=0)
    memo = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'ledger entries'
        constraints = [models.UniqueConstraint(fields=['payment', 'account', 'kind'],
                                               condition=models.Q(payment__isnull=False),
                                               name='one_entry_per_payment_account_kind')]

    def __str__(self):
        return f'{self.get_account_display()} {self.amount_kwacha:+.2f}'

    @property
    def amount_kwacha(self):
        return self.amount_ngwee / 100


class Payout(models.Model):
    """Money sent from the platform to a tutor's mobile money wallet.
    Created in a monthly batch, approved by an administrator, then sent
    through the payment provider. The tutor's balance only drops when the
    provider confirms the money arrived."""

    class Status(models.TextChoices):
        AWAITING = 'awaiting', 'Awaiting approval'
        SENDING = 'sending', 'Sending'
        COMPLETED = 'completed', 'Paid'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payouts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    msisdn = models.CharField(max_length=12)
    network = models.CharField(max_length=10)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.AWAITING, db_index=True)
    provider = models.CharField(max_length=20, blank=True)
    provider_status = models.CharField(max_length=40, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'K{self.amount} to {self.tutor} ({self.get_status_display()})'
