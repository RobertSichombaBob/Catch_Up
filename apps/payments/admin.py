from django.contrib import admin, messages

from .models import Payment, PaymentEvent
from .services import refresh_payment


class PaymentEventInline(admin.TabularInline):
    model = PaymentEvent
    extra = 0
    can_delete = False
    readonly_fields = ('kind', 'data', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('reference', 'user', 'course', 'amount', 'network', 'phone_display', 'status', 'created_at')
    list_filter = ('status', 'network', 'provider', 'created_at')
    search_fields = ('id', 'user__email', 'msisdn', 'provider_reference', 'course__title')
    readonly_fields = [f.name for f in Payment._meta.fields]
    inlines = [PaymentEventInline]
    actions = ['check_with_provider']
    date_hierarchy = 'created_at'

    def has_add_permission(self, request):
        return False

    @admin.action(description='Check status with the provider now')
    def check_with_provider(self, request, queryset):
        for payment in queryset.filter(status=Payment.Status.PENDING):
            refresh_payment(payment, force=True)
        messages.success(request, 'Checked the selected pending payments.')
