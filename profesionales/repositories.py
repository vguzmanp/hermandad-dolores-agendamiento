from django.db.models import Count, Q

from .models import Especialidad, Policlinico, Profesional


class ProfesionalRepository:
    def listar(self, especialidad_id=None, solo_activos=False):
        qs = Profesional.objects.select_related("especialidad", "usuario")
        if especialidad_id:
            qs = qs.filter(especialidad_id=especialidad_id)
        if solo_activos:
            qs = qs.filter(activo=True)
        return qs

    def especialidades(self):
        return Especialidad.objects.annotate(n_profesionales=Count("profesionales"))

    def policlinicos(self):
        return Policlinico.objects.select_related("usuario_tens").annotate(n_agendas=Count("agendas", filter=Q(agendas__activa=True)))

    def guardar(self, obj):
        obj.save()
        return obj
