from django.db import models


class ModelRun(models.Model):
    """A trained model's parameters and how well it did on held-out data."""
    name = models.CharField(max_length=60, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    n_samples = models.PositiveIntegerField(default=0)
    params = models.JSONField(default=dict)
    metrics = models.JSONField(default=dict)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ['-created_at']
        get_latest_by = 'created_at'

    def __str__(self):
        return f'{self.name} @ {self.created_at:%Y-%m-%d %H:%M}'
