from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'branches', views.BranchViewSet)
router.register(r'teams', views.TeamViewSet)
router.register(r'edit-logs', views.EditLogViewSet)

urlpatterns = [
    path('', include(router.urls)),
]