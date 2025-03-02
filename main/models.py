from django.db import models
import numpy as np


class Device(models.Model):
    name = models.CharField(max_length=100)
    ip = models.GenericIPAddressField(blank=True, null=True)
    port = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = 'Устройство'
        verbose_name_plural = 'Устройства'


class LocalData(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='local_datas')
    created_at = models.DateField(auto_now_add=True)
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f'Local data from {self.created_at} of {self.device}'
    
    class Meta:
        verbose_name = 'Данные из локальной сети'
        verbose_name_plural = 'Данные из локальных сети'

class AggregetedData(models.Model): 
    created_at = models.DateField(auto_now_add=True)
    local_datas = models.ManyToManyField(LocalData, related_name='aggregated_datas')
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f'Aggregated data from {self.created_at}'

    class Meta:
        verbose_name = 'Агрегированные данные'
        verbose_name_plural = 'Агрегированные данные'

    def aggregate_data(self):
        local_weights = [local.data for local in self.local_datas.all()]
        if local_weights:
            aggregated_data = [
                np.mean(np.array([np.array(w[layer_idx], dtype=np.float32) for w in local_weights]), axis=0).tolist()
                for layer_idx in range(len(local_weights[0]))
            ]
            return aggregated_data
        return []

    
    def save(self, aggregate=False, *args, **kwargs):
        if aggregate:
            aggregated_data = self.aggregate_data()
            if aggregated_data:
                self.data = aggregated_data 
                super().save(*args, **kwargs)
            else:
                raise ValueError("Failed to aggregate data")
        else:
            super().save(*args, **kwargs)
