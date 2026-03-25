from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
    TokenBlacklistView,  # optional logout endpoint
)

router = DefaultRouter()
router.register(r'users', views.UserViewSet)
router.register(r'branches', views.BranchViewSet)
router.register(r'teams', views.TeamViewSet)
router.register(r'edit-logs', views.EditLogViewSet, basename='editlog')

urlpatterns = [
    path('', include(router.urls)),
    path('api/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/token/blacklist/', TokenBlacklistView.as_view(), name='token_blacklist'), # optional logout
    path('api/logout/', views.LogoutView.as_view(), name='logout'),
]

# authentication urls and their usages
# Endpoint	Method	Purpose
# /api/token/	POST	Login – returns access and refresh tokens
# /api/token/refresh/	POST	Refresh expired access token
# /api/token/blacklist/	POST	Logout – blacklists refresh token (requires token_blacklist app)
# /api/logout/	POST	(Optional) custom logout that uses blacklist