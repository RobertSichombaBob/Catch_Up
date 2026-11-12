from django.urls import path

from . import views

app_name = 'classroom'

urlpatterns = [
    path('', views.my_classes, name='my_classes'),
    path('grades/', views.my_grades, name='my_grades'),
    path('groups/<int:pk>/join/', views.join_group, name='join_group'),
    path('book/<slug:slug>/', views.book, name='book'),
    path('sessions/<int:pk>/', views.session, name='session'),
    path('sessions/<int:pk>/check-in/', views.check_in, name='check_in'),
    path('sessions/<int:pk>/register/', views.register, name='register'),
    path('sessions/<int:pk>/cancel/', views.session_cancel, name='session_cancel'),
    path('assessments/<int:pk>/', views.assessment, name='assessment'),
    path('results/<int:pk>/', views.result, name='result'),
    path('submissions/<int:pk>/mark/', views.mark, name='mark'),
    path('submissions/<int:pk>/file/', views.submission_file, name='submission_file'),
    path('bookings/<int:pk>/', views.booking_reply, name='booking_reply'),

    path('teach/', views.tutor_home, name='tutor_home'),
    path('teach/<slug:slug>/', views.manage, name='manage'),
    path('teach/<slug:slug>/gradebook/', views.gradebook, name='gradebook'),
    path('teach/<slug:slug>/announce/', views.announce, name='announce'),
    path('teach/<slug:slug>/groups/new/', views.group_edit, name='group_new'),
    path('teach/<slug:slug>/groups/<int:pk>/', views.group_edit, name='group'),
    path('teach/<slug:slug>/groups/<int:pk>/remove/<int:student_id>/', views.group_remove, name='group_remove'),
    path('teach/<slug:slug>/sessions/new/', views.session_edit, name='session_new'),
    path('teach/<slug:slug>/sessions/<int:pk>/edit/', views.session_edit, name='session_edit'),
    path('teach/<slug:slug>/assessments/new/', views.assessment_edit, name='assessment_new'),
    path('teach/<slug:slug>/assessments/<int:pk>/', views.assessment_edit, name='assessment_edit'),
    path('teach/<slug:slug>/assessments/<int:assessment_pk>/questions/new/', views.question_edit,
         name='question_new'),
    path('teach/<slug:slug>/assessments/<int:assessment_pk>/questions/<int:pk>/', views.question_edit,
         name='question_edit'),
    path('teach/<slug:slug>/assessments/<int:assessment_pk>/questions/<int:pk>/delete/', views.question_delete,
         name='question_delete'),
]
