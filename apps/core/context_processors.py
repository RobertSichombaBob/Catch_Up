from django.conf import settings


def site(request):
    return {
        'SITE_NAME': settings.SITE_NAME,
        'SUPPORT_EMAIL': settings.SUPPORT_EMAIL,
        'COURSE_PRICE': settings.COURSE_PRICE_ZMW.split('.')[0],
        'PAYMENT_DEMO_MODE': settings.PAYMENT_PROVIDER == 'simulator',
    }
