import logging
from datetime import timedelta
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db.models import F

from apscheduler.schedulers.blocking import BlockingScheduler
from django_apscheduler.jobstores import DjangoJobStore

# 👇 Import Models ของคุณ
from recipes.models import UserStock, Notification 

logger = logging.getLogger(__name__)

def daily_stock_check_job():
    """
    ทำงานทุกวัน (ควรตั้งไว้หลังเที่ยงคืน เช่น 00:01)
    1. แจ้งเตือนของที่จะหมดอายุในอีก 4 วัน
    2. Disable ของที่หมดอายุไปแล้ว
    """
    print(f"⏰ เริ่มตรวจสอบสต็อกสินค้า: {timezone.now()}")
    
    # ดึงเฉพาะ 'วันที่' ปัจจุบัน (ไม่เอาเวลา)
    today = timezone.now().date()

    # ==========================================
    # LOGIC 1: แจ้งเตือนล่วงหน้า 4 วัน
    # ==========================================
    target_warning_date = today + timedelta(days=4)
    
    # หาของที่วันหมดอายุตรงกับ (วันนี้ + 4) และยังไม่ถูก disable
    warning_items = UserStock.objects.filter(
        expiration_date=target_warning_date, 
        disable=False
    )

    warning_count = 0
    for item in warning_items:
        # ใช้ get_or_create เพื่อป้องกันการแจ้งเตือนซ้ำ (เผื่อ Script รันเบิ้ล)
        # เราจะสร้าง Notification
        notif, created = Notification.objects.get_or_create(
            user=item.user,
            user_stock=item,
            defaults={
                'read_yet': False
            }
        )
        if created:
            warning_count += 1
            print(f"⚠️ สร้างแจ้งเตือนสำหรับ: {item.ingredient.name} (User: {item.user.username})")

    print(f"✅ สร้างแจ้งเตือนล่วงหน้าเสร็จสิ้น: {warning_count} รายการ")

    # ==========================================
    # LOGIC 2: ตัดของหมดอายุ (Disable)
    # ==========================================
    # หาของที่วันหมดอายุน้อยกว่าวันนี้ (< today) และยัง active อยู่
    expired_items_query = UserStock.objects.filter(
        expiration_date__lt=today,
        disable=False
    )
    
    # นับจำนวนก่อน update
    expired_count = expired_items_query.count()
    
    if expired_count > 0:
        # ใช้ .update() เพื่อความรวดเร็ว (ทำทีเดียวทั้งหมด ไม่ต้องวน Loop save)
        expired_items_query.update(disable=True)
        print(f"❌ Disable ของหมดอายุไปแล้ว: {expired_count} รายการ")
    else:
        print("✨ ไม่มีรายการสินค้าหมดอายุให้ตัด")


class Command(BaseCommand):
    help = "Runs APScheduler for UserStock management."

    def handle(self, *args, **options):
        scheduler = BlockingScheduler(timezone=settings.TIME_ZONE)
        scheduler.add_jobstore(DjangoJobStore(), "default")

        # ตั้งเวลาให้รันทุกวัน ตอน 00:01 (เที่ยงคืน 1 นาที)
        scheduler.add_job(
            daily_stock_check_job,
            trigger="cron",
            hour="00",
            minute="01",
            id="daily_stock_manager",
            max_instances=1,
            replace_existing=True,
        )
        print("✅ Added job 'daily_stock_manager' to run at 00:01.")
        logger.info("Scheduler started. Job 'daily_stock_manager' added.")
        
        try:
            print("🚀 Starting scheduler... (Press Ctrl+C to exit)")
            scheduler.start()
        except KeyboardInterrupt:
            print("🛑 Stopping scheduler...")
            logger.info("Stopping scheduler...")
            scheduler.shutdown()