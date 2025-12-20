from rest_framework.viewsets import ReadOnlyModelViewSet
from rest_framework.filters import SearchFilter
from rest_framework.pagination import PageNumberPagination

from recipes.models import Recipe
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
    search_fields = ['title', 'short_detail', 'tags__name']

    def get_queryset(self):
        qs = super().get_queryset().select_related('thumbnail_obj')
        tag_name = self.request.query_params.get('tag')
        if tag_name:
            qs = qs.filter(tags__name=tag_name)
        return qs
