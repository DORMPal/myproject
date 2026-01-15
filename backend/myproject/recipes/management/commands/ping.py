from django.core.management.base import BaseCommand

class Command(BaseCommand):
    help = "Test Ping"

    def handle(self, *args, **options):
        self.stdout.write("PONG! Pong! pong!")