from django.db import models
import numpy as np
from django.utils.timezone import now
import random
from django.conf import settings
from cryptography.fernet import Fernet
import json


class Device(models.Model):
    name = models.CharField(max_length=100)
    ip = models.GenericIPAddressField(blank=True, null=True)
    port = models.IntegerField(blank=True, null=True)
    last_seen = models.DateTimeField(null=True, blank=True)  # Время последнего пинга
    is_online = models.BooleanField(default=False)
    device_token = models.CharField(max_length=500, blank=True, null=True, db_index=True)

    def update_status(self):
        """Обновляет статус устройства."""
        self.last_seen = now()
        self.is_online = True
        self.save()

    def check_status(self):
        """Проверяет, онлайн ли устройство."""
        if self.last_seen and (now() - self.last_seen).total_seconds() > 60:  # 60 секунд таймаут
            self.is_online = False
            self.save()
        return self.is_online
    
    def _get_device_token(self):
        data = {
            'device_id': self.id,
            'device_name': self.name, 
            'date': now().strftime('%Y-%m-%d %H:%M:%S')
        }
        cipher_suite = Fernet(settings.FERNET_KEY.encode())
        encrypted_data = cipher_suite.encrypt(json.dumps(data).encode())
        return encrypted_data.decode()

    def __str__(self):
        return self.name

    def save(self, first_save=True, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.device_token and first_save:
            self.device_token = self._get_device_token()
            self.save(first_save=False)

    class Meta:
        verbose_name = 'Устройство'
        verbose_name_plural = 'Устройства'

class PredictResult(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='predict_results')
    results = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Predict result from {self.device}'
    
    class Meta:
        verbose_name = 'Результат предсказания'
        verbose_name_plural = 'Результаты предсказания'

class LocalData(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='local_datas')
    created_at = models.DateField(auto_now_add=True)
    data = models.JSONField(blank=True, null=True)

    def __str__(self):
        return f'Local data from {self.created_at} of {self.device}'
    
    def get_local_rounds_result(self):
        rounds_result = self.round_results.filter(device=self.device)
        x_label = [round_result.result for round_result in rounds_result]
        loss_label = [round_result.result.get('val_loss') for round_result in rounds_result]
        acc_label = [round_result.result.get('val_accuracy') for round_result in rounds_result]
        return x_label, loss_label, acc_label
    
    class Meta:
        verbose_name = 'Данные из локальной сети'
        verbose_name_plural = 'Данные из локальных сети'


class RoundResult(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='round_results')
    local_data = models.ForeignKey(LocalData, on_delete=models.CASCADE, related_name='round_results')
    round_number = models.IntegerField(default=0)
    result = models.JSONField(blank=True, null=True)
    
    def __str__(self):
        return f'Result of round {self.round_number} from {self.device}'
    
    class Meta:
        verbose_name = 'Результат раунда'
        verbose_name_plural = 'Результаты раунда'



class AggregetedData(models.Model): 
    created_at = models.DateField(auto_now_add=True)
    local_datas = models.ManyToManyField(LocalData, related_name='aggregated_datas')
    data = models.JSONField(blank=True, null=True)
    is_active = models.BooleanField(default=False, verbose_name='Статус активности')
    ready = models.BooleanField(default=False, verbose_name='Готовность данных')
    subscribed_devices = models.ManyToManyField(Device, related_name='subscribed_devices')
    round_count = models.IntegerField(default=0, verbose_name='Количество раунда')
    epoch_count = models.IntegerField(default=0, verbose_name='Количество эпох')

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
