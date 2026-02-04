# ==========================================================
# IMPORTS
# ==========================================================
import asyncio
import json
import os
import sys
import math
from typing import List, Dict, Optional
from datetime import date

# ================= Django =================
import django
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from asgiref.sync import sync_to_async

# ================= LiveKit =================
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

    from recipes.models import Ingredient, UserStock
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
    async def list_priority_ingredients(limit: int = 3):
        """
        คืนวัตถุดิบที่ควรใช้ก่อน (วันหมดอายุใกล้สุด)
        """

        @sync_to_async
        def _get():
            qs = (
                UserStock.objects
                .filter(user=user)
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

    SYSTEM_BASE = (
        f"วันนี้คือวันที่ {today_str}\n"
        "คุณคือ AI ผู้ช่วยจัดการวัตถุดิบในครัว\n"
        "กฎ:\n"
        "- เพิ่ม/ลบได้ทีละ 1 รายการ\n"
        "- ถ้าเพิ่มแต่ไม่รู้วันหมดอายุ ต้องถามก่อน\n"
        "- ถ้าจะ add_ingredient ให้เรียก resolve_ingredient_vector ก่อนทุกครั้ง\n"
        "- ถ้าลบ ต้องเรียก list_stock_expiry ก่อน\n"
        "- ถ้ามีหลายวันหมดอายุ ต้องถามให้ user เลือก\n"
        "- ถ้า add_ingredient คืน status = exists ให้ตอบว่า "
        "วัตถุดิบนี้มีอยู่แล้วในสต็อก และห้ามบอกว่าเพิ่มสำเร็จ\n"
        "- ระบบเก็บวันที่เป็น ค.ศ. (YYYY-MM-DD)\n"
        "- หากผู้ใช้พูดปี พ.ศ. ให้แปลงเป็น ค.ศ. ก่อนเรียกเครื่องมือ\n"
        "- เวลาตอบผู้ใช้ ให้แสดงวันที่เป็น ค.ศ.\n"
        "- ตอบเป็นภาษาไทย\n"
        "- หากผู้ใช้ถามว่า ควรใช้วัตถุดิบไหนก่อน / อะไรใกล้หมดอายุ / ควรทำอะไรก่อน\n"
        "  ให้เรียก list_priority_ingredients\n"
        "- ห้ามเดาเองโดยไม่เรียกเครื่องมือ\n"
        "- หลังได้ผลลัพธ์ ให้สรุปเป็นภาษาไทยแบบเข้าใจง่าย\n"
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
                        
                        # if tool_calls:
                        #     stop_after_tool = False
                        #     for tc in tool_calls:
                        #         print(f"⚙️ TOOL CALL: {tc}")
                        #         tool_name = tc.name
                        #         tool_args = json.loads(tc.arguments or "{}")

                        #         print(f"⚙️ EXEC TOOL: {tool_name} args={tool_args}")
                        #         # result = await tc.execute()
                        #         tool_fn = TOOLS.get(tool_name)
                        #         if not tool_fn:
                        #             raise RuntimeError(f"Unknown tool: {tool_name}")

                        #         result = await tool_fn(**tool_args)
                        #         print(f"⚙️ TOOL RESULT: {result}")

                        #         chat_ctx.add_message(
                        #             role="assistant",
                        #             id=tc.call_id,
                        #             content=json.dumps(result, ensure_ascii=False),
                        #         )
                        #         if tool_name == "resolve_ingredient_vector":
                        #             if result["status"] == "ambiguous":
                        #                 choices = "\n".join(
                        #                     [f"- {c['name']} (ความใกล้เคียง {c['score']})"
                        #                     for c in result["candidates"]]
                        #                 )

                        #                 chat_ctx.add_message(
                        #                     role="system",
                        #                     content=(
                        #                         "ชื่อวัตถุดิบยังไม่ชัดเจน\n"
                        #                         "กรุณาถามผู้ใช้ให้เลือกจากตัวเลือกด้านล่าง "
                        #                         "หรือพูดชื่อใหม่ให้ชัดเจน\n\n"
                        #                         f"{choices}\n\n"
                        #                         "ตอบเป็นภาษาไทยแบบเป็นธรรมชาติ "
                        #                         "และห้ามเรียกเครื่องมือใด ๆ"
                        #                     ),
                        #                 )
                        #                 continue
                        #         if tool_name == "add_ingredient" and result.get("status") == "added":
                        #             stop_after_tool = True
                        #     # chat_ctx.add_message(
                        #     #     role="system",
                        #     #     content=(
                        #     #         "เครื่องมือได้ถูกเรียกใช้งานเรียบร้อยแล้ว "
                        #     #         "โปรดสรุปคำตอบให้ผู้ใช้เป็นภาษาไทย "
                        #     #         "และห้ามเรียกเครื่องมือซ้ำ"
                        #     #     ),
                        #     # )
                        #     # chat_ctx.add_message(
                        #     #     role="system",
                        #     #     content=(
                        #     #         "การดำเนินการนี้เสร็จสมบูรณ์แล้ว "
                        #     #         "ห้ามใช้ข้อมูลวัตถุดิบหรือวันหมดอายุจากข้อความก่อนหน้านี้อีก "
                        #     #         "หากผู้ใช้พูดต่อ ให้ถือว่าเป็นคำสั่งใหม่"
                        #     #     ),
                        #     # )

                        #     # # ✅ ให้ LLM สรุปคำตอบครั้งสุดท้าย
                        #     # chat_ctx.add_message(
                        #     #     role="system",
                        #     #     content=(
                        #     #         "โปรดตอบผู้ใช้เป็นภาษาไทยตามผลลัพธ์ของเครื่องมือด้านบน "
                        #     #         "และห้ามเรียกเครื่องมือซ้ำ"
                        #     #     ),
                        #     # )
                        #     if stop_after_tool:
                        #         # ให้ LLM สรุป “ครั้งเดียว” แล้วจบ turn
                        #         chat_ctx.add_message(
                        #             role="system",
                        #             content=(
                        #                 "การเพิ่มวัตถุดิบเสร็จสมบูรณ์แล้ว "
                        #                 "โปรดตอบสรุปให้ผู้ใช้เป็นภาษาไทย "
                        #                 "และห้ามเรียกเครื่องมือใด ๆ อีก"
                        #             ),
                        #         )
                        #         # ❗ สำคัญ: continue ไม่ใช่ break
                        #         continue
                        #     continue
                            # break
                        if tool_calls:
                            stop_turn = False  # ใช้ปิด loop อย่างถูกต้อง
                            reset_after_reply = False

                            for tc in tool_calls:
                                tool_name = tc.name
                                tool_args = json.loads(tc.arguments or "{}")

                                tool_fn = TOOLS.get(tool_name)
                                if not tool_fn:
                                    raise RuntimeError(f"Unknown tool: {tool_name}")

                                result = await tool_fn(**tool_args)
                                print(f"⚙️ TOOL!!!!!!! {tool_name}: {result}")

                                # ⛔ สำคัญ: tool result ใช้ "ให้ LLM อ่าน" ไม่ใช่ให้ user เห็น
                                chat_ctx.add_message(
                                    role="assistant",
                                    id=tc.call_id,
                                    content=json.dumps(result, ensure_ascii=False),
                                )

                                # ===============================
                                # 🧠 HANDLE EACH TOOL EXPLICITLY
                                # ===============================

                                # ---------- resolve_ingredient_vector ----------
                                if tool_name == "resolve_ingredient_vector":
                                    if result["status"] == "ambiguous":
                                        choices = "\n".join(
                                            [f"- {c['name']} (ความใกล้เคียง {c['score']})"
                                            for c in result["candidates"]]
                                        )

                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ชื่อวัตถุดิบยังไม่ชัดเจน\n"
                                                "กรุณาถามผู้ใช้ให้เลือกจากตัวเลือกด้านล่าง "
                                                "หรือพูดชื่อใหม่ให้ชัดเจน\n\n"
                                                f"{choices}\n\n"
                                                "ตอบเป็นภาษาไทยแบบเป็นธรรมชาติ \n"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    elif result["status"] == "resolved":
                                        # ปล่อยให้ LLM เดินต่อ (เช่นไปถามวันหมดอายุ)
                                        # pass
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                f"วัตถุดิบคือ {result['item_name']} แน่นอนแล้ว\n"
                                                "ขั้นตอนถัดไป:\n"
                                                "- หากยังไม่ทราบวันหมดอายุ ให้ถามผู้ใช้ก่อน\n"
                                                "- ห้ามสรุปว่ามีหรือไม่มีในสต็อก\n"
                                                "- ห้ามบอกว่ามีอยู่แล้ว\n"
                                                "- ห้ามเรียกเครื่องมือใด ๆ\n"
                                                "- ตอบเป็นภาษาไทยแบบสุภาพและเป็นธรรมชาติ\n"
                                            ),
                                        )
                                        stop_turn = True

                                # ---------- add_ingredient ----------
                                elif tool_name == "add_ingredient":
                                    status = result.get("status")

                                    if status == "need_expiry":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ยังไม่ทราบวันหมดอายุของวัตถุดิบนี้ \n"
                                                "โปรดถามผู้ใช้ว่าวันหมดอายุคือวันไหน \n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด \nๆ"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    elif status == "exists":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "วัตถุดิบนี้มีอยู่ในสต็อกแล้ว \n"
                                                "โดยมีวันหมดอายุเดียวกัน \n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                                "และห้ามแสดง JSON หรือเรียกเครื่องมือ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    elif status == "added":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "เพิ่มวัตถุดิบเรียบร้อยแล้ว \n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด ๆ อีก\n"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True
                                        reset_after_reply = True

                                    elif status == "not_found":
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ไม่พบวัตถุดิบนี้ในระบบ \n"
                                                "โปรดขอให้ผู้ใช้พูดชื่อใหม่ให้ชัดเจน \n"
                                                "หรือเสนอชื่อที่ใกล้เคียง \n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                # ---------- list_stock_expiry ----------
                                elif tool_name == "list_stock_expiry":
                                    expiries = result.get("expiries", [])

                                    if not expiries:
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ไม่พบวัตถุดิบนี้ในสต็อก \n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    elif len(expiries) > 1:
                                        dates = "\n".join([f"- {d}" for d in expiries])
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "พบวัตถุดิบนี้หลายวันหมดอายุ\n"
                                                "กรุณาถามผู้ใช้ให้เลือกวันหมดอายุที่ต้องการ\n\n"
                                                f"{dates}\n\n"
                                                "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                                "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    # ถ้ามีวันเดียว ปล่อยให้ LLM เดินต่อไปลบ

                                # ---------- remove_ingredient ----------
                                elif tool_name == "remove_ingredient":
                                    chat_ctx.add_message(
                                        role="system",
                                        content=(
                                            "ลบวัตถุดิบเรียบร้อยแล้ว \n"
                                            "ตอบเป็นภาษาไทยแบบสุภาพ \n"
                                            "และห้ามเรียกเครื่องมือใด ๆ อีก\n"
                                            "ห้ามแสดง JSON และห้ามเรียกเครื่องมือใด ๆ\n"
                                        ),
                                    )
                                    stop_turn = True
                                elif tool_name == "list_priority_ingredients":
                                    items = result.get("items", [])

                                    if not items:
                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ขณะนี้ไม่มีวัตถุดิบในสต็อก\n"
                                                "ตอบผู้ใช้เป็นภาษาไทยแบบสุภาพ\n"
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True

                                    else:
                                        lines = "\n".join(
                                            [f"- {i['ingredient']} (หมดอายุ {i['expiration_date']})" for i in items]
                                        )

                                        chat_ctx.add_message(
                                            role="system",
                                            content=(
                                                "ต่อไปนี้คือวัตถุดิบที่ควรใช้ก่อน (เรียงตามวันหมดอายุใกล้สุด):\n\n"
                                                f"{lines}\n\n"
                                                "โปรดอธิบายให้ผู้ใช้เข้าใจง่าย "
                                                "เช่น แนะนำให้ใช้ตัวไหนก่อน "
                                                "และห้ามเรียกเครื่องมือใด ๆ\n"
                                            ),
                                        )
                                        stop_turn = True


                            # ⛔ ปิด while-loop อย่างถูกต้อง
                            if stop_turn:
                                continue
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
