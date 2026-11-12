from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Sum
from django.shortcuts import render

from .models import LedgerEntry, Payout
from .services import tutor_balance


@login_required
def earnings(request):
    user = request.user
    if not (user.is_tutor or user.is_platform_admin):
        raise PermissionDenied
    entries = LedgerEntry.objects.filter(tutor=user, account=LedgerEntry.Account.TUTOR) \
        .select_related('course', 'payment__user')
    earned = entries.filter(kind=LedgerEntry.Kind.SALE).aggregate(t=Sum('amount_ngwee'))['t'] or 0
    paid = -(entries.filter(kind=LedgerEntry.Kind.PAYOUT).aggregate(t=Sum('amount_ngwee'))['t'] or 0)
    return render(request, 'ledger/earnings.html', {
        'entries': entries[:100], 'balance': tutor_balance(user), 'earned': earned / 100, 'paid': paid / 100,
        'payouts': Payout.objects.filter(tutor=user)[:20],
    })
