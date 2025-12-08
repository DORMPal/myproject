# recipes/api_views.py
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Ingredient, Recipe


class IngredientDeleteWithRecipesView(APIView):
    """
    DELETE /api/ingredients/<id>/
    - หา ingredient ตาม id
    - เก็บ recipe_id ทุกอันที่เคยใช้ ingredient นี้
    - ลบ recipe ทั้งหมดนั้น (thumbnail จะโดนลบตามเพราะ on_delete=CASCADE)
    - ลบ ingredient ตัวนี้
    """

    def delete(self, request, pk, *args, **kwargs):
        ingredient = get_object_or_404(Ingredient, pk=pk)

        # ใช้ transaction.atomic กันครึ่งๆกลางๆ
        with transaction.atomic():
            # 1) หา recipe ทุกอันที่เคยใช้ ingredient นี้
            recipe_ids = list(
                ingredient.ingredient_recipes
                .values_list("recipe_id", flat=True)
                .distinct()
            )

            # 2) ลบ recipe ทั้งหมดที่เคยใช้ ingredient นี้
            #    ถ้ามี model RecipeThumbnail ที่ FK ผูกกับ Recipe + on_delete=CASCADE
            #    thumbnail จะโดนลบให้อัตโนมัติ
            Recipe.objects.filter(id__in=recipe_ids).delete()

            # 3) ลบ ingredient ตัวเอง (row ใน recipe_ingredient ที่เหลืออยู่จะโดน CASCADE ลบด้วย)
            ingredient.delete()

        return Response(
            {
                "detail": f"Ingredient {pk} and {len(recipe_ids)} recipes deleted."
            },
            status=status.HTTP_204_NO_CONTENT,
        )
