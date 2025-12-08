import re
from decimal import Decimal, InvalidOperation

import requests
from django.utils.dateparse import parse_datetime

from recipes.models import (
    Recipe,
    Ingredient,
    RecipeIngredient,
    Tag,
    RecipeThumbnail,
)

# รองรับตัวเศษส่วนแบบยูนิโค้ดที่ krua.co ใช้ เช่น ¼ ½ ¾
UNICODE_FRACTIONS = {
    "¼": Decimal("0.25"),
    "½": Decimal("0.5"),
    "¾": Decimal("0.75"),
}


def parse_fraction(text: str | None) -> Decimal | None:
    """
    แปลง string ปริมาณ ให้เป็น Decimal
    เช่น "1", "1 1/2", "1/4", "¼" → Decimal
    ถ้า parse ไม่ได้ให้คืน None (จะได้ไม่พังทั้งเมนู)
    """
    if not text:
        return None

    text = text.strip()

    # case เป็นตัวเศษส่วนยูนิโค้ดล้วน ๆ เช่น "¼"
    if text in UNICODE_FRACTIONS:
        return UNICODE_FRACTIONS[text]

    # case มีตัวเศษส่วนยูนิโค้ดปน เช่น "1¼"
    for ch, val in UNICODE_FRACTIONS.items():
        if ch in text:
            text = text.replace(ch, f" {str(val)}")

    # "1 1/2" หรือ "1 0.25"
    if " " in text:
        whole, frac = text.split(" ", 1)
        try:
            whole_dec = Decimal(whole)
        except InvalidOperation:
            return None
        frac_dec = parse_fraction(frac)
        if frac_dec is None:
            return whole_dec
        return whole_dec + frac_dec

    # "1/2"
    if "/" in text:
        num, den = text.split("/", 1)
        try:
            return Decimal(num) / Decimal(den)
        except InvalidOperation:
            return None

    # ปกติ "1.5" หรือ "220"
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


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
    - ใช้ name เป็น key หลัก
    - ถ้า unit เป็น None -> common=True
    - ถ้า unit ไม่ None -> common=False
    - อัปเดต unit_of_measure ถ้าเพิ่งรู้ข้อมูลใหม่
    - อัปเดต common ถ้าเปลี่ยนเงื่อนไข
    """
    ing, created = Ingredient.objects.get_or_create(name=name)

    new_common = (unit is None or unit == "")
    changed = False

    if unit and ing.unit_of_measure != unit:
        ing.unit_of_measure = unit
        changed = True

    if ing.common != new_common:
        ing.common = new_common
        changed = True

    if changed:
        ing.save()

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
    แล้วเซฟลง DB (Recipe + RecipeIngredient + Ingredient + Tags + Thumbnail แยกตาราง)
    """

    # ---------- 0) เลือก URL รูป thumbnail จาก JSON ----------
    thumb_url = None

    # ลองใช้ banner_images ก่อน
    banner_images = post.get("banner_images") or []
    if banner_images:
        thumb_url = banner_images[0].get("url")

    # ถ้าไม่มี banner_images ให้ fallback ไปใช้ seo_image
    if not thumb_url:
        seo_image = post.get("seo_image") or {}
        thumb_url = seo_image.get("url")

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

    # ---------- 1.1) ดาวน์โหลด thumbnail เก็บใน RecipeThumbnail (1–1) ----------
    if thumb_url:
        # ถ้ายังไม่มี thumbnail_obj หรือเพิ่งสร้าง recipe ใหม่ → ดาวน์โหลด
        existing_thumb = getattr(recipe, "thumbnail_obj", None)
        if created or existing_thumb is None:
            blob, mime_type = download_image_blob(thumb_url)
            if blob:
                RecipeThumbnail.objects.update_or_create(
                    recipe=recipe,
                    defaults={
                        "image": blob,
                        "mime_type": mime_type or "",
                        "source_url": thumb_url,
                    }
                )

    # ---------- 2) จัดการ Ingredients ----------
    recipe.recipe_ingredients.all().delete()

    main_ingredients = post.get("main_ingredients") or []

    for item in main_ingredients:
        ingredient_name = item.get("ingredient_name")
        ingredient_value = (item.get("ingredient_value") or "").strip()
        ingredient_unit = (item.get("ingredient_unit") or "").strip()
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
                sub_value = (sub.get("ingredient_value") or "").strip()
                sub_unit = (sub.get("ingredient_unit") or "").strip()

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

    # ---------- 3) จัดการ Tags ----------
    recipe.tags.clear()

    tag_items = post.get("tags") or []

    for t in tag_items:
        ext_id = t.get("id")
        name = (t.get("name") or "").strip()
        slug = (t.get("slug") or "").strip() or None
        taxonomy = t.get("taxonomy")

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


def download_image_blob(url: str):
    """
    ดาวน์โหลดรูปจาก URL แล้วคืน (bytes, mime_type)
    ถ้าดาวน์โหลดไม่ได้ คืน (None, None)
    """
    if not url:
        return None, None

    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        return resp.content, content_type
    except Exception:
        return None, None
