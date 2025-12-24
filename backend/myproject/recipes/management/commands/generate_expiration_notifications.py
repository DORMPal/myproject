import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction

from recipes.models import Notification, UserStock


class Command(BaseCommand):
    help = (
        "1) Create notifications for stocks expiring in exactly 4 days (disable=False)\n"
        "2) Auto-disable stocks expiring today (disable=True) without notification.\n"
        "Intended to be run daily."
    )

    def handle(self, *args, **options):
        today = timezone.localdate()
        notify_date = today + datetime.timedelta(days=4)

        created_count = 0

        with transaction.atomic():
            # (B) หมดอายุวันนี้ -> disable=True (ไม่แจ้งเตือน)
            disabled_count = (
                UserStock.objects.filter(
                    expiration_date=today,
                    disable=False,
                ).update(disable=True)
            )

            # (A) แจ้งเตือนเฉพาะอีก 4 วันพอดี (ยังไม่ disable)
            stocks_to_notify = (
                UserStock.objects.filter(
                    expiration_date=notify_date,
                    disable=False,
                ).select_related("user")
            )

            for stock in stocks_to_notify:
                _, created = Notification.objects.get_or_create(
                    user=stock.user,
                    user_stock=stock,
                    defaults={"read_yet": False},
                )
                if created:
                    created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created_count} notifications (expiring in 4 days), "
                f"auto-disabled {disabled_count} stocks (expiring today)."
            )
        )
