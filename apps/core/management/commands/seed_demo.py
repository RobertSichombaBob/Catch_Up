"""Fill a demo or staging site with realistic activity so every dashboard,
chart and model has something to show partners.

    python manage.py seed_catchup      # catalogue first
    python manage.py seed_demo         # then demo students, parents, payments...

Never run this on your live database: it creates fake students and payments.
It refuses unless DEBUG is on or --i-know-this-is-not-production is passed.
Demo accounts all use the password in DEMO_PASSWORD (default: CatchUp-demo-2026).
"""
import os
import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import ParentLink
from apps.classroom import services as cls
from apps.classroom.models import Assessment, Attendance, ClassGroup, ClassMembership, Question, Session
from apps.courses.models import Course, Enrollment, LessonProgress
from apps.ledger.models import LedgerEntry
from apps.ledger.services import record_sale
from apps.payments.models import Payment
from apps.schools.models import School, SchoolMember

User = get_user_model()
FIRST = ['Chanda', 'Mutale', 'Bwalya', 'Thandiwe', 'Mapalo', 'Kondwani', 'Lubasi', 'Namwinga', 'Chilufya',
         'Musonda', 'Taonga', 'Mwape', 'Precious', 'Daliso', 'Natasha', 'Kabwe', 'Luyando', 'Mulenga',
         'Chisomo', 'Inonge', 'Kasonde', 'Mwansa', 'Tiza', 'Bupe']
LAST = ['Mwanza', 'Banda', 'Phiri', 'Tembo', 'Zulu', 'Mulenga', 'Chola', 'Lungu', 'Sakala', 'Daka', 'Ngoma',
        'Kunda', 'Musonda', 'Mumba', 'Nyirenda', 'Kapata']
NETWORKS = [('MTN', '096'), ('AIRTEL', '097'), ('ZAMTEL', '095')]


class Command(BaseCommand):
    help = 'Create demo students, parents, a school, payments, classes and grades (not for production).'

    def add_arguments(self, parser):
        parser.add_argument('--students', type=int, default=36)
        parser.add_argument('--i-know-this-is-not-production', action='store_true', dest='force')

    @transaction.atomic
    def handle(self, *args, **opts):
        if not settings.DEBUG and not opts['force']:
            raise CommandError('Refusing to add demo data with DEBUG off. Pass --i-know-this-is-not-production '
                               'if this really is a demo or staging site.')
        courses = list(Course.objects.filter(is_published=True).select_related('tutor'))
        if not courses:
            raise CommandError('Run "python manage.py seed_catchup" first.')
        if User.objects.filter(email='student@demo.catchup').exists():
            self.stdout.write('Demo data already present.')
            return
        rnd = random.Random(2026)
        pw = os.environ.get('DEMO_PASSWORD', 'CatchUp-demo-2026')
        now = timezone.now()

        def person(email, first, last, role=User.Role.STUDENT, **extra):
            return User.objects.create_user(email=email, password=pw, first_name=first, last_name=last, role=role,
                                            **extra)

        star = person('student@demo.catchup', 'Chanda', 'Mwanza', year='a2', level='a_level', phone='0971234567')
        parent = person('parent@demo.catchup', 'Grace', 'Mwanza', role=User.Role.PARENT, phone='0961234567')
        ParentLink.objects.create(parent=parent, student=star, relationship='Mother')
        students = [star]
        for i in range(opts['students'] - 1):
            f, l = rnd.choice(FIRST), rnd.choice(LAST)
            students.append(person(f'{f.lower()}.{l.lower()}{i}@demo.catchup', f, l,
                                   year=rnd.choice(['as', 'a2', 'uni1', 'uni2']),
                                   level=rnd.choice(['a_level', 'university'])))

        school = School.objects.create(name='Lusaka Demo Secondary School', kind='secondary', town='Lusaka',
                                       province='Lusaka', contact_name='Head Teacher',
                                       contact_email='head@demo.catchup', is_approved=True,
                                       about='A demo school showing timetabled classes, registers and gradebooks.')
        head = person('school@demo.catchup', 'Head', 'Teacher', role=User.Role.STUDENT)
        SchoolMember.objects.create(school=school, user=head, role='admin')
        for s in students[:12]:
            SchoolMember.objects.create(school=school, user=s, role='student', class_name='Form 6A')

        # Payments over the last 20 weeks, growing, so the forecast has a trend.
        payments = 0
        for s in students:
            for course in rnd.sample(courses, k=rnd.choice([1, 1, 2, 2, 3])):
                months = rnd.choice([1, 2, 3, 4])
                first = now - timedelta(days=rnd.randint(5, 140), hours=rnd.choice([0, 1, 2, 3, 5, 8, 9, 10, 11, 12, 13]), minutes=rnd.randint(0, 59))
                e = Enrollment.objects.create(user=s, course=course, created_at=first,
                                              access_until=first + timedelta(days=30 * months))
                for m in range(months):
                    when = first + timedelta(days=30 * m)
                    if when > now:
                        break
                    net, prefix = rnd.choice(NETWORKS)
                    payer = parent if s == star and m % 2 else s
                    p = Payment.objects.create(user=payer, student=s if payer != s else None, course=course,
                                               amount=course.price, network=net, msisdn=f'260{prefix[1:]}{rnd.randint(1000000, 9999999)}',
                                               provider='simulator', status=Payment.Status.COMPLETED,
                                               completed_at=when, provider_reference=f'DEMO-{payments}')
                    Payment.objects.filter(pk=p.pk).update(created_at=when)
                    record_sale(p)
                    LedgerEntry.objects.filter(payment=p).update(created_at=when)
                    payments += 1
                if s == star:
                    e.access_until = now + timedelta(days=rnd.choice([2, 18]))
                    e.save(update_fields=['access_until'])
                # Lesson progress: about 65% of students stay active (recent
                # activity); the rest drift away, which the risk model learns from.
                lessons = list(course.lessons())
                active = s == star or rnd.random() < 0.65
                share = rnd.uniform(0.5, 1.0) if active else rnd.uniform(0.1, 0.45)
                done = lessons[:max(1, int(len(lessons) * share))]
                last = now - timedelta(days=rnd.uniform(0, 6)) if active else \
                    min(now - timedelta(days=rnd.uniform(24, 40)), first + timedelta(days=rnd.uniform(3, 12)))
                last = max(last, first + timedelta(hours=1))
                span = (last - first) / max(1, len(done))
                for j, lesson in enumerate(done):
                    lp = LessonProgress.objects.create(user=s, lesson=lesson)
                    LessonProgress.objects.filter(pk=lp.pk).update(completed_at=first + span * (j + 1))
                if not active and rnd.random() < 0.6:
                    e.access_until = min(e.access_until, now - timedelta(days=rnd.randint(8, 30)))
                    e.save(update_fields=['access_until'])
        # A few failed payments for the network-success table.
        for _ in range(14):
            net, prefix = rnd.choice(NETWORKS)
            Payment.objects.create(user=rnd.choice(students), course=rnd.choice(courses), amount=Decimal('80'),
                                   network=net, msisdn=f'260{prefix[1:]}{rnd.randint(1000000, 9999999)}',
                                   provider='simulator', status=Payment.Status.FAILED,
                                   failure_code='PAYMENT_NOT_APPROVED', failure_message='Declined on the phone.')

        # Classroom: groups, sessions with registers, quizzes with marks.
        for course in courses:
            enrolled = [e.user for e in course.enrollments.select_related('user')]
            group = ClassGroup.objects.create(course=course, name='Evening class', capacity=40,
                                              meeting_url='https://meet.google.com/demo-catchup')
            for st in enrolled[:20]:
                ClassMembership.objects.get_or_create(class_group=group, student=st)
            for k in range(6, 0, -1):
                s = Session.objects.create(course=course, tutor=course.tutor, title=f'Live class {7 - k}',
                                           starts_at=now - timedelta(days=k * 7, hours=2),
                                           meeting_url='https://meet.google.com/demo-catchup')
                for st in enrolled:
                    Attendance.objects.create(session=s, student=st, status=rnd.choices(
                        ['present', 'late', 'absent'], weights=[7, 1, 2])[0], marked_by=course.tutor)
            for k in (1, 3, 8):
                Session.objects.create(course=course, tutor=course.tutor, title=f'Live class: week {k} revision',
                                       starts_at=now + timedelta(days=k, hours=rnd.randint(1, 5)),
                                       meeting_url='https://meet.google.com/demo-catchup', kind='class')
            lessons = list(course.lessons())
            if not lessons:
                continue
            a = Assessment.objects.create(course=course, lesson=lessons[0], title=f'Check-in quiz: {lessons[0].title}'[:160],
                                          kind='quiz', is_published=True, required_to_progress=True, pass_mark=50,
                                          weight=20, max_attempts=3)
            q1 = Question.objects.create(assessment=a, order=1, kind='mcq', text='Which statement is correct?',
                                         choices='The first option\nThe second option\nThe third option', answer='2',
                                         explanation='The second option follows from the key idea in the lesson.')
            q2 = Question.objects.create(assessment=a, order=2, kind='numeric', text='What is \\( 12 \\times 7 \\)?',
                                         answer='84')
            for st in enrolled:
                if rnd.random() < 0.8:
                    sub = cls.start_attempt(st, a)
                    cls.submit(sub, {str(q1.pk): rnd.choice(['2', '2', '1']), str(q2.pk): rnd.choice(['84', '84', '48'])})
        self.stdout.write(self.style.SUCCESS(
            f'Demo ready: {len(students)} students, {payments} payments, 1 school.\n'
            f'  Student: student@demo.catchup  Parent: parent@demo.catchup  School admin: school@demo.catchup\n'
            f'  Password: {pw}'))
