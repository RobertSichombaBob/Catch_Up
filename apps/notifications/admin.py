from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.utils import timezone

from .models import Announcement, Notification
from .services import notify


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'user', 'is_read', 'emailed', 'created_at')
    list_filter = ('is_read', 'emailed')
    search_fields = ('title', 'user__email')


@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'send_email', 'sent_at', 'recipients')
    actions = ['send_announcement']

    @admin.action(description='Send to students now (in the app, and by email if ticked)')
    def send_announcement(self, request, queryset):
        User = get_user_model()
        for ann in queryset.filter(sent_at__isnull=True):
            users = User.objects.filter(is_active=True, role=User.Role.STUDENT)
            if ann.course_id:
                users = users.filter(enrollments__course_id=ann.course_id, enrollments__is_active=True)
            count = 0
            for user in users.distinct().iterator():
                notify(user, ann.title, ann.body, ann.url, send_email=ann.send_email)
                count += 1
            ann.sent_at, ann.recipients = timezone.now(), count
            ann.save(update_fields=['sent_at', 'recipients'])
            messages.success(request, f'"{ann.title}" sent to {count} student(s).')
