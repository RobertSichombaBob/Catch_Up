"""Tests for the full platform: money split, parents, verification, monthly
access, assessments and gating, attendance, schools, portals, the JSON API,
and a sweep that renders every page as every kind of user."""
import io
import zipfile
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import ParentLink, TutorProfile
from apps.classroom import services as cls
from apps.classroom.models import Assessment, Attendance, Booking, ClassGroup, Question, Session, Submission
from apps.courses.models import Course, CourseMaterial, Enrollment, Lesson, Module, Subject
from apps.ledger.models import LedgerEntry
from apps.ledger.services import split, tutor_balance
from apps.payments.models import Payment
from apps.payments.services import PaymentRefused, start_payment
from apps.schools.models import School, SchoolMember

User = get_user_model()
EMAIL = 'django.core.mail.backends.locmem.EmailBackend'
PW = 'x-Pass-12345'


def build_world():
    subject = Subject.objects.create(name='Mathematics', slug='mathematics', icon='sigma', colour='#0e7a4f')
    tutor = User.objects.create_user(email='t@example.com', password=PW, role=User.Role.TUTOR,
                                     first_name='Tess', last_name='Tutor')
    profile = TutorProfile.objects.create(user=tutor, status=TutorProfile.Status.APPROVED, tcz_number='TCZ1',
                                          degree_title='BSc Mathematics')
    profile.specialisations.set([subject])
    student = User.objects.create_user(email='s@example.com', password=PW, first_name='Sam', last_name='Student')
    parent = User.objects.create_user(email='p@example.com', password=PW, role=User.Role.PARENT,
                                      first_name='Pat', last_name='Parent')
    admin = User.objects.create_superuser(email='a@example.com', password=PW, role=User.Role.ADMIN, first_name='Ada')
    course = Course.objects.create(subject=subject, tutor=tutor, title='Pure Maths', summary='s',
                                   price=Decimal('80.00'), is_published=True)
    module = Module.objects.create(course=course, title='M1', order=1)
    l1 = Lesson.objects.create(module=module, title='One', order=1, content='<p>1</p>', is_preview=True)
    l2 = Lesson.objects.create(module=module, title='Two', order=2, content='<p>2</p>')
    l3 = Lesson.objects.create(module=module, title='Three', order=3, content='<p>3</p>')
    return dict(subject=subject, tutor=tutor, student=student, parent=parent, admin=admin, course=course,
                lessons=[l1, l2, l3])


def enrol(user, course, days=30):
    e, _ = Enrollment.objects.get_or_create(user=user, course=course)
    e.is_active = True
    e.access_until = timezone.now() + timedelta(days=days)
    e.save()
    return e


class SplitTests(TestCase):
    def test_split_adds_up_and_odd_ngwee_goes_to_platform(self):
        self.assertEqual(split(8000, 50, '0'), (0, 4000, 4000))
        fee, tutor, platform = split(8001, 50, '3')
        self.assertEqual(fee + tutor + platform, 8001)
        self.assertEqual(fee, 240)
        self.assertEqual(tutor, (8001 - 240) // 2)
        self.assertGreaterEqual(platform, tutor)


@override_settings(EMAIL_BACKEND=EMAIL, PAYMENT_PROVIDER='simulator', ALLOW_PAYMENT_SIMULATOR=True)
class MoneyAndParentTests(TestCase):
    def setUp(self):
        self.w = build_world()

    def _approve(self, client, payment):
        client.post(reverse('payments:simulate', args=[payment.pk]), {'decision': 'approve'})
        payment.refresh_from_db()

    def test_student_payment_splits_50_50_and_gives_a_month(self):
        w = self.w
        self.client.force_login(w['student'])
        p = start_payment(w['student'], w['course'], 'AIRTEL', '0971234567')
        self._approve(self.client, p)
        self.assertEqual(p.status, Payment.Status.COMPLETED)
        e = Enrollment.objects.get(user=w['student'], course=w['course'])
        self.assertTrue(e.has_access)
        self.assertGreaterEqual(e.days_left, 29)
        self.assertEqual(tutor_balance(w['tutor']), Decimal('40'))
        total = sum(LedgerEntry.objects.filter(payment=p).values_list('amount_ngwee', flat=True))
        self.assertEqual(total, 8000)
        # Approving twice never pays twice.
        self._approve(self.client, p)
        self.assertEqual(LedgerEntry.objects.filter(payment=p, kind='sale').count(), 2)

    def test_admin_course_keeps_100_percent(self):
        w = self.w
        own = Course.objects.create(subject=w['subject'], tutor=w['admin'], title='Admin course', summary='s',
                                    price=Decimal('80.00'), is_published=True)
        self.client.force_login(w['student'])
        p = start_payment(w['student'], own, 'MTN', '0961234567')
        self._approve(self.client, p)
        self.assertFalse(LedgerEntry.objects.filter(payment=p, account='tutor').exists())
        self.assertEqual(LedgerEntry.objects.get(payment=p, account='platform').amount_ngwee, 8000)

    def test_parent_links_by_code_and_pays_for_child(self):
        w = self.w
        self.client.force_login(w['parent'])
        r = self.client.post(reverse('portal:parent_link'), {'code': w['student'].invite_code,
                                                            'relationship': 'Mother'})
        self.assertRedirects(r, reverse('portal:parent_home'))
        self.assertTrue(ParentLink.objects.filter(parent=w['parent'], student=w['student']).exists())
        p = start_payment(w['parent'], w['course'], 'ZAMTEL', '0951234567', student=w['student'])
        self._approve(self.client, p)
        self.assertTrue(Enrollment.objects.get(user=w['student'], course=w['course']).has_access)
        self.assertEqual(self.client.get(reverse('portal:parent_home')).status_code, 200)
        self.assertEqual(self.client.get(reverse('api:child_overview', args=[w['student'].pk])).status_code, 200)

    def test_parent_cannot_pay_for_unlinked_child(self):
        with self.assertRaises(PaymentRefused):
            start_payment(self.w['parent'], self.w['course'], 'MTN', '0961234567', student=self.w['student'])

    def test_monthly_access_expires_and_renews(self):
        w = self.w
        e = enrol(w['student'], w['course'], days=-1)
        self.assertFalse(e.has_access)
        self.client.force_login(w['student'])
        r = self.client.get(reverse('courses:lesson', args=[w['course'].slug, w['lessons'][1].pk]))
        self.assertRedirects(r, reverse('payments:checkout', args=[w['course'].slug]))
        p = start_payment(w['student'], w['course'], 'MTN', '0961234567')
        self._approve(self.client, p)
        e.refresh_from_db()
        self.assertTrue(e.has_access)

    def test_cannot_pay_again_while_access_is_far_from_ending(self):
        enrol(self.w['student'], self.w['course'], days=25)
        with self.assertRaises(PaymentRefused):
            start_payment(self.w['student'], self.w['course'], 'MTN', '0961234567')


class VerificationTests(TestCase):
    def test_unverified_tutor_cannot_publish(self):
        w = build_world()
        new = User.objects.create_user(email='n@example.com', password=PW, role=User.Role.TUTOR)
        prof = TutorProfile.objects.create(user=new, status=TutorProfile.Status.SUBMITTED)
        prof.specialisations.set([w['subject']])
        self.assertFalse(new.is_verified_tutor)
        self.client.force_login(new)
        r = self.client.post(reverse('courses:new_course'), {
            'title': 'Mine', 'subject': w['subject'].pk, 'level': 'a_level', 'summary': 'x', 'price': '80',
            'is_published': 'on'})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Course.objects.filter(title='Mine', is_published=True).exists())

    def test_portal_rejects_wrong_role(self):
        w = build_world()
        r = self.client.post(reverse('portal:tutor_login'), {'username': w['student'].email, 'password': PW})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'student')
        r = self.client.post(reverse('portal:student_login'), {'username': w['student'].email, 'password': PW})
        self.assertEqual(r.status_code, 302)


class MaterialTests(TestCase):
    def test_upload_pdf_and_docx(self):
        w = build_world()
        self.client.force_login(w['tutor'])
        pdf = SimpleUploadedFile('notes.pdf', b'%PDF-1.4\n%\xe2\xe3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF',
                                 content_type='application/pdf')
        r = self.client.post(reverse('courses:upload_material', args=[w['course'].slug]),
                             {'title': 'Notes', 'category': 'notes', 'file': pdf})
        self.assertIn(r.status_code, (302, 200))
        self.assertTrue(CourseMaterial.objects.filter(title='Notes').exists())
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, 'w') as z:
            z.writestr('[Content_Types].xml', '<Types/>')
            z.writestr('word/document.xml', '<w:document xmlns:w="http://schemas.openxmlformats.org/'
                       'wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Hello</w:t></w:r></w:p></w:body>'
                       '</w:document>')
        docx = SimpleUploadedFile('sheet.docx', buf.getvalue())
        self.client.post(reverse('courses:upload_material', args=[w['course'].slug]),
                         {'title': 'Sheet', 'category': 'tutorial', 'file': docx})
        self.assertTrue(CourseMaterial.objects.filter(title='Sheet').exists())

    def test_rejects_disguised_file(self):
        w = build_world()
        self.client.force_login(w['tutor'])
        fake = SimpleUploadedFile('virus.pdf', b'MZ\x90\x00 this is an exe')
        self.client.post(reverse('courses:upload_material', args=[w['course'].slug]),
                         {'title': 'Bad', 'category': 'notes', 'file': fake})
        self.assertFalse(CourseMaterial.objects.filter(title='Bad').exists())


@override_settings(EMAIL_BACKEND=EMAIL)
class AssessmentTests(TestCase):
    def setUp(self):
        self.w = build_world()
        enrol(self.w['student'], self.w['course'])
        self.a = Assessment.objects.create(course=self.w['course'], lesson=self.w['lessons'][0], title='Quiz 1',
                                           is_published=True, required_to_progress=True,
                                           must_pass_to_progress=True, pass_mark=50)
        self.q1 = Question.objects.create(assessment=self.a, kind='mcq', text='2+2?', choices='3\n4\n5', answer='2')
        self.q2 = Question.objects.create(assessment=self.a, kind='numeric', text='pi', answer='3.14',
                                          tolerance=Decimal('0.01'))

    def test_gating_and_auto_marking(self):
        w = self.w
        self.client.force_login(w['student'])
        lesson2 = reverse('courses:lesson', args=[w['course'].slug, w['lessons'][1].pk])
        self.assertRedirects(self.client.get(lesson2), reverse('classroom:assessment', args=[self.a.pk]))
        self.assertEqual(self.client.get(reverse('classroom:assessment', args=[self.a.pk])).status_code, 200)
        r = self.client.post(reverse('classroom:assessment', args=[self.a.pk]),
                             {f'q_{self.q1.pk}': '1', f'q_{self.q2.pk}': '0'})
        sub = Submission.objects.get(student=w['student'])
        self.assertRedirects(r, reverse('classroom:result', args=[sub.pk]))
        self.assertEqual(sub.percent, Decimal('0.0'))
        self.assertEqual(self.client.get(lesson2).status_code, 302)  # failed: still blocked
        self.client.post(reverse('classroom:assessment', args=[self.a.pk]),
                         {f'q_{self.q1.pk}': '2', f'q_{self.q2.pk}': '3.141'})
        best = cls.best_submission(w['student'], self.a)
        self.assertEqual(best.percent, Decimal('100.0'))
        self.assertEqual(self.client.get(lesson2).status_code, 200)
        self.assertEqual(self.client.get(reverse('classroom:result', args=[best.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('classroom:my_grades')).status_code, 200)

    def test_written_answer_goes_to_tutor(self):
        w = self.w
        Question.objects.create(assessment=self.a, kind='written', text='Prove it', marks=4)
        self.client.force_login(w['student'])
        self.client.post(reverse('classroom:assessment', args=[self.a.pk]), {})
        sub = Submission.objects.get(student=w['student'])
        self.assertEqual(sub.status, 'submitted')
        self.client.force_login(w['tutor'])
        self.assertEqual(self.client.get(reverse('classroom:mark', args=[sub.pk])).status_code, 200)
        marks = {f'mark_{q.pk}': str(q.marks) for q in self.a.questions.all()}
        self.client.post(reverse('classroom:mark', args=[sub.pk]), {**marks, 'feedback': 'Good'})
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'graded')
        self.assertEqual(sub.percent, Decimal('100.0'))
        r = self.client.get(reverse('classroom:gradebook', args=[w['course'].slug]) + '?format=csv')
        self.assertIn(b'Sam', r.content)


class AttendanceAndSchoolTests(TestCase):
    def test_check_in_and_register(self):
        w = build_world()
        enrol(w['student'], w['course'])
        s = Session.objects.create(course=w['course'], tutor=w['tutor'], title='Live',
                                   starts_at=timezone.now() - timedelta(minutes=5))
        self.client.force_login(w['student'])
        self.client.post(reverse('classroom:check_in', args=[s.pk]), {'code': 'xxxx'})
        self.assertFalse(Attendance.objects.exists())
        self.client.post(reverse('classroom:check_in', args=[s.pk]), {'code': s.check_in_code})
        self.assertEqual(Attendance.objects.get().status, 'present')
        self.client.force_login(w['tutor'])
        self.client.post(reverse('classroom:register', args=[s.pk]), {f'status_{w["student"].pk}': 'late'})
        self.assertEqual(Attendance.objects.get().status, 'late')
        self.assertEqual(cls.attendance_rate(w['student']), 100)

    def test_school_register_and_join(self):
        w = build_world()
        self.client.force_login(w['parent'])
        r = self.client.post(reverse('schools:register'), {
            'name': 'Lusaka Boys', 'kind': 'secondary', 'town': 'Lusaka', 'contact_name': 'H',
            'contact_email': 'h@example.com', 'student_count_estimate': 300})
        school = School.objects.get(name='Lusaka Boys')
        self.assertRedirects(r, reverse('schools:manage', args=[school.slug]))
        self.client.force_login(w['student'])
        self.client.post(reverse('schools:join'), {'code': school.student_code.lower()})
        self.assertEqual(SchoolMember.objects.get(user=w['student']).role, 'student')
        teacher = User.objects.create_user(email='st@example.com', password=PW)
        self.client.force_login(teacher)
        self.client.post(reverse('schools:join'), {'code': school.teacher_code})
        self.assertEqual(SchoolMember.objects.get(user=teacher).role, 'teacher')
        r = self.client.post(reverse('courses:new_course'), {
            'title': 'School Physics', 'subject': w['subject'].pk, 'level': 'a_level', 'summary': 'x',
            'price': '80', 'school': school.pk, 'is_published': 'on'})
        self.assertEqual(r.status_code, 302, getattr(r, 'context', None) and r.context['form'].errors)
        c = Course.objects.get(title='School Physics')
        self.assertTrue(c.is_published)
        self.assertNotIn(c, Course.objects.published())


@override_settings(EMAIL_BACKEND=EMAIL)
class PageSweepTests(TestCase):
    """Every page renders for the people who are meant to see it."""

    def setUp(self):
        self.w = w = build_world()
        enrol(w['student'], w['course'])
        ParentLink.objects.create(parent=w['parent'], student=w['student'], relationship='Father')
        self.group = ClassGroup.objects.create(course=w['course'], name='6A')
        self.session = Session.objects.create(course=w['course'], tutor=w['tutor'], title='Live',
                                              starts_at=timezone.now() + timedelta(days=1))
        self.a = Assessment.objects.create(course=w['course'], lesson=w['lessons'][0], title='Q', is_published=True)
        self.q = Question.objects.create(assessment=self.a, kind='short', text='Capital?', answer='Lusaka')
        self.sub = cls.submit(cls.start_attempt(w['student'], self.a), {str(self.q.pk): 'Lusaka'})
        self.booking = Booking.objects.create(student=w['student'], course=w['course'], topic='Integration',
                                              preferred_start=timezone.now() + timedelta(days=2))
        self.school = School.objects.create(name='Test High', contact_name='x', contact_email='x@example.com',
                                            is_approved=True)
        SchoolMember.objects.create(school=self.school, user=w['admin'], role='admin')

    def sweep(self, user, names):
        if user:
            self.client.force_login(user)
        for name in names:
            url = name if name.startswith('/') else reverse(name)
            r = self.client.get(url)
            self.assertIn(r.status_code, (200, 302), f'{url} as {user}: {r.status_code}')

    def test_public_pages(self):
        w = self.w
        self.sweep(None, ['core:home', 'courses:catalog', 'core:pricing', 'core:about', 'core:help',
                          'portal:choose', 'portal:student_login', 'portal:parent_login', 'portal:tutor_login',
                          'portal:admin_login', 'portal:parent_signup', 'portal:tutor_signup', 'portal:tutors',
                          'schools:index', w['course'].get_absolute_url(),
                          reverse('portal:tutor_profile', args=[w['tutor'].pk]),
                          self.school.get_absolute_url()])

    def test_student_pages(self):
        w = self.w
        self.sweep(w['student'], [
            'core:dashboard', 'classroom:my_classes', 'classroom:my_grades', 'accounts:profile',
            'payments:history', 'notifications:inbox', 'api:student_overview',
            reverse('classroom:book', args=[w['course'].slug]),
            reverse('classroom:session', args=[self.session.pk]),
            reverse('classroom:assessment', args=[self.a.pk]),
            reverse('classroom:result', args=[self.sub.pk]),
            reverse('courses:lesson', args=[w['course'].slug, w['lessons'][1].pk]),
            reverse('payments:checkout', args=[w['course'].slug])])

    def test_parent_pages(self):
        self.sweep(self.w['parent'], ['portal:parent_home', 'portal:parent_link', 'accounts:profile',
                                      reverse('payments:checkout', args=[self.w['course'].slug])])

    def test_tutor_pages(self):
        w, slug = self.w, self.w['course'].slug
        self.sweep(w['tutor'], [
            'core:tutor_dashboard', 'classroom:tutor_home', 'ledger:earnings', 'portal:tutor_apply',
            'courses:new_course', 'api:tutor_overview', 'accounts:profile',
            reverse('courses:studio', args=[slug]), reverse('courses:edit_course', args=[slug]),
            reverse('classroom:manage', args=[slug]), reverse('classroom:gradebook', args=[slug]),
            reverse('classroom:group', args=[slug, self.group.pk]),
            reverse('classroom:session_new', args=[slug]),
            reverse('classroom:session_edit', args=[slug, self.session.pk]),
            reverse('classroom:session', args=[self.session.pk]),
            reverse('classroom:assessment_new', args=[slug]),
            reverse('classroom:assessment_edit', args=[slug, self.a.pk]),
            reverse('classroom:question_edit', args=[slug, self.a.pk, self.q.pk]),
            reverse('classroom:mark', args=[self.sub.pk]),
            reverse('classroom:booking_reply', args=[self.booking.pk])])

    def test_admin_pages(self):
        w = self.w
        self.sweep(w['admin'], ['portal:admin_home', 'portal:admin_tutors', 'api:admin_overview',
                                reverse('portal:admin_tutor', args=[w['tutor'].tutor_profile.pk]),
                                reverse('schools:manage', args=[self.school.slug]), '/admin/'])
