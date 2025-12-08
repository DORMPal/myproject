# recipes/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .api import RecipeViewSet
from .api_views import IngredientDeleteWithRecipesView

router = DefaultRouter()
# /api/recipes/  (list)
# /api/recipes/<id>/  (detail)
router.register(r"recipes", RecipeViewSet, basename="recipe")

urlpatterns = [
    # ViewSet URLs
    path("", include(router.urls)),

    # DELETE /api/ingredients/<pk>/
    path(
        "ingredients/<int:pk>/",
        IngredientDeleteWithRecipesView.as_view(),
        name="ingredient-delete-with-recipes",
    ),
]
