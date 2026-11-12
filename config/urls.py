from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from apps.core import views as core_views

admin.site.site_header = 'Catch Up administration'
admin.site.site_title = 'Catch Up admin'
admin.site.index_title = 'Run the platform'

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('apps.accounts.urls')),
    path('courses/', include('apps.courses.urls')),
    path('payments/', include('apps.payments.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('classroom/', include('apps.classroom.urls')),
    path('schools/', include('apps.schools.urls')),
    path('earnings/', include('apps.ledger.urls')),
    path('api/v1/', include('apps.analytics.urls')),
    path('healthz', core_views.healthz, name='healthz'),
    path('robots.txt', core_views.robots),
    path('manifest.webmanifest', TemplateView.as_view(
        template_name='manifest.webmanifest', content_type='application/manifest+json')),
    path('media/public/<path:path>', core_views.public_media, name='public_media'),
    path('', include('apps.portal.urls')),
    path('', include('apps.core.urls')),
]

handler404 = 'apps.core.views.error_404'
handler500 = 'apps.core.views.error_500'
