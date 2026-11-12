from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'level', 'is_active', 'date_joined')
    list_filter = ('role', 'level', 'is_active', 'is_staff')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('-date_joined',)
    fieldsets = (
        (None, {'fields': ('email', 'username', 'password')}),
        ('Profile', {'fields': ('first_name', 'last_name', 'role', 'phone', 'level', 'institution',
                                'headline', 'bio', 'email_notifications')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates', {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {'classes': ('wide',), 'fields': ('email', 'username', 'role', 'password1', 'password2')}),
    )
