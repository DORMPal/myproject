from django.db import models
from django.conf import settings   # 👈 ใช้ FK ไปยัง User


class Ingredient(models.Model):
    name = models.CharField(max_length=255, unique=True)
    unit_of_measure = models.CharField(max_length=255, null=True, blank=True)

    # ถ้า unit เป็น null → common=True (ของที่ใช้บ่อยหรือไม่มีสัดส่วน เช่น พริก, เกลือ)
    common = models.BooleanField(default=False)

    class Meta:
        db_table = 'ingredient'

    def __str__(self):
        return self.name


class Tag(models.Model):
    # id จาก krua.co (post.tags[].id) – ไม่ได้มีทุกอัน
    external_id = models.IntegerField(null=True, blank=True, unique=True)
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100, null=True, blank=True)
    taxonomy = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = 'tag'
        ordering = ['name']

    def __str__(self):
        return self.name


class Recipe(models.Model):
    external_id = models.IntegerField(null=True, blank=True)  # id จาก krua.co
    title = models.CharField(max_length=255)
    instructions = models.TextField(null=True, blank=True)    # HTML content
    servings = models.IntegerField(null=True, blank=True)
    short_detail = models.TextField(null=True, blank=True)
    level = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)

    seo_title = models.CharField(max_length=255, null=True, blank=True)
    seo_description = models.TextField(null=True, blank=True)
    seo_keyword_text = models.TextField(null=True, blank=True)

    # 👇 Many-to-Many กับ Tag
    tags = models.ManyToManyField(Tag, related_name='recipes', blank=True)

    # Many-to-Many กับ Ingredient ผ่าน RecipeIngredient
    ingredients = models.ManyToManyField(
        Ingredient,
        through='RecipeIngredient',
        related_name='recipes'
    )

    class Meta:
        db_table = 'recipe'

    def __str__(self):
        return self.title


class RecipeThumbnail(models.Model):
    """
    เก็บรูป thumbnail แยกตาราง แต่เป็น 1–1 กับ Recipe
    """
    recipe = models.OneToOneField(
        Recipe,
        on_delete=models.CASCADE,
        related_name='thumbnail_obj',   # recipe.thumbnail_obj
    )
    image = models.BinaryField(null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    source_url = models.URLField(max_length=500, null=True, blank=True)

    class Meta:
        db_table = 'recipe_thumbnail'

    def __str__(self):
        return f"Thumbnail of {self.recipe.title}"


class RecipeIngredient(models.Model):
    recipe = models.ForeignKey(
        Recipe, on_delete=models.CASCADE, related_name='recipe_ingredients'
    )
    ingredient = models.ForeignKey(
        Ingredient, on_delete=models.CASCADE, related_name='ingredient_recipes'
    )
    required_quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    required_unit = models.CharField(max_length=255, null=True, blank=True)
    group_name = models.CharField(
        max_length=100, null=True, blank=True
    )  # เช่น "เนื้อย่าง", "พริกแกงคั่ว"

    class Meta:
        db_table = 'recipe_ingredient'

    def __str__(self):
        return f"{self.recipe.title} - {self.ingredient.name}"


class UserStock(models.Model):
    """
    วัตถุดิบที่ผู้ใช้แต่ละคนมีในสต็อก
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='user_stocks',
    )
    ingredient = models.ForeignKey(
        Ingredient,
        on_delete=models.CASCADE,
        related_name='user_stocks',
    )
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    expiration_date = models.DateField(null=True, blank=True)
    date_added = models.DateField(auto_now_add=True)
    disable = models.BooleanField(default=False)

    class Meta:
        db_table = 'user_stock'

    def __str__(self):
        return f"{self.user} - {self.ingredient.name}"


class Notification(models.Model):
    """
    แจ้งเตือนที่ผูกกับ UserStock เมื่อใกล้หมดอายุ
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    user_stock = models.ForeignKey(
        UserStock,
        on_delete=models.CASCADE,
        related_name='notifications',
    )
    read_yet = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notification'
        unique_together = ('user', 'user_stock')
        indexes = [
            models.Index(fields=['user', 'read_yet']),
        ]

    def __str__(self):
        return f"Notification for {self.user} - {self.user_stock}"
