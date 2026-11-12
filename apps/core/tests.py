"""
End-to-end tests for Catch Up.  Run with:  python manage.py test
They run against whatever DATABASE_URL points to (Postgres in CI, SQLite locally).
"""
import json
from decimal import Decimal
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.courses.models import Course, Enrollment, Lesson, LessonProgress, Module, Subject
from apps.notifications.models import Notification
from apps.payments import providers
from apps.payments.models import Payment
from apps.payments.networks import detect_network, display_msisdn, normalise_msisdn
from apps.payments.providers import PawaPayProvider
from apps.payments.services import PaymentRefused, refresh_payment, start_payment

User = get_user_model()
EMAIL = 'django.core.mail.backends.locmem.EmailBackend'


def make_course(price='80.00'):
    tutor = User.objects.create_user(email='tutor@example.com', password='x-Pass-123', role=User.Role.TUTOR,
                                     first_name='Tess', last_name='Tutor')
    subject = Subject.objects.create(name='Maths', slug='maths')
    course = Course.objects.create(subject=subject, tutor=tutor, title='Algebra', summary='s', price=Decimal(price))
    module = Module.objects.create(course=course, title='M1', order=1)
    free = Lesson.objects.create(module=module, title='Free one', order=1, content='<p>free</p>', is_preview=True)
    paid = Lesson.objects.create(module=module, title='Paid one', order=2, content='<p>paid</p>')
    return course, free, paid


class NetworkTests(TestCase):
    def test_normalise(self):
        for raw in ['0971234567', '971234567', '+260 97 123 4567', '260971234567', '097-123-4567']:
            self.assertEqual(normalise_msisdn(raw), '260971234567', raw)
        for bad in ['', '12345', '0211234567', '09712345678', 'abc']:
            self.assertEqual(normalise_msisdn(bad), '', bad)

    def test_detect(self):
        self.assertEqual(detect_network('0961234567'), 'MTN')
        self.assertEqual(detect_network('0761234567'), 'MTN')
        self.assertEqual(detect_network('0971234567'), 'AIRTEL')
        self.assertEqual(detect_network('0771234567'), 'AIRTEL')
        self.assertEqual(detect_network('0951234567'), 'ZAMTEL')
        self.assertEqual(detect_network('0751234567'), 'ZAMTEL')
        self.assertEqual(display_msisdn('260971234567'), '097 123 4567')


class SanitizeTests(TestCase):
    def test_scripts_removed_from_lessons(self):
        course, free, _ = make_course()
        free.content = '<p onclick="x()">Hi</p><script>alert(1)</script><a href="javascript:x()">l</a><details><summary>A</summary>B</details>'
        free.save()
        free.refresh_from_db()
        self.assertNotIn('<script', free.content)
        self.assertNotIn('onclick', free.content)
        self.assertNotIn('javascript:', free.content)
        self.assertIn('<details>', free.content)


@override_settings(EMAIL_BACKEND=EMAIL)
class AccountTests(TestCase):
    def test_signup_logs_in_notifies_and_emails(self):
        resp = self.client.post(reverse('accounts:signup'), {
            'first_name': 'Ada', 'last_name': 'Banda', 'email': 'Ada@Example.com', 'level': 'a_level',
            'password1': 'Str0ng-Passw0rd!', 'password2': 'Str0ng-Passw0rd!', 'agree': 'on'})
        self.assertRedirects(resp, reverse('core:dashboard'))
        user = User.objects.get(email='ada@example.com')
        self.assertEqual(user.role, User.Role.STUDENT)
        self.assertEqual(Notification.objects.filter(user=user).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Welcome', mail.outbox[0].subject)
        self.assertTrue(mail.outbox[0].alternatives)  # HTML part

    def test_duplicate_email_rejected(self):
        User.objects.create_user(email='a@example.com', password='x-Pass-123')
        resp = self.client.post(reverse('accounts:signup'), {
            'first_name': 'A', 'last_name': 'B', 'email': 'A@example.com', 'level': 'a_level',
            'password1': 'Str0ng-Passw0rd!', 'password2': 'Str0ng-Passw0rd!', 'agree': 'on'})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(User.objects.filter(email__iexact='a@example.com').count(), 1)

    def test_login_case_insensitive_and_open_redirect_blocked(self):
        User.objects.create_user(email='b@example.com', password='x-Pass-123')
        resp = self.client.post(reverse('accounts:login'),
                                {'username': 'B@Example.com', 'password': 'x-Pass-123', 'next': 'https://evil.com/'})
        self.assertEqual(resp.status_code, 302)
        self.assertFalse(resp['Location'].startswith('https://evil.com'))

    def test_password_reset_email(self):
        User.objects.create_user(email='c@example.com', password='x-Pass-123')
        self.client.post(reverse('accounts:password_reset'), {'email': 'c@example.com'})
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('/accounts/password/reset/', mail.outbox[0].body)


@override_settings(EMAIL_BACKEND=EMAIL, PAYMENT_PROVIDER='simulator')
class PaywallAndPaymentTests(TestCase):
    def setUp(self):
        self.course, self.free, self.paid = make_course()
        self.student = User.objects.create_user(email='s@example.com', password='x-Pass-123', first_name='Sam')

    def test_preview_open_to_anyone_paid_lesson_locked(self):
        self.assertEqual(self.client.get(self.free.get_absolute_url()).status_code, 200)
        resp = self.client.get(self.paid.get_absolute_url())
        self.assertEqual(resp.status_code, 302)
        self.assertIn(reverse('accounts:login'), resp['Location'])
        self.client.force_login(self.student)
        resp = self.client.get(self.paid.get_absolute_url())
        self.assertRedirects(resp, reverse('payments:checkout', args=[self.course.slug]))

    def test_tutor_and_staff_can_open_everything(self):
        self.client.force_login(self.course.tutor)
        self.assertEqual(self.client.get(self.paid.get_absolute_url()).status_code, 200)

    def test_full_simulated_payment_unlocks_course_once(self):
        self.client.force_login(self.student)
        resp = self.client.post(reverse('payments:checkout', args=[self.course.slug]),
                                {'network': 'AIRTEL', 'phone': '0971234567'})
        payment = Payment.objects.get()
        self.assertRedirects(resp, reverse('payments:status', args=[payment.pk]))
        self.assertEqual(payment.amount, Decimal('80.00'))
        self.assertEqual(payment.msisdn, '260971234567')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertFalse(self.course.is_enrolled(self.student))

        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('payments:simulate', args=[payment.pk]), {'decision': 'approve'})
        # approving twice must not double-enrol or double-notify
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('payments:simulate', args=[payment.pk]), {'decision': 'approve'})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(Enrollment.objects.filter(user=self.student, course=self.course).count(), 1)
        self.assertEqual(self.client.get(self.paid.get_absolute_url()).status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.student, title__startswith='Payment received').count(), 1)
        self.assertEqual(Notification.objects.filter(user=self.course.tutor).count(), 1)
        receipts = [m for m in mail.outbox if m.subject.startswith('Payment received')]
        self.assertEqual(len(receipts), 1)
        self.assertIn(payment.reference, receipts[0].body)
        self.student.refresh_from_db()
        self.assertEqual(self.student.phone, '0971234567')

        data = self.client.get(reverse('payments:status_json', args=[payment.pk])).json()
        self.assertEqual(data['status'], 'completed')
        self.assertTrue(data['final'])

    def test_declined_payment_does_not_unlock(self):
        self.client.force_login(self.student)
        self.client.post(reverse('payments:checkout', args=[self.course.slug]), {'network': 'MTN', 'phone': '0961234567'})
        payment = Payment.objects.get()
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('payments:simulate', args=[payment.pk]), {'decision': 'decline'})
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertFalse(self.course.is_enrolled(self.student))
        self.assertTrue(any('not completed' in m.subject for m in mail.outbox))

    def test_simulator_rejects_numbers_ending_13(self):
        payment = start_payment(self.student, self.course, 'MTN', '0961234513')
        self.assertEqual(payment.status, Payment.Status.FAILED)

    def test_network_mismatch_and_bad_number_rejected(self):
        self.client.force_login(self.student)
        resp = self.client.post(reverse('payments:checkout', args=[self.course.slug]), {'network': 'MTN', 'phone': '0971234567'})
        self.assertContains(resp, 'looks like a Airtel Money number')
        resp = self.client.post(reverse('payments:checkout', args=[self.course.slug]), {'network': 'MTN', 'phone': '12345'})
        self.assertContains(resp, 'Enter a Zambian mobile number')
        self.assertFalse(Payment.objects.exists())

    def test_cannot_pay_twice_for_owned_course(self):
        Enrollment.objects.create(user=self.student, course=self.course)
        with self.assertRaises(PaymentRefused):
            start_payment(self.student, self.course, 'MTN', '0961234567')

    def test_repeat_click_reuses_pending_payment(self):
        p1 = start_payment(self.student, self.course, 'MTN', '0961234567')
        p2 = start_payment(self.student, self.course, 'MTN', '0961234567')
        self.assertEqual(p1.pk, p2.pk)

    def test_other_users_cannot_see_or_approve_payment(self):
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        other = User.objects.create_user(email='o@example.com', password='x-Pass-123')
        self.client.force_login(other)
        self.assertEqual(self.client.get(reverse('payments:status', args=[payment.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse('payments:simulate', args=[payment.pk]), {'decision': 'approve'}).status_code, 404)
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)

    def test_lesson_progress(self):
        Enrollment.objects.create(user=self.student, course=self.course)
        self.client.force_login(self.student)
        resp = self.client.post(reverse('courses:toggle_complete', args=[self.course.slug, self.free.pk]), {'then': 'next'})
        self.assertRedirects(resp, self.paid.get_absolute_url())
        self.assertEqual(Enrollment.objects.get(user=self.student).progress(), 50)


class FakeResponse:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, json.dumps(data)

    def json(self):
        return self._data


@override_settings(EMAIL_BACKEND=EMAIL, PAYMENT_PROVIDER='pawapay', PAWAPAY_API_TOKEN='test-token',
                   PAWAPAY_BASE_URL='https://api.sandbox.pawapay.io')
class PawaPayTests(TestCase):
    def setUp(self):
        self.course, self.free, self.paid = make_course()
        self.student = User.objects.create_user(email='p@example.com', password='x-Pass-123')

    @mock.patch('apps.payments.providers.requests.post')
    def test_request_body_matches_pawapay_v2(self, post):
        post.return_value = FakeResponse(200, {'depositId': 'x', 'status': 'ACCEPTED', 'created': '2026-01-01T00:00:00Z'})
        payment = start_payment(self.student, self.course, 'ZAMTEL', '0953456700')
        url = post.call_args.args[0]
        body = post.call_args.kwargs['json']
        headers = post.call_args.kwargs['headers']
        self.assertEqual(url, 'https://api.sandbox.pawapay.io/v2/deposits')
        self.assertEqual(headers['Authorization'], 'Bearer test-token')
        self.assertEqual(body['depositId'], str(payment.pk))
        self.assertEqual(body['amount'], '80.00')
        self.assertEqual(body['currency'], 'ZMW')
        self.assertEqual(body['payer'], {'type': 'MMO', 'accountDetails': {'phoneNumber': '260953456700', 'provider': 'ZAMTEL_ZMB'}})
        self.assertRegex(body['customerMessage'], r'^[a-zA-Z0-9 ]{4,22}$')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.provider, 'pawapay')

    @mock.patch('apps.payments.providers.requests.post')
    def test_rejected(self, post):
        post.return_value = FakeResponse(200, {'status': 'REJECTED', 'failureReason': {'failureCode': 'INVALID_PHONE_NUMBER', 'failureMessage': 'bad'}})
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertEqual(payment.failure_code, 'INVALID_PHONE_NUMBER')

    @mock.patch('apps.payments.providers.requests.post')
    def test_server_error_is_not_treated_as_failure(self, post):
        post.return_value = FakeResponse(500, {'failureReason': {'failureCode': 'UNKNOWN_ERROR'}})
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        self.assertEqual(payment.status, Payment.Status.PENDING)

    @mock.patch('apps.payments.providers.requests.get')
    @mock.patch('apps.payments.providers.requests.post')
    def test_callback_rechecks_status_and_unlocks(self, post, get):
        post.return_value = FakeResponse(200, {'status': 'ACCEPTED'})
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        get.return_value = FakeResponse(200, {'status': 'FOUND', 'data': {
            'depositId': str(payment.pk), 'status': 'COMPLETED', 'providerTransactionId': 'MP123'}})
        with self.captureOnCommitCallbacks(execute=True):
            resp = self.client.post(reverse('payments:pawapay_callback'), data=json.dumps(
                {'depositId': str(payment.pk), 'status': 'COMPLETED'}), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(any(m.subject.startswith('Payment received') for m in mail.outbox))
        self.assertEqual(get.call_args.args[0], f'https://api.sandbox.pawapay.io/v2/deposits/{payment.pk}')
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.COMPLETED)
        self.assertEqual(payment.provider_reference, 'MP123')
        self.assertTrue(self.course.is_enrolled(self.student))

    @mock.patch('apps.payments.providers.requests.get')
    @mock.patch('apps.payments.providers.requests.post')
    def test_forged_callback_cannot_unlock(self, post, get):
        post.return_value = FakeResponse(200, {'status': 'ACCEPTED'})
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        get.return_value = FakeResponse(200, {'status': 'FOUND', 'data': {'depositId': str(payment.pk), 'status': 'PROCESSING'}})
        self.client.post(reverse('payments:pawapay_callback'), data=json.dumps(
            {'depositId': str(payment.pk), 'status': 'COMPLETED'}), content_type='application/json')
        payment.refresh_from_db()
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertFalse(self.course.is_enrolled(self.student))

    @mock.patch('apps.payments.providers.requests.get')
    @mock.patch('apps.payments.providers.requests.post')
    def test_failed_status(self, post, get):
        post.return_value = FakeResponse(200, {'status': 'ACCEPTED'})
        payment = start_payment(self.student, self.course, 'AIRTEL', '0971234567')
        get.return_value = FakeResponse(200, {'status': 'FOUND', 'data': {
            'status': 'FAILED', 'failureReason': {'failureCode': 'INSUFFICIENT_BALANCE'}}})
        payment = refresh_payment(payment, force=True)
        self.assertEqual(payment.status, Payment.Status.FAILED)
        self.assertIn('not enough money', payment.failure_message)

    def test_callback_rejects_garbage(self):
        resp = self.client.post(reverse('payments:pawapay_callback'), data='not json', content_type='application/json')
        self.assertEqual(resp.status_code, 400)

    @mock.patch('apps.payments.providers.requests.post', side_effect=providers.requests.ConnectionError('down'))
    def test_network_down_keeps_payment_pending(self, post):
        payment = start_payment(self.student, self.course, 'MTN', '0961234567')
        self.assertEqual(payment.status, Payment.Status.PENDING)
        self.assertEqual(payment.provider_status, 'UNREACHABLE')


@override_settings(EMAIL_BACKEND=EMAIL)
class NotificationTests(TestCase):
    def test_email_opt_out_and_mark_read(self):
        from apps.notifications.services import notify
        user = User.objects.create_user(email='n@example.com', password='x-Pass-123', email_notifications=False)
        note = notify(user, 'Hello', 'Body', '/courses/')
        self.assertEqual(len(mail.outbox), 0)
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('notifications:inbox')), 'Hello')
        resp = self.client.post(reverse('notifications:open', args=[note.pk]))
        self.assertRedirects(resp, '/courses/', fetch_redirect_response=False)
        note.refresh_from_db()
        self.assertTrue(note.is_read)

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_HOST='127.0.0.1', EMAIL_PORT=1)
    def test_broken_mail_server_does_not_break_the_page(self):
        from apps.notifications.services import notify
        user = User.objects.create_user(email='m@example.com', password='x-Pass-123')
        note = notify(user, 'Hi', 'B')
        self.assertFalse(note.emailed)
        self.assertTrue(Notification.objects.filter(pk=note.pk).exists())


class SeedAndPagesTests(TestCase):
    @mock.patch.dict('os.environ', {'SEED_ACCOUNT_PASSWORD': 'Seed-Pass-123'})
    def test_seed_is_idempotent_and_every_page_renders(self):
        call_command('seed_catchup', verbosity=0)
        call_command('seed_catchup', verbosity=0)
        self.assertEqual(User.objects.filter(role=User.Role.TUTOR).count(), 5)
        self.assertEqual(User.objects.filter(role=User.Role.ADMIN, is_superuser=True).count(), 2)
        self.assertEqual(Course.objects.count(), 6)
        self.assertEqual(Lesson.objects.count(), 36)
        self.assertEqual(set(Course.objects.values_list('price', flat=True)), {Decimal('80.00')})
        for course in Course.objects.all():
            self.assertTrue(course.lessons().filter(is_preview=True).exists(), course)
        self.assertTrue(self.client.login(username='mwila.banda@catchup.example', password='Seed-Pass-123'))
        self.client.logout()

        public = ['/', '/courses/', '/courses/?subject=physics', '/courses/?level=university', '/courses/?q=enzyme',
                  '/pricing/', '/about/', '/help/', '/terms/', '/privacy/', '/accounts/login/', '/accounts/signup/',
                  '/accounts/password/reset/', '/healthz', '/robots.txt', '/manifest.webmanifest']
        public += [c.get_absolute_url() for c in Course.objects.all()]
        public += [lesson.get_absolute_url() for lesson in Lesson.objects.filter(is_preview=True)]
        for url in public:
            self.assertEqual(self.client.get(url).status_code, 200, url)
        self.assertEqual(self.client.get('/does-not-exist/').status_code, 404)

        admin = User.objects.get(email='admin@catchup.example')
        self.client.force_login(admin)
        private = ['/dashboard/', '/tutor/', '/notifications/', '/payments/history/', '/accounts/profile/',
                   '/accounts/password/', '/admin/', '/admin/payments/payment/', '/admin/courses/course/']
        private += [lesson.get_absolute_url() for lesson in Lesson.objects.all()]
        for url in private:
            self.assertEqual(self.client.get(url).status_code, 200, url)

    def test_students_cannot_open_tutor_studio(self):
        course, free, paid = make_course()
        student = User.objects.create_user(email='z@example.com', password='x-Pass-123')
        self.client.force_login(student)
        self.assertEqual(self.client.get('/tutor/').status_code, 403)
        self.assertEqual(self.client.get(reverse('courses:edit_lesson', args=[course.slug, paid.pk])).status_code, 403)

    def test_tutor_can_edit_lesson_and_html_is_cleaned(self):
        course, free, paid = make_course()
        self.client.force_login(course.tutor)
        resp = self.client.post(reverse('courses:edit_lesson', args=[course.slug, paid.pk]), {
            'module': paid.module_id, 'title': 'Paid one v2', 'order': 2, 'content': '<p>ok</p><script>x</script>'})
        self.assertEqual(resp.status_code, 302)
        paid.refresh_from_db()
        self.assertEqual(paid.title, 'Paid one v2')
        self.assertNotIn('script', paid.content)
