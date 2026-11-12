from django.conf import settings
from django.db import models


class Notification(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False, db_index=True)
    emailed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'is_read'])]

    def __str__(self):
        return self.title


class Announcement(models.Model):
    """Written in the admin. Saving with 'send now' ticked notifies every
    student (or every student in one course) in the app and by email."""
    title = models.CharField(max_length=160)
    body = models.TextField()
    url = models.CharField(max_length=300, blank=True, help_text='Optional link, e.g. /courses/')
    course = models.ForeignKey('courses.Course', null=True, blank=True, on_delete=models.SET_NULL,
                               help_text='Leave empty to send to all students')
    send_email = models.BooleanField(default=True)
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    recipients = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
