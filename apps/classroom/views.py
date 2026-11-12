import csv

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.courses.models import Course, active_enrollment_q
from apps.notifications.services import notify

from . import services
from .forms import (AnnouncementForm, AssessmentForm, BookingForm, BookingReplyForm, CheckInForm, ClassGroupForm,
                    QuestionForm, SessionForm)
from .models import (Announcement, Assessment, Attendance, Booking, ClassGroup, ClassMembership, Question, Session,
                     Submission)

User = get_user_model()


def _can_manage(user, course):
    return user.is_authenticated and (user.is_staff or user.is_platform_admin or course.tutor_id == user.pk)


def _managed_course(request, slug):
    course = get_object_or_404(Course.objects.select_related('subject', 'tutor'), slug=slug)
    if not _can_manage(request.user, course):
        raise PermissionDenied
    return course


def _courses_for(user):
    qs = Course.objects.select_related('subject')
    return qs if (user.is_staff or user.is_platform_admin) else qs.filter(tutor=user)


# ============================================================ Tutor side ===

@login_required
def tutor_home(request):
    if not (request.user.is_tutor or request.user.is_platform_admin or request.user.is_staff):
        raise PermissionDenied
    courses = _courses_for(request.user).annotate(
        students=Count('enrollments', filter=active_enrollment_q('enrollments__'), distinct=True),
        group_count=Count('class_groups', distinct=True))
    now = timezone.now()
    sessions = Session.objects.filter(course__in=courses, is_cancelled=False,
                                      starts_at__gte=now - timezone.timedelta(hours=3)) \
        .select_related('course', 'class_group')[:10]
    to_mark = Submission.objects.filter(assessment__course__in=courses, status=Submission.Status.SUBMITTED) \
        .select_related('student', 'assessment')[:20]
    bookings = Booking.objects.filter(course__in=courses, status=Booking.Status.REQUESTED) \
        .select_related('student', 'course')
    return render(request, 'classroom/tutor_home.html', {
        'courses': courses, 'sessions': sessions, 'to_mark': to_mark, 'bookings': bookings})


@login_required
def manage(request, slug):
    """One page to run a course's classes: groups, sessions, assessments,
    announcements and the gradebook link."""
    course = _managed_course(request, slug)
    return render(request, 'classroom/manage.html', {
        'course': course,
        'groups': course.class_groups.annotate(n=Count('memberships')),
        'upcoming': course.sessions.filter(starts_at__gte=timezone.now() - timezone.timedelta(hours=3))
        .select_related('class_group'),
        'past': course.sessions.filter(starts_at__lt=timezone.now() - timezone.timedelta(hours=3))
        .annotate(present=Count('attendance', filter=Q(attendance__status__in=['present', 'late'])))
        .order_by('-starts_at')[:10],
        'assessments': course.assessments.annotate(
            n_questions=Count('questions', distinct=True),
            n_submissions=Count('submissions', filter=~Q(submissions__status='in_progress'), distinct=True)),
        'announcements': course.class_announcements.all()[:5],
        'group_form': ClassGroupForm(), 'announcement_form': AnnouncementForm(course=course),
    })


@login_required
@require_http_methods(['GET', 'POST'])
def group_edit(request, slug, pk=None):
    course = _managed_course(request, slug)
    group = get_object_or_404(ClassGroup, pk=pk, course=course) if pk else None
    form = ClassGroupForm(request.POST or None, instance=group)
    if request.method == 'POST' and form.is_valid():
        group = form.save(commit=False)
        group.course = course
        group.save()
        add = request.POST.getlist('add_students')
        for sid in add:
            ClassMembership.objects.get_or_create(class_group=group, student_id=sid)
        messages.success(request, f'Saved class "{group.name}".')
        return redirect('classroom:group', slug=slug, pk=group.pk)
    enrolled = User.objects.filter(enrollments__in=course.enrollments.filter(active_enrollment_q())).distinct()
    members = group.students.all() if group else User.objects.none()
    return render(request, 'classroom/group_edit.html', {
        'course': course, 'group': group, 'form': form, 'members': members,
        'candidates': enrolled.exclude(pk__in=members.values('pk'))})


@login_required
@require_POST
def group_remove(request, slug, pk, student_id):
    course = _managed_course(request, slug)
    ClassMembership.objects.filter(class_group__course=course, class_group_id=pk, student_id=student_id).delete()
    return redirect('classroom:group', slug=slug, pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def session_edit(request, slug, pk=None):
    course = _managed_course(request, slug)
    session = get_object_or_404(Session, pk=pk, course=course) if pk else None
    form = SessionForm(request.POST or None, instance=session, course=course,
                       initial={'class_group': request.GET.get('group')} if not session else None)
    if request.method == 'POST' and form.is_valid():
        obj = form.save(commit=False)
        obj.course = course
        if not session:
            obj.tutor = course.tutor
        obj.save()
        if form.cleaned_data.get('notify_students'):
            services.announce_session(obj)
        messages.success(request, f'Saved "{obj.title}".')
        return redirect('classroom:session', pk=obj.pk)
    return render(request, 'classroom/session_edit.html', {'course': course, 'form': form, 'session': session})


@login_required
@require_POST
def session_cancel(request, pk):
    session = get_object_or_404(Session, pk=pk)
    if not _can_manage(request.user, session.course):
        raise PermissionDenied
    session.is_cancelled = True
    session.save(update_fields=['is_cancelled'])
    for student in session.expected_students():
        notify(student, title=f'Cancelled: {session.title}',
               body=f'The session on {timezone.localtime(session.starts_at):%A %d %B at %H:%M} is cancelled.',
               url=session.course.get_absolute_url())
    messages.success(request, 'Session cancelled and students notified.')
    return redirect('classroom:manage', slug=session.course.slug)


@login_required
def session(request, pk):
    """Students see the join link and check in; tutors take the register."""
    s = get_object_or_404(Session.objects.select_related('course', 'class_group', 'tutor'), pk=pk)
    manager = _can_manage(request.user, s.course)
    expected = s.expected_students()
    if not manager and not expected.filter(pk=request.user.pk).exists():
        raise Http404
    ctx = {'s': s, 'manager': manager}
    if manager:
        marks = {a.student_id: a for a in s.attendance.all()}
        ctx['register'] = [{'student': st, 'record': marks.get(st.pk)} for st in expected.order_by('first_name')]
        ctx['statuses'] = Attendance.Status.choices
    else:
        ctx['record'] = s.attendance.filter(student=request.user).first()
        ctx['form'] = CheckInForm()
    return render(request, 'classroom/session.html', ctx)


@login_required
@require_POST
def register(request, pk):
    s = get_object_or_404(Session, pk=pk)
    if not _can_manage(request.user, s.course):
        raise PermissionDenied
    marks = {k.split('_', 1)[1]: v for k, v in request.POST.items() if k.startswith('status_')}
    services.save_register(s, marks, request.user)
    messages.success(request, 'Register saved.')
    return redirect('classroom:session', pk=pk)


@login_required
@require_POST
def check_in(request, pk):
    s = get_object_or_404(Session, pk=pk)
    if not s.expected_students().filter(pk=request.user.pk).exists():
        raise Http404
    form = CheckInForm(request.POST)
    if form.is_valid():
        rec, error = services.check_in(s, request.user, form.cleaned_data['code'])
        if error:
            messages.error(request, error)
        else:
            messages.success(request, f'You are marked {rec.get_status_display().lower()}. Enjoy the session!')
    return redirect('classroom:session', pk=pk)


@login_required
@require_http_methods(['GET', 'POST'])
def assessment_edit(request, slug, pk=None):
    course = _managed_course(request, slug)
    obj = get_object_or_404(Assessment, pk=pk, course=course) if pk else None
    form = AssessmentForm(request.POST or None, instance=obj, course=course,
                          initial={'lesson': request.GET.get('lesson')} if not obj else None)
    qform = QuestionForm(initial={'marks': 1, 'order': (obj.questions.count() + 1) if obj else 1})
    if request.method == 'POST' and form.is_valid():
        saved = form.save(commit=False)
        saved.course = course
        saved.save()
        if saved.is_published and not saved.questions.exists() and not saved.allow_file_upload:
            saved.is_published = False
            saved.save(update_fields=['is_published'])
            messages.info(request, 'Saved as a draft: add questions (or allow uploads) before publishing.')
        else:
            messages.success(request, f'Saved "{saved.title}".')
        return redirect('classroom:assessment_edit', slug=slug, pk=saved.pk)
    return render(request, 'classroom/assessment_edit.html', {
        'course': course, 'form': form, 'obj': obj, 'qform': qform,
        'questions': obj.questions.all() if obj else []})


@login_required
@require_http_methods(['GET', 'POST'])
def question_edit(request, slug, assessment_pk, pk=None):
    course = _managed_course(request, slug)
    assessment = get_object_or_404(Assessment, pk=assessment_pk, course=course)
    obj = get_object_or_404(Question, pk=pk, assessment=assessment) if pk else None
    form = QuestionForm(request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        q = form.save(commit=False)
        q.assessment = assessment
        q.save()
        messages.success(request, 'Question saved.')
        return redirect('classroom:assessment_edit', slug=slug, pk=assessment.pk)
    return render(request, 'classroom/question_edit.html', {'course': course, 'assessment': assessment,
                                                            'form': form, 'obj': obj})


@login_required
@require_POST
def question_delete(request, slug, assessment_pk, pk):
    course = _managed_course(request, slug)
    Question.objects.filter(pk=pk, assessment_id=assessment_pk, assessment__course=course).delete()
    return redirect('classroom:assessment_edit', slug=slug, pk=assessment_pk)


@login_required
@require_http_methods(['GET', 'POST'])
def mark(request, pk):
    sub = get_object_or_404(Submission.objects.select_related('assessment__course', 'student'), pk=pk)
    if not _can_manage(request.user, sub.assessment.course):
        raise PermissionDenied
    questions = list(sub.assessment.questions.all())
    if request.method == 'POST':
        marks = {}
        for q in questions:
            value = request.POST.get(f'mark_{q.pk}')
            if value not in (None, ''):
                marks[str(q.pk)] = value
        if sub.upload and not questions and request.POST.get('mark_upload'):
            marks['upload'] = request.POST['mark_upload']
        try:
            services.grade(sub, marks, request.POST.get('feedback', '').strip(), request.user)
        except Exception:  # noqa: BLE001
            messages.error(request, 'Marks must be numbers.')
            return redirect('classroom:mark', pk=pk)
        messages.success(request, f'Marked {sub.student.display_name}: {sub.percent}%.')
        nxt = Submission.objects.filter(assessment=sub.assessment, status=Submission.Status.SUBMITTED).first()
        return redirect('classroom:mark', pk=nxt.pk) if nxt else redirect('classroom:tutor_home')
    rows = [{'q': q, 'answer': sub.answers.get(str(q.pk), ''), 'auto': sub.marks_by_question.get(str(q.pk))}
            for q in questions]
    return render(request, 'classroom/mark.html', {'sub': sub, 'rows': rows})


@login_required
def submission_file(request, pk):
    sub = get_object_or_404(Submission.objects.select_related('assessment__course'), pk=pk)
    if not (sub.student_id == request.user.pk or _can_manage(request.user, sub.assessment.course)):
        raise Http404
    if not sub.upload:
        raise Http404
    return FileResponse(sub.upload.open('rb'), filename=sub.upload.name.rsplit('/', 1)[-1])


@login_required
def gradebook(request, slug):
    course = _managed_course(request, slug)
    assessments, rows = services.gradebook(course)
    if request.GET.get('format') == 'csv':
        resp = HttpResponse(content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{course.slug}-gradebook.csv"'
        w = csv.writer(resp)
        w.writerow(['Student', 'Email'] + [a.title for a in assessments] + ['Average %', 'Grade', 'Attendance %'])
        for r in rows:
            w.writerow([r['student'].display_name, r['student'].email]
                       + ['' if s is None else s for s in r['scores']]
                       + [r['average'] or '', r['grade'], r['attendance'] if r['attendance'] is not None else ''])
        return resp
    return render(request, 'classroom/gradebook.html', {'course': course, 'assessments': assessments, 'rows': rows})


@login_required
@require_POST
def announce(request, slug):
    course = _managed_course(request, slug)
    form = AnnouncementForm(request.POST, course=course)
    if form.is_valid():
        a = form.save(commit=False)
        a.course, a.author = course, request.user
        a.save()
        students = a.class_group.students.all() if a.class_group else \
            User.objects.filter(enrollments__in=course.enrollments.filter(active_enrollment_q())).distinct()
        for st in students:
            notify(st, title=f'{course.title}: {a.title}', body=a.body, url=course.get_absolute_url())
            if a.notify_parents:
                for link in st.parent_links.select_related('parent'):
                    notify(link.parent, title=f'{course.title}: {a.title}', body=a.body,
                           url='/parent/')
        messages.success(request, f'Announcement sent to {len(students)} student(s).')
    else:
        messages.error(request, 'Give the announcement a title and a message.')
    return redirect('classroom:manage', slug=slug)


@login_required
@require_http_methods(['GET', 'POST'])
def booking_reply(request, pk):
    booking = get_object_or_404(Booking.objects.select_related('course', 'student'), pk=pk)
    if not _can_manage(request.user, booking.course):
        raise PermissionDenied
    form = BookingReplyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        d = form.cleaned_data
        booking.tutor_reply = d['reply']
        if d['decision'] == 'confirm':
            s = Session.objects.create(
                course=booking.course, tutor=booking.course.tutor, title=f'One-to-one: {booking.topic}'[:160],
                kind=Session.Kind.ONE_TO_ONE, starts_at=d['starts_at'] or booking.preferred_start,
                duration_minutes=booking.duration_minutes, meeting_url=d['meeting_url'], agenda=booking.message)
            booking.session = s
            booking.status = Booking.Status.CONFIRMED
            booking.save()
            notify(booking.student, title=f'Lesson confirmed: {booking.topic}',
                   body=f'{timezone.localtime(s.starts_at):%A %d %B at %H:%M}. {d["reply"]}'.strip(),
                   url=s.get_absolute_url())
        else:
            booking.status = Booking.Status.DECLINED
            booking.save()
            notify(booking.student, title=f'Lesson request declined: {booking.topic}',
                   body=d['reply'] or 'Your tutor could not take this time. Try another time.',
                   url='/classroom/')
        messages.success(request, 'Reply sent.')
        return redirect('classroom:tutor_home')
    return render(request, 'classroom/booking_reply.html', {'booking': booking, 'form': form})


# ========================================================== Student side ===

@login_required
def my_classes(request):
    user = request.user
    courses = Course.objects.filter(enrollments__in=user.enrollments.filter(active_enrollment_q()))
    now = timezone.now()
    sessions = Session.objects.filter(
        Q(course__in=courses, class_group__isnull=True, kind__in=['class', 'tutorial', 'extra', 'exam_prep'])
        | Q(class_group__students=user) | Q(bookings__student=user),
        is_cancelled=False, starts_at__gte=now - timezone.timedelta(hours=3)).distinct() \
        .select_related('course', 'class_group')[:20]
    groups = ClassGroup.objects.filter(course__in=courses).select_related('course') \
        .annotate(n=Count('memberships'))
    mine = set(user.memberships.values_list('class_group_id', flat=True))
    due = Assessment.objects.filter(course__in=courses, is_published=True).exclude(
        submissions__student=user, submissions__status__in=['submitted', 'graded']).select_related('course')[:10]
    return render(request, 'classroom/my_classes.html', {
        'sessions': sessions, 'groups': groups, 'mine': mine, 'courses': courses,
        'bookings': user.bookings.select_related('course', 'session')[:10], 'due': due})


@login_required
@require_POST
def join_group(request, pk):
    group = get_object_or_404(ClassGroup, pk=pk)
    if not group.course.is_enrolled(request.user):
        messages.error(request, 'Subscribe to the course first.')
    elif not group.is_open or group.seats_left <= 0:
        messages.error(request, 'This class is full or closed.')
    else:
        ClassMembership.objects.get_or_create(class_group=group, student=request.user)
        messages.success(request, f'You joined {group.name}.')
    return redirect('classroom:my_classes')


@login_required
@require_http_methods(['GET', 'POST'])
def book(request, slug):
    course = get_object_or_404(Course, slug=slug)
    if not course.is_enrolled(request.user):
        messages.info(request, 'Subscribe to the course to book lessons with its tutor.')
        return redirect('payments:checkout', slug=slug)
    form = BookingForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        b = form.save(commit=False)
        b.student, b.course = request.user, course
        b.save()
        notify(course.tutor, title=f'Lesson request from {request.user.display_name}',
               body=f'{b.topic}, {timezone.localtime(b.preferred_start):%A %d %B at %H:%M}.',
               url=f'/classroom/bookings/{b.pk}/')
        messages.success(request, 'Request sent. Your tutor will confirm the time.')
        return redirect('classroom:my_classes')
    return render(request, 'classroom/book.html', {'course': course, 'form': form})


@login_required
@require_http_methods(['GET', 'POST'])
def assessment(request, pk):
    a = get_object_or_404(Assessment.objects.select_related('course', 'lesson'), pk=pk)
    manager = _can_manage(request.user, a.course)
    if not a.is_published and not manager:
        raise Http404
    if not a.course.can_access_all(request.user):
        messages.info(request, 'Subscribe to the course to take its assessments.')
        return redirect('payments:checkout', slug=a.course.slug)
    previous = a.submissions.filter(student=request.user).exclude(status='in_progress')
    left = services.attempts_left(request.user, a)
    if request.method == 'POST':
        if left <= 0 and not manager:
            messages.error(request, 'You have used all your attempts.')
            return redirect('classroom:assessment', pk=pk)
        sub = services.start_attempt(request.user, a)
        answers = {str(q.pk): request.POST.get(f'q_{q.pk}', '').strip()[:5000] for q in a.questions.all()}
        upload = request.FILES.get('upload') if a.allow_file_upload else None
        if upload and upload.size > 25 * 1024 * 1024:
            messages.error(request, 'Your file is larger than 25 MB.')
            return redirect('classroom:assessment', pk=pk)
        services.submit(sub, answers, upload)
        return redirect('classroom:result', pk=sub.pk)
    return render(request, 'classroom/assessment.html', {
        'a': a, 'questions': a.questions.all(), 'previous': previous, 'left': left, 'manager': manager})


@login_required
def result(request, pk):
    sub = get_object_or_404(Submission.objects.select_related('assessment__course', 'student'), pk=pk)
    if sub.student_id != request.user.pk and not _can_manage(request.user, sub.assessment.course):
        raise Http404
    a = sub.assessment
    rows = [{'q': q, 'answer': sub.answers.get(str(q.pk), ''), 'got': sub.marks_by_question.get(str(q.pk))}
            for q in a.questions.all()]
    next_lesson = None
    if a.lesson_id:
        lessons = list(a.course.lessons())
        idx = next((i for i, item in enumerate(lessons) if item.pk == a.lesson_id), None)
        if idx is not None and idx + 1 < len(lessons):
            next_lesson = lessons[idx + 1]
    return render(request, 'classroom/result.html', {
        'sub': sub, 'a': a, 'rows': rows, 'grade': services.letter(sub.percent),
        'left': services.attempts_left(sub.student, a), 'next_lesson': next_lesson})


@login_required
def my_grades(request):
    subs = list(services.student_grades(request.user))
    for s in subs:
        s.grade = services.letter(s.percent)
    return render(request, 'classroom/my_grades.html', {
        'subs': subs,
        'attendance': services.attendance_rate(request.user)})


__all__ = ['Announcement']
