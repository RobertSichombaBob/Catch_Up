import mimetypes

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.files.storage import default_storage
from django.db import connection
from django.db.models import Count, Q, Sum
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from apps.accounts.models import TutorProfile
from apps.courses.models import Course, Enrollment, Subject, active_enrollment_q
from apps.ledger.models import LedgerEntry
from apps.ledger.services import tutor_balance
from apps.payments.models import Payment
from apps.classroom.models import Booking, Session, Submission
from django.utils import timezone

User = get_user_model()


def home(request):
    courses = Course.objects.published().select_related('subject', 'tutor') \
        .annotate(lesson_count=Count('modules__lessons', distinct=True))[:6]
    tutors = User.objects.filter(role=User.Role.TUTOR, is_active=True,
                                 tutor_profile__status=TutorProfile.Status.APPROVED) \
        .annotate(course_count=Count('courses_taught', filter=Q(courses_taught__is_published=True))) \
        .order_by('-course_count')[:4]
    from apps.schools.models import School
    return render(request, 'core/home.html', {
        'subjects': Subject.objects.annotate(course_count=Count('courses', filter=Q(courses__is_published=True))),
        'courses': courses,
        'tutors': tutors,
        'stats': {
            'courses': Course.objects.published().count(),
            'tutors': TutorProfile.objects.filter(status=TutorProfile.Status.APPROVED).count(),
            'students': User.objects.filter(role=User.Role.STUDENT).count(),
            'schools': School.objects.filter(is_approved=True).count(),
        },
    })


@login_required
def dashboard(request):
    user = request.user
    if user.is_tutor and not request.GET.get('as') == 'student':
        return redirect('core:tutor_dashboard')
    if user.is_parent:
        return redirect('portal:parent_home')
    enrollments = list(user.enrollments.filter(is_active=True).select_related('course__subject', 'course__tutor',
                                                                               'last_lesson'))
    for e in enrollments:
        e.percent = e.progress()
        e.resume = e.next_lesson()
    pending = user.payments.filter(status=Payment.Status.PENDING).select_related('course')[:3]
    from apps.analytics.services import recommend_courses, student_insights
    from apps.classroom.models import Assessment
    active_courses = [e.course for e in enrollments if e.has_access]
    sessions = Session.objects.filter(
        Q(course__in=active_courses, class_group__isnull=True) | Q(class_group__students=user)
        | Q(bookings__student=user),
        is_cancelled=False, starts_at__gte=timezone.now() - timezone.timedelta(hours=2)) \
        .distinct().select_related('course')[:4]
    due = Assessment.objects.filter(course__in=active_courses, is_published=True).exclude(
        submissions__student=user, submissions__status__in=['submitted', 'graded']) \
        .select_related('course', 'lesson')[:4]
    try:
        insights = student_insights(user)
    except Exception:  # noqa: BLE001 - coaching tips must never break the dashboard
        insights = {'week': 0, 'streak': 0, 'tips': []}
    return render(request, 'core/dashboard.html', {
        'enrollments': enrollments, 'pending_payments': pending,
        'suggestions': recommend_courses(user, k=3),
        'completed_lessons': user.lesson_progress.count(),
        'renewals': [e for e in enrollments if e.renewal_due or not e.has_access],
        'sessions': sessions, 'due': due, 'insights': insights,
    })


@login_required
def tutor_dashboard(request):
    user = request.user
    if not (user.is_tutor or user.is_platform_admin or user.is_staff):
        raise PermissionDenied
    courses = Course.objects.select_related('subject', 'tutor', 'school')
    if not (user.is_platform_admin or user.is_staff):
        courses = courses.filter(tutor=user)
    courses = courses.annotate(
        students=Count('enrollments', filter=active_enrollment_q('enrollments__'), distinct=True),
        material_count=Count('materials', distinct=True),
    )
    paid = Payment.objects.filter(course__in=courses, status=Payment.Status.COMPLETED)
    recent = Enrollment.objects.filter(course__in=courses).select_related('user', 'course')[:10]
    earnings = LedgerEntry.objects.filter(tutor=user, account=LedgerEntry.Account.TUTOR)
    profile = TutorProfile.objects.filter(user=user).first() if user.is_tutor else None
    return render(request, 'core/tutor_dashboard.html', {
        'courses': courses,
        'total_students': sum(c.students for c in courses),
        'revenue': paid.aggregate(total=Sum('amount'))['total'] or 0,
        'paid_count': paid.count(),
        'recent': recent,
        'balance': tutor_balance(user),
        'earning_rows': earnings.select_related('course', 'payment__user')[:8],
        'profile': profile,
        'can_publish': user.is_verified_tutor,
        'to_mark': Submission.objects.filter(assessment__course__in=courses, status='submitted').count(),
        'requests': Booking.objects.filter(course__in=courses, status='requested').count(),
        'upcoming': Session.objects.filter(course__in=courses, is_cancelled=False,
                                           starts_at__gte=timezone.now()).select_related('course')[:4],
    })


def page(request, name):
    templates = {'about': 'core/about.html', 'help': 'core/help.html', 'terms': 'core/terms.html',
                 'privacy': 'core/privacy.html', 'pricing': 'core/pricing.html'}
    return render(request, templates[name])


@require_GET
@cache_control(max_age=86400 * 30, public=True)
def public_media(request, path):
    """Course covers and profile photos. Only files under media/public/ are
    served here; tutor documents and paid materials have their own checked
    views. Works for the local disk and for S3-compatible storage."""
    name = f'public/{path}'
    if '..' in path or not default_storage.exists(name):
        raise Http404
    ctype = mimetypes.guess_type(name)[0] or 'application/octet-stream'
    if not ctype.startswith('image/'):
        raise Http404
    return FileResponse(default_storage.open(name, 'rb'), content_type=ctype)


@require_GET
def healthz(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except Exception:  # noqa: BLE001
        return JsonResponse({'status': 'error', 'database': 'unreachable'}, status=503)
    return JsonResponse({'status': 'ok'})


@require_GET
@cache_control(max_age=86400)
def robots(request):
    lines = ['User-agent: *', 'Disallow: /admin/', 'Disallow: /accounts/', 'Disallow: /payments/',
             'Disallow: /dashboard/', 'Allow: /']
    return HttpResponse('\n'.join(lines) + '\n', content_type='text/plain')


def error_404(request, exception=None):
    return render(request, '404.html', status=404)


def error_500(request):
    # Rendered without the request context, so it still works when the
    # database (used by the context processors) is the thing that failed.
    from django.template import loader
    return HttpResponse(loader.get_template('500.html').render(), status=500)
