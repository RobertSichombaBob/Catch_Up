from django.urls import path

from . import views

app_name = 'portal'

urlpatterns = [
    path('portal/', views.choose, name='choose'),
    path('student/login/', views.PortalLoginView.as_view(portal='student'), name='student_login'),
    path('parent/login/', views.PortalLoginView.as_view(portal='parent'), name='parent_login'),
    path('tutor/login/', views.PortalLoginView.as_view(portal='tutor'), name='tutor_login'),
    path('control/login/', views.PortalLoginView.as_view(portal='admin'), name='admin_login'),

    path('parent/signup/', views.parent_signup, name='parent_signup'),
    path('parent/', views.parent_home, name='parent_home'),
    path('parent/link/', views.parent_link, name='parent_link'),
    path('links/<int:pk>/remove/', views.unlink, name='unlink'),

    path('tutor/join/', views.tutor_signup, name='tutor_signup'),
    path('tutor/verification/', views.tutor_apply, name='tutor_apply'),
    path('tutors/', views.tutors, name='tutors'),
    path('tutors/<int:pk>/', views.tutor_profile, name='tutor_profile'),

    path('control/', views.admin_home, name='admin_home'),
    path('control/tutors/', views.admin_tutors, name='admin_tutors'),
    path('control/tutors/<int:pk>/', views.admin_tutor, name='admin_tutor'),
    path('control/tutors/<int:pk>/documents/<str:field>/', views.tutor_document, name='tutor_document'),
]
