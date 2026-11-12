from django.contrib import admin

from .models import Announcement, Assessment, Attendance, Booking, ClassGroup, Question, Session, Submission


class QuestionInline(admin.StackedInline):
    model = Question
    extra = 0


@admin.register(Assessment)
class AssessmentAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'kind', 'lesson', 'is_published', 'required_to_progress', 'due_at')
    list_filter = ('kind', 'is_published', 'course__subject')
    search_fields = ('title', 'course__title')
    inlines = [QuestionInline]


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ('student', 'assessment', 'attempt', 'status', 'percent', 'submitted_at')
    list_filter = ('status',)
    search_fields = ('student__email', 'assessment__title')


@admin.register(Session)
class SessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'kind', 'starts_at', 'duration_minutes', 'is_cancelled')
    list_filter = ('kind', 'is_cancelled')
    search_fields = ('title', 'course__title')
    date_hierarchy = 'starts_at'


admin.site.register(ClassGroup)
admin.site.register(Attendance)
admin.site.register(Booking)
admin.site.register(Announcement)
