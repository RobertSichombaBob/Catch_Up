"""Schools, colleges and universities can run on Catch Up: their own
teachers, students and private courses, with a school dashboard."""
import secrets

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models
from django.urls import reverse

from apps.core.utils import unique_slugify


def logo_path(instance, filename):
    return f'public/schools/{secrets.token_hex(8)}-{filename}'


def join_code():
    return secrets.token_hex(4).upper()


class School(models.Model):
    class Kind(models.TextChoices):
        SECONDARY = 'secondary', 'Secondary school (A-level)'
        COLLEGE = 'college', 'College'
        UNIVERSITY = 'university', 'University'
        TUTORING = 'tutoring', 'Tutoring centre'

    class Plan(models.TextChoices):
        TRIAL = 'trial', 'Free trial'
        STANDARD = 'standard', 'Standard'
        PREMIUM = 'premium', 'Premium'

    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=90, unique=True, blank=True)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.SECONDARY)
    town = models.CharField(max_length=80, blank=True)
    province = models.CharField(max_length=80, blank=True)
    about = models.TextField(blank=True)
    logo = models.ImageField(upload_to=logo_path, blank=True,
                             validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    contact_name = models.CharField(max_length=120)
    contact_email = models.EmailField()
    contact_phone = models.CharField(max_length=20, blank=True)
    student_count_estimate = models.PositiveIntegerField('number of students (approximate)', default=0)
    plan = models.CharField(max_length=10, choices=Plan.choices, default=Plan.TRIAL)
    is_approved = models.BooleanField(default=False, help_text='Approved schools appear publicly')
    teacher_code = models.CharField(max_length=12, default=join_code, unique=True)
    student_code = models.CharField(max_length=12, default=join_code, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slugify(self, self.name, max_length=90)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('schools:detail', args=[self.slug])


class SchoolMember(models.Model):
    class Role(models.TextChoices):
        ADMIN = 'admin', 'School administrator'
        TEACHER = 'teacher', 'Teacher'
        STUDENT = 'student', 'Student'

    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='school_memberships')
    role = models.CharField(max_length=10, choices=Role.choices)
    class_name = models.CharField(max_length=60, blank=True, help_text='e.g. Form 6A, BSc Year 1')
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['school', 'user'], name='unique_school_member')]
        ordering = ['role', 'user__first_name']

    def __str__(self):
        return f'{self.user} · {self.school} ({self.get_role_display()})'
