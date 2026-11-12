from django.urls import path

from . import views

app_name = 'payments'

urlpatterns = [
    path('checkout/<slug:slug>/', views.checkout, name='checkout'),
    path('history/', views.history, name='history'),
    path('<uuid:pk>/', views.status, name='status'),
    path('<uuid:pk>/status.json', views.status_json, name='status_json'),
    path('<uuid:pk>/simulate/', views.simulate, name='simulate'),
    path('callback/pawapay/', views.pawapay_callback, name='pawapay_callback'),
]
