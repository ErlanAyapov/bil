from django.db import models
import numpy as np
from django.utils.timezone import now
import random
from django.conf import settings
from cryptography.fernet import Fernet
import json
import base64
import pickle
from django.contrib.auth import get_user_model
from django.db import models
from django.utils.timezone import now


User = get_user_model()



class Device(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='devices', default=1)
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
            'ts': int(now().timestamp())
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
    # Store base64(pickle(weights)) as text for performance/compatibility
    data = models.TextField(blank=True, null=True)

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



class Train(models.Model):
    date         = models.DateField(default=now, db_index=True)  # <-- без lambda
    model_name   = models.CharField(max_length=32, db_index=True)   # 'dnn' | 'cnn' | 'cnn_lstm' ...
    round_count  = models.IntegerField(default=0)                    # сколько раундов завершено
    max_rounds   = models.IntegerField(default=50)
    epochs       = models.IntegerField(default=10)

    # текущие глобальные веса (последний снимок) — список списков чисел
    global_weights = models.JSONField(blank=True, null=True)

    is_active    = models.BooleanField(default=True)
    ready        = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)
    global_confusion = models.JSONField(blank=True, null=True)

    class Meta:
        ordering = ['-date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['date', 'model_name'],
                name='uniq_train_per_date_model'
            )
        ]

    def __str__(self):
        return f"Train {self.date} [{self.model_name}] r={self.round_count}/{self.max_rounds}"


class RoundResult(models.Model):
    # История раундов. Связываем с Train (можно оставить null=True, если будут старые записи без Train)
    train        = models.ForeignKey('Train', on_delete=models.CASCADE,
                                     related_name='round_results', null=True, blank=True)

    # Пер-устройство/локальные данные — как у тебя
    device       = models.ForeignKey('Device', on_delete=models.CASCADE, related_name='round_results')
    local_data   = models.ForeignKey('LocalData', on_delete=models.CASCADE, related_name='round_results')

    round_number = models.IntegerField(default=0)

    # Оригинальный «сырой» результат клиента (как и раньше)
    result       = models.JSONField(blank=True, null=True)

    # Агрегированные метрики (на витрину/сводка)
    avg_accuracy = models.FloatField(blank=True, null=True)
    avg_loss     = models.FloatField(blank=True, null=True)

    created_at   = models.DateTimeField(auto_now_add=True)  # <-- auto_now_add сам выставит

    def __str__(self):
        return f"Round {self.round_number} / {self.device}"

    class Meta:
        verbose_name = 'Результат раунда'
        verbose_name_plural = 'Результаты раунда'
        indexes = [
            models.Index(fields=['round_number']),
            models.Index(fields=['created_at']),
            models.Index(fields=['train', 'round_number']),
        ]




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
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
        ]

    def aggregate_data(self):
        import base64, pickle, numpy as np
        from django.utils.timezone import now

        # 1) Собираем LocalData, по возможности ограничив по дате (если поле есть)
        lds_qs = self.local_datas.all()
        # Если у LocalData есть created_at (date), можно сузить:
        # lds_qs = lds_qs.filter(created_at=now().date())

        local_weights = []
        bad = 0
        for local in lds_qs:
            try:
                raw = base64.b64decode((local.data or "").encode())
                w = pickle.loads(raw)
                # Ожидаем список/кортеж numpy-массивов
                if not isinstance(w, (list, tuple)) or not w:
                    raise TypeError("weights should be list/tuple of arrays")
                local_weights.append([np.asarray(a) for a in w])
            except Exception as e:
                bad += 1
                print(f"[WARN] Skipping corrupted weight for device {getattr(local, 'device_id', None)}: {e}")

        if not local_weights:
            raise ValueError("No valid local weights found for aggregation.")

        # 2) Если только один клиент — просто вернём его веса (FedAvg == идентичности)
        if len(local_weights) == 1:
            single = local_weights[0]
            # Приведём к list of lists (если вы так храните), иначе можно вернуть как есть
            return [arr.tolist() for arr in single]

        # 3) Проверка совместимости слоёв
        num_layers = len(local_weights[0])
        for i, w in enumerate(local_weights):
            if len(w) != num_layers:
                raise ValueError(f"Inconsistent number of layers: sample 0 has {num_layers}, sample {i} has {len(w)}")

        ref_shapes = [arr.shape for arr in local_weights[0]]
        for i, w in enumerate(local_weights[1:], start=1):
            for k, (a, s) in enumerate(zip(w, ref_shapes)):
                if a.shape != s:
                    raise ValueError(f"Incompatible shape at client {i}, layer {k}: {a.shape} != {s}")

        # 4) Усреднение через stack (надёжнее, чем mean по списку объектов)
        aggregated = []
        for layer_idx in range(num_layers):
            try:
                layer_stack = np.stack([w[layer_idx] for w in local_weights], axis=0)  # (N, ...)
                layer_mean  = layer_stack.mean(axis=0)
                aggregated.append(layer_mean.tolist())
            except Exception as e:
                # fallback: нули той же формы, но логируем
                print(f"[WARN] Aggregation failed at layer {layer_idx}: {e}. Filling zeros.")
                aggregated.append(np.zeros(ref_shapes[layer_idx], dtype=np.float32).tolist())

        return aggregated

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
 


# Доп. профиль пользователя
class Customer(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer')
    photo = models.ImageField(upload_to='media/avatars/', blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Customer profile for {self.user.username}'

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'
