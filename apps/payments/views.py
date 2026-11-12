import json
import logging
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.courses.models import Course

from .forms import CheckoutForm
from .models import Payment, PaymentEvent
from .networks import NETWORKS, detect_network
from .providers import COMPLETED, FAILED, ProviderResult
from .services import PaymentRefused, apply_result, refresh_payment, start_payment

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(['GET', 'POST'])
def checkout(request, slug):
    course = get_object_or_404(Course.objects.visible_to(request.user).select_related('subject', 'tutor'), slug=slug)
    children = list(request.user.children) if request.user.is_parent else []
    enrollment = course.enrollment_for(request.user)
    renewing = bool(enrollment and enrollment.has_access and enrollment.renewal_due)
    if not children and course.can_access_all(request.user) and not renewing:
        messages.info(request, 'You already have full access to this course.')
        return redirect(course)

    initial = {}
    if request.user.phone:
        initial = {'phone': request.user.phone, 'network': detect_network(request.user.phone) or None}
    form = CheckoutForm(request.POST or None, initial=initial, children=children)
    if request.method == 'POST' and form.is_valid():
        try:
            payment = start_payment(request.user, course, form.cleaned_data['network'], form.cleaned_data['phone'],
                                    student=form.cleaned_data.get('student'))
        except PaymentRefused as exc:
            form.add_error(None, str(exc))
        else:
            if not request.user.phone:
                request.user.phone = form.cleaned_data['phone']
                request.user.save(update_fields=['phone'])
            return redirect('payments:status', pk=payment.pk)
    return render(request, 'payments/checkout.html', {
        'course': course, 'form': form, 'networks': NETWORKS,
        'simulator': settings.PAYMENT_PROVIDER == 'simulator', 'renewing': renewing,
        'access_days': settings.ACCESS_PERIOD_DAYS, 'enrollment': enrollment,
    })


def _own_payment(request, pk):
    payment = get_object_or_404(Payment.objects.select_related('course', 'user'), pk=pk)
    if payment.user_id != request.user.pk and not request.user.is_staff:
        raise Http404
    return payment


@login_required
@require_GET
def status(request, pk):
    payment = refresh_payment(_own_payment(request, pk))
    return render(request, 'payments/status.html', {'payment': payment, 'course': payment.course})


@login_required
@require_GET
def status_json(request, pk):
    payment = refresh_payment(_own_payment(request, pk))
    return JsonResponse({
        'status': payment.status,
        'final': payment.is_final,
        'message': payment.failure_message,
        'course_url': payment.course.get_absolute_url(),
    })


@login_required
@require_POST
def simulate(request, pk):
    """Stand-in for the customer's phone. Only exists for the simulator."""
    payment = _own_payment(request, pk)
    if payment.provider != 'simulator':
        raise Http404
    if request.POST.get('decision') == 'approve':
        result = ProviderResult(COMPLETED, 'COMPLETED', reference=f'SIM-{payment.id.hex[:10]}')
    else:
        result = ProviderResult(FAILED, 'FAILED', failure_code='PAYMENT_NOT_APPROVED',
                                failure_message='The payment was declined on the phone.')
    apply_result(payment, result)
    return redirect('payments:status', pk=payment.pk)


@login_required
def history(request):
    payments = request.user.payments.select_related('course', 'student').all()[:50]
    return render(request, 'payments/history.html', {'payments': payments})


@csrf_exempt
@require_POST
def pawapay_callback(request):
    """
    pawaPay calls this when a deposit reaches a final state.

    The body is used only to find which payment it is about. The status itself
    is fetched again from pawaPay's API with our own token, so a forged
    callback cannot mark a payment as paid.
    """
    try:
        body = json.loads(request.body.decode('utf-8'))
        deposit_id = uuid.UUID(str(body.get('depositId')))
    except (ValueError, TypeError, AttributeError, UnicodeDecodeError):
        return HttpResponseBadRequest('invalid body')
    payment = Payment.objects.filter(pk=deposit_id, provider='pawapay').first()
    if payment is None:
        logger.warning('pawaPay callback for unknown deposit %s', deposit_id)
        return HttpResponse('ok')  # 200 so pawaPay does not keep retrying
    PaymentEvent.objects.create(payment=payment, kind='callback', data={'body': body})
    refresh_payment(payment, force=True)
    return HttpResponse('ok')
