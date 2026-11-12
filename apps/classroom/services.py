"""Rules for classes: lesson gating, marking, the gradebook and alerts."""
from decimal import Decimal

from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone

from apps.notifications.services import notify

from .models import Assessment, Attendance, Question, Session, Submission

GRADE_BANDS = [(80, 'A'), (70, 'B'), (60, 'C'), (50, 'D'), (40, 'E'), (0, 'F')]


def letter(percent):
    if percent is None:
        return '–'
    for floor, grade in GRADE_BANDS:
        if percent >= floor:
            return grade
    return 'F'


# ------------------------------------------------------------------ Gating --

def best_submission(student, assessment):
    return assessment.submissions.filter(student=student).exclude(status=Submission.Status.IN_PROGRESS) \
        .order_by('-percent', '-submitted_at').first()


def satisfies(student, assessment):
    sub = best_submission(student, assessment)
    if sub is None:
        return False
    if assessment.must_pass_to_progress:
        # Work waiting for the tutor counts as attempted, so students aren't stuck.
        return sub.status == Submission.Status.SUBMITTED or sub.passed
    return True


def blocking_assessment(user, lesson):
    """The first required assessment on an EARLIER lesson of the course that
    the student hasn't completed, or None. Tutors and staff are never blocked."""
    course = lesson.module.course
    if not user.is_authenticated or user.is_staff or user.is_platform_admin or course.tutor_id == user.pk:
        return None
    earlier = []
    for item in course.lessons():
        if item.pk == lesson.pk:
            break
        earlier.append(item.pk)
    if not earlier:
        return None
    required = Assessment.objects.filter(course=course, lesson_id__in=earlier, is_published=True,
                                         required_to_progress=True).select_related('lesson')
    for assessment in required:
        if not satisfies(user, assessment):
            return assessment
    return None


# ----------------------------------------------------------------- Marking --

def attempts_left(student, assessment):
    used = assessment.submissions.filter(student=student).exclude(status=Submission.Status.IN_PROGRESS).count()
    return max(0, assessment.max_attempts - used)


def start_attempt(student, assessment):
    current = assessment.submissions.filter(student=student, status=Submission.Status.IN_PROGRESS).first()
    if current:
        return current
    last = assessment.submissions.filter(student=student).aggregate(n=Max('attempt'))['n'] or 0
    return Submission.objects.create(assessment=assessment, student=student, attempt=last + 1)


@transaction.atomic
def submit(submission, answers, upload=None):
    """Store answers, mark what can be marked automatically, and grade
    straight away when nothing needs a tutor."""
    assessment = submission.assessment
    questions = list(assessment.questions.all())
    earned = Decimal(0)
    marks = {}
    needs_tutor = bool(upload)
    for q in questions:
        got = q.mark(answers.get(str(q.pk), ''))
        if got is None:
            needs_tutor = True
        else:
            marks[str(q.pk)] = got
            earned += got
    submission.answers = answers
    submission.marks_by_question = marks
    if upload:
        submission.upload = upload
    submission.submitted_at = timezone.now()
    total = sum(q.marks for q in questions)
    if needs_tutor:
        submission.status = Submission.Status.SUBMITTED
        submission.score = earned
    else:
        submission.status = Submission.Status.GRADED
        submission.score = earned
        submission.percent = round(earned * 100 / total, 1) if total else Decimal(100)
        submission.graded_at = submission.submitted_at
    submission.save()
    if needs_tutor:
        notify(assessment.course.tutor, title=f'Work to mark: {assessment.title}',
               body=f'{submission.student.display_name} submitted attempt {submission.attempt}.',
               url=reverse('classroom:mark', args=[submission.pk]), send_email=False)
    else:
        _notify_result(submission)
    return submission


@transaction.atomic
def grade(submission, marks, feedback, grader):
    """Tutor marks the written questions (and any upload); auto marks stay."""
    questions = {str(q.pk): q for q in submission.assessment.questions.all()}
    final = dict(submission.marks_by_question)
    for qid, value in marks.items():
        if qid in questions:
            final[qid] = max(0, min(Decimal(value), questions[qid].marks))
    total = sum(q.marks for q in questions.values())
    earned = sum(Decimal(v) for v in final.values())
    if 'upload' in marks:  # a whole-paper mark for uploaded work, out of 100
        submission.percent = max(0, min(Decimal(marks['upload']), Decimal(100)))
        submission.score = submission.percent
    else:
        submission.score = earned
        submission.percent = round(earned * 100 / total, 1) if total else Decimal(0)
    submission.marks_by_question = {k: float(v) for k, v in final.items()}
    submission.feedback = feedback
    submission.status = Submission.Status.GRADED
    submission.graded_by = grader
    submission.graded_at = timezone.now()
    submission.save()
    _notify_result(submission)
    return submission


def _notify_result(submission):
    a, student = submission.assessment, submission.student
    title = f'{a.title}: {submission.percent}% ({letter(submission.percent)})'
    body = 'Well done, you passed.' if submission.passed else \
        f'The pass mark is {a.pass_mark}%. Review the lesson and try again if you have attempts left.'
    notify(student, title=title, body=body, url=reverse('classroom:result', args=[submission.pk]), send_email=False)
    for link in student.parent_links.select_related('parent'):
        notify(link.parent, title=f'{student.first_name or student.display_name} scored {submission.percent}% '
                                  f'in {a.title}', body=f'{a.course.title}. Grade {letter(submission.percent)}.',
               url=reverse('portal:parent_home'))


# --------------------------------------------------------------- Gradebook --

def gradebook(course, students=None):
    """Rows of (student, {assessment: best percent}, weighted average)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    assessments = list(course.assessments.filter(is_published=True))
    if students is None:
        students = User.objects.filter(enrollments__course=course).distinct().order_by('first_name')
    subs = Submission.objects.filter(assessment__in=assessments, student__in=students,
                                     status=Submission.Status.GRADED)
    best = {}
    for s in subs:
        key = (s.student_id, s.assessment_id)
        if key not in best or s.percent > best[key]:
            best[key] = s.percent
    rows = []
    for st in students:
        scores = [best.get((st.pk, a.pk)) for a in assessments]
        weighted, weights = Decimal(0), 0
        for a, sc in zip(assessments, scores):
            if sc is not None:
                weighted += sc * a.weight
                weights += a.weight
        avg = round(weighted / weights, 1) if weights else None
        rows.append({'student': st, 'scores': scores, 'average': avg, 'grade': letter(avg),
                     'attendance': attendance_rate(st, course)})
    return assessments, rows


def student_grades(student):
    """Every graded assessment for one student, newest first."""
    return Submission.objects.filter(student=student, status=Submission.Status.GRADED) \
        .select_related('assessment__course').order_by('-graded_at')


# -------------------------------------------------------------- Attendance --

def attendance_rate(student, course=None):
    qs = Attendance.objects.filter(student=student, session__is_cancelled=False)
    if course is not None:
        qs = qs.filter(session__course=course)
    total = qs.count()
    if not total:
        return None
    present = qs.filter(status__in=[Attendance.Status.PRESENT, Attendance.Status.LATE]).count()
    return round(present * 100 / total)


def check_in(session, student, code):
    if code.strip() != session.check_in_code:
        return None, 'That code is not right. Ask your tutor to show it again.'
    if not session.is_live:
        return None, 'Check-in is open from 15 minutes before the session until it ends.'
    late = timezone.now() > session.starts_at + timezone.timedelta(minutes=10)
    rec, _ = Attendance.objects.update_or_create(
        session=session, student=student,
        defaults={'status': Attendance.Status.LATE if late else Attendance.Status.PRESENT, 'self_checked_in': True})
    return rec, None


def save_register(session, marks, tutor):
    """marks: {student_id: status}. Alerts parents after two absences in a row."""
    for student in session.expected_students():
        status = marks.get(str(student.pk))
        if status not in Attendance.Status.values:
            continue
        Attendance.objects.update_or_create(session=session, student=student,
                                            defaults={'status': status, 'marked_by': tutor})
        if status == Attendance.Status.ABSENT:
            recent = Attendance.objects.filter(student=student, session__course=session.course) \
                .order_by('-session__starts_at')[:2]
            if len(recent) == 2 and all(r.status == Attendance.Status.ABSENT for r in recent):
                for link in student.parent_links.select_related('parent'):
                    notify(link.parent, title=f'{student.first_name or student.display_name} missed two sessions',
                           body=f'{session.course.title}: absent from the last two sessions. '
                                f'Please check in with them.', url=reverse('portal:parent_home'))


# ------------------------------------------------------------ Notifications --

def announce_session(session):
    for student in session.expected_students():
        notify(student, title=f'New session: {session.title}',
               body=f'{timezone.localtime(session.starts_at):%A %d %B at %H:%M}, {session.duration_minutes} minutes.',
               url=session.get_absolute_url(), send_email=True)


def send_session_reminders(window_minutes=60):
    now = timezone.now()
    due = Session.objects.filter(is_cancelled=False, reminder_sent=False, starts_at__gt=now,
                                 starts_at__lte=now + timezone.timedelta(minutes=window_minutes))
    count = 0
    for session in due:
        for student in session.expected_students():
            notify(student, title=f'Starting soon: {session.title}',
                   body=f'Starts at {timezone.localtime(session.starts_at):%H:%M}. Join from Catch Up.',
                   url=session.get_absolute_url())
            count += 1
        session.reminder_sent = True
        session.save(update_fields=['reminder_sent'])
    return count


def question_kinds():
    return Question.Kind.choices
