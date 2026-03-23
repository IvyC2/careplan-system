from django.contrib import admin
from .models import Patient, Provider, Order, CarePlan


@admin.register(Patient)
class PatientAdmin(admin.ModelAdmin):
    list_display = ("mrn", "last_name", "first_name", "date_of_birth")
    search_fields = ("mrn", "last_name", "first_name")
    ordering = ("last_name", "first_name")


@admin.register(Provider)
class ProviderAdmin(admin.ModelAdmin):
    list_display = ("npi", "last_name", "first_name")
    search_fields = ("npi", "last_name", "first_name")
    ordering = ("last_name", "first_name")


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "patient", "provider", "medication_name", "primary_diagnosis", "created_at")
    search_fields = ("medication_name", "primary_diagnosis", "patient__last_name", "provider__last_name")
    list_filter = ("provider", "created_at")
    ordering = ("-created_at",)


@admin.register(CarePlan)
class CarePlanAdmin(admin.ModelAdmin):
    list_display = ("id", "order", "status", "created_at", "updated_at")
    search_fields = ("order__patient__last_name", "status")
    list_filter = ("status", "created_at")
    ordering = ("-created_at",)