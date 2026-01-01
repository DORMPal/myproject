from django.core.management.base import BaseCommand
from django.db import transaction

from recipes.models import (
    Ingredient,
    Tag,
    Recipe,
    RecipeIngredient,
    RecipeThumbnail,
    UserStock,
    Notification,
)


class Command(BaseCommand):
    help = "Migrate data from SQLite to MySQL"

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🚀 Start migrating data..."))

        self.migrate_ingredients()
        self.migrate_tags()
        self.migrate_recipes()
        self.migrate_recipe_ingredients()
        self.migrate_recipe_thumbnails()
        self.migrate_user_stocks()
        self.migrate_notifications()

        self.stdout.write(self.style.SUCCESS("✅ Migration completed"))

    # --------------------------------------------------
    def migrate_ingredients(self):
        self.stdout.write("➡ Migrating Ingredient")

        for ing in Ingredient.objects.using("sqlite").all():
            Ingredient.objects.update_or_create(
                name=ing.name,
                defaults={
                    "unit_of_measure": ing.unit_of_measure,
                    "common": ing.common,
                },
            )

    # --------------------------------------------------
    def migrate_tags(self):
        self.stdout.write("➡ Migrating Tag")

        for tag in Tag.objects.using("sqlite").all():
            Tag.objects.update_or_create(
                external_id=tag.external_id,
                defaults={
                    "name": tag.name,
                    "slug": tag.slug,
                    "taxonomy": tag.taxonomy,
                },
            )

    # --------------------------------------------------
    def migrate_recipes(self):
        self.stdout.write("➡ Migrating Recipe")

        for r in Recipe.objects.using("sqlite").all():
            recipe, _ = Recipe.objects.update_or_create(
                external_id=r.external_id,
                defaults={
                    "title": r.title,
                    "instructions": r.instructions,
                    "servings": r.servings,
                    "short_detail": r.short_detail,
                    "level": r.level,
                    "created_at": r.created_at,
                    "updated_at": r.updated_at,
                    "seo_title": r.seo_title,
                    "seo_description": r.seo_description,
                    "seo_keyword_text": r.seo_keyword_text,
                },
            )

            # many-to-many tag
            recipe.tags.clear()
            for tag in r.tags.using("sqlite").all():
                mysql_tag = Tag.objects.filter(
                    external_id=tag.external_id
                ).first()
                if mysql_tag:
                    recipe.tags.add(mysql_tag)

    # --------------------------------------------------
    def migrate_recipe_ingredients(self):
        self.stdout.write("➡ Migrating RecipeIngredient")

        for ri in RecipeIngredient.objects.using("sqlite").all():
            recipe = Recipe.objects.filter(
                external_id=ri.recipe.external_id
            ).first()
            ingredient = Ingredient.objects.filter(
                name=ri.ingredient.name
            ).first()

            if not recipe or not ingredient:
                continue

            RecipeIngredient.objects.update_or_create(
                recipe=recipe,
                ingredient=ingredient,
                group_name=ri.group_name,
                defaults={
                    "required_quantity": ri.required_quantity,
                    "required_unit": ri.required_unit,
                    # "group_name": ri.group_name,
                },
            )

    # --------------------------------------------------
    def migrate_recipe_thumbnails(self):
        self.stdout.write("➡ Migrating RecipeThumbnail")

        for thumb in RecipeThumbnail.objects.using("sqlite").all():
            recipe = Recipe.objects.filter(
                external_id=thumb.recipe.external_id
            ).first()
            if not recipe:
                continue

            RecipeThumbnail.objects.update_or_create(
                recipe=recipe,
                defaults={
                    "image": thumb.image,
                    "mime_type": thumb.mime_type,
                    "source_url": thumb.source_url,
                },
            )

    # --------------------------------------------------
    def migrate_user_stocks(self):
        self.stdout.write("➡ Migrating UserStock")

        for us in UserStock.objects.using("sqlite").all():
            ingredient = Ingredient.objects.filter(
                name=us.ingredient.name
            ).first()

            if not ingredient:
                continue

            UserStock.objects.update_or_create(
                user_id=us.user_id,   # ⚠ assumes user id same
                ingredient=ingredient,
                defaults={
                    "quantity": us.quantity,
                    "expiration_date": us.expiration_date,
                    "disable": us.disable,
                },
            )

    # --------------------------------------------------
    def migrate_notifications(self):
        self.stdout.write("➡ Migrating Notification")

        for n in Notification.objects.using("sqlite").all():
            Notification.objects.update_or_create(
                user_id=n.user_id,
                user_stock_id=n.user_stock_id,
                defaults={
                    "read_yet": n.read_yet,
                    "created_at": n.created_at,
                },
            )
