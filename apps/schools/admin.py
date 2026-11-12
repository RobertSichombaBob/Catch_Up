from django.contrib import admin

from .models import School, SchoolMember


class MemberInline(admin.TabularInline):
    model = SchoolMember
    extra = 0
    raw_id_fields = ('user',)


@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
    list_display = ('name', 'kind', 'town', 'plan', 'is_approved', 'created_at')
    list_filter = ('kind', 'plan', 'is_approved')
    search_fields = ('name', 'town', 'contact_email')
    inlines = [MemberInline]
    actions = ['approve']

    @admin.action(description='Approve selected schools')
    def approve(self, request, queryset):
        queryset.update(is_approved=True)
