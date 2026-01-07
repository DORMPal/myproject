from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.decorators import action
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from django.db.models import Prefetch

from recipes.models import Recipe, RecipeIngredient, UserStock
from recipes.serializers import RecipeSerializer


class RecipePagination(PageNumberPagination):
    # page=1 => items 0-19, page=2 => items 20-39, ...
    page_size = 20
    page_size_query_param = None  # enforce fixed size from requirement


class RecipeViewSet(ReadOnlyModelViewSet):
    """
    GET /api/recipes/           → list
    GET /api/recipes/{id}/      → detail
    รองรับ:
      - ?search=คำค้น    (ค้น title, short_detail, tag.name)
      - ?tag=ชื่อแท็ก    (filter ตาม tag เป๊ะ ๆ)
    """
    queryset = Recipe.objects.all().order_by('-created_at')
    serializer_class = RecipeSerializer
    pagination_class = RecipePagination
    filter_backends = [SearchFilter]
    search_fields = ['title']

    def get_queryset(self):
        qs = super().get_queryset().select_related('thumbnail_obj')
        tag_name = self.request.query_params.get('tag')
        if tag_name:
            qs = qs.filter(tags__name=tag_name)
        return qs

    @staticmethod
    def _build_recommendations(request, queryset, limit=None):
        """
        Core recommendation builder used by both the action and standalone endpoint.
        """
        user_ingredient_ids = set(
            UserStock.objects.filter(user=request.user, disable=False).values_list(
                "ingredient_id", flat=True
            )
        )

        recipe_ing_qs = RecipeIngredient.objects.select_related("ingredient")
        recipes = queryset.prefetch_related(
            Prefetch("recipe_ingredients", queryset=recipe_ing_qs),
            "tags",
        )

        recommendation_rows = []
        for recipe in recipes:
            # กรองเฉพาะวัตถุดิบที่ไม่ใช่ common (common=False)
            considered = [
                ri
                for ri in recipe.recipe_ingredients.all()
                if ri.ingredient and not ri.ingredient.common
            ]
            total_considered = len(considered)
            matched = sum(1 for ri in considered if ri.ingredient_id in user_ingredient_ids)

            # Skip recipes that match none of the considered ingredients
            # (ถ้ามีวัตถุดิบหลักที่ต้องใช้ แต่เราไม่มีเลย ข้ามไป)
            if total_considered > 0 and matched == 0:
                continue

            missing = total_considered - matched
            
            # คำนวณ % โดยไม่รวม common ingredients
            match_percentage = (
                100.0 if total_considered == 0 else round((matched / total_considered) * 100, 2)
            )
            
            missing_names = [
                ri.ingredient.name
                for ri in considered
                if ri.ingredient_id not in user_ingredient_ids
            ]

            recommendation_rows.append(
                {
                    "recipe": recipe,
                    "missing_ingredient_count": missing,
                    "match_percentage": match_percentage,
                    "missing_ingredients": missing_names,
                    "total_considered_ingredients": total_considered,
                    "matched_ingredients": matched,
                }
            )

        # ✅ แก้ไขการเรียงลำดับตรงนี้
        recommendation_rows.sort(
            key=lambda item: (
                -item["match_percentage"],        # 1. เปอร์เซ็นต์มากสุดขึ้นก่อน (ติดลบเพื่อให้เรียงมากไปน้อย)
                item["missing_ingredient_count"], # 2. ถ้า % เท่ากัน เอาอันที่ของขาดน้อยกว่าขึ้นก่อน
                item["recipe"].id,                # 3. ถ้าเท่ากันหมด เรียงตาม ID
            )
        )

        if limit is not None:
            recommendation_rows = recommendation_rows[:limit]

        serialized_recipes = RecipeSerializer(
            [item["recipe"] for item in recommendation_rows],
            many=True,
            context={"request": request},
        ).data

        results = []
        for serialized, extra in zip(serialized_recipes, recommendation_rows):
            serialized["missing_ingredient_count"] = extra["missing_ingredient_count"]
            serialized["match_percentage"] = extra["match_percentage"]
            serialized["missing_ingredients"] = extra["missing_ingredients"]
            serialized["total_considered_ingredients"] = extra["total_considered_ingredients"]
            serialized["matched_ingredients"] = extra["matched_ingredients"]
            results.append(serialized)

        return results

    @action(
        detail=False,
        methods=["get"],
        url_path="recommendations",
        permission_classes=[IsAuthenticated],
    )
    def recommendations(self, request):
        """
        Recommend recipes based on the user's active ingredients (top 5).
        Ranking: Highest match percentage first, then fewest missing ingredients.
        """
        results = self._build_recommendations(
            request,
            self.get_queryset().select_related("thumbnail_obj"),
            limit=5,
        )
        return Response({"count": len(results), "next": None, "previous": None, "results": results})


class RecipeRecommendView(APIView):
    """
    Standalone endpoint: GET /api/recommend (top 5 recommendations).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        recipe_qs = Recipe.objects.all().order_by("-created_at").select_related("thumbnail_obj")
        results = RecipeViewSet._build_recommendations(
            request,
            recipe_qs,
            limit=5, 
        )
        return Response({"count": len(results), "next": None, "previous": None, "results": results})