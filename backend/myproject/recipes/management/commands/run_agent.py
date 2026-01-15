import asyncio
import logging
import os
import sys
import re
from datetime import date, timedelta

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
)
from livekit.agents.llm import function_tool

# ================= Plugins =================
from livekit.plugins import openai, deepgram
from thefuzz import process

# ==========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

# ==========================================================
# NORMALIZATION / NLP HELPERS
# ==========================================================
CONFIRM_WORDS = [
    "ใช่", "ใช่ครับ", "ใช่ค่ะ", "โอเค", "ตกลง", "ได้", "เอาเลย",
    "ครับ", "ค่ะ", "โอเคครับ", "โอเคค่ะ"
]

NEGATE_WORDS = [
    "ไม่", "ไม่เอา", "ไม่ต้อง", "ยกเลิก", "ไม่ใช่"
]

ADD_KEYWORDS = ["เพิ่ม", "ซื้อ", "เอา"]
REMOVE_KEYWORDS = ["ลบ", "ทิ้ง", "เอาออก"]

def normalize(text: str) -> str:
    return re.sub(r"\s+", "", text.lower())

def is_confirm(text: str) -> bool:
    t = normalize(text)
    return any(normalize(w) in t for w in CONFIRM_WORDS)

def is_negate(text: str) -> bool:
    t = normalize(text)
    return any(normalize(w) in t for w in NEGATE_WORDS)

# ==========================================================
# DATE PARSER (THAI)
# ==========================================================
def parse_thai_date(text: str) -> date | None:
    today = date.today()
    t = text

    if "พรุ่งนี้" in t:
        return today + timedelta(days=1)
    if "มะรืน" in t:
        return today + timedelta(days=2)
    if "อาทิตย์หน้า" in t:
        return today + timedelta(days=7)
    if "สิ้นเดือน" in t:
        return (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    return None

# ==========================================================
# ITEM EXTRACTION
# ==========================================================
def split_items(text: str) -> list[str]:
    text = re.sub(r"(ช่วย|หน่อย|ให้ฉัน|ให้ผม)", "", text)
    text = re.sub(r"(ซื้อ|เพิ่ม|เอา|ลบ|ทิ้ง|เอาออก)", "", text)
    parts = re.split(r"[และ,กับ]", text)
    return [p.strip() for p in parts if p.strip()]

# ==========================================================
# ENTRYPOINT
# ==========================================================
async def entrypoint(ctx: JobContext):
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_project.settings")
    django.setup()

    from recipes.models import Ingredient, UserStock
    User = get_user_model()

    # ---------------- CONNECT ----------------
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()
    db_user = await sync_to_async(User.objects.get)(email=participant.identity)

    # ---------------- PLUGINS ----------------
    stt_plugin = deepgram.STT(
        api_key=os.getenv("DEEPGRAM_API_KEY"),
        language="th",
        model="nova-2",
    )
    tts_plugin = openai.TTS(api_key=os.getenv("OPENAI_API_KEY"))

    # ---------------- AUDIO OUT ----------------
    source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent", source)
    await ctx.room.local_participant.publish_track(track)

    # ---------------- STATE ----------------
    STATE = {
        "mode": "idle",
        "pending_add": [],
        "pending_remove": [],
        "remove_expiry_options": {},
        "awaiting_date_for": None,
    }

    # ======================================================
    # TOOLS
    # ======================================================
    @function_tool(name="add_ingredient")
    async def add_ingredient(item_name: str, expiration_date: date | None = None) -> str:
        @sync_to_async
        def _add():
            names = list(Ingredient.objects.filter(common=False).values_list("name", flat=True))
            best, score = process.extractOne(item_name, names)
            if score < 60:
                return f"ไม่พบวัตถุดิบ {item_name}"

            exp = expiration_date or (date.today() + timedelta(days=7))

            UserStock.objects.create(
                user=db_user,
                ingredient=Ingredient.objects.get(name=best),
                expiration_date=exp,
            )
            return f"เพิ่ม {best} (หมดอายุ {exp}) เรียบร้อยแล้ว"

        return await _add()

    @function_tool(name="remove_ingredient")
    async def remove_ingredient(item_name: str, expiration_date: date | None = None) -> str:
        @sync_to_async
        def _remove():
            qs = UserStock.objects.filter(user=db_user, ingredient__name=item_name)
            if expiration_date:
                qs = qs.filter(expiration_date=expiration_date)
            count = qs.count()
            qs.delete()
            return f"ลบ {item_name} จำนวน {count} รายการแล้ว"

        return await _remove()

    # ======================================================
    # AUDIO IN
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
    # MAIN LOOP
    # ======================================================
    async for event in stt_stream:
        if event.type != stt.SpeechEventType.FINAL_TRANSCRIPT:
            continue

        user_text = event.alternatives[0].text.strip()
        if not user_text:
            continue

        print("\n" + "=" * 60)
        print(f"[USER] 🗣️ {user_text}")
        reply = ""

        # ==================================================
        # CONFIRM / NEGATE HAS PRIORITY
        # ==================================================
        if STATE["mode"].startswith("confirm") and is_confirm(user_text):
            print(f"[INTENT] confirm ({STATE['mode']})")

            if STATE["mode"] == "confirm_add":
                for it in STATE["pending_add"]:
                    result = await add_ingredient(it["name"], it["expiry"])
                    print(f"[TOOL:add] {result}")
                reply = "เพิ่มเรียบร้อยแล้วครับ มีอะไรให้ช่วยอีกไหม"

            elif STATE["mode"] == "confirm_remove":
                for it in STATE["pending_remove"]:
                    expiries = STATE["remove_expiry_options"].get(it, [])
                    if len(expiries) > 1:
                        STATE["mode"] = "ask_expiry_remove"
                        STATE["awaiting_date_for"] = it
                        reply = (
                            f"{it} มีหลายวันหมดอายุ "
                            f"{', '.join(str(d) for d in expiries)} "
                            "ต้องการลบวันไหน หรือพูดว่าลบทั้งหมดครับ"
                        )
                        break
                    else:
                        await remove_ingredient(it, expiries[0] if expiries else None)
                        reply = "ลบเรียบร้อยแล้วครับ"

            STATE.update({
                "mode": "idle",
                "pending_add": [],
                "pending_remove": [],
                "remove_expiry_options": {},
                "awaiting_date_for": None,
            })

        # ==================================================
        # ADD
        # ==================================================
        elif any(k in user_text for k in ADD_KEYWORDS):
            items = split_items(user_text)
            expiry = parse_thai_date(user_text)

            STATE["pending_add"] = [{"name": i, "expiry": expiry} for i in items]
            STATE["mode"] = "confirm_add"

            print("[INTENT] add")
            print(f"[STATE] {STATE['pending_add']}")

            reply = f"ต้องการเพิ่ม {', '.join(items)} ใช่ไหมครับ"

        # ==================================================
        # REMOVE
        # ==================================================
        elif any(k in user_text for k in REMOVE_KEYWORDS):
            items = split_items(user_text)
            expiry_map = {}

            for it in items:
                expiries = await sync_to_async(
                    lambda i=it: list(
                        UserStock.objects.filter(
                            user=db_user,
                            ingredient__name=i
                        ).values_list("expiration_date", flat=True)
                    )
                )()
                expiry_map[it] = expiries

            STATE["pending_remove"] = items
            STATE["remove_expiry_options"] = expiry_map
            STATE["mode"] = "confirm_remove"

            print("[INTENT] remove")
            print(f"[STATE] options={expiry_map}")

            reply = f"ต้องการลบ {', '.join(items)} ใช่ไหมครับ"

        # ==================================================
        # FALLBACK
        # ==================================================
        else:
            print("[INTENT] smalltalk")
            reply = "มีอะไรให้ช่วยเกี่ยวกับวัตถุดิบไหมครับ"

        print(f"[AGENT] 🤖 {reply}")

        audio_out = tts_plugin.synthesize(reply)
        async for a in audio_out:
            await source.capture_frame(a.frame)

# ==========================================================
# DJANGO COMMAND
# ==========================================================
class Command(BaseCommand):
    help = "Run LiveKit Voice Agent Worker"

    def handle(self, *args, **options):
        self.stdout.write("🚀 Starting LiveKit Voice Agent")

        original_argv = sys.argv
        try:
            sys.argv = ["livekit-worker", "start"]
            cli.run_app(
                WorkerOptions(
                    entrypoint_fnc=entrypoint,
                )
            )
        finally:
            sys.argv = original_argv
