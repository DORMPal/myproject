# recipes/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from recipes.csrf import csrf

from .api import RecipeViewSet, RecipeRecommendView
from .api_views import (
    IngredientDeleteWithRecipesView,
    UserIngredientListView,
    UserIngredientDetailView,
    UserIngredientBulkDeleteView,
    IngredientListView,
    MeView,
    LogoutView,
    NotificationListView,
    NotificationDetailView,
)

router = DefaultRouter()
# /api/recipes/  (list)
# /api/recipes/<id>/  (detail)
router.register(r"recipes", RecipeViewSet, basename="recipe")

urlpatterns = [
    # ViewSet URLs
    path("", include(router.urls)),
    path("api/auth/csrf", csrf),

    # DELETE /api/ingredients/<pk>/
    path(
        "ingredients/<int:pk>/",
        IngredientDeleteWithRecipesView.as_view(),
        name="ingredient-delete-with-recipes",
    ),
    # GET/POST /api/user (body/query userId)
    path("user", UserIngredientListView.as_view(), name="user-ingredient-list"),
    # DELETE /api/user/ingredient  (bulk delete by ingredient ids)
    path(
        "user/ingredient",
        UserIngredientBulkDeleteView.as_view(),
        name="user-ingredient-bulk-delete",
    ),
    # POST/PATCH/DELETE /api/user/<ingredient_id>/
    path(
        "user/<int:ingredient_id>/",
        UserIngredientDetailView.as_view(),
        name="user-ingredient-detail",
    ),
    # GET /api/ingredient
    path("ingredient", IngredientListView.as_view(), name="ingredient-list"),
    # GET /api/auth/me (session-based)
    path("auth/me", MeView.as_view(), name="auth-me"),
    # POST /api/auth/logout
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),
    # GET /api/notifications
    path("notifications", NotificationListView.as_view(), name="notification-list"),
    # PATCH /api/notifications/<pk>/
    path("notifications/<int:pk>/", NotificationDetailView.as_view(), name="notification-detail"),
    # GET /api/recommend (top 10)
    path("recommend", RecipeRecommendView.as_view(), name="recipe-recommend"),
]
