"""JSON for the TypeScript dashboards (static/ts/). Uses the normal session
login, so there are no extra tokens to manage. Types are mirrored in
frontend/src/types.ts."""
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncWeek
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.classroom.models import Session, Submission
from apps.courses.models import Course, Enrollment, LessonProgress
from apps.ledger.models import LedgerEntry

from . import services


def _weeks(n=12):
    start = timezone.localdate() - timedelta(days=timezone.localdate().weekday(), weeks=n - 1)
    return [(start + timedelta(weeks=i)) for i in range(n)]


def _series(qs, date_field, value=None, n=12):
    since = timezone.now() - timedelta(weeks=n)
    rows = qs.filter(**{f'{date_field}__gte': since}).annotate(w=TruncWeek(date_field)).values('w')
    rows = rows.annotate(v=Sum(value) if value else Count('id'))
    data = {r['w'].date(): float(r['v'] or 0) for r in rows}
    return [{'x': w.isoformat(), 'y': data.get(w, 0)} for w in _weeks(n)]


def _student_payload(user):
    enrollments = user.enrollments.filter(is_active=True).select_related('course')
    progress = [{'label': e.course.title, 'value': e.progress()} for e in enrollments]
    grades = [{'x': s.graded_at.date().isoformat(), 'y': float(s.percent), 'label': s.assessment.title}
              for s in Submission.objects.filter(student=user, status='graded').select_related('assessment')
              .order_by('graded_at')[:30]]
    return {
        'progress': progress,
        'lessons_per_week': _series(LessonProgress.objects.filter(user=user), 'completed_at'),
        'grades': grades,
        'insights': services.student_insights(user),
    }


@login_required
@require_GET
def student_overview(request):
    return JsonResponse(_student_payload(request.user))


@login_required
@require_GET
def child_overview(request, pk):
    if not request.user.child_links.filter(student_id=pk).exists():
        raise PermissionDenied
    link = get_object_or_404(request.user.child_links.select_related('student'), student_id=pk)
    return JsonResponse(_student_payload(link.student))


@login_required
@require_GET
def tutor_overview(request):
    user = request.user
    if not (user.is_tutor or user.is_platform_admin or user.is_staff):
        raise PermissionDenied
    courses = Course.objects.filter(tutor=user)
    earnings = LedgerEntry.objects.filter(tutor=user, account='tutor', kind='sale')
    risk = services.at_risk_students(tutor=user, limit=8)
    sessions = Session.objects.filter(course__in=courses, starts_at__lte=timezone.now(), is_cancelled=False) \
        .annotate(present=Count('attendance', filter=Q(attendance__status__in=['present', 'late'])),
                  marked=Count('attendance')).order_by('-starts_at')[:10]
    return JsonResponse({
        'enrolments': _series(Enrollment.objects.filter(course__in=courses), 'created_at'),
        'earnings': [{'x': p['x'], 'y': p['y'] / 100} for p in _series(earnings, 'created_at', 'amount_ngwee')],
        'by_course': [{'label': c.title,
                       'value': float(earnings.filter(course=c).aggregate(t=Sum('amount_ngwee'))['t'] or 0) / 100}
                      for c in courses],
        'attendance': [{'label': timezone.localtime(s.starts_at).strftime('%d %b'),
                        'value': round(s.present * 100 / s.marked) if s.marked else 0} for s in reversed(sessions)],
        'risk': [{'student': r['student'].display_name, 'course': r['course'].title, 'risk': r['risk'],
                  'level': r['level'], 'reasons': r['reasons']} for r in risk],
    })


@login_required
@require_GET
def admin_overview(request):
    if not (request.user.is_platform_admin or request.user.is_staff):
        raise PermissionDenied
    forecast = services.revenue_forecast()
    insights = services.payment_insights()
    source, importance = services.feature_importance()
    split = LedgerEntry.objects.filter(kind='sale').values('account').annotate(t=Sum('amount_ngwee'))
    from apps.analytics.models import ModelRun
    run = ModelRun.objects.filter(name='risk').first()
    return JsonResponse({
        'revenue': [{'x': h['week'], 'y': h['total']} for h in forecast['history']],
        'forecast': [{'x': f['week'], 'y': f['total'], 'low': f['low'], 'high': f['high']}
                     for f in forecast['forecast']],
        'forecast_message': forecast.get('message', ''),
        'split': [{'label': {'tutor': 'Tutors', 'platform': 'Platform', 'fees': 'Fees'}[r['account']],
                   'value': (r['t'] or 0) / 100} for r in split],
        'networks': [{'label': r['network'], 'value': r['rate'] or 0, 'total': r['total']}
                     for r in insights['by_network']],
        'hours': [{'label': f'{h["hour"]:02d}', 'value': h['total']} for h in insights['by_hour']],
        'signups': _series(Enrollment.objects.all(), 'created_at'),
        'suspicious': insights['suspicious'], 'spike': insights['spike'],
        'model': {'source': source, 'importance': importance,
                  'metrics': run.metrics if run else {}, 'trained_at': run.created_at.isoformat() if run else None},
    })
