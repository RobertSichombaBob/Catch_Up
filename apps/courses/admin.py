from django.contrib import admin

from .models import Course, Enrollment, Lesson, LessonProgress, Module, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'order', 'colour')
    prepopulated_fields = {'slug': ('name',)}


class ModuleInline(admin.TabularInline):
    model = Module
    extra = 0


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ('title', 'subject', 'tutor', 'level', 'price', 'is_published')
    list_filter = ('subject', 'level', 'is_published')
    search_fields = ('title', 'summary')
    inlines = [ModuleInline]


class LessonInline(admin.StackedInline):
    model = Lesson
    extra = 0
    fields = ('title', 'slug', 'order', 'is_preview', 'minutes', 'content')


@admin.register(Module)
class ModuleAdmin(admin.ModelAdmin):
    list_display = ('title', 'course', 'order')
    list_filter = ('course',)
    inlines = [LessonInline]


@admin.register(Lesson)
class LessonAdmin(admin.ModelAdmin):
    list_display = ('title', 'module', 'order', 'is_preview', 'minutes')
    list_filter = ('module__course', 'is_preview')
    search_fields = ('title', 'content')


@admin.register(Enrollment)
class EnrollmentAdmin(admin.ModelAdmin):
    list_display = ('user', 'course', 'is_active', 'created_at', 'payment')
    list_filter = ('course', 'is_active')
    search_fields = ('user__email', 'course__title')
    raw_id_fields = ('user', 'payment', 'last_lesson')


admin.site.register(LessonProgress)
