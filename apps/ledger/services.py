from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db.models import Sum

from .models import LedgerEntry


def to_ngwee(amount):
    return int((Decimal(amount) * 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def split(gross_ngwee, tutor_percent, fee_percent):
    """Return (fee, tutor, platform) in ngwee. The fee comes off the top and
    the rest is shared. The tutor's share is rounded down, so any odd ngwee
    goes to the platform and the three parts always add up to the gross."""
    fee = (gross_ngwee * Decimal(fee_percent) / 100).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
    fee = int(fee)
    net = gross_ngwee - fee
    tutor = net * tutor_percent // 100
    return fee, tutor, net - tutor


def record_sale(payment):
    """Write the split for a completed payment. Must be called inside the
    transaction that completes it. Calling it twice changes nothing."""
    if payment.ledger_entries.filter(kind=LedgerEntry.Kind.SALE).exists():
        return
    course = payment.course
    tutor_percent = 0 if course.is_platform_course else settings.TUTOR_SHARE_PERCENT
    fee, tutor_amt, platform_amt = split(to_ngwee(payment.amount), tutor_percent, settings.PAYMENT_FEE_PERCENT)
    common = {'payment': payment, 'course': course, 'kind': LedgerEntry.Kind.SALE,
              'tutor_share_percent': tutor_percent}
    rows = [LedgerEntry(account=LedgerEntry.Account.PLATFORM, amount_ngwee=platform_amt, **common)]
    if tutor_amt:
        rows.append(LedgerEntry(account=LedgerEntry.Account.TUTOR, tutor=course.tutor, amount_ngwee=tutor_amt, **common))
    if fee:
        rows.append(LedgerEntry(account=LedgerEntry.Account.FEES, amount_ngwee=fee, **common))
    LedgerEntry.objects.bulk_create(rows)


def tutor_balance(tutor):
    """Earnings not yet paid out, in kwacha."""
    total = LedgerEntry.objects.filter(tutor=tutor, account=LedgerEntry.Account.TUTOR) \
        .aggregate(t=Sum('amount_ngwee'))['t'] or 0
    return Decimal(total) / 100


def totals(qs=None):
    qs = qs if qs is not None else LedgerEntry.objects.all()
    rows = qs.values('account').annotate(t=Sum('amount_ngwee'))
    out = {a: Decimal(0) for a in LedgerEntry.Account.values}
    for r in rows:
        out[r['account']] = Decimal(r['t'] or 0) / 100
    return out


# ------------------------------------------------------------------ Payouts --

def create_payout_batch(minimum=None):
    """One payout per tutor whose unpaid balance is at least the minimum and
    who has a valid payout number. Skips tutors with a payout already open."""
    from django.contrib.auth import get_user_model

    from apps.payments.networks import detect_network, normalise_msisdn

    from .models import Payout
    minimum = Decimal(minimum if minimum is not None else settings.PAYOUT_MINIMUM)
    created = []
    User = get_user_model()
    for tutor in User.objects.filter(role='tutor', tutor_profile__status='approved'):
        if Payout.objects.filter(tutor=tutor, status__in=[Payout.Status.AWAITING, Payout.Status.SENDING]).exists():
            continue
        balance = tutor_balance(tutor)
        phone = tutor.tutor_profile.payout_phone or tutor.phone
        msisdn = normalise_msisdn(phone or '')
        if balance < minimum or not msisdn:
            continue
        created.append(Payout.objects.create(tutor=tutor, amount=balance, msisdn=msisdn,
                                             network=detect_network(phone) or 'MTN'))
    return created


def send_payout(payout, approved_by):
    from django.db import transaction

    from apps.payments.providers import get_provider

    from .models import Payout
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout.pk)
        if payout.status != Payout.Status.AWAITING:
            return payout
        if tutor_balance(payout.tutor) < payout.amount:
            payout.status = Payout.Status.CANCELLED
            payout.failure_message = 'Balance changed since the batch was made.'
            payout.save()
            return payout
        payout.status = Payout.Status.SENDING
        payout.approved_by = approved_by
        payout.provider = settings.PAYMENT_PROVIDER
        payout.save()
    result = get_provider(payout.provider).payout(payout)
    return apply_payout_result(payout, result)


def apply_payout_result(payout, result):
    from django.db import transaction
    from django.utils import timezone

    from apps.notifications.services import notify
    from apps.payments.providers import COMPLETED, FAILED

    from .models import Payout
    with transaction.atomic():
        payout = Payout.objects.select_for_update().get(pk=payout.pk)
        if payout.status != Payout.Status.SENDING:
            return payout
        payout.provider_status = (result.provider_status or '')[:40]
        if result.reference:
            payout.provider_reference = result.reference[:100]
        if result.state == COMPLETED:
            payout.status = Payout.Status.COMPLETED
            payout.completed_at = timezone.now()
            LedgerEntry.objects.create(account=LedgerEntry.Account.TUTOR, kind=LedgerEntry.Kind.PAYOUT,
                                       tutor=payout.tutor, amount_ngwee=-to_ngwee(payout.amount),
                                       memo=f'Payout {payout.id.hex[:8]} to {payout.msisdn}')
        elif result.state == FAILED:
            payout.status = Payout.Status.FAILED
            payout.failure_message = (result.failure_message or '')[:255]
        payout.save()
    if payout.status == Payout.Status.COMPLETED:
        notify(payout.tutor, title=f'K{payout.amount:,.2f} sent to your mobile money',
               body=f'Your Catch Up earnings were paid to {payout.msisdn}.', url='/earnings/')
    return payout
