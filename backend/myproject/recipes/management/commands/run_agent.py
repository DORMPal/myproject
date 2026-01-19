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
async def entrypoint(ctx: JobContext):
    # ---------------- Django ----------------
    print("🚀 Setting up Django...")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_project.settings")
    django.setup()

    from recipes.models import Ingredient, UserStock
    User = get_user_model()

    # ---------------- Connect ----------------
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    user = await sync_to_async(User.objects.get)(email=participant.identity)

    print("👤 USER:", user.email)

    # ---------------- Plugins ----------------
    stt_plugin = deepgram.STT(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        language="th-TH",
        model="nova-2",
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
    source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent", source)
    await ctx.room.local_participant.publish_track(track)

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

        top3 = sorted(scored, key=lambda x: x[1], reverse=True)[:3]
        return {
            "candidates": [{"name": n, "score": round(s, 3)} for n, s in top3]
        }

    @function_tool
    async def add_ingredient(item_name: str, expiration_date: Optional[str]):
        @sync_to_async
        def _add():
            ing = Ingredient.objects.get(name=item_name)

            exists = UserStock.objects.filter(
                user=user,
                ingredient=ing,
                expiration_date=expiration_date,
            ).exists()

            if exists:
                return "already_exists"

            UserStock.objects.create(
                user=user,
                ingredient=ing,
                expiration_date=expiration_date,
            )
            return "added"

        result = await _add()
        # STATE["mode"] = "idle"
        # STATE["pending_item"] = None
        # STATE["pending_expiry"] = None
        # STATE["candidates"] = []

        if result == "already_exists":
            return {
                "status": "exists",
                "item_name": item_name,
                "expiration_date": expiration_date,
            }

        return {
            "status": "added",
            "item_name": item_name,
            "expiration_date": expiration_date,
        }


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
    chat_ctx = llm.ChatContext()
    print("📜 openai.ChatContext()...")
    chat_ctx.add_message(
        role="system",
        content=(
            f"วันนี้คือวันที่ {today_str}\n"
            "คุณคือ AI ผู้ช่วยจัดการวัตถุดิบในครัว\n"
            "กฎ:\n"
            "- เพิ่ม/ลบได้ทีละ 1 รายการ\n"
            "- ถ้าเพิ่มแต่ไม่รู้วันหมดอายุ ต้องถามก่อน\n"
            "- ถ้าชื่อไม่ชัด ให้เรียก resolve_ingredient_vector\n"
            "- ถ้าลบ ต้องเรียก list_stock_expiry ก่อน\n"
            "- ถ้ามีหลายวันหมดอายุ ต้องถามให้ user เลือก\n"
            "- ถ้า add_ingredient คืน status = exists ให้ตอบว่า "
            "วัตถุดิบนี้มีอยู่แล้วในสต็อก และห้ามบอกว่าเพิ่มสำเร็จ\n"
            "- ตอบเป็นภาษาไทย\n"
        ),
    )

    # ======================================================
    # AUDIO IN
    # ======================================================
    print("🎧 before voice...")
    # ======================================================
    # AUDIO IN (CORRECT & SAFE)
    # ======================================================
    audio_track = None
    while audio_track is None:
        for pub in participant.track_publications.values():
            if pub.kind == rtc.TrackKind.KIND_AUDIO and pub.track:
                audio_track = pub.track
                break
        await asyncio.sleep(0.1)

    audio_stream = rtc.AudioStream(audio_track)
    stt_stream = stt_plugin.stream()

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

                            # 🛠️ TOOL CALLS
                            if delta.tool_calls:
                                print("🛠️ TOOL CALL DELTA:", delta.tool_calls)
                                tool_calls.extend(delta.tool_calls)

                            # 💬 NORMAL TEXT
                            if delta.content:
                                print("💬 DELTA CONTENT:", delta.content)
                                reply_text += delta.content
                        print(f"🤖 AGENTV2: {reply_text} toolcall: {tool_calls}")
                        
                        if tool_calls:
                            for tc in tool_calls:
                                print(f"⚙️ TOOL CALL: {tc}")
                                tool_name = tc.name
                                tool_args = json.loads(tc.arguments or "{}")

                                print(f"⚙️ EXEC TOOL: {tool_name} args={tool_args}")
                                # result = await tc.execute()
                                tool_fn = TOOLS.get(tool_name)
                                if not tool_fn:
                                    raise RuntimeError(f"Unknown tool: {tool_name}")

                                result = await tool_fn(**tool_args)
                                print(f"⚙️ TOOL RESULT: {result}")

                                chat_ctx.add_message(
                                    role="assistant",
                                    id=tc.call_id,
                                    content=json.dumps(result, ensure_ascii=False),
                                )
                            # chat_ctx.add_message(
                            #     role="system",
                            #     content=(
                            #         "เครื่องมือได้ถูกเรียกใช้งานเรียบร้อยแล้ว "
                            #         "โปรดสรุปคำตอบให้ผู้ใช้เป็นภาษาไทย "
                            #         "และห้ามเรียกเครื่องมือซ้ำ"
                            #     ),
                            # )
                            chat_ctx.add_message(
                                role="system",
                                content=(
                                    "การดำเนินการนี้เสร็จสมบูรณ์แล้ว "
                                    "ห้ามใช้ข้อมูลวัตถุดิบหรือวันหมดอายุจากข้อความก่อนหน้านี้อีก "
                                    "หากผู้ใช้พูดต่อ ให้ถือว่าเป็นคำสั่งใหม่"
                                ),
                            )

                            # ✅ ให้ LLM สรุปคำตอบครั้งสุดท้าย
                            chat_ctx.add_message(
                                role="system",
                                content=(
                                    "โปรดตอบผู้ใช้เป็นภาษาไทยตามผลลัพธ์ของเครื่องมือด้านบน "
                                    "และห้ามเรียกเครื่องมือซ้ำ"
                                ),
                            )
                            continue
                            # break

                        if reply_text:
                            print("🤖 FINAL ANSWER:", reply_text)
                            chat_ctx.add_message(role="assistant", content=reply_text)
                            await send_ui_message(ctx, "agent_text", reply_text)
                            audio = tts_plugin.synthesize(reply_text)
                            async for a in audio:
                                await source.capture_frame(a.frame)
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
