from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from documents import views

router = DefaultRouter()
router.register("documents", views.DocumentViewSet, basename="document")
router.register("fields", views.FieldViewSet, basename="field")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("api/metrics/", views.metrics, name="metrics"),
    path("api/health/", views.health, name="health"),
]
