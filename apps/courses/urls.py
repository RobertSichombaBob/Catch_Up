from django.urls import path

from . import views

app_name = 'courses'

urlpatterns = [
    path('', views.catalog, name='catalog'),
    path('new/', views.edit_course, name='new_course'),
    path('<slug:slug>/edit/', views.edit_course, name='edit_course'),
    path('<slug:slug>/studio/', views.studio, name='studio'),
    path('<slug:slug>/materials/upload/', views.upload_material, name='upload_material'),
    path('<slug:slug>/materials/<int:pk>/', views.material, name='material'),
    path('<slug:slug>/materials/<int:pk>/file/', views.material_file, name='material_file'),
    path('<slug:slug>/materials/<int:pk>/delete/', views.delete_material, name='delete_material'),
    path('<slug:slug>/', views.detail, name='detail'),
    path('<slug:slug>/lessons/<int:pk>/', views.lesson, name='lesson'),
    path('<slug:slug>/lessons/<int:pk>/complete/', views.toggle_complete, name='toggle_complete'),
    path('<slug:slug>/lessons/<int:pk>/edit/', views.edit_lesson, name='edit_lesson'),
    path('<slug:slug>/lessons/new/', views.edit_lesson, name='new_lesson'),
    path('<slug:slug>/modules/new/', views.add_module, name='add_module'),
]
