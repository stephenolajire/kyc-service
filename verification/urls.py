from django.urls import path
from .views import VerifyView, HealthView

urlpatterns = [
    path("verify/", VerifyView.as_view(), name="verify"),
    path("health/", HealthView.as_view(), name="health"),
]