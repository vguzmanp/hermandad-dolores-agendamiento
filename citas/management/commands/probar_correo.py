from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Envía un correo de prueba para revisar la configuración SMTP."

    def add_arguments(self, parser):
        parser.add_argument("destino", help="Correo que recibirá la prueba")

    def handle(self, *args, **opciones):
        if not settings.ENVIAR_CORREOS:
            raise CommandError("ENVIAR_CORREOS está en False en el archivo .env.")
        if not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise CommandError("Faltan EMAIL_HOST_USER o EMAIL_HOST_PASSWORD en el archivo .env.")
        try:
            send_mail("Correo de prueba — Hermandad de Dolores",
                      "La configuración de correo funciona correctamente.", None, [opciones["destino"]])
        except Exception as error:
            raise CommandError(f"No se pudo enviar: {error}")
        self.stdout.write(self.style.SUCCESS(f"Correo enviado a {opciones['destino']}."))
