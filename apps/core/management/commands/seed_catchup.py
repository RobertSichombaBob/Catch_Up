"""Create the starter subjects, tutors, admins and courses.

Safe to run on every deploy: it only adds what is missing. Courses are only
created when the database has none, so it never duplicates a live catalogue.
"""
import os
import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import TutorProfile
from apps.core import seed_data
from apps.courses.models import Course, Lesson, Module, Subject

User = get_user_model()


class Command(BaseCommand):
    help = 'Add the starter catalogue and placeholder accounts (idempotent).'

    def add_arguments(self, parser):
        parser.add_argument('--update-content', action='store_true',
                            help='Overwrite starter lessons with the built-in text (undoes edits made on the site).')

    def _password(self, email):
        pw = os.environ.get('SEED_ACCOUNT_PASSWORD')
        if pw:
            return pw
        pw = secrets.token_urlsafe(12)
        self.stdout.write(f'  {email}: {pw}')
        return pw

    @transaction.atomic
    def handle(self, *args, **opts):
        subjects = {}
        for slug, name, tagline, icon, colour, order in seed_data.SUBJECTS:
            subjects[slug], _ = Subject.objects.get_or_create(
                slug=slug, defaults={'name': name, 'tagline': tagline, 'icon': icon, 'colour': colour, 'order': order})

        for email, first, last in seed_data.ADMINS:
            if not User.objects.filter(email=email).exists():
                User.objects.create_superuser(email=email, password=self._password(email), first_name=first,
                                              last_name=last, role=User.Role.ADMIN)

        for email, first, last, headline, subj, degree in seed_data.TUTORS:
            user = User.objects.filter(email=email).first()
            if not user:
                user = User.objects.create_user(email=email, password=self._password(email), first_name=first,
                                                last_name=last, role=User.Role.TUTOR, headline=headline,
                                                bio=f'{first} is a qualified, TCZ-registered teacher. {headline}.')
            profile, created = TutorProfile.objects.get_or_create(user=user, defaults={
                'status': TutorProfile.Status.APPROVED, 'qualification': TutorProfile.Qualification.BACHELOR,
                'degree_title': degree, 'degree_institution': 'University of Zambia', 'tcz_number': 'PLACEHOLDER',
                'years_experience': 6, 'review_note': 'Seeded placeholder tutor. Replace before launch.'})
            if created:
                profile.specialisations.set([subjects[s] for s in subj])

        if Course.objects.exists() and not opts['update_content']:
            self.stdout.write('Courses already exist; starter courses skipped.')
            return
        for spec in seed_data.COURSES:
            tutor = User.objects.get(email=spec['tutor'])
            course, _ = Course.objects.get_or_create(title=spec['title'], defaults={
                'subject': subjects[spec['subject']], 'tutor': tutor, 'level': spec['level'], 'year': spec['year'],
                'summary': spec['summary'], 'outcomes': spec['outcomes'],
                'description': f'<p>{spec["summary"]} Every lesson has a worked example and a check-yourself '
                               f'question, and the first lesson is free.</p>'})
            order = 0
            for m_index, (m_title, lessons) in enumerate(spec['modules'], start=1):
                module, _ = Module.objects.get_or_create(course=course, title=m_title, defaults={'order': m_index})
                for l_index, item in enumerate(lessons, start=1):
                    order += 1
                    obj = Lesson.objects.filter(module=module, title=item['title']).first()
                    if obj is None:
                        Lesson.objects.create(module=module, title=item['title'], order=l_index,
                                              content=item['content'], is_preview=order == 1)
                    elif opts['update_content']:
                        obj.content = item['content']
                        obj.save()
        self.stdout.write(self.style.SUCCESS('Starter catalogue ready.'))
