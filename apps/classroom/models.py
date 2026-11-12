"""Everything a tutor needs to run a class: groups, live sessions and
bookings, attendance, continuous assessment, grading and announcements."""
import secrets
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from apps.core.utils import sanitize_html


def new_check_in_code():
    return f'{secrets.randbelow(10000):04d}'


def submission_path(instance, filename):
    return f'private/submissions/{instance.assessment_id}/{secrets.token_hex(8)}-{filename}'


class ClassGroup(models.Model):
    """A cohort within a course, e.g. "Pure Maths, Saturday group"."""
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='class_groups')
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    capacity = models.PositiveSmallIntegerField(default=40)
    meeting_url = models.URLField('default meeting link', blank=True,
                                  help_text='Google Meet, Zoom or Teams link used for this group\'s sessions')
    students = models.ManyToManyField(settings.AUTH_USER_MODEL, through='ClassMembership', related_name='class_groups')
    is_open = models.BooleanField('students can join', default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['course__title', 'name']

    def __str__(self):
        return f'{self.course.title}: {self.name}'

    @property
    def seats_left(self):
        return max(0, self.capacity - self.memberships.count())


class ClassMembership(models.Model):
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name='memberships')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='memberships')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['class_group', 'student'], name='unique_class_membership')]


class Session(models.Model):
    """A scheduled live class, tutorial or one-to-one lesson."""

    class Kind(models.TextChoices):
        CLASS = 'class', 'Live class'
        TUTORIAL = 'tutorial', 'Tutorial'
        EXTRA = 'extra', 'Extra lesson'
        ONE_TO_ONE = 'one_to_one', 'One-to-one lesson'
        EXAM_PREP = 'exam_prep', 'Exam preparation'

    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='sessions')
    class_group = models.ForeignKey(ClassGroup, null=True, blank=True, on_delete=models.SET_NULL,
                                    related_name='sessions', help_text='Leave empty for every student in the course')
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sessions_taught')
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.CLASS)
    starts_at = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60, validators=[MinValueValidator(10),
                                                                                MaxValueValidator(480)])
    meeting_url = models.URLField('meeting link', blank=True)
    location = models.CharField(max_length=160, blank=True, help_text='For in-person sessions')
    agenda = models.TextField(blank=True)
    check_in_code = models.CharField(max_length=4, default=new_check_in_code,
                                     help_text='Students enter this during the session to mark themselves present')
    recording_url = models.URLField(blank=True)
    is_cancelled = models.BooleanField(default=False)
    reminder_sent = models.BooleanField(default=False, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['starts_at']

    def __str__(self):
        return f'{self.title} ({timezone.localtime(self.starts_at):%d %b %H:%M})'

    @property
    def ends_at(self):
        return self.starts_at + timezone.timedelta(minutes=self.duration_minutes)

    @property
    def is_live(self):
        now = timezone.now()
        return self.starts_at - timezone.timedelta(minutes=15) <= now <= self.ends_at

    @property
    def is_past(self):
        return timezone.now() > self.ends_at

    @property
    def link(self):
        return self.meeting_url or (self.class_group.meeting_url if self.class_group else '')

    def expected_students(self):
        from django.contrib.auth import get_user_model

        from apps.courses.models import active_enrollment_q
        User = get_user_model()
        if self.kind == self.Kind.ONE_TO_ONE:
            return User.objects.filter(bookings__session=self)
        if self.class_group_id:
            return self.class_group.students.all()
        return User.objects.filter(enrollments__in=self.course.enrollments.filter(active_enrollment_q())).distinct()

    def get_absolute_url(self):
        return reverse('classroom:session', args=[self.pk])


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'present', 'Present'
        LATE = 'late', 'Late'
        ABSENT = 'absent', 'Absent'
        EXCUSED = 'excused', 'Excused'

    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name='attendance')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='attendance')
    status = models.CharField(max_length=10, choices=Status.choices)
    note = models.CharField(max_length=200, blank=True)
    self_checked_in = models.BooleanField(default=False)
    marked_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='+')
    marked_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['session', 'student'], name='unique_attendance')]
        verbose_name_plural = 'attendance'

    @property
    def counts_as_present(self):
        return self.status in (self.Status.PRESENT, self.Status.LATE)


class Booking(models.Model):
    """A student asks their tutor for an extra lesson. The tutor confirms
    it, which creates a one-to-one session with a meeting link."""

    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Requested'
        CONFIRMED = 'confirmed', 'Confirmed'
        DECLINED = 'declined', 'Declined'
        CANCELLED = 'cancelled', 'Cancelled'

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bookings')
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='bookings')
    preferred_start = models.DateTimeField()
    duration_minutes = models.PositiveSmallIntegerField(default=60, choices=[(30, '30 minutes'), (45, '45 minutes'),
                                                                             (60, '1 hour'), (90, '1.5 hours'),
                                                                             (120, '2 hours')])
    topic = models.CharField(max_length=200, help_text='What would you like help with?')
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    tutor_reply = models.CharField(max_length=300, blank=True)
    session = models.ForeignKey(Session, null=True, blank=True, on_delete=models.SET_NULL, related_name='bookings')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.student} · {self.topic}'


class Assessment(models.Model):
    """A quiz, problem set, test or assignment. Quizzes with multiple choice,
    numeric and short answers are marked automatically; written answers and
    uploaded work are marked by the tutor."""

    class Kind(models.TextChoices):
        QUIZ = 'quiz', 'Quiz'
        PROBLEM_SET = 'problem_set', 'Problem set'
        TEST = 'test', 'Test'
        ASSIGNMENT = 'assignment', 'Assignment'
        EXAM = 'exam', 'Exam'

    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='assessments')
    lesson = models.ForeignKey('courses.Lesson', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='assessments', help_text='Attach to a lesson for continuous assessment')
    title = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.QUIZ)
    instructions = models.TextField(blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    time_limit_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    max_attempts = models.PositiveSmallIntegerField(default=2, validators=[MinValueValidator(1)])
    pass_mark = models.PositiveSmallIntegerField('pass mark (%)', default=50, validators=[MaxValueValidator(100)])
    weight = models.PositiveSmallIntegerField('weight in final grade (%)', default=10,
                                              validators=[MaxValueValidator(100)])
    required_to_progress = models.BooleanField(
        default=True, help_text='Students must attempt this before opening the next lesson')
    must_pass_to_progress = models.BooleanField(
        default=False, help_text='Students must reach the pass mark, not just attempt it')
    allow_file_upload = models.BooleanField(default=False, help_text='Students can upload their worked solutions')
    show_answers_after = models.BooleanField('show correct answers after submitting', default=True)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['course', 'lesson__module__order', 'lesson__order', 'created_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.instructions = sanitize_html(self.instructions)
        super().save(*args, **kwargs)

    @property
    def total_marks(self):
        return sum(q.marks for q in self.questions.all())

    def get_absolute_url(self):
        return reverse('classroom:assessment', args=[self.pk])


class Question(models.Model):
    class Kind(models.TextChoices):
        MCQ = 'mcq', 'Multiple choice'
        NUMERIC = 'numeric', 'Numeric answer'
        SHORT = 'short', 'Short answer (exact text)'
        WRITTEN = 'written', 'Written answer (tutor marks)'

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='questions')
    order = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.MCQ)
    text = models.TextField(help_text='Maths: \\( x^2 \\) inline or \\[ x^2 \\] on its own line')
    choices = models.TextField(blank=True, help_text='Multiple choice: one option per line')
    answer = models.CharField(max_length=300, blank=True,
                              help_text='Multiple choice: the number of the correct option (1, 2, 3...). '
                                        'Numeric: the value. Short answer: accepted answers separated by |')
    tolerance = models.DecimalField(max_digits=10, decimal_places=4, default=Decimal('0'),
                                    help_text='Numeric: how far from the answer still counts as correct')
    marks = models.PositiveSmallIntegerField(default=1)
    explanation = models.TextField(blank=True, help_text='Shown after submitting')

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return self.text[:60]

    @property
    def choice_list(self):
        return [c.strip() for c in self.choices.splitlines() if c.strip()]

    @property
    def auto_marked(self):
        return self.kind != self.Kind.WRITTEN

    def mark(self, response):
        """Marks earned for a response, or None if a tutor must mark it."""
        response = (response or '').strip()
        if self.kind == self.Kind.WRITTEN:
            return None
        if not response:
            return 0
        if self.kind == self.Kind.MCQ:
            return self.marks if response == self.answer.strip() else 0
        if self.kind == self.Kind.NUMERIC:
            try:
                given = Decimal(response.replace(',', ''))
                target = Decimal(self.answer.replace(',', ''))
            except Exception:  # noqa: BLE001
                return 0
            return self.marks if abs(given - target) <= self.tolerance else 0
        accepted = {a.strip().lower() for a in self.answer.split('|') if a.strip()}
        return self.marks if response.lower() in accepted else 0


class Submission(models.Model):
    class Status(models.TextChoices):
        IN_PROGRESS = 'in_progress', 'In progress'
        SUBMITTED = 'submitted', 'Waiting for marking'
        GRADED = 'graded', 'Marked'

    assessment = models.ForeignKey(Assessment, on_delete=models.CASCADE, related_name='submissions')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')
    attempt = models.PositiveSmallIntegerField(default=1)
    answers = models.JSONField(default=dict, blank=True)
    marks_by_question = models.JSONField(default=dict, blank=True)
    upload = models.FileField(upload_to=submission_path, blank=True,
                              validators=[FileExtensionValidator(['pdf', 'jpg', 'jpeg', 'png', 'docx'])])
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IN_PROGRESS)
    score = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    feedback = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                                  related_name='+')

    class Meta:
        ordering = ['-started_at']
        constraints = [models.UniqueConstraint(fields=['assessment', 'student', 'attempt'],
                                               name='unique_submission_attempt')]

    def __str__(self):
        return f'{self.student} · {self.assessment} · attempt {self.attempt}'

    @property
    def passed(self):
        return self.percent is not None and self.percent >= self.assessment.pass_mark

    @property
    def is_late(self):
        due = self.assessment.due_at
        return bool(due and self.submitted_at and self.submitted_at > due)


class Announcement(models.Model):
    course = models.ForeignKey('courses.Course', on_delete=models.CASCADE, related_name='class_announcements')
    class_group = models.ForeignKey(ClassGroup, null=True, blank=True, on_delete=models.CASCADE,
                                    related_name='announcements')
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='+')
    title = models.CharField(max_length=160)
    body = models.TextField()
    notify_parents = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title
