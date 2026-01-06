import logging
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import connections
from django.db.utils import OperationalError
from django.core.mail import send_mail  # 👈 สำหรับส่งเมล

from apscheduler.schedulers.blocking import BlockingScheduler
from django_apscheduler.jobstores import DjangoJobStore

# 👇 Import Models ของคุณ
from recipes.models import UserStock, Notification 

logger = logging.getLogger(__name__)

def daily_stock_check_job():
    """
    ทำงานทุกวัน (ควรตั้งไว้หลังเที่ยงคืน เช่น 00:01)
    1. แจ้งเตือนของที่จะหมดอายุในอีก 4 วัน (รวบส่งเมลเดียว)
    2. Disable ของที่หมดอายุไปแล้ว
    """
    print(f"\n⏰ [JOB START] เริ่มตรวจสอบสต็อกสินค้า: {timezone.now()}")
    
    today = timezone.now().date()

    # ==========================================================
    # LOGIC 1: แจ้งเตือนล่วงหน้า 4 วัน (แบบรวบยอดส่งเมล)
    # ==========================================================
    target_warning_date = today + timedelta(days=4)
    
    # 1.1 หาของที่วันหมดอายุตรงกับเป้าหมาย และยังไม่ disabled
    warning_items = UserStock.objects.filter(
        expiration_date=target_warning_date, 
        disable=False
    ).select_related('user', 'ingredient') # Optimization: ดึง user/ingredient มาเลยจะได้ไม่ query ซ้ำ

    # ตัวแปรสำหรับจัดกลุ่มของที่จะส่งเมล: { UserObj: [Item1, Item2, ...] }
    email_grouping = {} 
    warning_count = 0

    for item in warning_items:
        # สร้าง Notification ใน App (ทำทีละอันเหมือนเดิม เพื่อให้แจ้งเตือนในเว็บแยกรายการ)
        notif, created = Notification.objects.get_or_create(
            user=item.user,
            user_stock=item,
            defaults={'read_yet': False}
        )
        
        if created:
            warning_count += 1
            print(f"   ⚠️ สร้างแจ้งเตือนใน App: {item.ingredient.name} (User: {item.user.username})")
            
            # เก็บเข้ากลุ่มเตรียมส่งเมล (Key คือ User object)
            if item.user not in email_grouping:
                email_grouping[item.user] = []
            
            email_grouping[item.user].append(item)

    # 1.2 วนลูปส่งเมล (1 User = 1 Email)
    if email_grouping:
        print(f"   📧 กำลังเตรียมส่ง {len(email_grouping)} อีเมล...")

        for user, items in email_grouping.items():
            if not user.email:
                print(f"      ❌ ข้าม User {user.username} (ไม่มีอีเมล)")
                continue

            # สร้างเนื้อหาอีเมล (Subject & Message)
            item_count = len(items)
            subject = f"เตือน! วัตถุดิบ {item_count} รายการ กำลังจะหมดอายุในอีก 4 วัน"
            
            # สร้างลิสต์รายการสินค้าแบบ Bullet point
            item_list_str = ""
            for i, item in enumerate(items, 1):
                
                item_list_str += f"{i}. {item.ingredient.name} \n"

            message = (
                f"สวัสดีคุณ {user.username},\n\n"
                f"รายการวัตถุดิบเหล่านี้จะหมดอายุในวันที่ {target_warning_date}:\n\n"
                f"{item_list_str}\n"
                f"อย่าลืมนำมาใช้ทำอาหารนะครับ!\n\n"
                
            )

            try:
                send_mail(
                    subject,
                    message,
                    settings.EMAIL_HOST_USER,  # ส่งจากเมลใน config
                    [user.email],              # ส่งหา User คนนี้
                    fail_silently=False,
                )
                print(f"      ✅ ส่งเมลหา {user.email} สำเร็จ ({item_count} รายการ)")
            except Exception as e:
                print(f"      ❌ ส่งเมลหา {user.email} ล้มเหลว: {e}")

    else:
        print("   ✨ ไม่มีรายการใหม่ต้องแจ้งเตือนทางเมล")


    # ==========================================================
    # LOGIC 2: ตัดของหมดอายุ (Disable)
    # ==========================================================
    expired_items_query = UserStock.objects.filter(
        expiration_date__lt=today,
        disable=False
    )
    
    expired_count = expired_items_query.count()
    
    if expired_count > 0:
        expired_items_query.update(disable=True)
        print(f"❌ Disable ของหมดอายุไปแล้ว: {expired_count} รายการ")
    else:
        print("✨ ไม่มีรายการสินค้าหมดอายุให้ตัด")
        
    print(f"🏁 [JOB END] จบการทำงานรอบนี้\n" + "="*30)


class Command(BaseCommand):
    help = "Runs APScheduler for UserStock management."

    def handle(self, *args, **options):
        # 1. รอ Database ก่อน (กัน Error 2002)
        self.stdout.write("⏳ Waiting for database connection...")
        db_conn = connections['default']
        while True:
            try:
                db_conn.cursor()
                self.stdout.write(self.style.SUCCESS("✅ Database is available!"))
                break
            except OperationalError:
                self.stdout.write("💤 Database unavailable, waiting 1 second...")
                time.sleep(1)

        # 2. ตั้งค่า Scheduler
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # ตั้งเวลา (แก้เป็น 00:01 เพื่อใช้งานจริง)
        scheduler.add_job(
            daily_stock_check_job,
            trigger="cron",
            hour="00",     # เที่ยงคืน
            minute="01",   # 1 นาที
            id="daily_stock_manager",
            max_instances=1,
            replace_existing=True,
        )
        
        # Log บอกสถานะ
        print("✅ Added job 'daily_stock_manager' to run at 00:01.")
        logger.info("Scheduler started. Job 'daily_stock_manager' added.")
        
        try:
            print("🚀 Starting scheduler... (Press Ctrl+C to exit)")
            scheduler.start()
        except KeyboardInterrupt:
            print("🛑 Stopping scheduler...")
            logger.info("Stopping scheduler...")
            scheduler.shutdown()