from django.conf import settings
from django.contrib.auth import views as auth_views
from django.urls import path, reverse_lazy

from . import views

app_name = 'accounts'

urlpatterns = [
    path('signup/', views.signup, name='signup'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('profile/', views.profile, name='profile'),
    path('password/', views.PasswordChangeView.as_view(), name='password_change'),
    path('password/reset/', auth_views.PasswordResetView.as_view(
        template_name='accounts/password_reset.html',
        email_template_name='emails/password_reset.txt',
        html_email_template_name='emails/password_reset.html',
        subject_template_name='emails/password_reset_subject.txt',
        success_url=reverse_lazy('accounts:password_reset_done'),
        extra_email_context={'site_url': settings.SITE_URL, 'support_email': settings.SUPPORT_EMAIL,
                             'site_name': settings.SITE_NAME},
    ), name='password_reset'),
    path('password/reset/sent/', auth_views.PasswordResetDoneView.as_view(
        template_name='accounts/password_reset_done.html'), name='password_reset_done'),
    path('password/reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='accounts/password_reset_confirm.html',
        success_url=reverse_lazy('accounts:password_reset_complete'),
    ), name='password_reset_confirm'),
    path('password/reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='accounts/password_reset_complete.html'), name='password_reset_complete'),
]
