from rest_framework.routers import DefaultRouter
from recipes.api import RecipeViewSet

router = DefaultRouter()
router.register('recipes', RecipeViewSet, basename='recipe')

urlpatterns = router.urls
