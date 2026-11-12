import secrets

from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

INVITE_ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'  # no 0/O or 1/I, easy to read aloud


def new_invite_code():
    return ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(6))


def tutor_document_path(instance, filename):
    return f'private/tutors/{instance.user_id}/{secrets.token_hex(8)}-{filename}'


def photo_path(instance, filename):
    return f'public/avatars/{instance.pk or "new"}-{secrets.token_hex(6)}-{filename}'


class CatchUpUserManager(UserManager):
    """Users sign in with their email address. A username is still stored
    because Django's admin expects one, and it is generated from the email."""

    def _unique_username(self, email):
        base = (email.split('@')[0] or 'user')[:140]
        username, n = base, 2
        while self.model.objects.filter(username__iexact=username).exists():
            username = f'{base}{n}'
            n += 1
        return username

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError('An email address is required.')
        email = self.normalize_email(email).lower()
        extra.setdefault('username', self._unique_username(email))
        username = extra.pop('username')
        return super().create_user(username, email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        email = self.normalize_email(email).lower()
        extra.setdefault('username', self._unique_username(email))
        extra.setdefault('role', User.Role.ADMIN)
        username = extra.pop('username')
        return super().create_superuser(username, email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        STUDENT = 'student', 'Student'
        TUTOR = 'tutor', 'Tutor'
        PARENT = 'parent', 'Parent or guardian'
        ADMIN = 'admin', 'Administrator'

    class Level(models.TextChoices):
        A_LEVEL = 'a_level', 'A-level'
        UNIVERSITY = 'university', 'University'
        OTHER = 'other', 'Other'

    class Year(models.TextChoices):
        AS = 'as', 'A-level: AS (Year 12)'
        A2 = 'a2', 'A-level: A2 (Year 13)'
        UNI_1 = 'uni1', 'University: 1st year'
        UNI_2 = 'uni2', 'University: 2nd year'

    email = models.EmailField('email address', unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.STUDENT)
    phone = models.CharField(max_length=20, blank=True, help_text='Mobile money number, e.g. 0971234567')
    level = models.CharField(max_length=20, choices=Level.choices, blank=True)
    institution = models.CharField(max_length=150, blank=True)
    headline = models.CharField(max_length=150, blank=True, help_text='Tutors: shown on course pages')
    bio = models.TextField(blank=True)
    email_notifications = models.BooleanField(default=True)
    year = models.CharField('year of study', max_length=10, choices=Year.choices, blank=True)
    photo = models.ImageField(upload_to=photo_path, blank=True,
                              validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    invite_code = models.CharField(max_length=8, blank=True, db_index=True,
                                   help_text='Students share this with a parent to link accounts.')

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username']

    objects = CatchUpUserManager()

    class Meta:
        ordering = ['first_name', 'last_name']

    def __str__(self):
        return self.get_full_name() or self.email

    def save(self, *args, **kwargs):
        if self.email:
            self.email = self.email.strip().lower()
        if self.role == self.Role.STUDENT and not self.invite_code:
            self.invite_code = new_invite_code()
        super().save(*args, **kwargs)

    @property
    def display_name(self):
        return self.get_full_name() or self.email.split('@')[0]

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        if parts:
            return ''.join(p[0] for p in parts).upper()[:2]
        return self.email[:2].upper()

    @property
    def is_tutor(self):
        return self.role == self.Role.TUTOR

    @property
    def is_student(self):
        return self.role == self.Role.STUDENT

    @property
    def is_parent(self):
        return self.role == self.Role.PARENT

    @property
    def is_platform_admin(self):
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_verified_tutor(self):
        """Tutors may publish and be paid only after an admin approves their
        documents. Platform admins can always publish their own courses."""
        if self.is_platform_admin:
            return True
        if not self.is_tutor:
            return False
        profile = getattr(self, 'tutor_profile', None)
        return bool(profile and profile.status == TutorProfile.Status.APPROVED)

    @property
    def children(self):
        return User.objects.filter(parent_links__parent=self).order_by('first_name')

    @property
    def home_url_name(self):
        if self.is_platform_admin or self.is_staff:
            return 'portal:admin_home'
        if self.is_tutor:
            return 'core:tutor_dashboard'
        if self.is_parent:
            return 'portal:parent_home'
        return 'core:dashboard'


class ParentLink(models.Model):
    """A parent or guardian who may follow a student's progress. Created
    when the parent enters the student's invite code, so the student has
    agreed by sharing it. Either side can remove the link."""
    parent = models.ForeignKey(User, on_delete=models.CASCADE, related_name='child_links',
                               limit_choices_to={'role': User.Role.PARENT})
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='parent_links',
                                limit_choices_to={'role': User.Role.STUDENT})
    relationship = models.CharField(max_length=40, blank=True, help_text='e.g. Mother, Father, Guardian')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['parent', 'student'], name='unique_parent_link')]
        ordering = ['student__first_name']

    def __str__(self):
        return f'{self.parent} follows {self.student}'


DOC_TYPES = ['pdf', 'jpg', 'jpeg', 'png']


class TutorProfile(models.Model):
    """Every tutor is vetted before they can publish or be paid: a TCZ
    (Teaching Council of Zambia) registration, a degree, and a specialisation
    in each subject they teach."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Not submitted yet'
        SUBMITTED = 'submitted', 'Waiting for review'
        APPROVED = 'approved', 'Verified'
        REJECTED = 'rejected', 'Changes needed'

    class Qualification(models.TextChoices):
        DIPLOMA = 'diploma', 'Diploma in Education'
        BACHELOR = 'bachelor', "Bachelor's degree"
        MASTER = 'master', "Master's degree"
        PHD = 'phd', 'Doctorate (PhD)'

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='tutor_profile')
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    tcz_number = models.CharField('TCZ registration number', max_length=40, blank=True)
    nrc_number = models.CharField('NRC or passport number', max_length=40, blank=True)
    qualification = models.CharField('highest qualification', max_length=12, choices=Qualification.choices, blank=True)
    degree_title = models.CharField(max_length=160, blank=True, help_text='e.g. BSc Education (Mathematics)')
    degree_institution = models.CharField('awarding institution', max_length=160, blank=True)
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    specialisations = models.ManyToManyField('courses.Subject', blank=True, related_name='specialist_tutors',
                                             help_text='Subjects your degree qualifies you to teach')
    years_experience = models.PositiveSmallIntegerField(default=0)
    current_school = models.CharField('current school or university', max_length=160, blank=True)
    tcz_certificate = models.FileField(upload_to=tutor_document_path, blank=True,
                                       validators=[FileExtensionValidator(DOC_TYPES)])
    degree_certificate = models.FileField(upload_to=tutor_document_path, blank=True,
                                          validators=[FileExtensionValidator(DOC_TYPES)])
    id_document = models.FileField('NRC or passport copy', upload_to=tutor_document_path, blank=True,
                                   validators=[FileExtensionValidator(DOC_TYPES)])
    cv = models.FileField('CV (optional)', upload_to=tutor_document_path, blank=True,
                          validators=[FileExtensionValidator(['pdf', 'docx'])])
    payout_phone = models.CharField('mobile money number for payouts', max_length=20, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='+')
    review_note = models.TextField(blank=True, help_text='Shown to the tutor when changes are needed')

    class Meta:
        ordering = ['-submitted_at']

    def __str__(self):
        return f'{self.user} ({self.get_status_display()})'

    REQUIRED_FIELDS_FOR_SUBMIT = ('tcz_number', 'nrc_number', 'qualification', 'degree_title',
                                  'degree_institution', 'tcz_certificate', 'degree_certificate', 'id_document')

    def missing_items(self):
        missing = [self._meta.get_field(f).verbose_name for f in self.REQUIRED_FIELDS_FOR_SUBMIT
                   if not getattr(self, f)]
        if self.pk and not self.specialisations.exists():
            missing.append('at least one specialisation')
        return missing

    def mark_submitted(self):
        self.status = self.Status.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=['status', 'submitted_at'])
