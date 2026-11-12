"""Data science and machine learning for Catch Up.

Every dashboard number and prediction comes from here, so views stay thin
and the logic can be tested and improved in one place.

* At-risk students: a logistic regression on engagement features. Until
  there is enough history to train on, it uses expert starting weights, so
  it gives sensible answers from day one. Each prediction comes with the
  reasons behind it, because a tutor or parent needs to know what to do.
* Course recommendations: item-to-item collaborative filtering ("students
  who took this also took") blended with level and subject matching.
* Revenue forecast: Holt's linear exponential smoothing with an 80% band.
* Payment insights: success rates by network and hour, and anomaly flags.
* Lesson drop-off: where in a course students stop.

Models are trained by `python manage.py train_models` (a nightly cron job),
never inside a web request.
"""
import math
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

import numpy as np
from django.contrib.auth import get_user_model
from django.db.models import Avg, Count, Max, Q, Sum
from django.db.models.functions import ExtractHour, TruncDate, TruncWeek
from django.utils import timezone

from apps.classroom.models import Attendance, Submission
from apps.courses.models import Course, Enrollment, Lesson, LessonProgress
from apps.payments.models import Payment

from .models import ModelRun

User = get_user_model()

# ------------------------------------------------------------------ Risk ---

FEATURES = ['days_inactive', 'completion', 'pace', 'attendance', 'avg_score', 'failed_attempts', 'days_to_expiry']
LABELS = {
    'days_inactive': 'days since last activity',
    'completion': 'share of lessons completed',
    'pace': 'lessons completed per week',
    'attendance': 'attendance rate',
    'avg_score': 'average assessment score',
    'failed_attempts': 'failed assessment attempts',
    'days_to_expiry': 'days until access ends',
}
# Starting weights (on standardised features) chosen from teaching
# experience: inactivity and missed classes raise risk; progress, scores
# and attendance lower it. Replaced by trained weights once data exists.
PRIOR = {'bias': -1.0, 'days_inactive': 1.4, 'completion': -0.9, 'pace': -0.6, 'attendance': -0.8,
         'avg_score': -0.7, 'failed_attempts': 0.5, 'days_to_expiry': -0.3}
PRIOR_SCALE = {'mean': [7, 0.4, 1.0, 0.75, 60, 1, 15], 'std': [7, 0.3, 1.0, 0.25, 20, 1.5, 10]}


def _features_for(enrollment, now):
    user, course = enrollment.user, enrollment.course
    progress = LessonProgress.objects.filter(user=user, lesson__module__course=course)
    total = course.lessons().count() or 1
    done = progress.count()
    last = progress.aggregate(m=Max('completed_at'))['m'] or enrollment.created_at
    weeks = max(1.0, (now - enrollment.created_at).days / 7)
    att = Attendance.objects.filter(student=user, session__course=course, session__is_cancelled=False)
    att_total = att.count()
    attendance = (att.filter(status__in=['present', 'late']).count() / att_total) if att_total else 0.75
    subs = Submission.objects.filter(student=user, assessment__course=course, status='graded')
    avg = subs.aggregate(a=Avg('percent'))['a']
    failed = sum(1 for s in subs if not s.passed)
    expiry = (enrollment.access_until - now).days if enrollment.access_until else 30
    return {
        'days_inactive': max(0, (now - last).days),
        'completion': done / total,
        'pace': done / weeks,
        'attendance': attendance,
        'avg_score': float(avg) if avg is not None else 60.0,
        'failed_attempts': failed,
        'days_to_expiry': max(-30, min(60, expiry)),
    }


def _sigmoid(z):
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def _current_model():
    run = ModelRun.objects.filter(name='risk').first()
    if run and run.params.get('weights'):
        return run.params, 'trained'
    return {'weights': [PRIOR[f] for f in FEATURES], 'bias': PRIOR['bias'], **PRIOR_SCALE}, 'starter'


def score_enrollments(enrollments):
    """Risk of dropping out for each enrolment, 0 to 1, with reasons."""
    params, source = _current_model()
    w = np.array(params['weights'], dtype=float)
    mean, std = np.array(params['mean'], dtype=float), np.array(params['std'], dtype=float)
    std[std == 0] = 1
    now = timezone.now()
    out = []
    for e in enrollments:
        f = _features_for(e, now)
        x = (np.array([f[k] for k in FEATURES], dtype=float) - mean) / std
        contrib = w * x
        p = float(_sigmoid(params['bias'] + contrib.sum()))
        reasons = [_reason(FEATURES[i], f) for i in np.argsort(-contrib)[:2] if contrib[i] > 0.15]
        out.append({'enrollment': e, 'student': e.user, 'course': e.course, 'risk': round(p, 2),
                    'level': 'high' if p >= 0.6 else 'medium' if p >= 0.35 else 'low',
                    'reasons': reasons, 'features': f, 'model': source})
    out.sort(key=lambda r: -r['risk'])
    return out


def _reason(name, f):
    v = f[name]
    return {
        'days_inactive': f'No activity for {v} days',
        'completion': f'Only {round(v * 100)}% of lessons done',
        'pace': f'Slow pace: {v:.1f} lessons a week',
        'attendance': f'Attendance {round(v * 100)}%',
        'avg_score': f'Average score {v:.0f}%',
        'failed_attempts': f'{v} failed assessment attempt{"s" if v != 1 else ""}',
        'days_to_expiry': f'Access ends in {v} days' if v >= 0 else 'Access has ended',
    }[name]


def at_risk_students(course=None, tutor=None, students=None, limit=20, min_level='medium'):
    qs = Enrollment.objects.filter(is_active=True).select_related('user', 'course')
    if course is not None:
        qs = qs.filter(course=course)
    if tutor is not None:
        qs = qs.filter(course__tutor=tutor)
    if students is not None:
        qs = qs.filter(user__in=students)
    order = {'low': 0, 'medium': 1, 'high': 2}
    rows = [r for r in score_enrollments(qs[:500]) if order[r['level']] >= order[min_level]]
    return rows[:limit]


def _label(enrollment, now):
    """1 if the student dropped out: access ran out and was not renewed within
    7 days, or no activity for 21+ days. None if it is too early to tell."""
    last = LessonProgress.objects.filter(user=enrollment.user, lesson__module__course=enrollment.course) \
        .aggregate(m=Max('completed_at'))['m'] or enrollment.created_at
    if enrollment.access_until and enrollment.access_until < now - timedelta(days=7):
        return 1
    if (now - last).days >= 21:
        return 1
    if (now - enrollment.created_at).days >= 28:
        return 0
    return None


def train_risk_model(min_samples=40, epochs=600, lr=0.1, l2=0.01):
    """Fit logistic regression with gradient descent (numpy only), hold out
    25% to measure accuracy and AUC, and save it if it beats chance."""
    now = timezone.now()
    X, y = [], []
    for e in Enrollment.objects.select_related('user', 'course')[:20000]:
        label = _label(e, now)
        if label is None:
            continue
        f = _features_for(e, now)
        X.append([f[k] for k in FEATURES])
        y.append(label)
    n = len(y)
    if n < min_samples or len(set(y)) < 2:
        return None, f'Not enough labelled history yet ({n} samples; need {min_samples} with both outcomes).'
    X, y = np.array(X, dtype=float), np.array(y, dtype=float)
    # Stratified 75/25 split, so both outcomes appear in the test set.
    rng = np.random.default_rng(42)
    tr, te = [], []
    for cls_ in (0.0, 1.0):
        members = rng.permutation(np.where(y == cls_)[0])
        cut = max(1, int(round(len(members) * 0.75)))
        if len(members) > 1:
            cut = min(cut, len(members) - 1)
        tr.extend(members[:cut])
        te.extend(members[cut:])
    tr, te = np.array(tr), np.array(te)
    mean, std = X[tr].mean(0), X[tr].std(0)
    std[std == 0] = 1
    Z = (X - mean) / std
    w, b = np.zeros(len(FEATURES)), 0.0
    for _ in range(epochs):
        p = _sigmoid(Z[tr] @ w + b)
        grad = p - y[tr]
        w -= lr * (Z[tr].T @ grad / len(tr) + l2 * w)
        b -= lr * grad.mean()
    p_te = _sigmoid(Z[te] @ w + b)
    acc = float(((p_te >= 0.5) == y[te]).mean()) if len(te) else 0.0
    auc = _auc(y[te], p_te)
    if auc < 0.55:
        return None, (f'Trained on {n} enrolments but the model was no better than chance (AUC {auc:.2f}); '
                      f'kept the current model.')
    run = ModelRun.objects.create(
        name='risk', n_samples=n,
        params={'weights': w.round(4).tolist(), 'bias': round(float(b), 4), 'mean': mean.round(4).tolist(),
                'std': std.round(4).tolist(), 'features': FEATURES},
        metrics={'accuracy': round(acc, 3), 'auc': round(auc, 3), 'test_size': int(len(te)),
                 'dropout_rate': round(float(y.mean()), 3)})
    return run, f'Trained on {n} enrolments: accuracy {acc:.0%}, AUC {auc:.2f}.'


def _auc(y, p):
    pos, neg = p[y == 1], p[y == 0]
    if not len(pos) or not len(neg):
        return 0.5
    wins = sum((pp > neg).sum() + 0.5 * (pp == neg).sum() for pp in pos)
    return float(wins / (len(pos) * len(neg)))


def feature_importance():
    params, source = _current_model()
    return source, sorted(({'feature': LABELS[f], 'weight': round(wt, 2)}
                           for f, wt in zip(FEATURES, params['weights'])), key=lambda r: -abs(r['weight']))


# ------------------------------------------------------- Recommendations ---

def recommend_courses(user, k=3):
    """Courses this student is likely to want next, with a reason each."""
    mine = set(Enrollment.objects.filter(user=user).values_list('course_id', flat=True))
    candidates = list(Course.objects.published().exclude(pk__in=mine).select_related('subject', 'tutor'))
    if not candidates:
        return []
    scores = defaultdict(float)
    reasons = {}
    # 1. Collaborative filtering: cosine similarity between course audiences.
    if mine:
        audience = defaultdict(set)
        for uid, cid in Enrollment.objects.values_list('user_id', 'course_id'):
            audience[cid].add(uid)
        for c in candidates:
            for m in mine:
                a, b = audience.get(c.pk, set()), audience.get(m, set())
                if a and b:
                    sim = len(a & b) / math.sqrt(len(a) * len(b))
                    if sim > 0:
                        scores[c.pk] += 2 * sim
                        reasons.setdefault(c.pk, 'Students in your courses also take this')
    # 2. Content: the student's level/year and the subjects they study.
    my_subjects = set(Course.objects.filter(pk__in=mine).values_list('subject_id', flat=True))
    level = 'a_level' if user.year in ('as', 'a2') or user.level == 'a_level' else \
        'university' if user.year in ('uni1', 'uni2') or user.level == 'university' else None
    popularity = dict(Enrollment.objects.values_list('course_id').annotate(n=Count('id')))
    top = max(popularity.values()) if popularity else 1
    for c in candidates:
        if c.subject_id in my_subjects:
            scores[c.pk] += 1.0
            reasons.setdefault(c.pk, f'Builds on your {c.subject.name}')
        if level and c.level in (level, 'both'):
            scores[c.pk] += 0.8
            reasons.setdefault(c.pk, f'Matches your {"A-level" if level == "a_level" else "university"} level')
        if user.year and c.year == user.year:
            scores[c.pk] += 0.6
        scores[c.pk] += 0.5 * popularity.get(c.pk, 0) / top
        reasons.setdefault(c.pk, 'Popular with students')
    ranked = sorted(candidates, key=lambda c: -scores[c.pk])[:k]
    for c in ranked:
        c.reason = reasons[c.pk]
    return ranked


# ----------------------------------------------------------- Forecasting ---

def weekly_revenue(weeks=26):
    since = timezone.now() - timedelta(weeks=weeks)
    rows = Payment.objects.filter(status=Payment.Status.COMPLETED, completed_at__gte=since) \
        .annotate(w=TruncWeek('completed_at')).values('w').annotate(t=Sum('amount')).order_by('w')
    data = {r['w'].date(): float(r['t']) for r in rows}
    if not data:
        return []
    start = min(data)
    end = timezone.localdate() - timedelta(days=timezone.localdate().weekday())
    out, d = [], start
    while d <= end:
        out.append({'week': d.isoformat(), 'total': data.get(d, 0.0)})
        d += timedelta(weeks=1)
    return out


def holt_forecast(values, horizon=8, alpha=0.5, beta=0.3):
    """Holt's linear trend method. Returns (fitted, forecast, band) where band
    is the half-width of an ~80% interval from the one-step residuals."""
    if len(values) < 2:
        return [], [], 0.0
    level, trend = values[0], values[1] - values[0]
    fitted, resid = [values[0]], []
    for v in values[1:]:
        pred = level + trend
        fitted.append(pred)
        resid.append(v - pred)
        new_level = alpha * v + (1 - alpha) * (level + trend)
        trend = beta * (new_level - level) + (1 - beta) * trend
        level = new_level
    forecast = [max(0.0, level + (h + 1) * trend) for h in range(horizon)]
    band = 1.28 * float(np.std(resid)) if resid else 0.0
    return fitted, forecast, band


def revenue_forecast(horizon=8):
    history = weekly_revenue()
    if len(history) < 4:
        return {'history': history, 'forecast': [], 'ready': False,
                'message': 'Forecasts appear after 4 weeks of payments.'}
    values = [h['total'] for h in history]
    _, fc, band = holt_forecast(values, horizon)
    last = timezone.datetime.fromisoformat(history[-1]['week']).date()
    forecast = [{'week': (last + timedelta(weeks=i + 1)).isoformat(), 'total': round(v, 2),
                 'low': round(max(0, v - band), 2), 'high': round(v + band, 2)} for i, v in enumerate(fc)]
    return {'history': history, 'forecast': forecast, 'ready': True,
            'next_month': round(sum(f['total'] for f in forecast[:4]), 2)}


# ------------------------------------------------------- Payment insights ---

def payment_insights(days=30):
    since = timezone.now() - timedelta(days=days)
    qs = Payment.objects.filter(created_at__gte=since)
    by_network = list(qs.values('network').annotate(
        total=Count('id'), ok=Count('id', filter=Q(status='completed'))).order_by('network'))
    for r in by_network:
        r['rate'] = round(r['ok'] * 100 / r['total']) if r['total'] else None
    by_hour = {r['h']: r for r in qs.annotate(h=ExtractHour('created_at')).values('h').annotate(
        total=Count('id'), ok=Count('id', filter=Q(status='completed')))}
    hours = [{'hour': h, 'total': by_hour.get(h, {}).get('total', 0), 'ok': by_hour.get(h, {}).get('ok', 0)}
             for h in range(24)]
    failures = list(qs.filter(status='failed').values('failure_code').annotate(n=Count('id')).order_by('-n')[:5])
    # Anomalies: many failed attempts by one account in a day (possible fraud
    # or a confused customer who needs help), and unusual daily volume.
    suspicious = list(Payment.objects.filter(created_at__gte=timezone.now() - timedelta(days=1), status='failed')
                      .values('user__email').annotate(n=Count('id')).filter(n__gte=4).order_by('-n'))
    daily = [r['n'] for r in qs.annotate(d=TruncDate('created_at')).values('d').annotate(n=Count('id'))]
    spike = None
    if len(daily) >= 7:
        arr = np.array(daily, dtype=float)
        z = (arr[-1] - arr[:-1].mean()) / (arr[:-1].std() or 1)
        if abs(z) >= 2.5:
            spike = {'z': round(float(z), 1), 'today': int(arr[-1]), 'usual': round(float(arr[:-1].mean()), 1)}
    return {'by_network': by_network, 'by_hour': hours, 'failures': failures, 'suspicious': suspicious,
            'spike': spike}


# ------------------------------------------------------------ Engagement ---

def lesson_dropoff(course):
    """Students who completed each lesson, in course order."""
    lessons = list(course.lessons())
    counts = dict(LessonProgress.objects.filter(lesson__in=lessons).values_list('lesson').annotate(n=Count('id')))
    enrolled = course.enrollments.count() or 1
    return [{'lesson': lesson.title, 'done': counts.get(lesson.pk, 0),
             'percent': round(counts.get(lesson.pk, 0) * 100 / enrolled)} for lesson in lessons]


def student_insights(user):
    """Plain-language coaching for a student's dashboard."""
    tips = []
    now = timezone.now()
    week = LessonProgress.objects.filter(user=user, completed_at__gte=now - timedelta(days=7)).count()
    streak = study_streak(user)
    if week == 0:
        tips.append('You have not completed a lesson this week. Even one short lesson keeps your momentum.')
    elif week >= 5:
        tips.append(f'Great week: {week} lessons done. Keep it up!')
    weak = Submission.objects.filter(student=user, status='graded', percent__lt=50) \
        .select_related('assessment__lesson').order_by('-graded_at').first()
    if weak and weak.assessment.lesson:
        tips.append(f'Revisit "{weak.assessment.lesson.title}" before your next attempt at {weak.assessment.title}.')
    for r in score_enrollments(Enrollment.objects.filter(user=user, is_active=True).select_related('course')):
        if r['level'] == 'high':
            tips.append(f'{r["course"].title}: {r["reasons"][0] if r["reasons"] else "you are falling behind"}.')
    return {'week': week, 'streak': streak, 'tips': tips[:3]}


def study_streak(user):
    days = set(LessonProgress.objects.filter(user=user).annotate(d=TruncDate('completed_at'))
               .values_list('d', flat=True))
    streak, d = 0, timezone.localdate()
    if d not in days:
        d -= timedelta(days=1)
    while d in days:
        streak += 1
        d -= timedelta(days=1)
    return streak


def platform_kpis():
    now = timezone.now()
    paid = Payment.objects.filter(status='completed')
    mrr = Enrollment.objects.filter(is_active=True, access_until__gt=now).aggregate(t=Sum('course__price'))['t']
    return {
        'mrr': mrr or Decimal(0),
        'arpu': paid.filter(completed_at__gte=now - timedelta(days=30)).aggregate(a=Avg('amount'))['a'] or 0,
        'learners_7d': LessonProgress.objects.filter(completed_at__gte=now - timedelta(days=7))
        .values('user').distinct().count(),
        'lessons_7d': LessonProgress.objects.filter(completed_at__gte=now - timedelta(days=7)).count(),
        'lessons_total': Lesson.objects.count(),
    }
