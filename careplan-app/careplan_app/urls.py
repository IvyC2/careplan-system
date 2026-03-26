from django.urls import path
from . import views

urlpatterns = [
    # 原有页面路由（保持不变）/ Existing page routes (unchanged)
    path('', views.index, name='index'),
    path('generate/', views.generate_careplan, name='generate_careplan'),

    # 新 REST API 路由 / New REST API routes
    path('api/orders/', views.api_create_order, name='api_create_order'),
    path('api/orders/<int:order_id>/', views.api_get_order, name='api_get_order'),

    # CarePlan status for polling
    path('api/careplan/<int:careplan_id>/status/', views.api_careplan_status, name='api_careplan_status'),
]