from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.db.models import F
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CourseForm, LessonForm, MaterialForm
from .materials import readable_html
from .models import (Course, CourseMaterial, Enrollment, Lesson, LessonProgress, Module, Subject,
                     active_enrollment_q)


def catalog(request):
    courses = Course.objects.published().select_related('subject', 'tutor') \
        .annotate(lesson_count=Count('modules__lessons', distinct=True))
    subject_slug = request.GET.get('subject', '')
    level = request.GET.get('level', '')
    q = request.GET.get('q', '').strip()[:100]
    if subject_slug:
        courses = courses.filter(subject__slug=subject_slug)
    if level in (Course.Level.A_LEVEL, Course.Level.UNIVERSITY):
        courses = courses.filter(level__in=[level, Course.Level.BOTH])
    year = request.GET.get('year', '')
    if year in ('as', 'a2', 'uni1', 'uni2'):
        courses = courses.filter(Q(year=year) | Q(year=''))
    if q:
        courses = courses.filter(Q(title__icontains=q) | Q(summary__icontains=q) | Q(subject__name__icontains=q)
                                 | Q(modules__lessons__title__icontains=q)).distinct()
    enrolled_ids = set()
    if request.user.is_authenticated:
        enrolled_ids = set(request.user.enrollments.filter(is_active=True).values_list('course_id', flat=True))
    return render(request, 'courses/catalog.html', {
        'courses': courses, 'subjects': Subject.objects.all(), 'subject_slug': subject_slug,
        'level': level, 'q': q, 'enrolled_ids': enrolled_ids, 'year': year,
    })


def detail(request, slug):
    course = get_object_or_404(Course.objects.select_related('subject', 'tutor', 'school'), slug=slug)
    if not course.is_published and not course.can_access_all(request.user):
        raise Http404
    if course.school_id and not course.can_access_all(request.user) and \
            not Course.objects.visible_to(request.user).filter(pk=course.pk).exists():
        raise Http404
    modules = course.modules.prefetch_related('lessons')
    has_access = course.can_access_all(request.user)
    enrollment = None
    done_ids = set()
    if request.user.is_authenticated:
        enrollment = course.enrollments.filter(user=request.user, is_active=True).first()
        done_ids = set(LessonProgress.objects.filter(user=request.user, lesson__module__course=course)
                       .values_list('lesson_id', flat=True))
    lessons = list(course.lessons())
    return render(request, 'courses/detail.html', {
        'course': course, 'modules': modules, 'has_access': has_access, 'enrollment': enrollment,
        'done_ids': done_ids, 'lesson_count': len(lessons),
        'total_minutes': sum(lesson.minutes for lesson in lessons),
        'preview_lesson': next((lesson for lesson in lessons if lesson.is_preview), None),
        'student_count': course.enrollments.filter(is_active=True).count(),
        'materials': course.materials.select_related('lesson'),
        'can_edit': _can_edit(request.user, course),
    })


def lesson(request, slug, pk):
    course = get_object_or_404(Course.objects.select_related('subject', 'tutor'), slug=slug)
    lesson_obj = get_object_or_404(Lesson.objects.select_related('module'), pk=pk, module__course=course)
    if not course.is_published and not course.can_access_all(request.user):
        raise Http404
    if not lesson_obj.can_view(request.user):
        if not request.user.is_authenticated:
            messages.info(request, 'Sign in or create a free account to continue.')
            return redirect(f"{_login_url()}?next={request.path}")
        messages.info(request, 'Unlock the full course to open this lesson.')
        return redirect('payments:checkout', slug=course.slug)
    from apps.classroom.services import blocking_assessment
    blocker = blocking_assessment(request.user, lesson_obj)
    if blocker:
        messages.info(request, f'Complete "{blocker.title}" first. Continuous assessment keeps you on track.')
        return redirect('classroom:assessment', pk=blocker.pk)

    lessons = list(course.lessons())
    index = next(i for i, item in enumerate(lessons) if item.pk == lesson_obj.pk)
    prev_lesson = lessons[index - 1] if index > 0 else None
    next_lesson = lessons[index + 1] if index + 1 < len(lessons) else None
    has_access = course.can_access_all(request.user)
    done_ids = set()
    if request.user.is_authenticated:
        done_ids = set(LessonProgress.objects.filter(user=request.user, lesson__module__course=course)
                       .values_list('lesson_id', flat=True))
        Enrollment.objects.filter(user=request.user, course=course).update(last_lesson=lesson_obj)
    progress = round(len(done_ids) * 100 / len(lessons)) if lessons else 0
    return render(request, 'courses/lesson.html', {
        'course': course, 'lesson': lesson_obj, 'modules': course.modules.prefetch_related('lessons'),
        'prev_lesson': prev_lesson, 'next_lesson': next_lesson, 'has_access': has_access,
        'done_ids': done_ids, 'is_done': lesson_obj.pk in done_ids, 'progress': progress,
        'position': index + 1, 'total': len(lessons),
        'next_locked': bool(next_lesson and not next_lesson.can_view(request.user)),
        'materials': lesson_obj.materials.all(),
        'assessments': lesson_obj.assessments.filter(is_published=True),
    })


def _login_url():
    from django.urls import reverse
    return reverse('accounts:login')


@login_required
@require_POST
def toggle_complete(request, slug, pk):
    lesson_obj = get_object_or_404(Lesson, pk=pk, module__course__slug=slug)
    if not lesson_obj.can_view(request.user):
        raise PermissionDenied
    progress = LessonProgress.objects.filter(user=request.user, lesson=lesson_obj)
    if progress.exists():
        progress.delete()
    else:
        LessonProgress.objects.get_or_create(user=request.user, lesson=lesson_obj)
        if request.POST.get('then') == 'next':
            course = lesson_obj.module.course
            lessons = list(course.lessons())
            idx = next(i for i, item in enumerate(lessons) if item.pk == lesson_obj.pk)
            if idx + 1 < len(lessons):
                nxt = lessons[idx + 1]
                if nxt.can_view(request.user):
                    from apps.classroom.services import blocking_assessment
                    blocker = blocking_assessment(request.user, nxt)
                    if blocker:
                        messages.info(request, f'Nice work. Now try "{blocker.title}" to unlock the next lesson.')
                        return redirect('classroom:assessment', pk=blocker.pk)
                    return redirect(nxt)
                return redirect('payments:checkout', slug=course.slug)
            messages.success(request, f'You finished every lesson in {course.title}. Brilliant work!')
            return redirect(course)
    return redirect(lesson_obj)


# --- Tutor studio -------------------------------------------------------------

def _can_edit(user, course):
    return user.is_authenticated and (user.is_staff or user.is_platform_admin or course.tutor_id == user.pk)


@login_required
@require_http_methods(['GET', 'POST'])
def edit_lesson(request, slug, pk=None):
    course = get_object_or_404(Course, slug=slug)
    if not _can_edit(request.user, course):
        raise PermissionDenied
    instance = get_object_or_404(Lesson, pk=pk, module__course=course) if pk else None
    form = LessonForm(request.POST or None, instance=instance, course=course,
                      initial={'module': request.GET.get('module')} if not instance else None)
    if request.method == 'POST' and form.is_valid():
        saved = form.save()
        messages.success(request, f'Saved "{saved.title}".')
        return redirect(saved)
    return render(request, 'courses/edit_lesson.html', {'course': course, 'form': form, 'lesson': instance})


@login_required
@require_POST
def add_module(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_edit(request.user, course):
        raise PermissionDenied
    title = request.POST.get('title', '').strip()[:160]
    if title:
        last = course.modules.order_by('-order').first()
        Module.objects.create(course=course, title=title, order=(last.order + 1) if last else 1)
        messages.success(request, f'Added module "{title}".')
    return redirect('core:tutor_dashboard')


def _can_create(user):
    if not user.is_authenticated:
        return False
    if user.is_tutor or user.is_platform_admin or user.is_staff:
        return True
    # School teachers and administrators can create private courses for their school.
    return user.school_memberships.filter(role__in=['admin', 'teacher']).exists()


@login_required
@require_http_methods(['GET', 'POST'])
def edit_course(request, slug=None):
    """Create a course (verified tutors and admins) or edit one you own."""
    course = get_object_or_404(Course, slug=slug) if slug else None
    if course and not _can_edit(request.user, course):
        raise PermissionDenied
    if not course and not _can_create(request.user):
        raise PermissionDenied
    initial = None
    if not course:
        initial = {'is_published': False}
        school_slug = request.GET.get('school')
        if school_slug:
            from apps.schools.models import School
            school = School.objects.filter(slug=school_slug).first()
            if school:
                initial['school'] = school.pk
    form = CourseForm(request.POST or None, request.FILES or None, instance=course, user=request.user,
                      initial=initial)
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        if not course:
            saved.tutor = request.user
        saved.save()
        if not course:
            Module.objects.create(course=saved, title='Getting started', order=1)
            messages.success(request, f'Created "{saved.title}". Add lessons and upload your materials next.')
        else:
            messages.success(request, 'Course saved.')
        return redirect('courses:studio', slug=saved.slug)
    return render(request, 'courses/edit_course.html', {'form': form, 'course': course})


@login_required
def studio(request, slug):
    """One course's control panel: lessons, materials and students."""
    course = get_object_or_404(Course.objects.select_related('subject', 'tutor'), slug=slug)
    if not _can_edit(request.user, course):
        raise PermissionDenied
    students = course.enrollments.select_related('user').order_by('-created_at')
    total = course.lessons().count()
    rows = []
    for e in students:
        done = LessonProgress.objects.filter(user=e.user, lesson__module__course=course).count()
        rows.append({'e': e, 'percent': round(done * 100 / total) if total else 0})
    return render(request, 'courses/studio.html', {
        'course': course, 'modules': course.modules.prefetch_related('lessons'),
        'materials': course.materials.select_related('lesson'), 'rows': rows,
        'active_count': course.enrollments.filter(active_enrollment_q()).count(),
        'material_form': MaterialForm(course=course),
    })


@login_required
@require_POST
def upload_material(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not _can_edit(request.user, course):
        raise PermissionDenied
    form = MaterialForm(request.POST, request.FILES, course=course)
    if form.is_valid():
        material = form.save(commit=False)
        material.course = course
        material.kind = form.detected_kind
        material.size = form.cleaned_data['file'].size
        material.html = readable_html(form.cleaned_data['file'], material.kind)
        material.uploaded_by = request.user
        material.save()
        messages.success(request, f'Uploaded "{material.title}".')
    else:
        errors = '; '.join(f'{form.fields[f].label if f in form.fields else ""}: {" ".join(e)}'.strip(': ')
                           for f, e in form.errors.items())
        messages.error(request, f'Upload failed. {errors}')
    return redirect('courses:studio', slug=course.slug)


@login_required
@require_POST
def delete_material(request, slug, pk):
    material = get_object_or_404(CourseMaterial, pk=pk, course__slug=slug)
    if not _can_edit(request.user, material.course):
        raise PermissionDenied
    material.file.delete(save=False)
    material.delete()
    messages.success(request, 'File removed.')
    return redirect('courses:studio', slug=slug)


def material(request, slug, pk):
    """Read a file in the browser."""
    item = get_object_or_404(CourseMaterial.objects.select_related('course', 'lesson'), pk=pk, course__slug=slug)
    if not item.can_view(request.user):
        if not request.user.is_authenticated:
            return redirect(f"{_login_url()}?next={request.path}")
        messages.info(request, 'Subscribe to the course to open its materials.')
        return redirect('payments:checkout', slug=slug)
    CourseMaterial.objects.filter(pk=item.pk).update(views=F('views') + 1)
    return render(request, 'courses/material.html', {'item': item, 'course': item.course})


@xframe_options_sameorigin
def material_file(request, slug, pk):
    """The original file: shown inline (PDF, images) or downloaded."""
    item = get_object_or_404(CourseMaterial.objects.select_related('course'), pk=pk, course__slug=slug)
    if not item.can_view(request.user):
        raise Http404
    inline = request.GET.get('inline') == '1' and item.kind in ('pdf', 'image')
    if not inline and not item.allow_download and not _can_edit(request.user, item.course):
        raise PermissionDenied
    response = FileResponse(item.file.open('rb'), as_attachment=not inline, filename=item.filename)
    response['Cache-Control'] = 'private, max-age=300'
    return response
