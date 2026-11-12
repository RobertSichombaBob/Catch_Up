from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods, require_POST

from apps.classroom.models import Session
from apps.notifications.services import notify

from .forms import JoinForm, SchoolForm
from .models import School, SchoolMember

User = get_user_model()


def index(request):
    schools = School.objects.filter(is_approved=True).annotate(n=Count('members'))
    return render(request, 'schools/index.html', {'schools': schools, 'form': SchoolForm(),
                                                  'join_form': JoinForm()})


@login_required
@require_http_methods(['GET', 'POST'])
def register(request):
    form = SchoolForm(request.POST or None, request.FILES or None,
                      initial={'contact_name': request.user.display_name, 'contact_email': request.user.email})
    if request.method == 'POST' and form.is_valid():
        school = form.save()
        SchoolMember.objects.create(school=school, user=request.user, role=SchoolMember.Role.ADMIN)
        for admin in User.objects.filter(Q(role='admin') | Q(is_superuser=True), is_active=True):
            notify(admin, title=f'New school: {school.name}', body=f'{school.get_kind_display()}, {school.town}.',
                   url=f'/admin/schools/school/{school.pk}/change/', send_email=False)
        messages.success(request, f'{school.name} is set up. Share the join codes with your teachers and students.')
        return redirect('schools:manage', slug=school.slug)
    return render(request, 'schools/register.html', {'form': form})


@login_required
@require_POST
def join(request):
    form = JoinForm(request.POST)
    if not form.is_valid():
        messages.error(request, 'Enter your school join code.')
        return redirect('schools:index')
    code = form.cleaned_data['code'].strip().upper()
    school = School.objects.filter(Q(teacher_code=code) | Q(student_code=code)).first()
    if not school:
        messages.error(request, 'That code is not recognised. Check it with your school.')
        return redirect('schools:index')
    role = SchoolMember.Role.TEACHER if school.teacher_code == code else SchoolMember.Role.STUDENT
    SchoolMember.objects.get_or_create(school=school, user=request.user,
                                       defaults={'role': role, 'class_name': form.cleaned_data['class_name']})
    messages.success(request, f'Welcome to {school.name}.')
    return redirect('schools:detail', slug=school.slug)


def _membership(user, school):
    if not user.is_authenticated:
        return None
    return SchoolMember.objects.filter(school=school, user=user).first()


def detail(request, slug):
    school = get_object_or_404(School, slug=slug)
    member = _membership(request.user, school)
    staff = request.user.is_authenticated and (request.user.is_staff or request.user.is_platform_admin)
    if not member and not staff and not school.is_approved:
        return render(request, 'schools/pending.html', {'school': school}, status=404)
    courses = school.courses.filter(is_published=True).select_related('subject', 'tutor') \
        .annotate(lesson_count=Count('modules__lessons', distinct=True))
    teachers = school.members.filter(role__in=['teacher', 'admin']).select_related('user')
    sessions = Session.objects.filter(course__school=school, is_cancelled=False,
                                      starts_at__gte=timezone.now()).select_related('course')[:8]
    return render(request, 'schools/detail.html', {
        'school': school, 'member': member, 'courses': courses, 'teachers': teachers, 'sessions': sessions,
        'counts': dict(school.members.values_list('role').annotate(n=Count('id'))), 'staff': staff})


@login_required
def manage(request, slug):
    school = get_object_or_404(School, slug=slug)
    member = _membership(request.user, school)
    if not (member and member.role == SchoolMember.Role.ADMIN) and not request.user.is_platform_admin:
        raise PermissionDenied
    members = school.members.select_related('user')
    role = request.GET.get('role', '')
    if role:
        members = members.filter(role=role)
    from apps.classroom.services import attendance_rate
    rows = []
    for m in members[:300]:
        rows.append({'m': m, 'attendance': attendance_rate(m.user) if m.role == 'student' else None,
                     'courses': m.user.enrollments.filter(is_active=True).count()})
    return render(request, 'schools/manage.html', {
        'school': school, 'rows': rows, 'role': role, 'roles': SchoolMember.Role.choices,
        'courses': school.courses.select_related('tutor'),
        'counts': dict(school.members.values_list('role').annotate(n=Count('id'))),
        'join_url': request.build_absolute_uri(reverse('schools:index'))})


@login_required
@require_POST
def member_update(request, slug, pk):
    school = get_object_or_404(School, slug=slug)
    me = _membership(request.user, school)
    if not (me and me.role == SchoolMember.Role.ADMIN) and not request.user.is_platform_admin:
        raise PermissionDenied
    m = get_object_or_404(SchoolMember, pk=pk, school=school)
    action = request.POST.get('action')
    if action == 'remove' and m.user != request.user:
        m.delete()
        messages.success(request, 'Member removed.')
    elif action in SchoolMember.Role.values:
        m.role = action
        m.save(update_fields=['role'])
        messages.success(request, f'{m.user.display_name} is now a {m.get_role_display().lower()}.')
    return redirect('schools:manage', slug=slug)


@login_required
@require_POST
def new_codes(request, slug):
    school = get_object_or_404(School, slug=slug)
    me = _membership(request.user, school)
    if not (me and me.role == SchoolMember.Role.ADMIN):
        raise PermissionDenied
    from .models import join_code
    school.teacher_code, school.student_code = join_code(), join_code()
    school.save(update_fields=['teacher_code', 'student_code'])
    messages.success(request, 'New join codes created. The old ones no longer work.')
    return redirect('schools:manage', slug=slug)
