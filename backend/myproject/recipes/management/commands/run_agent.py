import asyncio
import logging
import os
import sys
import json
from datetime import date, timedelta
from typing import Literal, List, Optional
from pydantic import BaseModel, Field

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
    llm,
)
from livekit.agents.llm import function_tool

# ================= Plugins =================
from livekit.plugins import openai, deepgram
from thefuzz import process

# ==========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("voice-agent")

class UserIntent(BaseModel):
    intent: Literal["add", "remove", "confirm", "cancel", "smalltalk"]
    items: List[str] = Field(default_factory=list)
    date: Optional[str] = None
    next_action: Literal["ask_expiry", "confirm", "execute", "resolve_item","none"]

# ==========================================================
# DATE PARSER (THAI)
# ==========================================================
def parse_thai_date(text: str | None) -> date | None:
    if not text:
        return None

    today = date.today()

    if "พรุ่งนี้" in text:
        return today + timedelta(days=1)
    if "มะรืน" in text:
        return today + timedelta(days=2)
    if "อาทิตย์หน้า" in text:
        return today + timedelta(days=7)
    if "สิ้นเดือน" in text:
        return (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)

    return None


# ==========================================================
# SEND MESSAGE TO FRONTEND (DATA CHANNEL)
# ==========================================================
async def send_ui_message(ctx: JobContext, type_: str, text: str):
    payload = json.dumps({
        "type": type_,
        "text": text,
    }).encode("utf-8")

    print(f"[DATA] -> {type_}: {text}")

    await ctx.room.local_participant.publish_data(
        payload,
        reliable=True,
    )


# ==========================================================
# ENTRYPOINT
# ==========================================================
async def entrypoint(ctx: JobContext):
    # ---------------- Django Setup ----------------
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "my_project.settings")
    django.setup()

    from recipes.models import Ingredient, UserStock
    User = get_user_model()

    # ---------------- Connect Room ----------------
    await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    participant = await ctx.wait_for_participant()

    db_user = await sync_to_async(User.objects.get)(
        email=participant.identity
    )

    print("👤 USER:", db_user.email)

    

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
        voice="nova",
        api_key=os.getenv("OPENAI_API_KEY")
    )

    # ---------------- Audio Out ----------------
    source = rtc.AudioSource(24000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("agent", source)
    await ctx.room.local_participant.publish_track(track)

    # ======================================================
    # CONVERSATION MEMORY (LLM BRAIN)
    # ======================================================
    chat_ctx = llm.ChatContext()
    chat_ctx.add_message(
        role="system",
        content=(
            "today's date is " + str(date.today()) + "\n"
            "คุณคือ AI ผู้ช่วยจัดการวัตถุดิบในครัว (Kitchen Inventory Assistant)\n"
            "\n"
            "บทบาทและความสามารถ:\n"
            "- เข้าใจคำสั่งผู้ใช้แบบภาษาคนธรรมชาติ ไม่ต้อง fix คำ\n"
            "- รองรับการสนทนาแบบหลายรอบ (multi-turn conversation)\n"
            "- จดจำบริบทก่อนหน้าและใช้ประกอบการตัดสินใจ\n"
            "- ตอบกลับเป็นภาษาไทยเท่านั้น\n"
            "\n"
            "Intent ที่ต้องรองรับ:\n"
            "- add        : เพิ่มวัตถุดิบ\n"
            "- remove     : ลบวัตถุดิบ\n"
            "- confirm    : ยืนยันการกระทำก่อนหน้า\n"
            "- cancel     : ยกเลิกการกระทำก่อนหน้า\n"
            "- smalltalk  : คำพูดทั่วไปหรือคำถามที่ไม่ใช่คำสั่ง\n"
            "\n"
            "==============================\n"
            "กฎสำหรับการเพิ่มวัตถุดิบ (add):\n"
            "1. ต้องรองรับการเพิ่มหลายวัตถุดิบในคำสั่งเดียว\n"
            "   ตัวอย่าง: \"เพิ่มไก่กับหมู\" → items = [\"ไก่\", \"หมู\"]\n"
            "\n"
            "2. ถ้าผู้ใช้ไม่ได้ระบุวันหมดอายุ:\n"
            "   - ให้ถามกลับผู้ใช้ก่อนว่า วัตถุดิบนี้หมดอายุเมื่อไหร่\n"
            "   - ถ้าผู้ใช้ตอบวันหมดอายุในรอบถัดไป ให้นำไปใช้\n"
            "   - ถ้าผู้ใช้ตอบแบบไม่ระบุวัน หรือบอกว่าไม่รู้ / ไม่แน่ใจ\n"
            "     ให้ใส่ค่า date เป็น null และอนุญาตให้เพิ่มได้\n"
            "\n"
            "3. ถ้าผู้ใช้ระบุวันหมดอายุมาพร้อมคำสั่งเพิ่ม:\n"
            "   - ให้ดึงวันหมดอายุนั้นมาใช้ทันที\n"
            "\n"
            "==============================\n"
            "กฎสำหรับการลบวัตถุดิบ (remove):\n"
            "1. ถ้าวัตถุดิบมีเพียงรายการเดียว ให้ลบได้ทันทีหลังยืนยัน\n"
            "\n"
            "2. ถ้าวัตถุดิบเดียวกันมีหลายวันหมดอายุ:\n"
            "   ตัวอย่าง: นม หมดอายุพรุ่งนี้ และอีก 3 วัน\n"
            "   - ต้องแจ้งผู้ใช้ว่ามีหลายรายการ\n"
            "   - ต้องบอกวันหมดอายุที่มีทั้งหมดให้ผู้ใช้เลือก\n"
            "   - ผู้ใช้สามารถเลือก:\n"
            "     • ลบเฉพาะวันใดวันหนึ่ง\n"
            "     • หรือพูดว่า \"ลบทั้งหมด\"\n"
            "\n"
            "==============================\n"
            "กฎทั่วไป:\n"
            "- ถ้าข้อมูลไม่ครบ ห้ามเดา ให้ถามกลับ\n"
            "- ถ้าผู้ใช้พูดยืนยัน (เช่น ได้เลย, เอาอันนี้, ใช่)\n"
            "  ให้ผูกกับ intent ก่อนหน้าตามบริบท\n"
            "- ห้ามทำการเพิ่มหรือลบจนกว่าจะได้รับการยืนยันเมื่อจำเป็น\n"
            "\n"
            "==============================\n"
            "รูปแบบคำตอบ:\n"
            "- เมื่อวิเคราะห์ intent แล้ว ให้ตอบกลับเป็น JSON เท่านั้น\n"
            "- ต้องตรงตาม schema ที่ระบบกำหนด\n"
            "- ห้ามใส่ข้อความอธิบายนอก JSON\n"
            "เรื่องชื่อวัตถุดิบ:\n"
            "- คุณไม่จำเป็นต้องรู้ชื่อวัตถุดิบจริงในระบบ\n"
            "- ให้คืนชื่อวัตถุดิบตามที่ผู้ใช้พูดหรือเข้าใจเชิงความหมาย\n"
            "- ระบบภายนอกจะเป็นผู้ตรวจสอบความตรงกัน\n"
            "- ถ้าชื่ออาจคลาดเคลื่อน ให้ next_action = \"resolve_item\"\n"
        ),
    )

    # ======================================================
    # STATE (fallback safety)
    # ======================================================
    STATE = {
        "mode": "idle",              # idle | awaiting_expiry | awaiting_confirm
        "pending_items": [],
        "pending_intent": None,
        "pending_date": None,
    }

    # ======================================================
    # TOOLS
    # ======================================================
    @function_tool(name="add_ingredient")
    async def add_ingredient(
        item_name: str,
        expiration_date: str | None = None
    ) -> str:
        @sync_to_async
        def _add():
            names = list(
                Ingredient.objects.filter(common=False)
                .values_list("name", flat=True)
            )

            best, score = process.extractOne(item_name, names)
            if score < 60:
                return f"ไม่พบวัตถุดิบ {item_name}"

            # exp = parse_thai_date(expiration_date) or (
            #     date.today() + timedelta(days=7)
            # )
            exp = expiration_date or date.today() + timedelta(days=7)

            UserStock.objects.create(
                user=db_user,
                ingredient=Ingredient.objects.get(name=best),
                expiration_date=exp,
            )

            return f"เพิ่ม {best} (หมดอายุ {exp}) เรียบร้อยแล้ว"

        return await _add()
    async def get_stock_details(item_name: str):
        @sync_to_async
        def _get():
            # หาชื่อที่ตรงที่สุดก่อน
            names = list(Ingredient.objects.filter(common=False).values_list("name", flat=True))
            best, score = process.extractOne(item_name, names)
            if score < 60: return None, []

            # ดึงรายการวันหมดอายุทั้งหมดของสินค้านั้น
            stocks = UserStock.objects.filter(
                user=db_user, 
                ingredient__name=best
            ).values_list("expiration_date", flat=True)
            
            return best, list(stocks) # คืนค่า (ชื่อจริง, รายการวันที่)
        return await _get()

    @function_tool(name="remove_ingredient")
    async def remove_ingredient(item_name: str, target_date: str | None = None) -> str:
        @sync_to_async
        def _remove():
            qs = UserStock.objects.filter(user=db_user, ingredient__name=item_name)
            
            # ถ้าระบุวันมา ให้ลบเฉพาะวันนั้น
            if target_date:
                qs = qs.filter(expiration_date=target_date)
            
            count = qs.count()
            qs.delete()
            return f"ลบ {item_name} {'หมดอายุ '+str(target_date) if target_date else 'ทั้งหมด'} จำนวน {count} รายการแล้ว"

        return await _remove()

    # ======================
    # LLM PARSER
    # ======================
    async def llm_parse(user_text: str) -> dict:
        chat_ctx.add_message(role="user", content=user_text)
        print("🧠 LLM PARSING:", user_text)

        stream =  llm_plugin.chat(
            chat_ctx=chat_ctx,
            response_format=UserIntent
        )
        print("🧠 STREAM...", stream)
        full_json_text = ""
        async for chunk in stream:
            delta = getattr(chunk, "delta", None)
            if delta and delta.content:
                full_json_text += delta.content

        print(f"🧠 RAW JSON: {full_json_text}")

        try:
            parsed_data = json.loads(full_json_text)
            return parsed_data
        except json.JSONDecodeError:
            print("❌ JSON Parse Error")
            # Return ค่า Default กันตาย
            return {
                "intent": "smalltalk",
                "items": [],
                "date": None,
                "next_action": "none"
            }
        
    # ======================================================
    # HELPER: AI REPLY GENERATOR
    # ======================================================
    async def generate_reply(system_status: str) -> str:
        """
        ฟังก์ชันสำหรับให้ AI แต่งประโยคตอบกลับเอง โดยอิงจากสถานะระบบ
        """
        gen_ctx = llm.ChatContext()
        gen_ctx.add_message(role="system", content=(
            "คุณคือ 'เชฟผู้ช่วย' (Kitchen Chef) ในครัวที่มีบุคลิก:\n"
            "- ร่าเริง เป็นกันเอง กระตือรือร้น (Friendly & Enthusiastic)\n"
            "- พูดภาษาไทยที่เป็นธรรมชาติ เหมือนคนคุยกัน\n"
            "- ห้ามพูดคำว่า 'ระบบ' หรือ 'สถานะ' ให้พูดเหมือนคุณเป็นคนจัดการเอง\n"
            "- ตอบสั้นๆ กระชับ เข้าใจง่าย\n"
            "\n"
            f"จงแต่งประโยคตอบกลับผู้ใช้ จากข้อมูลสถานะนี้: {system_status}"
        ))

        # เรียก LLM (แบบไม่ใช้ JSON schema เอา Text ล้วนๆ)
        stream = llm_plugin.chat(chat_ctx=gen_ctx)
        
        full_text = ""
        async for chunk in stream:
            delta = getattr(chunk, "delta", None)
            if delta and delta.content:
                full_text += delta.content
        
        return full_text

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
        print("🗣 USER:", user_text)
        

        await send_ui_message(ctx, "user_text", user_text)
        print("🧠 LLM PARSING:", user_text)

        parsed = await llm_parse(user_text)
        
        intent = parsed["intent"]
        items = parsed.get("items", []) or STATE["pending_items"]
        date_text = parsed.get("date")
        
        # Action จาก LLM (บางที LLM ช่วยตัดสินใจว่า confirm หรือยัง)
        action = parsed.get("next_action", "none")

        reply = ""

        # ------------------------------------------------------
        # PRIORITY 1: CANCEL
        # ------------------------------------------------------
        if intent == "cancel":
            STATE.clear()
            STATE["mode"] = "idle"
            STATE["pending_items"] = []
            # reply = "ยกเลิกรายการให้แล้วครับ"
            reply = await generate_reply("User สั่งยกเลิก -> ระบบทำการเคลียร์สถานะเรียบร้อยแล้ว")

        # ------------------------------------------------------
        # PRIORITY 2: STATE HANDLING (จัดการงานค้าง)
        # ------------------------------------------------------
        
        # Case 2.1: กำลังรอเลือกวันที่จะลบ (กรณีมีหลาย Slot)
        elif STATE["mode"] == "awaiting_remove_selection":
            target_item = STATE["pending_items"][0] # ชื่อของที่กำลังจะลบ
            
            # ถ้า User บอกวันที่มา หรือ บอกว่า "ทั้งหมด"
            if date_text:
                # ลบเฉพาะวันที่เลือก
                await remove_ingredient(target_item, date_text)
                # reply = f"ลบ {target_item} ของวันที่ {date_text} เรียบร้อยครับ"
                reply = await generate_reply(f"ลบ {target_item} ล็อตของวันที่ {date_text} ออกจากระบบสำเร็จ")
                STATE.clear()
                STATE["mode"] = "idle"
                STATE["pending_items"] = []
            elif "ทั้งหมด" in user_text or "ทุกอัน" in user_text:
                # ลบเกลี้ยง
                await remove_ingredient(target_item, None)
                # reply = f"ลบ {target_item} ทั้งหมดทุกรายการเรียบร้อยครับ"
                reply = await generate_reply(f"ลบ {target_item} ทั้งหมดทุกรายการ ออกจากระบบสำเร็จ")
                STATE.clear()
                STATE["mode"] = "idle"
                STATE["pending_items"] = []
            else:
                # reply = "ขอโทษครับ ช่วยระบุวันที่ต้องการลบ หรือบอกว่าลบทั้งหมดอีกทีได้ไหมครับ"
                reply = await generate_reply(f"User เลือกวันที่ไม่ชัดเจน ให้ถามย้ำอย่างสุภาพว่าจะลบ {target_item} ของวันที่เท่าไหร่ หรือจะให้ลบทั้งหมด")

        # Case 2.2: รอ Confirm การลบ (กรณีมี Slot เดียว)
        elif STATE["mode"] == "confirm_remove":
            if intent == "confirm" or "ลบ" in user_text or "ใช่" in user_text:
                target_item = STATE["pending_items"][0]
                await remove_ingredient(target_item, None) # ลบเลย (เพราะมีอันเดียว)
                #  reply = f"ลบ {target_item} เรียบร้อยแล้วครับ"
                reply = await generate_reply(f"ยืนยันการลบ {target_item} เรียบร้อยแล้ว")
                STATE.clear()
                STATE["mode"] = "idle"
                STATE["pending_items"] = []
            else:
                # reply = "โอเคครับ งั้นยังไม่ลบนะครับ"
                reply = await generate_reply("User เปลี่ยนใจไม่ลบ -> รับทราบและยกเลิกคำสั่งลบ")
                STATE.clear()
                STATE["mode"] = "idle"

        # Case 2.3: รอ Confirm การเพิ่ม (เหมือนเดิม)
        elif STATE["mode"] == "awaiting_confirm": # (Logic เพิ่มของเดิม)
             is_confirmed = (intent == "confirm" or action == "execute")
             if is_confirmed:
                added_names = []
                for it in STATE["pending_items"]:
                    await add_ingredient(it, STATE["pending_date"])
                    added_names.append(it)
                # reply = "เพิ่มเรียบร้อยแล้วครับ"
                reply = await generate_reply(f"บันทึก {', '.join(added_names)} ลงในตู้เย็นเรียบร้อยแล้ว")
                STATE.clear()
                STATE["mode"] = "idle"
                STATE["pending_items"] = []
             else:
                # reply = "ตกลงให้เพิ่มเลยไหมครับ"
                reply = await generate_reply("ข้อมูลครบถ้วนแล้ว ให้ถามย้ำผู้ใช้ว่า 'ยืนยันให้บันทึกเลยไหม'")

        # ------------------------------------------------------
        # PRIORITY 3: NEW COMMANDS
        # ------------------------------------------------------
        
        # Case 3.1: สั่งลบ (Remove Logic ใหม่)
        elif intent == "remove":
            if not items:
                # reply = "ต้องการให้ลบอะไรครับ"
                reply = await generate_reply("User สั่งลบแต่ไม่ได้บอกชื่อวัตถุดิบ ให้ถามกลับว่าจะให้ลบอะไร")
            else:
                item_to_check = items[0] # เช็คทีละตัวก่อน (เพื่อความง่าย)
                real_name, dates = await get_stock_details(item_to_check)

                if not real_name:
                    # reply = f"หา {item_to_check} ไม่เจอในตู้เย็นครับ"
                    reply = await generate_reply(f"User จะลบ {item_to_check} แต่หาไม่เจอในระบบ แจ้ง User ว่าไม่มีของสิ่งนี้")
                elif len(dates) == 0:
                    # reply = f"ไม่มี {real_name} เหลือในตู้เย็นแล้วครับ"
                    reply = await generate_reply(f"User จะลบ {real_name} แต่เช็คแล้วยอดคงเหลือเป็น 0")
                
                # A. มีวันเดียว -> ถามยืนยัน
                elif len(dates) == 1:
                    STATE["mode"] = "confirm_remove"
                    STATE["pending_items"] = [real_name]
                    exp_str = dates[0].strftime("%d/%m/%Y")
                    # reply = f"เจอ {real_name} หมดอายุ {exp_str} ต้องการลบเลยไหมครับ"
                    reply = await generate_reply(f"เจอ {real_name} 1 รายการ (หมดอายุ {exp_str}) ให้ถาม User ว่าจะลบเลยไหม")

                # B. มีหลายวัน -> แจ้งและให้เลือก
                else:
                    STATE["mode"] = "awaiting_remove_selection"
                    STATE["pending_items"] = [real_name]
                    
                    # สร้างข้อความ list วันที่
                    date_strs = [d.strftime("%d/%m") for d in dates]
                    # reply = (f"มี {real_name} อยู่ {len(dates)} รายการครับ "
                    #          f"คือวันที่ {', '.join(date_strs)} "
                    #          "ต้องการลบอันไหน หรือให้ลบทั้งหมดครับ")
                    reply = await generate_reply(f"เจอ {real_name} {len(dates)} รายการ คือวันที่ {', '.join(date_strs)} ให้ถาม User ว่าจะลบอันไหน หรือลบทั้งหมด")

        # Case 3.2: สั่งเพิ่ม (Add Logic)
        elif intent == "add":
            STATE["pending_items"] = items
            STATE["pending_intent"] = "add"

            if action == "ask_expiry":
                STATE["mode"] = "awaiting_expiry"
                # reply = f"{', '.join(items)} หมดอายุเมื่อไหร่ครับ"
                reply = await generate_reply(f"รับคำสั่งเพิ่ม {', '.join(items)} แล้ว แต่ยังไม่รู้วันหมดอายุ ให้ถาม User ว่าหมดอายุเมื่อไหร่")
            else:
                STATE["mode"] = "awaiting_confirm"
                STATE["pending_date"] = date_text
                # reply = f"ต้องการเพิ่ม {', '.join(items)} ใช่ไหมครับ"
                reply = await generate_reply(f"เตรียมเพิ่ม {', '.join(items)} วันหมดอายุ {date_text or '7 วันข้างหน้า'} ให้ถามยืนยันความถูกต้อง")
        
        # Case 3.3: Smalltalk
        else:
            #  reply = "มีอะไรให้ช่วยอีกไหมครับ"
            reply = await generate_reply("User พูดเรื่องทั่วไป ให้ตอบรับอย่างเป็นกันเอง แล้วถามว่ามีเรื่องวัตถุดิบให้ช่วยไหม")

        # ------------------------------------------------------
        # END LOOP
        # ------------------------------------------------------
        print("🤖 AGENT:", reply)
        if reply:
            chat_ctx.add_message(role="assistant", content=reply)
            await send_ui_message(ctx, "agent_text", reply)
            audio_out = tts_plugin.synthesize(reply)
            async for a in audio_out:
                await source.capture_frame(a.frame)
        # audio_out = tts_plugin.synthesize(reply)
        # async for a in audio_out:
        #     await source.capture_frame(a.frame)


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
                WorkerOptions(entrypoint_fnc=entrypoint)
            )
        finally:
            sys.argv = original_argv