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
    UserStockDetailView,  # ✅ ต้อง Import ตัวนี้เข้ามา (ในโค้ดคุณมีแล้ว)
    IngredientListView,
    MeView,
    LogoutView,
    NotificationListView,
    NotificationDetailView,
    TagListView,
    VoiceCommandView,
)

router = DefaultRouter()
# /api/recipes/  (list)
# /api/recipes/<id>/  (detail)
router.register(r"recipes", RecipeViewSet, basename="recipe")

urlpatterns = [
    # ViewSet URLs
    path("", include(router.urls)),
    path("auth/csrf", csrf),

    # DELETE /api/ingredients/<pk>/ (ลบ Ingredient ออกจากระบบทั้งหมด)
    path(
        "ingredients/<int:pk>/",
        IngredientDeleteWithRecipesView.as_view(),
        name="ingredient-delete-with-recipes",
    ),

    # GET/POST /api/user (List stock ของ User)
    path("user", UserIngredientListView.as_view(), name="user-ingredient-list"),

    # DELETE /api/user/ingredient (Bulk delete)
    path(
        "user/ingredient",
        UserIngredientBulkDeleteView.as_view(),
        name="user-ingredient-bulk-delete",
    ),

    # ------------------------------------------------------------------
    # ✅ 1. สำหรับ "เพิ่มของใหม่" (POST) อ้างอิงด้วย Ingredient ID
    # ------------------------------------------------------------------
    path(
        "user/<int:ingredient_id>/",
        UserIngredientDetailView.as_view(),
        name="user-ingredient-detail",
    ),

    # ------------------------------------------------------------------
    # ✅ 2. สำหรับ "แก้ไข/ลบของเดิม" (PATCH/DELETE) อ้างอิงด้วย Stock ID
    # (เพิ่มส่วนนี้เข้ามาเพื่อให้ทำงานคู่กับ UserStockDetailView ที่สร้างใหม่)
    # ------------------------------------------------------------------
    path(
        "stock/<int:pk>/",
        UserStockDetailView.as_view(),
        name="user-stock-detail",
    ),
    # ------------------------------------------------------------------

    # GET /api/ingredient (List master ingredients)
    path("ingredient", IngredientListView.as_view(), name="ingredient-list"),

    # Auth
    path("auth/me", MeView.as_view(), name="auth-me"),
    path("auth/logout", LogoutView.as_view(), name="auth-logout"),

    # Notifications
    path("notifications", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<int:pk>/", NotificationDetailView.as_view(), name="notification-detail"),

    # Tags & Recommend
    path("tags", TagListView.as_view(), name="tag-list"),
    path("recommend", RecipeRecommendView.as_view(), name="recipe-recommend"),
    
    # Voice Command
    path('voice-command', VoiceCommandView.as_view(), name='voice-command'),
]