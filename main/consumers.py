# consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json, pickle
import numpy as np
from django.utils.timezone import now 


class DeviceStatusConsumer(AsyncWebsocketConsumer):
    # Список всех подключенных клиентов
    connected_clients = set()
    

    async def connect(self):
        await self.accept()
        # Добавляем клиента в список
        self.connected_clients.add(self)

        # Отправляем текущее состояние всех устройств новому клиенту
        devices = await self.get_all_devices()
        await self.send(json.dumps({
            "type": "full_update",
            "devices": devices
        }))

    async def disconnect(self, close_code):
        # Удаляем клиента из списка
        if self in self.connected_clients:
            self.connected_clients.remove(self)

    @database_sync_to_async
    def get_device(self, device_token):
        from .models import Device
        try:
            return Device.objects.get(device_token=device_token)
        except Device.DoesNotExist:
            return None

    @database_sync_to_async
    def get_all_devices(self):
        from .models import Device
        return list(Device.objects.values(
            "device_token",
            "name"
        ))

    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            msg_type = data.get("type")

            # Обработка heartbeat
            if msg_type == "heartbeat":
                await self.send(json.dumps({"type": "pong"}))
                return

            

            device_token = data.get('device_token')
            prediction = data.get('prediction')
            confidence = data.get('confidence')
            prediction_label = data.get('prediction_label')
            ip_data = data.get('ip_data')

            # Получаем устройство из БД
            device = await self.get_device(device_token)
            if not device:
                await self.send_error("Device not found")
                return

            # Обновляем статус
            new_status = "danger" if prediction != 0 else "safe"
            await database_sync_to_async(device.save)()

            # Рассылаем обновление ВСЕМ клиентам
            await self.broadcast({
                "type": "status_update",
                "device_token": device_token,
                "status": new_status,
                "device_name": device.name,
                "device_id": device.id,
                "prediction": prediction,
                "confidence": confidence,
                "prediction_label": prediction_label,
                "ip_data": ip_data
            })

        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")

    async def broadcast(self, message):
        for client in self.connected_clients:
            await client.send(json.dumps(message))

    async def send_error(self, message):
        await self.send(json.dumps({
            "type": "error",
            "message": message
        }))


class TrainModelConsumer(AsyncWebsocketConsumer):
    connected_clients = set()
    round_weights = {}

    async def connect(self):
        await self.accept()
        self.connected_clients.add(self)
        self.device = None

        # Получить активные агрегированные данные
        self.agg_data = await self.get_active_agg_data()

        if self.agg_data and self.agg_data.data:
            await self.send(json.dumps({
                "type": "global_weights",
                "payload": pickle.dumps(self.agg_data.data).hex(),
                "round": self.agg_data.round_count
            }))

    async def disconnect(self, code):
        self.connected_clients.discard(self)

    async def receive(self, text_data):
        data = json.loads(text_data)
        if data["type"] == "weights":
            await self.process_weights(data)

    async def process_weights(self, data):
        device_token = data.get("device_token")
        self.device = await self.get_device(device_token)
        if not self.device:
            return

        # Получить веса и метрики от клиента
        weights = pickle.loads(bytes.fromhex(data["payload"]))
        metrics = data.get("metrics", {})
        round_num = data.get("round")

        # Сохранить метрики в базу
        local_data = await self.get_or_create_local_data(self.device)
        await self.save_round_result(self.device, local_data, round_num, metrics)

        # Добавить веса устройства в память
        self.round_weights[self.device.id] = weights

        # Если все подключённые клиенты прислали веса — выполнить агрегацию
        if len(self.round_weights) == len(self.connected_clients):
            await self.aggregate_and_broadcast(round_num)

    async def aggregate_and_broadcast(self, round_num):
        # Записываем локальные веса в LocalData
        await self.write_local_data_to_agg()

        # Агрегация и сохранение глобальных весов через save(aggregate=True)
        await self.aggregate_and_save(round_num + 1)

        # Отправка новых глобальных весов всем клиентам
        await self.broadcast_all({
            "type": "global_weights",
            "payload": pickle.dumps(self.agg_data.data).hex(),
            "round": self.agg_data.round_count
        })

        # Очистить текущие локальные веса
        self.round_weights.clear()

    async def broadcast_all(self, message):
        for client in self.connected_clients:
            await client.send(json.dumps(message))

    # ----- БД операции -----

    @database_sync_to_async
    def get_device(self, token):
        from .models import Device

        try:
            return Device.objects.get(device_token=token)
        except Device.DoesNotExist:
            return None

    @database_sync_to_async
    def get_active_agg_data(self):
        from .models import AggregetedData
        return AggregetedData.objects.filter(is_active=True).order_by("-created_at").first()

    @database_sync_to_async
    def get_or_create_local_data(self, device):
        from .models import LocalData
        return LocalData.objects.get_or_create(device=device, created_at=now().date())[0]

    @database_sync_to_async
    def save_round_result(self, device, local_data, round_num, metrics):
        from .models import RoundResult
        RoundResult.objects.create(
            device=device,
            local_data=local_data,
            round_number=round_num,
            result=metrics
        )

    @database_sync_to_async
    def write_local_data_to_agg(self):
        from .models import LocalData, Device
        # Обновляем связь LocalData с AggregetedData
        for device_id, weights in self.round_weights.items():
            try:
                device = Device.objects.get(id=device_id)
                local_data, _ = LocalData.objects.get_or_create(device=device, created_at=now().date())
                if local_data.data is None:
                    local_data.data = weights
                    local_data.save()
                self.agg_data.local_datas.add(local_data)
            except Device.DoesNotExist:
                pass

    @database_sync_to_async
    def aggregate_and_save(self, new_round):
        self.agg_data.round_count = new_round
        self.agg_data.save(aggregate=True)
