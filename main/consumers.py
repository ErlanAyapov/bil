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
    connected_clients = set()   # набор Consumer-объектов
    round_weights     = {}      # {device_id: weights}
    MAX_ROUND_COUNT = 10


    async def connect(self):
        await self.accept()
        self.connected_clients.add(self)
        self.device = None
        self.agg_data = await self.get_active_agg_data()

        # Добавляем в группу UI для group_send
        if self.channel_layer:
            await self.channel_layer.group_add(
                "ui_training",
                self.channel_name
            )


    async def disconnect(self, code):
        self.connected_clients.discard(self)
        if self.channel_layer:
            await self.channel_layer.group_discard(
                "ui_training",
                self.channel_name
            )


    async def receive(self, text_data):
        data = json.loads(text_data)
        # print(f"Received data: {data}")
        if data["type"] == "hello":                 # hand-shake
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return
            if self.agg_data and self.agg_data.data:
                await self.send(json.dumps({
                    "type": "global_weights",
                    "payload": pickle.dumps(self.agg_data.data).hex(),
                    "round":   self.agg_data.round_count
                }))

        elif data["type"] == "weights":             # результаты очередного раунда
            await self.process_weights(data)
        elif data["type"] == "subscribe":
            # подписка на обновления
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return 
            print(f"Subscribed device: {data.get('client')}")
            print(f"Connected clients: {self.connected_clients}")
            await self.broadcast({
                "type": "subscribe",
                "device_token": self.device.device_token,
                "device_name": data.get("client"),
                "device_id": self.device.id,
            })
        elif data["type"] == "start_training":
            # запуск обучения
            if self.connected_clients:
                await self.broadcast({
                    "type": "start_training",
                    "model": data.get("model"),
                    "rounds": data.get("rounds"), 
                    
                })
                if data.get("rounds"):
                    self.MAX_ROUND_COUNT = data.get("rounds")
            else:
                await self.close(code=4001)
        else:
            await self.close(code=4002)

    async def process_weights(self, data):
        if not self.device:
            return

        weights  = pickle.loads(bytes.fromhex(data["payload"]))
        metrics  = data.get("metrics", [])
        round_no = data.get("round")
        local_data = await self.get_or_create_local_data(self.device)
        await self.save_round_result(self.device, local_data, round_no, metrics)

        self.round_weights[self.device.id] = weights

        # когда ВСЕ текущие клиенты прислали веса — агрегируем
        ready = self.round_weights.keys() == {c.device.id for c in self.connected_clients if c.device}
        if ready:
            await self.aggregate_and_broadcast(round_no, metrics)

    @database_sync_to_async
    def get_average_accuracy(self, round_num):
        from .models import RoundResult
        results = RoundResult.objects.filter(round_number=round_num)
        accs = []
        for r in results:
            for m in r.result:
                if isinstance(m, dict) and "acc" in m:
                    accs.append(m["acc"])
        return sum(accs) / len(accs) if accs else 0.0


    
    # ──────────────── Агрегация + рассылка ─────────────────
    async def aggregate_and_broadcast(self, round_num, metrics):
        if self.agg_data is None:
            self.agg_data = await self.get_or_create_active_agg()

        # После агрегирования, перед broadcast
        avg_accuracy = await self.get_average_accuracy(round_num)

        await self.write_local_data_to_agg()          # сохр. локальные веса
        await self.aggregate_and_save(round_num + 1)  # FedAvg и save()
        current_round = self.agg_data.round_count - 1
        payload = {
            "type": "global_weights",
            "payload": pickle.dumps(self.agg_data.data).hex(),
            "round":   current_round,
            "accuracy": avg_accuracy,
        }
        await self.broadcast_all(payload) 
        await self.broadcast({
            "type": "start_training",
            "round": self.agg_data.round_count,
            "model": "cnn",
        })  

        self.round_weights.clear()

    async def broadcast_all(self, message: dict):
        # Клиентам обучающим
        for c in self.connected_clients:
            await c.send(json.dumps(message))

        # Отправляем фронтенду или другим подписанным получателям
        if self.channel_layer:
            await self.channel_layer.group_send(
                "ui_training",
                {"type": "ui.message", "message": message}
            )
        else:
            print("[WARN] channel_layer is None, skipping group_send")

    async def ui_message(self, event):
        await self.send(json.dumps(event["message"]))

    async def broadcast(self, message):
        for client in self.connected_clients:
            await client.send(json.dumps(message))

    # ─────────────────── помощь БД (sync→async) ────────────
    @database_sync_to_async
    def get_device(self, token):
        from .models import Device
        return Device.objects.filter(device_token=token).first()

    @database_sync_to_async
    def get_active_agg_data(self):
        from .models import AggregetedData
        return (AggregetedData.objects
                .filter(is_active=True)
                .order_by("-created_at")
                .first())

    @database_sync_to_async
    def get_or_create_local_data(self, device):
        from .models import LocalData
        return LocalData.objects.get_or_create(device=device, created_at=now().date())[0]

    @database_sync_to_async
    def save_round_result(self, device, local_data, rnd, metrics):
        from .models import RoundResult
        RoundResult.objects.create(device=device,
                                   local_data=local_data,
                                   round_number=rnd,
                                   result=metrics)

    @database_sync_to_async
    def write_local_data_to_agg(self):
        from .models import LocalData, Device
        import base64, pickle
        for dev_id, w in self.round_weights.items():
            dev = Device.objects.filter(id=dev_id).first()
            if not dev:
                continue
            ld, _ = LocalData.objects.get_or_create(device=dev, created_at=now().date())
            ld.data = base64.b64encode(pickle.dumps(w)).decode()
            ld.save(update_fields=["data"])
            self.agg_data.local_datas.add(ld)




    @database_sync_to_async
    def aggregate_and_save(self, new_round):
        from .models import AggregetedData
        agg = AggregetedData.objects.get(pk=self.agg_data.pk)
        agg.round_count = new_round
        agg.save(aggregate=True)



    @database_sync_to_async
    def get_or_create_active_agg(self):
        from .models import AggregetedData
        obj, _ = AggregetedData.objects.get_or_create(
            is_active=True,
            defaults=dict(round_count=0)
        )
        return obj
