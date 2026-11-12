from django.contrib import admin

from .models import LedgerEntry


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'account', 'kind', 'tutor', 'course', 'kwacha', 'tutor_share_percent', 'payment')
    list_filter = ('account', 'kind', 'created_at')
    search_fields = ('tutor__email', 'course__title', 'memo')
    date_hierarchy = 'created_at'
    readonly_fields = [f.name for f in LedgerEntry._meta.fields]

    @admin.display(description='Amount (K)')
    def kwacha(self, obj):
        return f'{obj.amount_kwacha:,.2f}'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


from django.contrib import messages  # noqa: E402

from .models import Payout  # noqa: E402
from .services import send_payout  # noqa: E402


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'tutor', 'amount', 'msisdn', 'network', 'status', 'provider_reference')
    list_filter = ('status', 'network')
    search_fields = ('tutor__email', 'msisdn', 'provider_reference')
    readonly_fields = [f.name for f in Payout._meta.fields]
    actions = ['approve_and_send']

    def has_add_permission(self, request):
        return False

    @admin.action(description='Approve and send the selected payouts')
    def approve_and_send(self, request, queryset):
        done = 0
        for payout in queryset.filter(status=Payout.Status.AWAITING):
            send_payout(payout, request.user)
            done += 1
        messages.success(request, f'Sent {done} payout(s). Check their status in the list.')
