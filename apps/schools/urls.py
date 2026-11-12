from django.urls import path

from . import views

app_name = 'schools'

urlpatterns = [
    path('', views.index, name='index'),
    path('register/', views.register, name='register'),
    path('join/', views.join, name='join'),
    path('<slug:slug>/', views.detail, name='detail'),
    path('<slug:slug>/manage/', views.manage, name='manage'),
    path('<slug:slug>/manage/codes/', views.new_codes, name='new_codes'),
    path('<slug:slug>/manage/members/<int:pk>/', views.member_update, name='member_update'),
]
