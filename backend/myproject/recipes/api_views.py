# recipes/api_views.py

import json
import uuid
import requests
from datetime import date, datetime,timedelta
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from thefuzz import process
from .models import Ingredient, UserStock
import os
from livekit import api

from .models import Ingredient, Recipe, UserStock, Notification, Tag
from .serializers import IngredientSerializer, UserStockSerializer, NotificationSerializer, TagSerializer

User = get_user_model()
# OLLAMA_API_URL = getattr(settings, 'OLLAMA_API_URL', 'http://ollama:11434/api/generate')


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
            .order_by("expiration_date")
        )
        data = UserStockSerializer(stocks, many=True).data
        return Response(data)

    def post(self, request, *args, **kwargs):
        return self.get(request, *args, **kwargs)


# recipes/api_views.py

class UserIngredientDetailView(APIView):
    """
    POST /api/user/<ingredient_id>/
    - ใช้สำหรับ ADD วัตถุดิบใหม่เข้าตู้เย็น (สร้าง UserStock แถวใหม่เสมอ)
    - อ้างอิงด้วย Ingredient ID
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, ingredient_id, *args, **kwargs):
        user = request.user
        ingredient = get_object_or_404(Ingredient, pk=ingredient_id)
        expiration_date = request.data.get("expiration_date", None)
        disable_status = request.data.get("disable", False)

        # 🔍 1. เช็คก่อนว่ามีของชิ้นนี้ ในวันหมดอายุนี้ อยู่แล้วหรือยัง?
        exists = UserStock.objects.filter(
            user=user,
            ingredient=ingredient,
            expiration_date=expiration_date
        ).exists()

        if exists:
            # 🛑 ถ้ามีแล้ว ส่ง Error 409 กลับไป
            return Response(
                {"detail": f"มี {ingredient.name} (วันหมดอายุนี้) ในตู้เย็นแล้ว"}, 
                status=status.HTTP_409_CONFLICT
            )

        # ✅ ใช้ .create() เพื่อสร้าง Batch ใหม่เสมอ (อนุญาตให้ซ้ำได้)
        stock = UserStock.objects.create(
            user=user,
            ingredient=ingredient,
            quantity=request.data.get("quantity", 1), 
            expiration_date=request.data.get("expiration_date", None),
            disable=request.data.get("disable", False)
        )

        return Response(UserStockSerializer(stock).data, status=status.HTTP_201_CREATED)


class UserStockDetailView(APIView):
    """
    PATCH  /api/stock/<pk>/
    DELETE /api/stock/<pk>/
    - ใช้สำหรับ แก้ไข หรือ ลบ สต็อกที่มีอยู่แล้ว
    - ⚠️ ต้องส่ง pk เป็น ID ของตาราง UserStock (ไม่ใช่ ID ของ Ingredient)
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        user = request.user
        # ✅ หาจาก ID ของ UserStock โดยตรง (เจาะจงนมขวดนั้นๆ ได้เลย)
        stock = get_object_or_404(UserStock, pk=pk, user=user)

        updated = False
        for field in ("quantity", "expiration_date", "disable"):
            if field in request.data:
                setattr(stock, field, request.data.get(field))
                updated = True
        
        if updated:
            stock.save()
            Notification.objects.filter(user=user, user_stock=stock).delete()

        return Response(UserStockSerializer(stock).data)

    def delete(self, request, pk, *args, **kwargs):
        user = request.user
        # ✅ ลบเฉพาะ UserStock แถวนี้ (ไม่กระทบนมขวดอื่น)
        stock = get_object_or_404(UserStock, pk=pk, user=user)
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


class LogoutView(APIView):
    """
    POST /api/auth/logout
    Logs out the current user by clearing the session.
    """

    def post(self, request, *args, **kwargs):
        from django.contrib.auth import logout
        logout(request)
        return Response({"detail": "Successfully logged out"}, status=status.HTTP_200_OK)


class NotificationListView(APIView):
    """
    GET /api/notifications
    Returns all notifications for the current user and count of unread notifications.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        notifications = Notification.objects.filter(user=user).order_by('-created_at')
        unread_count = notifications.filter(read_yet=False).count()
        
        data = NotificationSerializer(notifications, many=True).data
        return Response({
            'notifications': data,
            'unread_count': unread_count
        })


class NotificationDetailView(APIView):
    """
    PATCH /api/notifications/<pk>/
    Updates the read status of a notification to True.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk, *args, **kwargs):
        user = request.user
        notification = get_object_or_404(Notification, pk=pk, user=user)
        
        notification.read_yet = True
        notification.save()
        
        return Response(NotificationSerializer(notification).data)


class TagListView(APIView):
    """
    GET /api/tags
    Returns all tags available in the system.
    """

    def get(self, request, *args, **kwargs):
        tags = Tag.objects.all().order_by('name')
        data = TagSerializer(tags, many=True).data
        return Response(data)

# class VoiceCommandView(APIView):
#     """
#     POST /api/voice-command
#     """
#     permission_classes = [IsAuthenticated]

#     def post(self, request, *args, **kwargs):
#         user_text = request.data.get('text', '')
#         if not user_text:
#             return Response({'success': False, 'message': 'ไม่ได้รับข้อความเสียง'}, status=status.HTTP_400_BAD_REQUEST)

#         print(f"🎤 [VOICE] User text: {user_text}")

#         # today_str = date.today().isoformat()
#         today = date.today()

#         # ✅ 1. แก้ Prompt: ย้ำเรื่อง Format YYYY-MM-DD ให้ชัดเจนขึ้น
#         system_prompt = f"""
#         You are an inventory assistant. Current Date: {today.isoformat()}
#         Extract data into JSON format only.
        
#         Fields: 
#         - "action": "add" or "remove"
#         - "item": ingredient name (string)
#         - "date_value": string (if fixed date: "YYYY-MM-DD", if relative: number of days/months/years)
#         - "date_unit": string (only for relative: "day", "week", "month", "year")
        
#         Example 1: "ซื้อกีวี อีก 2 ปีหมดอายุ" -> {{"action": "add", "item": "กีวี", "is_fixed_date": false, "date_value": "2", "date_unit": "year"}}
#         Example 2: "นมหมดอายุพรุ่งนี้" -> {{"action": "add", "item": "นม", "is_fixed_date": false, "date_value": "1", "date_unit": "day"}}
#         Example 3: "หมูหมดอายุ 31 ธันวา" -> {{"action": "add", "item": "หมู", "is_fixed_date": true, "date_value": "{today.year}-12-31", "date_unit": null}}
#         """

#         try:
#             payload = {
#                 "model": "qwen2.5:1.5b", 
#                 "prompt": f"{system_prompt}\nUser Input: {user_text}\nJSON Output:",
#                 "stream": False,
#                 "format": "json"
#             }
#             ollama_resp = requests.post(OLLAMA_API_URL, json=payload, timeout=30)
#             ai_data = ollama_resp.json()
            
#             raw_response = ai_data.get('response', '{}')
#             print(f"🤖 [OLLAMA] Response: {raw_response}")
            
#             parsed_data = json.loads(raw_response)
#         except Exception as e:
#             print(f"❌ [ERROR] AI Failed: {e}")
#             return Response({'success': False, 'message': 'AI ประมวลผลไม่สำเร็จ'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

#         action = parsed_data.get('action', 'add')
#         item_name = parsed_data.get('item', '')
#         expiration_date_str = parsed_data.get('expiration_date', None) # รับค่าเป็น String ก่อน

#         # ✅ 2. เพิ่ม Logic แปลงวันที่ (Date Parsing) ให้รองรับหลาย Format กันเหนียว
#         final_expiration_date = None
#         if expiration_date_str:
#             try:
#                 # ลองแปลงแบบ YYYY-MM-DD (มาตรฐาน)
#                 final_expiration_date = datetime.strptime(expiration_date_str, '%Y-%m-%d').date()
#             except ValueError:
#                 try:
#                     # ถ้าพัง ลองแปลงแบบ MM-DD-YYYY (แบบที่ AI เพิ่งส่งผิดมา)
#                     final_expiration_date = datetime.strptime(expiration_date_str, '%m-%d-%Y').date()
#                 except ValueError:
#                     try:
#                         # ถ้าพังอีก ลองแปลงแบบ DD-MM-YYYY
#                         final_expiration_date = datetime.strptime(expiration_date_str, '%d-%m-%Y').date()
#                     except ValueError:
#                         print(f"⚠️ Date format invalid: {expiration_date_str} -> Ignored")
#                         final_expiration_date = None

#         if not item_name:
#             return Response({'success': False, 'message': 'ไม่เข้าใจชื่อวัตถุดิบ'}, status=status.HTTP_400_BAD_REQUEST)

#         # Fuzzy Match
#         # แก้ไขบรรทัดนี้ตามที่คุณเคยแจ้ง (filter common=False)
#         all_ingredients = list(
#             Ingredient.objects
#             .filter(common=False)
#             .values_list('name', flat=True)
#         )
#         best_match, score = process.extractOne(item_name, all_ingredients)
#         print(f"🔍 [MATCH] '{item_name}' -> '{best_match}' ({score}%)")

#         if score < 60:
#             return Response({'success': False, 'message': f"หา '{item_name}' ไม่เจอในระบบ"}, status=status.HTTP_404_NOT_FOUND)

#         # Update DB
#         ingredient_obj = Ingredient.objects.get(name=best_match)
#         stock, created = UserStock.objects.get_or_create(
#             user=request.user,
#             ingredient=ingredient_obj,
#             defaults={'quantity': 1}
#         )
        
#         message = ""
        
#         if action == 'remove':
#             stock.expiration_date = None
#             message = f"ลบวันหมดอายุของ {best_match} แล้ว"
#         else:
#             if final_expiration_date:
#                 # ✅ ใช้ตัวแปรที่แปลงเป็น Python Date Object แล้ว (Django จะไม่งอแง)
#                 stock.expiration_date = final_expiration_date 
#                 message = f"อัปเดต {best_match} วันหมดอายุ {final_expiration_date}"
#             else:
#                 message = f"อัปเดต {best_match} (ไม่ได้ระบุวันหมดอายุ)"
        
#         stock.save()

#         return Response({
#             'success': True,
#             'message': message,
#             'data': {
#                 'item': best_match,
#                 'expiration_date': stock.expiration_date
#             }
#         })

class LiveKitTokenView(APIView):
    """
    GET /api/livekit/token
    - สร้าง Token เพื่อให้ Frontend connect เข้าห้อง LiveKit
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        
        # สร้าง Token
        token = api.AccessToken(
            os.getenv("LIVEKIT_API_KEY"),
            os.getenv("LIVEKIT_API_SECRET")
        )
        
        # ระบุตัวตน (User Email) เพื่อให้ Agent รู้ว่าใครคุยด้วย
        token.with_identity(user.email) 
        token.with_name(user.get_full_name() or user.username)
        
        # ให้สิทธิ์เข้าห้อง
        my_uuid = str(uuid.uuid4())
        token.with_grants(api.VideoGrants(
            room_join=True,
            room="kitchen-voice-room" + f"{my_uuid}", 
        ))

        return Response({"token": token.to_jwt()})