from django.core.management.base import BaseCommand

from apps.carriers.sync import sync_all


class Command(BaseCommand):
    help = "Sincroniza tracking de todas as encomendas ativas com a API PacoteVício."

    def handle(self, *args, **options):
        results = sync_all()
        for key, value in results.items():
            self.stdout.write(f"{key}: {value}")