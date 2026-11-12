"""Role portals: a sign-in page for each kind of user, the parent area,
tutor verification, and the administrator's control room."""
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncWeek
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.accounts.forms import LoginForm
from apps.analytics import services as analytics
from apps.schools.models import School
from apps.accounts.models import ParentLink, TutorProfile
from apps.courses.models import Course, Enrollment, LessonProgress, active_enrollment_q
from apps.ledger.models import LedgerEntry
from apps.ledger.services import totals
from apps.notifications.services import notify
from apps.payments.models import Payment

from .forms import LinkChildForm, ParentSignUpForm, TutorReviewForm, TutorSignUpForm, TutorVerificationForm

User = get_user_model()

PORTALS = {
    'student': {'title': 'Student sign-in', 'lead': 'Pick up your lessons where you left off.', 'icon': 'graduation',
                'signup': 'accounts:signup', 'signup_label': 'Create a free student account'},
    'parent': {'title': 'Parent sign-in', 'lead': "Follow your child's progress, attendance and payments.",
               'icon': 'heart', 'signup': 'portal:parent_signup', 'signup_label': 'Create a parent account'},
    'tutor': {'title': 'Tutor sign-in', 'lead': 'Manage your courses, students and earnings.', 'icon': 'briefcase',
              'signup': 'portal:tutor_signup', 'signup_label': 'Apply to teach on Catch Up'},
    'admin': {'title': 'Administrator sign-in', 'lead': 'Restricted to Catch Up staff.', 'icon': 'shield',
              'signup': None, 'signup_label': ''},
}


def role_of(user):
    if user.is_platform_admin or user.is_staff:
        return 'admin'
    return {'tutor': 'tutor', 'parent': 'parent'}.get(user.role, 'student')


def choose(request):
    if request.user.is_authenticated:
        return redirect(request.user.home_url_name)
    return render(request, 'portal/choose.html', {'portals': PORTALS})


class PortalLoginView(auth_views.LoginView):
    """Same email login as everywhere, but each portal only lets in its own
    role and sends people to their own dashboard."""
    form_class = LoginForm
    template_name = 'portal/login.html'
    portal = 'student'

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(portal=self.portal, info=PORTALS[self.portal], portals=PORTALS)
        return ctx

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(request.user.home_url_name)
        return super().dispatch(request, *args, **kwargs)

    def form_valid(self, form):
        user = form.get_user()
        actual = role_of(user)
        if actual != self.portal:
            form.add_error(None, f'This is the {PORTALS[self.portal]["title"].lower()} page. '
                                 f'Your account is a {actual} account, so please use the '
                                 f'{PORTALS[actual]["title"].lower()} page.')
            return self.form_invalid(form)
        response = super().form_valid(form)
        if not form.cleaned_data.get('remember'):
            self.request.session.set_expiry(0)
        return response

    def get_default_redirect_url(self):
        return reverse(self.request.user.home_url_name)


def _signup(request, form_class, template, welcome):
    if request.user.is_authenticated:
        return redirect(request.user.home_url_name)
    form = form_class(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user, backend='apps.accounts.backends.EmailBackend')
        notify(user, title=welcome['title'], body=welcome['body'], url=reverse(user.home_url_name))
        messages.success(request, f'Welcome, {user.first_name}!')
        return redirect(welcome.get('next') or user.home_url_name)
    return render(request, template, {'form': form})


@require_http_methods(['GET', 'POST'])
def parent_signup(request):
    return _signup(request, ParentSignUpForm, 'portal/parent_signup.html', {
        'title': 'Welcome to Catch Up',
        'body': "Ask your child for the 6-character invite code on their profile, then link their account "
                "to follow their progress.",
        'next': 'portal:parent_link',
    })


@require_http_methods(['GET', 'POST'])
def tutor_signup(request):
    return _signup(request, TutorSignUpForm, 'portal/tutor_signup.html', {
        'title': 'Thanks for applying to teach',
        'body': 'Upload your TCZ certificate, degree and ID so we can verify you. Most reviews take 2 working days.',
        'next': 'portal:tutor_apply',
    })


# ---------------------------------------------------------------- Tutors ---

def _require_tutor(user):
    if not user.is_tutor:
        raise PermissionDenied


@login_required
@require_http_methods(['GET', 'POST'])
def tutor_apply(request):
    _require_tutor(request.user)
    profile, _ = TutorProfile.objects.get_or_create(user=request.user)
    locked = profile.status in (TutorProfile.Status.SUBMITTED, TutorProfile.Status.APPROVED)
    form = TutorVerificationForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == 'POST' and not locked and form.is_valid():
        profile = form.save()
        if 'submit' in request.POST:
            missing = profile.missing_items()
            if missing:
                messages.error(request, 'Saved. Before submitting, please add: ' + ', '.join(str(m) for m in missing) + '.')
            else:
                profile.mark_submitted()
                for admin in User.objects.filter(Q(role=User.Role.ADMIN) | Q(is_superuser=True), is_active=True):
                    notify(admin, title=f'Tutor application: {request.user.display_name}',
                           body='Documents are ready for review.',
                           url=reverse('portal:admin_tutor', args=[profile.pk]), send_email=False)
                messages.success(request, "Submitted. We'll email you when your review is done.")
        else:
            messages.success(request, 'Your details are saved.')
        return redirect('portal:tutor_apply')
    return render(request, 'portal/tutor_apply.html', {'form': form, 'profile': profile, 'locked': locked})


def tutors(request):
    qs = User.objects.filter(role=User.Role.TUTOR, is_active=True,
                             tutor_profile__status=TutorProfile.Status.APPROVED) \
        .select_related('tutor_profile').prefetch_related('tutor_profile__specialisations') \
        .annotate(course_count=Count('courses_taught', filter=Q(courses_taught__is_published=True)))
    subject = request.GET.get('subject', '')
    if subject:
        qs = qs.filter(tutor_profile__specialisations__slug=subject)
    from apps.courses.models import Subject
    return render(request, 'portal/tutors.html', {'tutors': qs, 'subjects': Subject.objects.all(),
                                                   'subject': subject})


def tutor_profile(request, pk):
    tutor = get_object_or_404(User.objects.select_related('tutor_profile'), pk=pk, role=User.Role.TUTOR,
                              tutor_profile__status=TutorProfile.Status.APPROVED)
    courses = tutor.courses_taught.published().select_related('subject') \
        .annotate(lesson_count=Count('modules__lessons', distinct=True))
    students = Enrollment.objects.filter(course__tutor=tutor, is_active=True).values('user').distinct().count()
    return render(request, 'portal/tutor_profile.html', {'tutor': tutor, 'courses': courses, 'students': students})


# ---------------------------------------------------------------- Parents ---

def _require_parent(user):
    if not user.is_parent:
        raise PermissionDenied


def child_summary(child, link_id=None):
    from apps.classroom.services import attendance_rate, student_grades
    grades = list(student_grades(child)[:5])
    all_grades = [g.percent for g in student_grades(child)]
    enrollments = list(child.enrollments.select_related('course__subject', 'course__tutor'))
    for e in enrollments:
        e.percent = e.progress()
    week_ago = timezone.now() - timedelta(days=7)
    last = child.lesson_progress.order_by('-completed_at').first()
    return {
        'child': child,
        'enrollments': enrollments,
        'lessons_this_week': child.lesson_progress.filter(completed_at__gte=week_ago).count(),
        'last_active': last.completed_at if last else child.last_login,
        'payments': child.payments.select_related('course')[:5],
        'needs_renewal': [e for e in enrollments if e.has_access and e.renewal_due],
        'expired': [e for e in enrollments if not e.has_access],
        'attendance': attendance_rate(child),
        'grades': grades,
        'average': round(sum(all_grades) / len(all_grades), 1) if all_grades else None,
        'link_id': link_id,
    }


@login_required
def parent_home(request):
    _require_parent(request.user)
    children = [child_summary(link.student, link.pk) for link in
                request.user.child_links.select_related('student')]
    return render(request, 'portal/parent_home.html', {'children': children})


@login_required
@require_http_methods(['GET', 'POST'])
def parent_link(request):
    _require_parent(request.user)
    form = LinkChildForm(request.POST or None, parent=request.user)
    if request.method == 'POST' and form.is_valid():
        ParentLink.objects.create(parent=request.user, student=form.student,
                                  relationship=form.cleaned_data['relationship'])
        notify(form.student, title=f'{request.user.display_name} is now following your progress',
               body='If you did not share your invite code with them, remove the link on your profile page.',
               url=reverse('accounts:profile'))
        messages.success(request, f'You are now linked to {form.student.display_name}.')
        return redirect('portal:parent_home')
    return render(request, 'portal/parent_link.html', {'form': form})


@login_required
@require_POST
def unlink(request, pk):
    """Either the parent or the student can remove a link."""
    link = get_object_or_404(ParentLink, pk=pk)
    if request.user not in (link.parent, link.student):
        raise Http404
    link.delete()
    messages.success(request, 'The link has been removed.')
    return redirect(request.user.home_url_name if request.user.is_parent else 'accounts:profile')


# ----------------------------------------------------------- Administrator ---

def _require_admin(user):
    if not (user.is_platform_admin or user.is_staff):
        raise PermissionDenied


@login_required
def admin_home(request):
    _require_admin(request.user)
    now = timezone.now()
    since = now - timedelta(days=30)
    paid = Payment.objects.filter(status=Payment.Status.COMPLETED)
    recent = Payment.objects.filter(created_at__gte=since)
    by_network = []
    for code, label in Payment._meta.get_field('network').choices:
        n = recent.filter(network=code)
        total = n.count()
        ok = n.filter(status=Payment.Status.COMPLETED).count()
        by_network.append({'code': code, 'label': label, 'total': total, 'ok': ok,
                           'rate': round(ok * 100 / total) if total else None})
    weekly = paid.filter(completed_at__gte=now - timedelta(weeks=12)) \
        .annotate(week=TruncWeek('completed_at')).values('week') \
        .annotate(total=Sum('amount'), count=Count('id')).order_by('week')
    split = totals()
    split30 = totals(LedgerEntry.objects.filter(created_at__gte=since))
    roles = dict(User.objects.values_list('role').annotate(n=Count('id')))
    top_courses = Course.objects.annotate(
        students=Count('enrollments', filter=active_enrollment_q('enrollments__'), distinct=True),
        revenue=Sum('payments__amount', filter=Q(payments__status=Payment.Status.COMPLETED)),
    ).select_related('tutor', 'subject').order_by('-revenue', '-students')[:8]
    active_learners = LessonProgress.objects.filter(completed_at__gte=now - timedelta(days=7)) \
        .values('user').distinct().count()
    return render(request, 'portal/admin_home.html', {
        'revenue_total': paid.aggregate(t=Sum('amount'))['t'] or 0,
        'revenue_30': paid.filter(completed_at__gte=since).aggregate(t=Sum('amount'))['t'] or 0,
        'split': split, 'split30': split30,
        'roles': {'students': roles.get('student', 0), 'parents': roles.get('parent', 0),
                  'tutors': roles.get('tutor', 0), 'admins': roles.get('admin', 0)},
        'pending_tutors': TutorProfile.objects.filter(status=TutorProfile.Status.SUBMITTED).select_related('user'),
        'by_network': by_network,
        'weekly': [{'week': w['week'].date().isoformat(), 'total': float(w['total']), 'count': w['count']}
                   for w in weekly],
        'top_courses': top_courses,
        'active_learners': active_learners,
        'active_subscriptions': Enrollment.objects.filter(active_enrollment_q()).count(),
        'recent_payments': Payment.objects.select_related('user', 'course')[:8],
        'kpis': analytics.platform_kpis(),
        'at_risk': analytics.at_risk_students(limit=8),
        'forecast': analytics.revenue_forecast(),
        'pay_insights': analytics.payment_insights(),
        'schools_pending': School.objects.filter(is_approved=False).count(),
    })


@login_required
def admin_tutors(request):
    _require_admin(request.user)
    status = request.GET.get('status', TutorProfile.Status.SUBMITTED)
    qs = TutorProfile.objects.select_related('user').prefetch_related('specialisations')
    if status != 'all':
        qs = qs.filter(status=status)
    counts = dict(TutorProfile.objects.values_list('status').annotate(n=Count('id')))
    return render(request, 'portal/admin_tutors.html', {
        'profiles': qs, 'status': status, 'statuses': TutorProfile.Status.choices, 'counts': counts})


@login_required
@require_http_methods(['GET', 'POST'])
def admin_tutor(request, pk):
    _require_admin(request.user)
    profile = get_object_or_404(TutorProfile.objects.select_related('user'), pk=pk)
    form = TutorReviewForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        approve = form.cleaned_data['decision'] == 'approve'
        profile.status = TutorProfile.Status.APPROVED if approve else TutorProfile.Status.REJECTED
        profile.review_note = form.cleaned_data['note']
        profile.reviewed_by = request.user
        profile.reviewed_at = timezone.now()
        profile.save()
        if approve:
            notify(profile.user, title='You are verified to teach on Catch Up',
                   body='Your documents were approved. You can now create courses, publish them and earn '
                        '50% of every student payment.', url=reverse('core:tutor_dashboard'))
        else:
            notify(profile.user, title='Your tutor application needs changes',
                   body=profile.review_note, url=reverse('portal:tutor_apply'))
        messages.success(request, f'{profile.user.display_name} has been {"approved" if approve else "sent back"}.')
        return redirect('portal:admin_tutors')
    docs = [(f, profile._meta.get_field(f).verbose_name, getattr(profile, f))
            for f in ('tcz_certificate', 'degree_certificate', 'id_document', 'cv')]
    return render(request, 'portal/admin_tutor.html', {'profile': profile, 'form': form, 'docs': docs})


DOC_FIELDS = {'tcz_certificate', 'degree_certificate', 'id_document', 'cv'}


@login_required
def tutor_document(request, pk, field):
    """Private documents: only admins and the tutor themselves can open them."""
    profile = get_object_or_404(TutorProfile, pk=pk)
    if field not in DOC_FIELDS:
        raise Http404
    if not (request.user.is_platform_admin or request.user.is_staff or request.user == profile.user):
        raise PermissionDenied
    f = getattr(profile, field)
    if not f:
        raise Http404
    return FileResponse(f.open('rb'), filename=f.name.rsplit('/', 1)[-1])
