from django.contrib import admin

from .models import ModelRun


@admin.register(ModelRun)
class ModelRunAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at', 'n_samples', 'metrics')
    readonly_fields = ('name', 'created_at', 'n_samples', 'params', 'metrics', 'notes')
