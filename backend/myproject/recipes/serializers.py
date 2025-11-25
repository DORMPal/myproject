from rest_framework import serializers
from recipes.models import Recipe, RecipeIngredient, Tag


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
        ]
