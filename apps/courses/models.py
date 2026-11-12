import re
import secrets
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.core.utils import sanitize_html, unique_slugify


def default_price():
    return Decimal(settings.COURSE_PRICE_ZMW)


def cover_path(instance, filename):
    return f'public/covers/{secrets.token_hex(8)}-{filename}'


def material_path(instance, filename):
    return f'private/materials/{instance.course_id}/{secrets.token_hex(8)}-{filename}'


def active_enrollment_q(prefix=''):
    """Enrolments that currently give access: active and either lifetime
    (no end date) or paid up until a date still in the future."""
    now = timezone.now()
    return Q(**{f'{prefix}is_active': True}) & (
        Q(**{f'{prefix}access_until__isnull': True}) | Q(**{f'{prefix}access_until__gt': now}))


class Subject(models.Model):
    name = models.CharField(max_length=80, unique=True)
    slug = models.SlugField(max_length=80, unique=True)
    tagline = models.CharField(max_length=160, blank=True)
    icon = models.CharField(max_length=40, default='book', help_text='Icon name from static/img/icons.svg')
    colour = models.CharField(max_length=7, default='#4F46E5', help_text='Hex colour, e.g. #4F46E5')
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'name']

    def __str__(self):
        return self.name


class PublishedCourseQuerySet(models.QuerySet):
    def published(self):
        """Public catalogue: published and not private to a school."""
        return self.filter(is_published=True, school__isnull=True)

    def visible_to(self, user):
        qs = self.filter(is_published=True)
        if user.is_authenticated:
            return qs.filter(Q(school__isnull=True) | Q(school__members__user=user)).distinct()
        return qs.filter(school__isnull=True)


class Course(models.Model):
    class Level(models.TextChoices):
        A_LEVEL = 'a_level', 'A-level'
        UNIVERSITY = 'university', 'University'
        BOTH = 'both', 'A-level & University'

    subject = models.ForeignKey(Subject, on_delete=models.PROTECT, related_name='courses')
    tutor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='courses_taught',
                              limit_choices_to={'role__in': ['tutor', 'admin']},
                              help_text='A verified tutor, or an admin for courses the platform runs itself')
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    level = models.CharField(max_length=20, choices=Level.choices, default=Level.BOTH)
    summary = models.CharField(max_length=240)
    description = models.TextField(blank=True, help_text='HTML allowed; it is cleaned when saved.')
    outcomes = models.TextField(blank=True, help_text='One learning outcome per line.')
    year = models.CharField('year of study', max_length=10, blank=True,
                            choices=[('as', 'AS (Year 12)'), ('a2', 'A2 (Year 13)'),
                                     ('uni1', 'University 1st year'), ('uni2', 'University 2nd year')])
    cover = models.ImageField(upload_to=cover_path, blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])],
                              help_text='Optional photo for the course card, at least 1200 x 675 pixels')
    school = models.ForeignKey('schools.School', null=True, blank=True, on_delete=models.SET_NULL,
                               related_name='courses',
                               help_text='Private to this school\'s members. Empty means public.')
    price = models.DecimalField('monthly price (K)', max_digits=8, decimal_places=2, default=default_price)
    is_published = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = PublishedCourseQuerySet.as_manager()

    class Meta:
        ordering = ['subject__order', 'title']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title, max_length=90)
        self.description = sanitize_html(self.description)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('courses:detail', args=[self.slug])

    @property
    def outcome_list(self):
        return [line.strip() for line in self.outcomes.splitlines() if line.strip()]

    def lessons(self):
        return Lesson.objects.filter(module__course=self).order_by('module__order', 'order', 'pk')

    def first_lesson(self):
        return self.lessons().first()

    def is_free(self):
        return self.price <= 0

    @property
    def is_platform_course(self):
        """Courses run by the platform's own staff keep 100% of revenue."""
        return self.tutor.is_platform_admin

    def enrollment_for(self, user):
        if not user.is_authenticated:
            return None
        return self.enrollments.filter(user=user).first()

    def is_enrolled(self, user):
        if not user.is_authenticated:
            return False
        return self.enrollments.filter(Q(user=user) & active_enrollment_q()).exists()

    def can_access_all(self, user):
        """Enrolled students, the course tutor and admins can open every lesson."""
        if not user.is_authenticated:
            return False
        if user.is_platform_admin or user.is_staff or self.tutor_id == user.pk:
            return True
        return self.is_enrolled(user)


class Module(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='modules')
    title = models.CharField(max_length=160)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ['order', 'pk']

    def __str__(self):
        return f'{self.course.title}: {self.title}'


class Lesson(models.Model):
    module = models.ForeignKey(Module, on_delete=models.CASCADE, related_name='lessons')
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=90)
    order = models.PositiveSmallIntegerField(default=0)
    content = models.TextField(help_text='Lesson HTML. Scripts and unsafe tags are removed when saved.')
    minutes = models.PositiveSmallIntegerField(default=0, help_text='Estimated reading time. Leave 0 to calculate it.')
    is_preview = models.BooleanField(default=False, help_text='Free for everyone, even without paying')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['module__order', 'order', 'pk']
        constraints = [models.UniqueConstraint(fields=['module', 'slug'], name='unique_lesson_slug_per_module')]

    def __str__(self):
        return self.title

    @property
    def course(self):
        return self.module.course

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.title, max_length=90,
                                       queryset=Lesson.objects.filter(module=self.module))
        self.content = sanitize_html(self.content)
        if not self.minutes:
            words = len(re.findall(r'\w+', strip_tags(self.content)))
            self.minutes = max(4, round(words / 110))  # study pace, slower than casual reading
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('courses:lesson', args=[self.module.course.slug, self.pk])

    def can_view(self, user):
        return self.is_preview or self.module.course.can_access_all(user)


class Enrollment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name='enrollments')
    payment = models.OneToOneField('payments.Payment', null=True, blank=True, on_delete=models.SET_NULL,
                                   related_name='enrollment')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)
    last_lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    access_until = models.DateTimeField(null=True, blank=True,
                                        help_text='End of the paid month. Empty means no end date.')

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'course'], name='unique_enrollment')]

    def __str__(self):
        return f'{self.user} in {self.course}'

    @property
    def has_access(self):
        return self.is_active and (self.access_until is None or self.access_until > timezone.now())

    @property
    def days_left(self):
        if self.access_until is None:
            return None
        return max(0, (self.access_until - timezone.now()).days)

    @property
    def renewal_due(self):
        days = self.days_left
        return days is not None and days <= settings.RENEWAL_WINDOW_DAYS

    def extend_access(self, days):
        start = max(self.access_until or timezone.now(), timezone.now())
        self.access_until = start + timedelta(days=days)

    def progress(self):
        total = self.course.lessons().count()
        if not total:
            return 0
        done = LessonProgress.objects.filter(user=self.user, lesson__module__course=self.course).count()
        return round(done * 100 / total)

    def next_lesson(self):
        done = LessonProgress.objects.filter(user=self.user, lesson__module__course=self.course) \
            .values_list('lesson_id', flat=True)
        return self.course.lessons().exclude(pk__in=list(done)).first() or self.course.first_lesson()


class LessonProgress(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='lesson_progress')
    lesson = models.ForeignKey(Lesson, on_delete=models.CASCADE, related_name='progress')
    completed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'lesson'], name='unique_lesson_progress')]


class CourseMaterial(models.Model):
    """A file a tutor attaches to a course or a lesson: notes, slides,
    tutorial sheets, past papers. Stored privately and only served to
    students who have access."""

    class Kind(models.TextChoices):
        PDF = 'pdf', 'PDF'
        WORD = 'word', 'Word document'
        SLIDES = 'slides', 'PowerPoint slides'
        HTML = 'html', 'Web page (HTML)'
        SHEET = 'sheet', 'Spreadsheet'
        IMAGE = 'image', 'Image'

    class Category(models.TextChoices):
        NOTES = 'notes', 'Notes'
        SLIDES = 'slides', 'Slides'
        TUTORIAL = 'tutorial', 'Tutorial sheet'
        PAST_PAPER = 'past_paper', 'Past paper'
        BOOK = 'book', 'Book or chapter'
        OTHER = 'other', 'Other'

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='materials')
    lesson = models.ForeignKey(Lesson, null=True, blank=True, on_delete=models.SET_NULL, related_name='materials',
                               help_text='Optional: show this file inside one lesson')
    title = models.CharField(max_length=160)
    description = models.CharField(max_length=300, blank=True)
    category = models.CharField(max_length=12, choices=Category.choices, default=Category.NOTES)
    file = models.FileField(upload_to=material_path)
    kind = models.CharField(max_length=10, choices=Kind.choices, editable=False)
    size = models.PositiveIntegerField(default=0, editable=False)
    html = models.TextField(blank=True, editable=False, help_text='Readable copy shown in the browser')
    allow_download = models.BooleanField(default=True)
    is_preview = models.BooleanField('free for everyone', default=False)
    order = models.PositiveSmallIntegerField(default=0)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name='+')
    views = models.PositiveIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order', '-created_at']

    def __str__(self):
        return self.title

    @property
    def filename(self):
        return self.file.name.rsplit('/', 1)[-1].split('-', 1)[-1]

    @property
    def icon(self):
        return {'pdf': 'file', 'word': 'file', 'slides': 'grid', 'html': 'globe', 'sheet': 'grid',
                'image': 'eye'}.get(self.kind, 'file')

    def can_view(self, user):
        return self.is_preview or self.course.can_access_all(user)

    def get_absolute_url(self):
        return reverse('courses:material', args=[self.course.slug, self.pk])
