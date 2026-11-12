import uuid

from django.conf import settings
from django.db import models

from .networks import NETWORK_CHOICES, display_msisdn


class Payment(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'Waiting for approval'
        COMPLETED = 'completed', 'Paid'
        FAILED = 'failed', 'Failed'

    # The id is sent to the provider as the deposit id, so it is a UUID.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='payments')
    course = models.ForeignKey('courses.Course', on_delete=models.PROTECT, related_name='payments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.PROTECT,
                                related_name='payments_received',
                                help_text='Who gets access, when a parent pays for their child. Empty: the payer.')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default='ZMW')
    network = models.CharField(max_length=10, choices=NETWORK_CHOICES)
    msisdn = models.CharField('phone number', max_length=12)
    provider = models.CharField(max_length=20)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider_status = models.CharField(max_length=40, blank=True)
    provider_reference = models.CharField(max_length=100, blank=True)
    failure_code = models.CharField(max_length=60, blank=True)
    failure_message = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    last_checked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'course', 'status'])]

    def __str__(self):
        return f'K{self.amount} {self.get_network_display()} {self.get_status_display()} ({self.user})'

    @property
    def phone_display(self):
        return display_msisdn(self.msisdn)

    @property
    def learner(self):
        return self.student or self.user

    @property
    def is_final(self):
        return self.status in (self.Status.COMPLETED, self.Status.FAILED)

    @property
    def reference(self):
        return 'CU-' + self.id.hex[:8].upper()


class PaymentEvent(models.Model):
    """Audit trail: every request to and answer from the provider."""
    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='events')
    kind = models.CharField(max_length=30)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
