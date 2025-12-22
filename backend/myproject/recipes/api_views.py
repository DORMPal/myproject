# recipes/api_views.py
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Ingredient, Recipe, UserStock
from .serializers import IngredientSerializer, UserStockSerializer

User = get_user_model()


class IngredientDeleteWithRecipesView(APIView):
    """
    DELETE /api/ingredients/<pk>/
    - หา ingredient ตาม id
    - หา recipe ที่ใช้ ingredient นี้
    - ลบ recipe ทั้งหมดนั้น (thumbnail จะโดนลบตามเพราะ on_delete=CASCADE)
    - ลบ ingredient ตัวนี้ (row ใน recipe_ingredient จะโดนลบตามถ้า FK เป็น CASCADE)
    """

    # permission_classes = [IsAuthenticated]  # ปรับได้ (เช่น IsAdminUser)

    def delete(self, request, pk, *args, **kwargs):
        ingredient = get_object_or_404(Ingredient, pk=pk)

        with transaction.atomic():
            recipe_ids = list(
                ingredient.ingredient_recipes.values_list("recipe_id", flat=True).distinct()
            )

            # ลบ recipe ทั้งหมดที่เกี่ยวข้อง (thumbnail 1-1 จะ cascade)
            Recipe.objects.filter(id__in=recipe_ids).delete()

            # ลบ ingredient (recipe_ingredient จะ cascade ถ้าตั้ง FK ถูก)
            ingredient.delete()

        # 204 ตามหลักไม่ควรส่ง body (ถ้าจะส่งข้อมูล แนะนำ 200)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserIngredientListView(APIView):
    """
    GET  /api/user
    POST /api/user (mirror GET)
    - ใช้ user จาก session (request.user)
    - คืนรายการ stock ของ user นั้น
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        stocks = (
            # UserStock.objects.filter(user=user, disable=False)
            UserStock.objects.filter(user=user)
            .select_related("ingredient")
            .order_by("-date_added")
        )
        data = UserStockSerializer(stocks, many=True).data
        return Response(data)

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


class UserIngredientDetailView(APIView):
    """
    POST   /api/user/<ingredient_id>/   body: quantity?, expiration_date?, disable?
    PATCH  /api/user/<ingredient_id>/   body: fields to update
    DELETE /api/user/<ingredient_id>/
    - ทำงานกับ UserStock ของ "user ที่ login อยู่" เท่านั้น
    """

    permission_classes = [IsAuthenticated]

    def _get_stock(self, user, ingredient_id):
        ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
        stock, _ = UserStock.objects.get_or_create(
            user=user,
            ingredient=ingredient,
            defaults={"disable": False},
        )
        return stock

    def post(self, request, ingredient_id, *args, **kwargs):
        user = request.user
        stock = self._get_stock(user, ingredient_id)

        for field in ("quantity", "expiration_date", "disable"):
            if field in request.data:
                setattr(stock, field, request.data.get(field))
        # ใน post/patch หลังจาก loop
        if "disable" not in request.data:
            stock.disable = False

        stock.save()
        return Response(UserStockSerializer(stock).data, status=status.HTTP_201_CREATED)

    def patch(self, request, ingredient_id, *args, **kwargs):
        user = request.user
        stock = self._get_stock(user, ingredient_id)

        updated = False
        for field in ("quantity", "expiration_date", "disable"):
            if field in request.data:
                setattr(stock, field, request.data.get(field))
                updated = True
        if "disable" not in request.data:
            stock.disable = False
        if updated:
            stock.save()

        return Response(UserStockSerializer(stock).data)

    def delete(self, request, ingredient_id, *args, **kwargs):
        user = request.user
        stock = get_object_or_404(UserStock, user=user, ingredient_id=ingredient_id)
        stock.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserIngredientBulkDeleteView(APIView):
    """
    DELETE /api/user/ingredient
    body: { "ingredient_ids": [<id>, <id>, ...] }
    - ลบ stock หลายรายการของ user ที่ล็อกอินอยู่
    """

    permission_classes = [IsAuthenticated]

    def delete(self, request, *args, **kwargs):
        ingredient_ids = request.data.get("ingredient_ids", [])
        if not isinstance(ingredient_ids, (list, tuple)) or len(ingredient_ids) == 0:
            return Response(
                {"detail": "ingredient_ids must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # cast to int and drop invalid values
        normalized_ids = []
        for raw in ingredient_ids:
            try:
                normalized_ids.append(int(raw))
            except (TypeError, ValueError):
                continue

        if not normalized_ids:
            return Response(
                {"detail": "ingredient_ids must contain numeric ids"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = request.user
        deleted_count, _ = UserStock.objects.filter(
            user=user, ingredient_id__in=normalized_ids
        ).delete()

        return Response({"deleted": deleted_count})


class IngredientListView(APIView):
    """
    GET /api/ingredient
    (อันนี้จะเปิด public ก็ได้ หรือจะล็อกอินก่อนก็ได้)
    """

    def get(self, request, *args, **kwargs):
        # ingredients = Ingredient.objects.all().order_by("name")
        ingredients = (
            Ingredient.objects
            .filter(common=False)
            .order_by("name")
        )
        data = IngredientSerializer(ingredients, many=True).data
        return Response(data)


class MeView(APIView):
    """
    GET /api/auth/me
    Uses session auth (HttpOnly cookie) to return current user info.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # debug ชั่วคราว
        print("query_params:", dict(request.query_params))
        print("is_authenticated:", request.user.is_authenticated)
        print("session:", list(request.session.items()))
        print("user:", request.user.id, request.user.email, request.user.get_full_name())

        user = request.user
        return Response(
            {
                "id": user.id,
                "email": user.email,
                "name": user.get_full_name() or user.username,
            }
        )
