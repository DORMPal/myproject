import re
from decimal import Decimal

from django.utils.dateparse import parse_datetime

from recipes.models import Recipe, Ingredient, RecipeIngredient, Tag


def parse_fraction(text: str | None) -> Decimal | None:
    """
    แปลง string ปริมาณ ให้เป็น Decimal
    เช่น "1", "1 1/2", "1/4" → Decimal
    """
    if not text:
        return None
    text = text.strip()

    # "1 1/2"
    if " " in text:
        whole, frac = text.split(" ", 1)
        return Decimal(whole) + parse_fraction(frac)

    # "1/2"
    if "/" in text:
        num, den = text.split("/", 1)
        return Decimal(num) / Decimal(den)

    # ปกติ "1.5" หรือ "220"
    return Decimal(text)


def normalize_name_qty_unit(raw_name: str,
                            value: str | None,
                            unit: str | None):
    """
    แปลงชื่อและปริมาณวัตถุดิบพิเศษ เช่น
    'เนื้อพิคันย่า (ชิ้นละ 220 กรัม)' + value='1', unit='ชิ้น'
    → name='เนื้อพิคันย่า', qty=220, unit='กรัม'

    ถ้าไม่เข้า pattern ก็คืนค่าปกติ
    """
    value = value or ""
    unit = (unit or "").strip() or None

    # ตัดวงเล็บออก ให้เหลือชื่อสั้น ๆ
    base_name = re.sub(r'\(.*?\)', '', raw_name).strip()

    qty = parse_fraction(value) if value else None

    # หา text ข้างในวงเล็บ
    m_paren = re.search(r'\((.*?)\)', raw_name)
    if m_paren and qty is not None:
        inside = m_paren.group(1)

        # pattern พวก "ชิ้นละ 220 กรัม", "ตัวละ 100 กรัม" ฯลฯ
        m_pattern = re.search(
            r'ละ\s*([\d\s\/\.]+)\s*(กรัม|มิลลิลิตร|มล\.?|มล|ซีซี|ช้อนโต๊ะ|ช้อนชา)',
            inside
        )
        if m_pattern:
            per_value_text = m_pattern.group(1)
            per_unit = m_pattern.group(2)

            per_value = parse_fraction(per_value_text)
            if per_value is not None:
                total = qty * per_value
                return base_name, total, per_unit

    # ถ้าไม่เข้า pattern พิเศษ ก็คืนค่าปกติ
    return base_name, qty, unit


def get_or_create_ingredient(name: str, unit: str | None) -> Ingredient:
    """
    ใช้ชื่อเป็น key หลัก ถ้ามีแล้วไม่สร้างใหม่
    ถ้า unit เดิมว่างและของใหม่มีค่า ก็อัปเดต unit ให้
    """
    ing, created = Ingredient.objects.get_or_create(name=name)
    if unit and not ing.unit_of_measure:
        ing.unit_of_measure = unit
        ing.save(update_fields=["unit_of_measure"])
    return ing


def parse_servings(serves_text: str | None) -> int | None:
    """
    '6 คน' -> 6
    """
    if not serves_text:
        return None
    m = re.search(r'(\d+)', serves_text)
    if m:
        return int(m.group(1))
    return None


def import_recipe_from_post(post: dict) -> Recipe:
    """
    รับ dict ที่คือ posts ใน JSON (pageProps.posts)
    แล้วเซฟลง DB (Recipe + RecipeIngredient + Ingredient + Tags)
    """
    # ---------- 1) สร้าง/อัปเดต Recipe ----------
    recipe, created = Recipe.objects.update_or_create(
        external_id=post["id"],
        defaults={
            "title": post.get("title"),
            "instructions": post.get("content") or "",
            "servings": parse_servings(post.get("serves")),
            "short_detail": post.get("short_detail") or "",
            "level": post.get("level"),
            "created_at": parse_datetime(post.get("created")) if post.get("created") else None,
            "updated_at": parse_datetime(post.get("modified")) if post.get("modified") else None,
            "seo_title": post.get("seo_title") or "",
            "seo_description": post.get("seo_description") or "",
            "seo_keyword_text": post.get("seo_keyword_text") or "",
        }
    )

    # ---------- 2) จัดการ Ingredients ----------
    # ลบ RecipeIngredient เดิมทิ้งก่อน (กันข้อมูลซ้ำ)
    recipe.recipe_ingredients.all().delete()

    main_ingredients = post.get("main_ingredients") or []

    for item in main_ingredients:
        ingredient_name = item.get("ingredient_name")
        ingredient_value = item.get("ingredient_value", "").strip()
        ingredient_unit = item.get("ingredient_unit", "").strip()
        sub_ingredients = item.get("sub_ingredients")

        # กรณีธรรมดา (ไม่มี sub_ingredients)
        if not sub_ingredients:
            clean_name, qty, unit = normalize_name_qty_unit(
                ingredient_name,
                ingredient_value,
                ingredient_unit
            )
            ing = get_or_create_ingredient(clean_name, unit)
            RecipeIngredient.objects.create(
                recipe=recipe,
                ingredient=ing,
                required_quantity=qty,
                required_unit=unit,
                group_name=None
            )
        else:
            # กรณีมี sub_ingredients เช่น "เนื้อย่าง", "พริกแกงคั่ว"
            group_name = ingredient_name
            for sub in sub_ingredients:
                sub_name = sub.get("sub_ingredient_name")
                sub_value = sub.get("ingredient_value", "").strip()
                sub_unit = sub.get("ingredient_unit", "").strip()

                clean_name, qty, unit = normalize_name_qty_unit(
                    sub_name, sub_value, sub_unit
                )
                ing = get_or_create_ingredient(clean_name, unit)
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    ingredient=ing,
                    required_quantity=qty,
                    required_unit=unit,
                    group_name=group_name
                )

    # ---------- 3) จัดการ Tags (ทำในฟังก์ชันเดิมนี้เลย) ----------
    # ล้าง tags เดิมก่อน กันค่าค้าง
    recipe.tags.clear()

    # จาก JSON: "tags": [{ "id": 91, "name": "...", "slug": "..." }, ...]
    tag_items = post.get("tags") or []

    for t in tag_items:
        ext_id = t.get("id")
        name = (t.get("name") or "").strip()
        slug = (t.get("slug") or "").strip() or None
        taxonomy = t.get("taxonomy")  # บางตัวมี taxonomy

        if not name:
            continue

        if ext_id is not None:
            tag, _ = Tag.objects.get_or_create(
                external_id=ext_id,
                defaults={"name": name, "slug": slug, "taxonomy": taxonomy}
            )
            changed = False
            if tag.name != name:
                tag.name = name
                changed = True
            if slug and tag.slug != slug:
                tag.slug = slug
                changed = True
            if taxonomy and tag.taxonomy != taxonomy:
                tag.taxonomy = taxonomy
                changed = True
            if changed:
                tag.save()
        else:
            tag, _ = Tag.objects.get_or_create(
                name=name,
                defaults={"slug": slug, "taxonomy": taxonomy}
            )

        recipe.tags.add(tag)

    return recipe
