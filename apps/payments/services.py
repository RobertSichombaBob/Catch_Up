import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.courses.models import Enrollment
from apps.ledger.services import record_sale
from apps.notifications.services import notify

from .models import Payment, PaymentEvent
from .networks import normalise_msisdn
from .providers import COMPLETED, FAILED, ProviderResult, get_provider

logger = logging.getLogger(__name__)

CHECK_INTERVAL = timedelta(seconds=4)
NOT_FOUND_GIVE_UP_AFTER = timedelta(minutes=10)
SIMULATOR_EXPIRES_AFTER = timedelta(minutes=30)


class PaymentRefused(Exception):
    """Raised when we will not start a payment (bad number, already enrolled...)."""


def start_payment(user, course, network, phone, student=None):
    """Start a mobile money payment. A parent can pay for a linked child by
    passing student; the child then gets the access."""
    msisdn = normalise_msisdn(phone)
    if not msisdn:
        raise PaymentRefused('Enter a valid Zambian mobile number, for example 0971234567.')
    if student is not None and student != user:
        if not user.child_links.filter(student=student).exists():
            raise PaymentRefused('You can only pay for children linked to your account.')
    learner = student or user
    enrollment = course.enrollment_for(learner)
    if enrollment and enrollment.has_access and not enrollment.renewal_due:
        raise PaymentRefused('You already have this course.' if learner == user
                             else f'{learner.display_name} already has this course.')

    provider = get_provider()
    # Reuse a recent payment that is still waiting, instead of sending a
    # second prompt to the same phone.
    recent = Payment.objects.filter(
        user=user, course=course, status=Payment.Status.PENDING, msisdn=msisdn, network=network,
        student=student if student is not None and student != user else None,
        created_at__gte=timezone.now() - timedelta(minutes=3),
    ).first()
    if recent:
        return recent

    payment = Payment.objects.create(
        user=user, course=course, amount=course.price, currency='ZMW',
        student=student if student is not None and student != user else None,
        network=network, msisdn=msisdn, provider=provider.name,
    )
    result = provider.start(payment)
    _log(payment, 'start', result)
    apply_result(payment, result)
    payment.refresh_from_db()
    return payment


def refresh_payment(payment, force=False):
    """Ask the provider for the latest status, at most every few seconds."""
    if payment.is_final:
        return payment
    now = timezone.now()
    if not force and payment.last_checked_at and now - payment.last_checked_at < CHECK_INTERVAL:
        return payment
    Payment.objects.filter(pk=payment.pk).update(last_checked_at=now)

    provider = get_provider(payment.provider)
    result = provider.check(payment)
    _log(payment, 'check', result)

    age = now - payment.created_at
    if result.provider_status == 'NOT_FOUND':
        if payment.provider_status in ('UNREACHABLE',) or payment.provider_status.startswith('HTTP_5'):
            # Our first request may never have arrived. Sending it again is safe
            # because the provider ignores duplicates of the same deposit id.
            result = provider.start(payment)
            _log(payment, 'retry_start', result)
        elif age > NOT_FOUND_GIVE_UP_AFTER:
            result = ProviderResult(FAILED, 'NOT_FOUND', failure_code='NOT_FOUND',
                                    failure_message='The payment request did not reach the network. Please try again.')
    elif payment.provider == 'simulator' and age > SIMULATOR_EXPIRES_AFTER:
        result = ProviderResult(FAILED, 'EXPIRED', failure_code='PAYMENT_NOT_APPROVED',
                                failure_message='The payment was not approved in time.')

    apply_result(payment, result)
    payment.refresh_from_db()
    return payment


def apply_result(payment, result):
    """Record a provider answer. Safe to call many times and from several
    requests at once: the row lock makes sure the course is granted and the
    student is notified exactly once."""
    newly = None
    with transaction.atomic():
        locked = Payment.objects.select_for_update().get(pk=payment.pk)
        if locked.is_final:
            return locked
        if result.provider_status:
            locked.provider_status = result.provider_status[:40]
        if result.reference:
            locked.provider_reference = result.reference[:100]
        if result.state == COMPLETED:
            locked.status = Payment.Status.COMPLETED
            locked.completed_at = timezone.now()
            enrollment, _ = Enrollment.objects.select_for_update().get_or_create(
                user=locked.learner, course=locked.course, defaults={'payment': locked})
            enrollment.is_active = True
            enrollment.payment = locked
            enrollment.extend_access(settings.ACCESS_PERIOD_DAYS)
            enrollment.save(update_fields=['is_active', 'payment', 'access_until'])
            record_sale(locked)
            newly = COMPLETED
        elif result.state == FAILED:
            locked.status = Payment.Status.FAILED
            locked.failure_code = result.failure_code[:60]
            locked.failure_message = result.failure_message[:255]
            newly = FAILED
        locked.save()

    if newly == COMPLETED:
        transaction.on_commit(lambda: _notify_paid(locked))
    elif newly == FAILED:
        transaction.on_commit(lambda: _notify_failed(locked))
    return locked


def _notify_paid(payment):
    course = payment.course
    learner = payment.learner
    if learner != payment.user:
        notify(learner, title=f'{course.title} is unlocked for you',
               body=f'{payment.user.display_name} paid for your course. Start learning now.',
               url=reverse('courses:detail', args=[course.slug]))
    notify(
        payment.user,
        title=f'Payment received: {course.title}',
        body=f'We received K{payment.amount:.0f} from {payment.phone_display}. '
             f'You have full access for {settings.ACCESS_PERIOD_DAYS} days.',
        url=reverse('courses:detail', args=[course.slug]),
        email_template='emails/payment_success',
        context={'payment': payment, 'course': course},
    )
    for link in learner.parent_links.select_related('parent').exclude(parent=payment.user):
        notify(
            link.parent,
            title=f'{learner.first_name or learner.display_name} enrolled in {course.title}',
            body=f'A payment of K{payment.amount:.0f} was received. You can follow progress on your dashboard.',
            url=reverse('portal:parent_home'),
        )
    tutor = course.tutor
    notify(
        tutor,
        title=f'New student in {course.title}',
        body=f'{learner.display_name} just enrolled.',
        url=reverse('core:tutor_dashboard'),
        send_email=False,
    )


def _notify_failed(payment):
    notify(
        payment.user,
        title=f'Payment not completed: {payment.course.title}',
        body=payment.failure_message or 'The payment could not be completed. You have not been charged.',
        url=reverse('payments:checkout', args=[payment.course.slug]),
        email_template='emails/payment_failed',
        context={'payment': payment, 'course': payment.course},
    )


def _log(payment, kind, result):
    PaymentEvent.objects.create(payment=payment, kind=kind, data={
        'state': result.state, 'provider_status': result.provider_status,
        'failure_code': result.failure_code, 'uncertain': result.uncertain, 'raw': result.raw,
    })
