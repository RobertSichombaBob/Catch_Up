from django.urls import path

from . import api

app_name = 'api'

urlpatterns = [
    path('student/overview/', api.student_overview, name='student_overview'),
    path('parent/children/<int:pk>/', api.child_overview, name='child_overview'),
    path('tutor/overview/', api.tutor_overview, name='tutor_overview'),
    path('admin/overview/', api.admin_overview, name='admin_overview'),
]
