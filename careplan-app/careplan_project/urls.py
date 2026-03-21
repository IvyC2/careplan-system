from django.urls import path, include

urlpatterns = [
    path('', include('careplan_app.urls')),
]