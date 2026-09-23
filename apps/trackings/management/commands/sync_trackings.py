import logging

from django.core.management.base import BaseCommand, CommandError

from apps.carriers.sync import sync_all


logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sincroniza tracking de todas as encomendas ativas com a API PacoteVício."

    def add_arguments(self, parser):
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Imprime apenas os totais, sem o cabeçalho.",
        )

    def handle(self, *args, **options):
        quiet = options["quiet"]
        results = sync_all()
        if results["pausado"]:
            logger.warning("Cota diária atingida — %s encomendas pausadas.", results["pausado"])
        if not quiet:
            self.stdout.write("=" * 40)
        for key, value in results.items():
            self.stdout.write(f"{key}: {value}")
        if not quiet:
            self.stdout.write("=" * 40)
        if results["erro"] or results["pausado"]:
            raise CommandError(
                f"Sync terminou com {results['erro']} erro(s) e "
                f"{results['pausado']} pausado(s) pela cota."
            )