from django.urls import path

from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('tutor/', views.tutor_dashboard, name='tutor_dashboard'),
    path('about/', views.page, {'name': 'about'}, name='about'),
    path('pricing/', views.page, {'name': 'pricing'}, name='pricing'),
    path('help/', views.page, {'name': 'help'}, name='help'),
    path('terms/', views.page, {'name': 'terms'}, name='terms'),
    path('privacy/', views.page, {'name': 'privacy'}, name='privacy'),
]
