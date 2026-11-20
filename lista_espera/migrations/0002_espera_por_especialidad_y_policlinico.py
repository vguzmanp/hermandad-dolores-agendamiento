"""
La lista de espera queda ligada solo a una especialidad y un policlínico (no a un
profesional). A las solicitudes antiguas sin policlínico se les asigna uno donde
se atienda la especialidad; si no existe ninguno, se eliminan.
"""
import django.db.models.deletion
from django.db import migrations, models


def completar_policlinico(apps, schema_editor):
    SolicitudEspera = apps.get_model("lista_espera", "SolicitudEspera")
    Agenda = apps.get_model("agenda", "Agenda")
    for s in SolicitudEspera.objects.filter(policlinico__isnull=True):
        agendas = Agenda.objects.filter(profesional__especialidad_id=s.especialidad_id, activa=True)
        if s.profesional_id:
            agendas = agendas.filter(profesional_id=s.profesional_id) or agendas
        agenda = agendas.order_by("policlinico_id").first()
        if agenda is None:
            s.delete()
        else:
            s.policlinico_id = agenda.policlinico_id
            s.save(update_fields=["policlinico"])


class Migration(migrations.Migration):
    dependencies = [
        ("agenda", "0001_initial"),
        ("lista_espera", "0001_initial"),
        ("profesionales", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(completar_policlinico, migrations.RunPython.noop),
        migrations.RemoveField(model_name="solicitudespera", name="profesional"),
        migrations.AlterField(
            model_name="solicitudespera",
            name="policlinico",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="solicitudes_espera",
                                    to="profesionales.policlinico", verbose_name="policlínico"),
        ),
    ]
