import math
import time
import requests

from django.core.management.base import BaseCommand

from recipes.utils.krua_import import import_recipe_from_post


BASE_LIST_URL = "https://krua.co/api/recipe"
# buildId นี้มาจากตัวอย่างที่คุณให้ (เปลี่ยนได้ถ้าเว็บเปลี่ยน)
BASE_NEXT_DATA_URL = "https://krua.co/_next/data/lbRV51YihGA29VEc5NnZQ"


def fetch_recipe_list(page: int, sort: str = "newest") -> dict:
    params = {
        "page": page,
        "sort": sort,
    }
    resp = requests.get(BASE_LIST_URL, params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def build_detail_url(link: str) -> str:
    """
    link จาก list จะเป็น "/recipe/sweet-potato-balls"
    แปลงเป็น:
    BASE_NEXT_DATA_URL + "/recipe/sweet-potato-balls.json"
    """
    if not link.startswith("/"):
        link = "/" + link
    return f"{BASE_NEXT_DATA_URL}{link}.json"


class Command(BaseCommand):
    help = "Import ALL recipes from krua.co via /api/recipe (paginated) + Next.js data"

    def add_arguments(self, parser):
        parser.add_argument(
            "--start-page",
            type=int,
            default=1,
            help="เริ่มจากหน้าไหน (default=1)",
        )
        parser.add_argument(
            "--end-page",
            type=int,
            default=None,
            help="สุดหน้าที่จะดึง (ถ้าไม่ใส่จะใช้จาก total)",
        )
        parser.add_argument(
            "--sleep",
            type=float,
            default=0.2,
            help="ดีเลย์ระหว่างการยิง detail (วินาที, default=0.2)",
        )

    def handle(self, *args, **options):
        start_page = options["start_page"]
        end_page = options["end_page"]
        delay = options["sleep"]

        # ยิงหน้าต้นเพื่อรู้ total
        self.stdout.write(self.style.NOTICE(
            f"Fetching list page {start_page}..."
        ))
        first_page_data = fetch_recipe_list(start_page)
        total = first_page_data.get("total")
        data_list = first_page_data.get("data") or []
        per_page = len(data_list) or 25

        self.stdout.write(self.style.NOTICE(
            f"Total recipes: {total}, per page: {per_page}"
        ))

        total_pages = math.ceil(total / per_page) if total else start_page

        if end_page is None or end_page > total_pages:
            end_page = total_pages

        self.stdout.write(self.style.NOTICE(
            f"Will import from page {start_page} to {end_page}"
        ))

        current_page = start_page
        while current_page <= end_page:
            if current_page == start_page:
                page_data = first_page_data
            else:
                self.stdout.write(self.style.NOTICE(
                    f"Fetching list page {current_page}..."
                ))
                try:
                    page_data = fetch_recipe_list(current_page)
                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"[PAGE ERROR] page {current_page}: {e}"
                    ))
                    current_page += 1
                    continue

            recipes_list = page_data.get("data") or []

            self.stdout.write(self.style.NOTICE(
                f"Page {current_page}: {len(recipes_list)} items"
            ))

            # loop แต่ละเมนู
            for item in recipes_list:
                title = item.get("title")
                link = item.get("link")

                if not link:
                    self.stderr.write(self.style.WARNING(
                        f"  [SKIP] No link for title: {title}"
                    ))
                    continue

                detail_url = build_detail_url(link)

                try:
                    self.stdout.write(
                        self.style.NOTICE(f"  Fetching detail: {detail_url}")
                    )
                    resp = requests.get(detail_url, timeout=20)
                    resp.raise_for_status()
                    json_data = resp.json()

                    post = json_data["pageProps"]["posts"]

                    recipe = import_recipe_from_post(post)

                    self.stdout.write(self.style.SUCCESS(
                        f"    Imported: #{recipe.id} - {recipe.title}"
                    ))

                except Exception as e:
                    self.stderr.write(self.style.ERROR(
                        f"    [ERROR] {detail_url} : {e} (skip)"
                    ))
                    continue

                if delay and delay > 0:
                    time.sleep(delay)

            current_page += 1

        self.stdout.write(self.style.SUCCESS("Done importing all pages."))
