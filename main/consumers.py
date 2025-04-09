# consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Device
import json

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
        try:
            return Device.objects.get(device_token=device_token)
        except Device.DoesNotExist:
            return None

    @database_sync_to_async
    def get_all_devices(self):
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
                "prediction_label": prediction_label
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