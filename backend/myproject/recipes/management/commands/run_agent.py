# ==========================================================
# IMPORTS
# ==========================================================
import asyncio
import json
import os
import sys
import math
from typing import List, Dict, Optional
from datetime import date, timedelta

# ================= Django =================
import django
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async
from django.db.models import Prefetch

# ================= LiveKit =================
# from recipes.models import Recipe, RecipeIngredient
from livekit import rtc
from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    stt,
    llm
)
from livekit.agents.llm import function_tool

# ================= Plugins =================
from livekit.plugins import openai, deepgram
from livekit.plugins import google
from openai import AsyncOpenAI

from datetime import date

# ==========================================================
# CONFIG
# ==========================================================
EMBEDDING_MODEL = "text-embedding-3-small"
CACHE_FILE = "ingredient_embeddings_v1.json"

INGREDIENT_EMBEDDINGS: Dict[str, List[float]] = {}
EMBEDDING_READY = False

# ==========================================================
# VECTOR UTILS
# ==========================================================
def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb + 1e-8)

# ==========================================================
# SEND TO FRONTEND
# ==========================================================
async def send_ui_message(ctx: JobContext, type_: str, text: str):
    payload = json.dumps({
        "type": type_,
        "text": text,
    }).encode("utf-8")

    print(f"[DATA] -> {type_}: {text}")
    await ctx.room.local_participant.publish_data(payload, reliable=True)

# ==========================================================
# PREPARE EMBEDDINGS (CACHE)
# ==========================================================
async def prepare_embeddings(Ingredient):
    global EMBEDDING_READY

    if EMBEDDING_READY:
        return

    # 1) Load from cache
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            INGREDIENT_EMBEDDINGS.update(json.load(f))
        EMBEDDING_READY = True
        print(f"✅ Loaded {len(INGREDIENT_EMBEDDINGS)} embeddings from cache")
        return

    print("📦 Building ingredient embeddings...")

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    @sync_to_async
    def load_names():
        return list(
            Ingredient.objects
            .filter(common=False)
            .values_list("name", flat=True)
        )

    names = await load_names()
    temp = {}

    BATCH = 50
    for i in range(0, len(names), BATCH):
        batch = names[i:i+BATCH]
        resp = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=batch,
        )
        for j, item in enumerate(resp.data):
            temp[batch[j]] = item.embedding

    INGREDIENT_EMBEDDINGS.update(temp)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(temp, f, ensure_ascii=False)

    EMBEDDING_READY = True
    print("✅ Embedding ready")

# ==========================================================
# ENTRYPOINT
# ==========================================================
async def validate_env():
    # ---------------- Django ----------------
    print("🚀 Setting up Django...")

    google_creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    
    if not google_creds:
        print("❌ Error: GOOGLE_APPLICATION_CREDENTIALS not found in .env")
        return

    # (Optional) เช็คเพื่อความชัวร์ว่าไฟล์มันเข้าไปใน Docker จริงไหม
    if not os.path.exists(google_creds):
        print(f"❌ Error: File not found at {google_creds}")
        # list ดูว่าใน /app มีอะไรบ้าง (Debugging)
        print("Files in /app:", os.listdir("/app"))
        return
async def entrypoint(ctx: JobContext):

    await validate_env()

# ==========================================================
# SET UP DJANGO Because this is a management command
# ==========================================================
   
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_project.settings")
    django.setup()

    from recipes.models import Ingredient, UserStock,Recipe, RecipeIngredient
    User = get_user_model()

    # ======================================================
    # SET UP LIVEKIT
    # ======================================================

    # ---------------- Connect ----------------
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)

    # ----------------- User ------------------
    participant = await ctx.wait_for_participant()
    user = await sync_to_async(User.objects.get)(email=participant.identity)

    print("👤 USER:", user.email)

    # ---------------- Plugins ----------------
    # stt_plugin = deepgram.STT(
    #     api_key=os.getenv("DEEPGRAM_API_KEY"),
    #     language="th-TH",
    #     model="nova-2",
    # )

    # ========================================================
    # PLUGINS
    # ========================================================
    stt_plugin = google.STT(
        languages="th-TH", 
        model="latest_long"
    )

    llm_plugin = openai.LLM(
        model="gpt-4o-mini",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    tts_plugin = openai.TTS(
        model="gpt-4o-mini-tts",
        api_key=os.getenv("OPENAI_API_KEY"),
    )

    # ---------------- Audio Out ----------------
    source = rtc.AudioSource(24000, 1) # 24kHz, Mono, same like gpt-4o-mini-tts
    track = rtc.LocalAudioTrack.create_audio_track("agent", source) # เสียงที่ track นี้จะเอาไปส่งให้ user
    await ctx.room.local_participant.publish_track(track) # audio track นี้ publish เข้า LiveKit room

    # ---------------- Embeddings ----------------
    await prepare_embeddings(Ingredient)
    print("🧪 Checking embedding sanity...")
    for k, v in list(INGREDIENT_EMBEDDINGS.items())[:1]:
        print("   sample:", k, type(v), len(v))

    # ======================================================
    # STATE
    # ======================================================
    STATE = {
        "mode": "idle",            # idle | await_expiry | await_remove_choice
        "pending_item": None,
        "pending_expiry": None,
        "candidates": [],
    }

    # ======================================================
    # TOOLS
    # ======================================================
    print("🛠️ Setting up tools function...")
    @function_tool
    async def recommend_recipes_for_user(limit: int = 3):
        @sync_to_async
        def _get():
            user_ingredient_ids = set(
                UserStock.objects
                .filter(user=user, disable=False)
                .values_list("ingredient_id", flat=True)
            )

            recipes = Recipe.objects.prefetch_related(
                Prefetch(
                    "recipe_ingredients",
                    queryset=RecipeIngredient.objects.select_related("ingredient"),
                )
            )

            rows = []
            for recipe in recipes:
                considered = [
                    ri for ri in recipe.recipe_ingredients.all()
                    if ri.ingredient and not ri.ingredient.common
                ]

                total = len(considered)
                matched = sum(
                    1 for ri in considered
                    if ri.ingredient_id in user_ingredient_ids
                )

                if total > 0 and matched == 0:
                    continue

                missing = total - matched
                match_percentage = 100.0 if total == 0 else round((matched / total) * 100, 2)

                missing_names = [
                    ri.ingredient.name
                    for ri in considered
                    if ri.ingredient_id not in user_ingredient_ids
                ]

                rows.append({
                    "recipe_name": recipe.title,
                    "match_percentage": match_percentage,
                    "missing_ingredient_count": missing,
                    "missing_ingredients": missing_names,
                })

            rows.sort(
                key=lambda r: (
                    -r["match_percentage"],
                    r["missing_ingredient_count"],
                )
            )

            return rows[:limit]

        results = await _get()
        return {"count": len(results), "results": results}

    @function_tool
    async def recommend_recipes_with_ingredient(
        ingredient_name: str,
        limit: int = 3,
    ):
        """
        แนะนำเมนูที่ต้องมีวัตถุดิบที่กำหนด (เช่น กุ้งแก้ว)
        """

        @sync_to_async
        def _get():
            # หา ingredient ก่อน
            ing = Ingredient.objects.filter(name=ingredient_name).first()
            if not ing:
                return {
                    "status": "ingredient_not_found",
                    "ingredient": ingredient_name,
                    "results": [],
                }

            user_ingredient_ids = set(
                UserStock.objects
                .filter(user=user, disable=False)
                .values_list("ingredient_id", flat=True)
            )

            # 🔒 filter recipe ที่ "ต้องมี ingredient นี้"
            recipes = (
                Recipe.objects
                .filter(recipe_ingredients__ingredient=ing)
                .distinct()
                .prefetch_related(
                    Prefetch(
                        "recipe_ingredients",
                        queryset=RecipeIngredient.objects.select_related("ingredient"),
                    )
                )
            )

            rows = []
            for recipe in recipes:
                considered = [
                    ri for ri in recipe.recipe_ingredients.all()
                    if ri.ingredient and not ri.ingredient.common
                ]

                total = len(considered)
                matched = sum(
                    1 for ri in considered
                    if ri.ingredient_id in user_ingredient_ids
                )

                # ถ้า recipe นี้ใช้วัตถุดิบหลัก แต่ user ไม่มีเลย → ข้าม
                if total > 0 and matched == 0:
                    continue

                missing = total - matched
                match_percentage = (
                    100.0 if total == 0
                    else round((matched / total) * 100, 2)
                )

                missing_names = [
                    ri.ingredient.name
                    for ri in considered
                    if ri.ingredient_id not in user_ingredient_ids
                ]

                rows.append({
                    "recipe_name": recipe.title,
                    "required_ingredient": ingredient_name,
                    "match_percentage": match_percentage,
                    "missing_ingredient_count": missing,
                    "missing_ingredients": missing_names,
                })

            rows.sort(
                key=lambda r: (
                    -r["match_percentage"],
                    r["missing_ingredient_count"],
                )
            )

            return {
                "status": "ok",
                "ingredient": ingredient_name,
                "results": rows[:limit],
            }

        return await _get()
    @function_tool
    async def list_expiring_soon(days: int = 3):
        today = date.today()

        @sync_to_async
        def _get():
            qs = (
                UserStock.objects
                .filter(
                    user=user,
                    disable=False,
                    expiration_date__lte=today + timedelta(days=days),
                )
                .select_related("ingredient")
                .order_by("expiration_date")
            )
            return [
                {"ingredient": s.ingredient.name, "expiration_date": str(s.expiration_date)}
                for s in qs
            ]

        items = await _get()
        return {"days": days, "items": items}
    @function_tool
    async def clear_expired_ingredients():
        today = date.today()

        @sync_to_async
        def _clear():
            qs = UserStock.objects.filter(
                user=user,
                disable=True
            )
            count = qs.count()
            qs.delete()
            return count

        removed = await _clear()
        return {"removed": removed}
    @function_tool
    async def list_priority_ingredients(limit: int = 3):
        """
        คืนวัตถุดิบที่ควรใช้ก่อน (วันหมดอายุใกล้สุด)
        """

        @sync_to_async
        def _get():
            qs = (
                UserStock.objects
                .filter(user=user,
                        disable=False,)
                .select_related("ingredient")
                .order_by("expiration_date")[:limit]
            )

            return [
                {
                    "ingredient": s.ingredient.name,
                    "expiration_date": str(s.expiration_date),
                }
                for s in qs
            ]

        items = await _get()

        return {
            "count": len(items),
            "items": items,
        }

    @function_tool
    async def resolve_ingredient_vector(text: str):
        client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        resp = await client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[text],
        )
        qv = resp.data[0].embedding

        scored = [
            (name, cosine_similarity(qv, vec))
            for name, vec in INGREDIENT_EMBEDDINGS.items()
        ]

        scored.sort(key=lambda x: x[1], reverse=True)
        top = scored[:3]

        BEST_THRESHOLD = 0.92

        best_name, best_score = top[0]

        if best_score >= BEST_THRESHOLD:
            return {
                "status": "resolved",
                "item_name": best_name,
                "score": round(best_score, 3),
            }

        return {
            "status": "ambiguous",
            "candidates": [
                {"name": n, "score": round(s, 3)} for n, s in top
            ],
        }

    @function_tool
    async def add_ingredient(item_name: str, expiration_date: Optional[str]):
        @sync_to_async
        def _add():
            ing = Ingredient.objects.filter(name=item_name).first()

            if not ing:
                return {
                    "status": "not_found",
                    "item_name": item_name,
                }

            if expiration_date is None:
                return {
                    "status": "need_expiry",
                    "item_name": item_name,
                }

            exists = UserStock.objects.filter(
                user=user,
                ingredient=ing,
                expiration_date=expiration_date,
            ).exists()

            if exists:
                return {
                    "status": "exists",
                    "item_name": item_name,
                    "expiration_date": expiration_date,
                }

            UserStock.objects.create(
                user=user,
                ingredient=ing,
                expiration_date=expiration_date,
            )

            return {
                "status": "added",
                "item_name": item_name,
                "expiration_date": expiration_date,
            }

        return await _add()



    @function_tool
    async def list_stock_expiry(item_name: str):
        @sync_to_async
        def _get():
            return list(
                UserStock.objects.filter(
                    user=user,
                    ingredient__name=item_name,
                ).values_list("expiration_date", flat=True)
            )
        dates = await _get()
        return {"expiries": [str(d) for d in dates]}

    @function_tool
    async def remove_ingredient(item_name: str, expiration_date: Optional[str]):
        @sync_to_async
        def _remove():
            qs = UserStock.objects.filter(
                user=user,
                ingredient__name=item_name,
            )
            if expiration_date:
                qs = qs.filter(expiration_date=expiration_date)
            qs.delete()
        await _remove()
        return {"status": "removed"}

    # ======================================================
    # SYSTEM PROMPT
    # ======================================================
    today_str = date.today().strftime("%Y-%m-%d")
    print("🧠 Initializing system prompt finish function...")
    print("📜 Setting up system prompt...")
    # chat_ctx = llm.ChatContext()
    print("📜 openai.ChatContext()...")

    # SYSTEM_BASE = (
    #     f"วันนี้คือวันที่ {today_str}\n"
    #     "คุณคือ AI ผู้ช่วยจัดการวัตถุดิบในครัว\n"
    #     "กฎ:\n"
    #     "- เพิ่ม/ลบได้ทีละ 1 รายการ\n"
    #     "- ถ้าเพิ่มแต่ไม่รู้วันหมดอายุ ต้องถามก่อน\n"
    #     "- ถ้าจะ add_ingredient ให้เรียก resolve_ingredient_vector ก่อนทุกครั้ง\n"
    #     "- ถ้าลบ ต้องเรียก list_stock_expiry ก่อน\n"
    #     "- ถ้ามีหลายวันหมดอายุ ต้องถามให้ user เลือก\n"
    #     "- ถ้า add_ingredient คืน status = exists ให้ตอบว่า "
    #     "วัตถุดิบนี้มีอยู่แล้วในสต็อก และห้ามบอกว่าเพิ่มสำเร็จ\n"
    #     "- ระบบเก็บวันที่เป็น ค.ศ. (YYYY-MM-DD)\n"
    #     "- หากผู้ใช้พูดปี พ.ศ. ให้แปลงเป็น ค.ศ. ก่อนเรียกเครื่องมือ\n"
    #     "- เวลาตอบผู้ใช้ ให้แสดงวันที่เป็น ค.ศ.\n"
    #     "- ตอบเป็นภาษาไทย\n"
    #     "- หากผู้ใช้ถามว่า ควรใช้วัตถุดิบไหนก่อน / อะไรใกล้หมดอายุ / ควรทำอะไรก่อน\n"
    #     "  ให้เรียก list_priority_ingredients\n"
    #     "- ห้ามเดาเองโดยไม่เรียกเครื่องมือ\n"
    #     "- หลังได้ผลลัพธ์ ให้สรุปเป็นภาษาไทยแบบเข้าใจง่าย\n"
    # )
    SYSTEM_BASE = (
        f"วันนี้คือวันที่ {today_str}\n"
        "คุณคือ AI เชฟผู้ช่วยจัดการวัตถุดิบและแนะนำเมนูอาหาร (Kitchen Assistant)\n"
        "หน้าที่ของคุณคือการจัดการสต็อกและแนะนำการทำอาหารตามวัตถุดิบที่มี\n\n"
        "กฎการเลือกใช้เครื่องมือ (Tool Usage Rules):\n"
        "1. **การเพิ่มวัตถุดิบ (Add):**\n"
        "   - ต้องเรียก `resolve_ingredient_vector` เพื่อตรวจสอบชื่อก่อนเสมอ\n"
        "   - หากสถานะเป็น resolved ถึงจะเรียก `add_ingredient`\n"
        "   - ถ้าผู้ใช้ไม่บอกวันหมดอายุ ต้องถามก่อน ห้ามเดาเอง\n"
        "2. **การลบวัตถุดิบ (Remove):**\n"
        "   - ต้องเรียก `list_stock_expiry` ก่อนเพื่อดูว่ามีของจริงไหม\n"
        "   - จากนั้นจึงเรียก `remove_ingredient` ตามวันที่ที่ระบุ\n"
        "3. **การตรวจสอบและแจ้งเตือน (Check/List):**\n"
        "   - ถามว่า 'มีอะไรต้องรีบใช้', 'อะไรจะหมดอายุ', 'ควรใช้อะไรก่อน' -> เรียก `list_priority_ingredients` หรือ `list_expiring_soon`\n"
        "   - สั่งว่า 'เคลียร์ของเสีย', 'ลบของหมดอายุทิ้งให้หมด' -> เรียก `clear_expired_ingredients`\n"
        "4. **การแนะนำเมนูอาหาร (Recipe Recommendation):**\n"
        "   - ถามว่า 'ทำอะไรกินดี', 'มีของพวกนี้ทำเมนูอะไรได้บ้าง' -> เรียก `recommend_recipes_for_user`\n\n"
        "5. **การแนะนำเมนูอาหารโดยพูดวัตถุดิบ :**\n"
        "   - ถ้าผู้ใช้ถามว่า 'มี X ทำอะไรได้บ้าง', 'อยากได้เมนูที่มี X' -> เรียก `recommend_recipes_with_ingredient` โดย X คือวัตถุดิบที่พูดถึง\n\n"
        "ข้อปฏิบัติทั่วไป:\n"
        "- ระบบเก็บวันที่แบบ ค.ศ. (YYYY-MM-DD) หากได้ยิน พ.ศ. ให้แปลงเป็น ค.ศ.\n"
        "- ตอบกลับเป็นภาษาไทยที่สุภาพ เป็นธรรมชาติ และเข้าใจง่าย\n"
        "- ห้ามสร้างข้อมูลเท็จ (Hallucination) ให้ตอบตามผลลัพธ์ของเครื่องมือเท่านั้น\n"
    )

    def reset_chat_ctx():
        ctx = llm.ChatContext()
        ctx.add_message(role="system", content=SYSTEM_BASE)
        return ctx
    
    # chat_ctx.add_message(
    #     role="system",
    #     content=(
    #         f"วันนี้คือวันที่ {today_str}\n"
    #         "คุณคือ AI ผู้ช่วยจัดการวัตถุดิบในครัว\n"
    #         "กฎ:\n"
    #         "- เพิ่ม/ลบได้ทีละ 1 รายการ\n"
    #         "- ถ้าเพิ่มแต่ไม่รู้วันหมดอายุ ต้องถามก่อน\n"
    #         "- ถ้าจะ add_ingredient ให้เรียก resolve_ingredient_vector ก่อนทุกครั้ง\n"
    #         "- ถ้าลบ ต้องเรียก list_stock_expiry ก่อน\n"
    #         "- ถ้ามีหลายวันหมดอายุ ต้องถามให้ user เลือก\n"
    #         "- ถ้า add_ingredient คืน status = exists ให้ตอบว่า "
    #         "วัตถุดิบนี้มีอยู่แล้วในสต็อก และห้ามบอกว่าเพิ่มสำเร็จ\n"
    #         "- ระบบเก็บวันที่เป็น ค.ศ. (YYYY-MM-DD)\n"
    #         "- หากผู้ใช้พูดปี พ.ศ. ให้แปลงเป็น ค.ศ. ก่อนเรียกเครื่องมือ\n"
    #         "- เวลาตอบผู้ใช้ ให้แสดงวันที่เป็น ค.ศ.\n"
    #         "- ตอบเป็นภาษาไทย\n"
    #     ),
    # )
    chat_ctx = reset_chat_ctx()

    print("🎧 before voice...")
    # ======================================================
    # AUDIO IN (CORRECT & SAFE)
    # ======================================================
    audio_track = None
    while audio_track is None:
        for pub in participant.track_publications.values(): # สิ่งที่ user “ประกาศว่าจะส่ง”
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
                audio_track = pub.track # สิ่งที่ user “ส่งมา”
                break
        await asyncio.sleep(0.1)

    audio_stream = rtc.AudioStream(audio_track)
    stt_stream = stt_plugin.stream()

    # ======================================================
    # PUSH AUDIO TO STT
    # ======================================================    
    async def push_audio():
        async for e in audio_stream:
            stt_stream.push_frame(e.frame)

    asyncio.create_task(push_audio())



    # ======================================================
    # STT LOOP (IMPORTANT)
    # ======================================================
    async def stt_loop():
        try:
            async for event in stt_stream:
                nonlocal chat_ctx 
                print("🎙 STT EVENT:", event.type)
                if event.type != stt.SpeechEventType.FINAL_TRANSCRIPT:
                    continue

                text = event.alternatives[0].text.strip()
                if not text:
                    continue

                print("🗣 USER:", text)
                await send_ui_message(ctx, "user_text", text)

                chat_ctx.add_message(role="user", content=text)

                TOOLS = {
                    "resolve_ingredient_vector": resolve_ingredient_vector,
                    "add_ingredient": add_ingredient,
                    "list_stock_expiry": list_stock_expiry,
                    "remove_ingredient": remove_ingredient,
                    "list_priority_ingredients": list_priority_ingredients,
                    "recommend_recipes_for_user": recommend_recipes_for_user,
                    "recommend_recipes_with_ingredient": recommend_recipes_with_ingredient,
                    "list_expiring_soon": list_expiring_soon,
                    "clear_expired_ingredients": clear_expired_ingredients,
                }
                while True:
                    print("START WHILE...")
                    try:
                        stream = llm_plugin.chat(
                            chat_ctx=chat_ctx,
                            # tools=[
                            #     resolve_ingredient_vector,
                            #     add_ingredient,
                            #     list_stock_expiry,
                            #     remove_ingredient,
                            # ],
                            tools=list(TOOLS.values()),
                        )

                        tool_calls = []
                        reply_text = ""
                        print(f"🤖 AGENT: {stream}")
                        print("STREAM CREATED")

                        async for chunk in stream:
                            print("⬇️ RAW CHUNK:", chunk)

                            delta = chunk.delta
                            if not delta:
                                continue

                            # ======================================================
                            # PARSE DELTA
                            # ======================================================
                            if delta.tool_calls:
                                print("🛠️ TOOL CALL DELTA:", delta.tool_calls)
                                tool_calls.extend(delta.tool_calls)

                            # 💬 NORMAL TEXT
                            if delta.content:
                                print("💬 DELTA CONTENT:", delta.content)
                                reply_text += delta.content
                        print(f"🤖 AGENTV2: {reply_text} toolcall: {tool_calls}")
                        
                        stop_turn = False
                        reset_after_reply = False
                        if tool_calls:
                            # stop_turn = False
                            # reset_after_reply = False

                            for tc in tool_calls:
                                tool_name = tc.name
                                tool_args = json.loads(tc.arguments or "{}")

                                tool_fn = TOOLS.get(tool_name)
                                if not tool_fn:
                                    print(f"❌ Unknown tool triggered: {tool_name}")
                                    continue # Skip unknown tool

                                # Execute Tool
                                try:
                                    result = await tool_fn(**tool_args)
                                    print(f"⚙️ TOOL EXECUTED: {tool_name} -> {result}")
                                except Exception as e:
                                    result = {"error": str(e)}
                                
                                # ส่งผลลัพธ์กลับให้ LLM รู้ (User ไม่เห็นอันนี้)
                                chat_ctx.add_message(
                                    role="assistant",
                                    id=tc.call_id,
                                    content=json.dumps(result, ensure_ascii=False),
                                )

                                # =========================================================
                                # 🧠 HANDLE TOOL RESULTS (INSTRUCTION TO LLM)
                                # =========================================================

                                # 1. RESOLVE INGREDIENT (ค้นหาชื่อ)
                                if tool_name == "resolve_ingredient_vector":
                                    if result["status"] == "ambiguous":
                                        choices = "\n".join([f"- {c['name']}" for c in result["candidates"]])
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"ชื่อไม่ชัดเจน ให้ถามผู้ใช้ว่าหมายถึงอันไหน:\n{choices}\nตอบเป็นภาษาไทย ห้ามเรียกเครื่องมือซ้ำ"
                                        )
                                        stop_turn = True
                                    elif result["status"] == "resolved":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"เจอวัตถุดิบคือ '{result['item_name']}' แล้ว\nถามวันหมดอายุต่อ (ถ้ายังไม่รู้) หรือดำเนินการเพิ่มถ้าข้อมูลครบ"
                                        )
                                        # ไม่ stop_turn ปล่อยให้ LLM ตัดสินใจต่อ (เช่นเรียก add_ingredient ทันทีถ้า user บอกวันมาแล้ว)

                                # 2. ADD INGREDIENT (เพิ่มของ)
                                elif tool_name == "add_ingredient":
                                    status = result.get("status")
                                    if status == "need_expiry":
                                        chat_ctx.add_message(
                                            role="system",
                                            content="ขาดวันหมดอายุ ถามผู้ใช้ว่าหมดอายุวันไหน (ตอบไทยสุภาพ)"
                                        )
                                        stop_turn = True
                                    elif status == "exists":
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: วัตถุดิบนี้ล็อตวันหมดอายุนี้ มีในระบบอยู่แล้ว ไม่ได้เพิ่มซ้ำ"
                                        )
                                        stop_turn = True
                                    elif status == "added":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"แจ้งผู้ใช้ว่า: เพิ่ม {result['item_name']} (หมดอายุ {result['expiration_date']}) เรียบร้อยแล้ว"
                                        )
                                        stop_turn = True
                                        reset_after_reply = True # จบงานแล้ว เคลียร์ context ได้
                                    elif status == "not_found":
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: ไม่พบชื่อวัตถุดิบนี้ในฐานข้อมูลหลัก"
                                        )
                                        stop_turn = True

                                # 3. LIST STOCK EXPIRY (เช็คก่อนลบ)
                                elif tool_name == "list_stock_expiry":
                                    expiries = result.get("expiries", [])
                                    if not expiries:
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: ไม่พบวัตถุดิบนี้ในสต็อกเลย"
                                        )
                                        stop_turn = True
                                    elif len(expiries) > 1:
                                        dates = ", ".join(expiries)
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"พบหลายวันหมดอายุ ({dates}) ถามผู้ใช้ว่าจะลบอันไหน"
                                        )
                                        stop_turn = True
                                    # ถ้ามี 1 อัน LLM มักจะฉลาดพอที่จะเรียก remove ต่อเอง หรือถามยืนยัน

                                # 4. REMOVE INGREDIENT (ลบของ)
                                elif tool_name == "remove_ingredient":
                                    chat_ctx.add_message(
                                        role="system",
                                        content="แจ้งผู้ใช้ว่า: ลบวัตถุดิบออกจากสต็อกเรียบร้อยแล้ว"
                                    )
                                    stop_turn = True
                                    reset_after_reply = True

                                # 5. LIST PRIORITY / EXPIRING SOON (แนะนำของต้องรีบใช้)
                                elif tool_name in ["list_priority_ingredients", "list_expiring_soon"]:
                                    items = result.get("items", [])
                                    if not items:
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: ไม่มีวัตถุดิบที่ใกล้หมดอายุในช่วงนี้ สต็อกปลอดภัยดี"
                                        )
                                    else:
                                        lines = "\n".join([f"- {i['ingredient']} (หมดอายุ {i['expiration_date']})" for i in items])
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"สรุปรายการวัตถุดิบที่ต้องรีบใช้ให้ผู้ใช้ฟัง:\n{lines}\nตอบเป็นภาษาไทย แนะนำว่าควรทำเมนูง่ายๆ หรือรีบใช้ก่อนเสีย"
                                        )
                                    stop_turn = True

                                # 6. RECOMMEND RECIPES (แนะนำเมนู) [NEW]
                                elif tool_name == "list_recommend_recipes":
                                    recipes = result.get("results", [])
                                    count = result.get("count", 0)
                                    
                                    if count == 0:
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: จากวัตถุดิบที่มี ยังไม่พอสำหรับทำเมนูแนะนำในระบบ ลองซื้อของเพิ่มไหม"
                                        )
                                    else:
                                        # สร้าง text สรุปเมนู
                                        rec_text = ""
                                        for r in recipes:
                                            missing_txt = ""
                                            if r['missing_ingredient_count'] > 0:
                                                missing_txt = f"(ขาด: {', '.join(r['missing_ingredients'])})"
                                            rec_text += f"- เมนู {r['recipe_name']} (ตรง {r['match_percentage']}%) {missing_txt}\n"
                                        
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"แนะนำเมนูที่ทำได้จากของในตู้เย็น:\n{rec_text}\nเชียร์ให้ผู้ใช้ลองทำเมนูที่เปอร์เซ็นต์ตรงกันสูงที่สุด"
                                        )
                                    stop_turn = True
                                elif tool_name == "recommend_recipes_with_ingredient":
                                    status = result.get("status")
                                    ingredient = result.get("ingredient")
                                    recipes = result.get("results", [])

                                    if status == "ingredient_not_found":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"แจ้งผู้ใช้ว่า: ไม่พบวัตถุดิบชื่อ '{ingredient}' ในระบบ"
                                        )
                                        stop_turn = True

                                    elif not recipes:
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                f"แจ้งผู้ใช้ว่า: "
                                                f"ยังไม่มีเมนูที่ใช้ '{ingredient}' "
                                                f"และสามารถทำได้จากวัตถุดิบที่มีในตอนนี้"
                                            )
                                        )
                                        stop_turn = True

                                    else:
                                        rec_text = ""
                                        for r in recipes:
                                            missing_txt = ""
                                            if r["missing_ingredient_count"] > 0:
                                                missing_txt = f"(ขาด: {', '.join(r['missing_ingredients'])})"

                                            rec_text += (
                                                f"- เมนู {r['recipe_name']} "
                                                f"(ตรง {r['match_percentage']}%) {missing_txt}\n"
                                            )

                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                f"แนะนำเมนูที่ต้องมีวัตถุดิบ '{ingredient}':\n"
                                                f"{rec_text}"
                                                "อธิบายกับผู้ใช้ว่าแนะนำเพราะมีวัตถุดิบนี้ "
                                                "และเลือกเมนูที่เปอร์เซ็นต์ตรงสูงสุดก่อน"
                                            )
                                        )
                                        stop_turn = True

                                # 7. CLEAR EXPIRED (เคลียร์ของเสีย) [NEW]
                                elif tool_name == "clear_expired_ingredients":
                                    removed_count = result.get("removed", 0)
                                    if removed_count == 0:
                                        chat_ctx.add_message(
                                            role="system",
                                            content="แจ้งผู้ใช้ว่า: ไม่มีของหมดอายุให้เคลียร์ ตู้เย็นสะอาดดีแล้ว"
                                        )
                                    else:
                                        chat_ctx.add_message(
                                            role="system",
                                            content=f"แจ้งผู้ใช้ว่า: กำจัดของหมดอายุออกไปให้แล้วจำนวน {removed_count} รายการ"
                                        )
                                    stop_turn = True
                                    reset_after_reply = True

                            # จบ Loop ของ tool_calls
                            if stop_turn:
                                continue 
                            
                            # ถ้า Loop จบแล้วแต่ stop_turn ยังเป็น False แปลว่า LLM อยากเรียก tool ต่อเนื่อง
                            # (เช่น resolve -> add ใน turn เดียวกัน) ก็ปล่อยให้วน while loop ใหญ่ต่อไป
                            continue

                        if reply_text:
                            print("🤖 FINAL ANSWER:", reply_text)
                            chat_ctx.add_message(role="assistant", content=reply_text) # ทำให้ LLM “จำได้” ว่ามันพูดอะไรไปแล้ว
                            await send_ui_message(ctx, "agent_text", reply_text)
                            audio = tts_plugin.synthesize(reply_text) # ใช้ TTS สังเคราะห์เสียง
                            async for a in audio: # ส่งเสียงทีละเฟรม
                                await source.capture_frame(a.frame)
                            if reset_after_reply:
                                chat_ctx = reset_chat_ctx() # รีเซ็ต context หลังตอบ
                            break
                        print("⚠️ LLM returned nothing, stopping")
                        break
                    except Exception as e:
                        print("❌ LLM LOOP CRASH:", repr(e))
                        import traceback; traceback.print_exc()
                        break
                    
        except Exception as e:
            print("🔴 STT ERROR:", e)
            import traceback; traceback.print_exc()

    # 🔥 START LOOP
    asyncio.create_task(stt_loop())

    print("🟢 Agent alive, waiting for disconnect")
    await ctx.wait_for_disconnect()

# ==========================================================
# DJANGO COMMAND
# ==========================================================
class Command(BaseCommand):
    help = "Run LiveKit Voice Agent"

    def handle(self, *args, **options):
        sys.argv = ["livekit-worker", "start"]
        cli.run_app(
            WorkerOptions(entrypoint_fnc=entrypoint)
        )
