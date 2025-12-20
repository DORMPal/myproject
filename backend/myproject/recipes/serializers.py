import base64
from rest_framework import serializers
from recipes.models import Recipe, RecipeIngredient, Tag, Ingredient, UserStock


class RecipeIngredientSerializer(serializers.ModelSerializer):
    ingredient_name = serializers.CharField(source='ingredient.name')

    class Meta:
        model = RecipeIngredient
        fields = [
            'ingredient_name',
            'required_quantity',
            'required_unit',
            'group_name',
        ]


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ['id', 'external_id', 'name', 'slug', 'taxonomy']


class RecipeSerializer(serializers.ModelSerializer):
    ingredients = RecipeIngredientSerializer(
        many=True, source='recipe_ingredients'
    )
    tags = TagSerializer(many=True)
    thumbnail = serializers.SerializerMethodField()

    class Meta:
        model = Recipe
        fields = [
            'id',
            'external_id',
            'title',
            'short_detail',
            'instructions',
            'servings',
            'level',
            'created_at',
            'tags',
            'ingredients',
            'thumbnail',
        ]

    def get_thumbnail(self, obj: Recipe):
        thumb = getattr(obj, 'thumbnail_obj', None)
        if not thumb or not thumb.image:
            return None
        try:
            encoded = base64.b64encode(thumb.image).decode('ascii')
            return {
                'mime_type': thumb.mime_type,
                'data': f"data:{thumb.mime_type};base64,{encoded}" if thumb.mime_type else encoded,
                'source_url': thumb.source_url,
            }
        except Exception:
            return None


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ['id', 'name', 'unit_of_measure', 'common']


class UserStockSerializer(serializers.ModelSerializer):
    ingredient = IngredientSerializer()

    class Meta:
        model = UserStock
        fields = ['id', 'ingredient', 'quantity', 'expiration_date', 'date_added', 'disable']
