# consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
import json, pickle, asyncio
import numpy as np
from django.utils.timezone import now 
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
import weakref
from django.db import transaction
from channels.db import database_sync_to_async


class DeviceStatusConsumer(AsyncWebsocketConsumer):
    # Список всех подключенных клиентов
    # connected_clients = set()
    connected_clients = weakref.WeakSet()

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
            f = Fernet(settings.FERNET_KEY.encode())
            payload = f.decrypt(device_token.encode(), ttl=3600)
            data = json.loads(payload.decode())
            return Device.objects.filter(id=data.get('device_id')).first()
        except (InvalidToken, Exception):
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
            await self.broadcast_all({
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

    async def broadcast_all(self, message):
        for client in self.connected_clients:
            await client.send(json.dumps(message))

    async def send_error(self, message):
        await self.send(json.dumps({
            "type": "error",
            "message": message
        }))


class TrainModelConsumer(AsyncWebsocketConsumer):
    # слабые ссылки, чтобы не удерживать объекты
    connected_clients = weakref.WeakSet()
    aggregations = {}
    agg_init_lock = asyncio.Lock()

    # параметры ожидания и синхронизации
    AGG_TIMEOUT_SEC = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = None
        self.lock = asyncio.Lock()
        self.training_clients = set()   # set(device_id) зафиксированный на старте
        self.round_weights = {}         # {device_id: [layer arrays]}
        self.round_deadline = None
        self.current_model = None       # 'dnn' | 'cnn' | ...
        self.train = None
        self.timeout_task = None
        # текущая Train-сессия (сегодня + model_name)

    async def connect(self):
        await self.accept()
        self.connected_clients.add(self)

        # UI-группа (лог/прогресс)
        if self.channel_layer:
            await self.channel_layer.group_add("ui_training", self.channel_name)

    async def disconnect(self, code):
        self.connected_clients.discard(self)
        if self.channel_layer:
            await self.channel_layer.group_discard("ui_training", self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data or "{}")
        t = data.get("type")

        if t == "hello":
            print("Client connected:", data)
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return

            # если уже есть активная Train и глобальные веса — отдаём
            if self.train and self.train.get("global_weights"):
                await self.send(json.dumps({
                    "type": "global_weights",
                    "payload": pickle.dumps(self.train["global_weights"]).hex(),
                    "round":   self.train["round_count"],
                    "accuracy": None,
                    "model": self.train["model_name"],
                    "train_id": self.train["id"],
                }))

            await self.ui_log(f"Подключен {self.device.name}" )

        elif t == "subscribe":
            # подписка клиента (отправим в UI инфо)
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return

            msg = {
                "type": "subscribe",
                "device_token": self.device.device_token,
                "device_name": data.get("client") or self.device.name,
                "device_id": self.device.id,
            }

            # раньше было: await self.broadcast_all(msg)
            await self.broadcast_all(msg)
        elif t == "ui_sync":
            # пошлём текущий список подписанных устройств (сокетов с device)
            items = []
            for c in list(self.connected_clients):
                dev = getattr(c, "device", None)
                if dev:
                    items.append({
                        "device_id": dev.id,
                        "device_name": getattr(dev, "name", "") or "",
                        "device_token": getattr(dev, "device_token", "") or ""
                    })
            await self.send(json.dumps({"type": "full_subscribers", "items": items}))

        elif t == "start_training":
            # UI-команда: задали модель и лимиты — найдём/создадим Train (сегодня + модель)
            model = (data.get("model") or "dnn").lower()
            max_rounds = int(data.get("rounds") or 50)
            epochs = int(data.get("epochs") or 10)

            self.train = await self.get_or_create_today_train(model, max_rounds, epochs)
            print(f"Training session: {self.train}")
            self.current_model = self.train["model_name"]
            print(f"Training session ready: {self.train}")
            # зафиксируем участников (только реальные устройства с device)
            loop = asyncio.get_running_loop()
            agg = await self._get_agg_state(self.train["id"])
            async with agg["lock"]:
                agg["training_clients"] = {c.device.id for c in self.connected_clients if getattr(c, "device", None)}
                agg["round_weights"] = {}
                agg["round_deadline"] = loop.time() + self.AGG_TIMEOUT_SEC
            await self._schedule_timeout_shared(self.train["id"], self.train["round_count"])

            # разошлём клиентам команду (продолжить с текущего round_count)
            await self.broadcast_all({
                "type": "start_training",
                "model": self.current_model,
                "round": self.train["round_count"],
                "rounds": self.train["max_rounds"],
                "train_id": self.train["id"],
            })
            await self.ui_log(f"▶ Старт обучения: {self.current_model}, раунд с {self.train['round_count']}")

            # если у Train уже есть глобальные веса — полезно дёрнуть их рассылку для новых клиентов
            if self.train.get("global_weights"):
                await self.broadcast_all({
                    "type": "global_weights",
                    "payload": pickle.dumps(self.train["global_weights"]).hex(),
                    "round":   self.train["round_count"],
                    "accuracy": None,
                    "model": self.current_model,
                    "train_id": self.train["id"],
                })

        elif t == "weights":
            # print(f'data weights: {data}')
            print(f"Received weights message from device_token={data.get('device_token')}")
            print(f"train_id: {data.get('train_id')}")

            self.train = await self.get_train_by_id(data.get("train_id"))
            await self.process_weights(data)

        else:
            await self.close(code=4002)

    async def process_weights(self, data):
        # обязательные условия
        # print(f'device: {self.device}, train: {self.train}  ')
        if not self.device:
            return
        if not self.train:
            # если клиент прислал веса до команды старта — игнорируем
            return

        weights  = pickle.loads(bytes.fromhex(data["payload"]))
        round_no = int(data.get("round") or self.train["round_count"])
        metrics  = self._normalize_metrics(data.get("metrics"), round_no)
        print(f"Received weights from {self.device.name} for round {round_no}")
        print(f"Metrics: {metrics}")
        print(f"Weights layers: {len(weights)}")
        # сохраним per-device метрики как раньше (если используешь RoundResult на пер-девайс)
        local_data = await self.get_or_create_local_data(self.device)
        await self.save_device_round_result(self.device, local_data, round_no, metrics, train_id=self.train["id"])

        # запишем веса в буфер текущего раунда
        agg = await self._get_agg_state(self.train["id"])
        async with agg["lock"]:
            agg["round_weights"][self.device.id] = [np.asarray(a) for a in weights]

            have = set(agg["round_weights"].keys())
            goal = set(agg.get("training_clients") or [])
            # Fallback: если snapshot не зафиксирован, берём всех подписанных с устройством
            if not goal:
                goal = {getattr(c.device, 'id', None) for c in list(self.connected_clients) if getattr(c, 'device', None)}
                goal.discard(None)

            loop = asyncio.get_running_loop()
            # Инициализируем дедлайн раунда, если его ещё нет
            if not agg.get("round_deadline"):
                agg["round_deadline"] = loop.time() + self.AGG_TIMEOUT_SEC
                await self._schedule_timeout_shared(self.train["id"], self.train["round_count"]) 
            time_expired = bool(agg.get("round_deadline")) and (loop.time() >= agg["round_deadline"])
            ready = (len(goal) > 0 and have >= goal) or time_expired
        
        print(f'ready to aggregate? {ready} (have {len(have)}/{len(goal)}, expired={time_expired})')
        if ready:
            await self.aggregate_and_broadcast_all(round_no, metrics)
            # подготовка к следующему сбору
            agg = await self._get_agg_state(self.train["id"])
            async with agg["lock"]:
                agg["round_weights"].clear()
                agg["round_deadline"] = asyncio.get_running_loop().time() + self.AGG_TIMEOUT_SEC
            await self._schedule_timeout_shared(self.train["id"], self.train["round_count"]) 

    async def aggregate_and_broadcast_all(self, round_num, metrics):
        """
        FedAvg буфера self.round_weights → обновляем Train.global_weights и Train.round_count,
        пишем агрегированную строку RoundResult (train-wide), шлём global_weights клиентам/в UI.
        """
        print(f"Aggregating weights for round {round_num}...")
        print(f'Train before agg: {self.train}')
        if not self.train:
            return

        # 1) FedAvg
        new_weights = await self.fedavg_current_round()
        if new_weights is None:
            await self.ui_log("⚠ Нет валидных весов для агрегации"); return

        # 2) Обновим Train: глобальные веса + инкремент round_count
        self.train = await self.update_train_after_agg(self.train["id"], new_weights)

        # 3) Усреднённая accuracy по этому round_num (из RoundResult per-device)
        avg_accuracy = await self.get_average_accuracy(self.train["id"], round_num)
        avg_loss = metrics.get("loss") if isinstance(metrics, dict) else None
        print(f"Aggregated round {round_num}: avg_accuracy={avg_accuracy}, avg_loss={avg_loss}")
        # 4) Сохранить «строку истории» для этого Train/round
        await self.save_round_history(
            train_id=self.train["id"],
            round_number=self.train["round_count"],   # уже инкрементированный номер
            avg_accuracy=avg_accuracy,
            avg_loss=avg_loss,
            snapshot_weights=new_weights
        )

        # 5) Разослать всем обновление
        await self.broadcast_all({
            "type": "global_weights",
            "payload": pickle.dumps(new_weights).hex(),
            "round":   self.train["round_count"],   # уже инкрементирован
            "accuracy": avg_accuracy,
            "model": self.train["model_name"],
            "train_id": self.train["id"],
        })
        await self.ui_log(f"[agg] Раунд завершён → {self.train['round_count']} (avg_acc={avg_accuracy})")



        # 6) Стоп/продолжить
        if self.train["round_count"] >= self.train["max_rounds"]:
            await self.mark_train_finished(self.train["id"])
            await self.broadcast_all({
                "type": "training_complete",
                "rounds": self.train["max_rounds"],
                "final_accuracy": avg_accuracy,
                "train_id": self.train["id"],
            })
            await self.ui_log("✔ Обучение завершено")
            return

        # следующий раунд
        await self.broadcast_all({
            "type": "start_training",
            "round": self.train["round_count"],   # теперь точно следующий
            "model": self.train["model_name"],
            "train_id": self.train["id"],
        })


    async def broadcast_all(self, message: dict):
        # клиентам-обучателям
        for c in list(self.connected_clients):
            try:
                await c.send(json.dumps(message))
            except Exception:
                pass
        # UI-группа
        if self.channel_layer:
            await self.channel_layer.group_send("ui_training", {"type": "ui.message", "message": message})

    async def broadcast_all(self, message: dict):
        for c in list(self.connected_clients):
            try:
                await c.send(json.dumps(message))
            except Exception:
                pass

    async def ui_message(self, event):
        await self.send(json.dumps(event["message"]))

    async def ui_log(self, text: str):
        if self.channel_layer:
            await self.channel_layer.group_send("ui_training", {"type": "ui.message", "message": {"type":"train_log","text": text}})

    async def _get_agg_state(self, train_id: int):
        if train_id in self.aggregations:
            return self.aggregations[train_id]
        async with self.agg_init_lock:
            st = self.aggregations.get(train_id)
            if st:
                return st
            self.aggregations[train_id] = {
                "lock": asyncio.Lock(),
                "training_clients": set(),
                "round_weights": {},
                "round_deadline": None,
                "timeout_task": None,
            }
            return self.aggregations[train_id]

    async def _schedule_timeout_shared(self, train_id: int, round_no: int):
        st = await self._get_agg_state(train_id)
        async with st["lock"]:
            tt = st.get("timeout_task")
            if tt and not tt.done():
                tt.cancel()
            st["timeout_task"] = asyncio.create_task(self._timeout_trigger_shared(train_id, round_no))

    async def _timeout_trigger_shared(self, train_id: int, round_no: int):
        try:
            await asyncio.sleep(self.AGG_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return
        st = await self._get_agg_state(train_id)
        # If round already advanced, nothing to do
        current_round = self.train["round_count"] if self.train else None
        if current_round != round_no:
            return
        if st["round_weights"]:
            await self.ui_log(f"[timeout] Aggregating on timeout for round {round_no}. Collected: {len(st['round_weights'])} clients")
            await self.aggregate_and_broadcast_all(round_no, {"timeout": True})

    async def _timeout_trigger(self, round_no: int):
        try:
            await asyncio.sleep(self.AGG_TIMEOUT_SEC)
        except asyncio.CancelledError:
            return
        # On timeout, aggregate whatever has been collected for this round
        async with self.lock:
            # If round already advanced, nothing to do
            if not self.train or self.train.get("round_count") != round_no:
                return
        if self.round_weights:
            await self.ui_log(f"[timeout] Aggregating on timeout for round {round_no}. Collected: {len(self.round_weights)} clients")
            await self.aggregate_and_broadcast_all(round_no, {"timeout": True})

    # ---------------------- DB helpers ----------------------

    @database_sync_to_async
    def get_device(self, token):
        from .models import Device
        if not token:
            return None
        try: 
            return Device.objects.get(device_token=token)
        except (InvalidToken, Exception):
            return None
        

    @database_sync_to_async
    def get_train_by_id(self, train_id):
        from .models import Train
        try:
            obj = Train.objects.get(id=train_id)
            return {
                "id": obj.id,
                "date": obj.date.isoformat(),
                "model_name": obj.model_name,
                "round_count": obj.round_count,
                "max_rounds": obj.max_rounds,
                "epochs": obj.epochs,
                "global_weights": obj.global_weights,     # уже сериализовано
                "is_active": obj.is_active,
                "ready": getattr(obj, "ready", False),
                "created": False,
            }

        except Train.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_today_train(self, model_name: str, max_rounds: int, epochs: int):
        from .models import Train
        today = now().date()

        # блокируем строку на время правок (если существует)
        try:
            obj = (
                Train.objects.select_for_update()
                .get(date=today, model_name=model_name)
            )
            created = False
        except Train.DoesNotExist:
            obj = Train(
                date=today,
                model_name=model_name,
                max_rounds=max_rounds,
                epochs=epochs,
                is_active=True,
                round_count=0,
            )
            obj.save()
            created = True

        # точечно обновляем, если надо
        changed_fields = []
        if obj.max_rounds != max_rounds:
            obj.max_rounds = max_rounds; changed_fields.append("max_rounds")
        if obj.epochs != epochs:
            obj.epochs = epochs; changed_fields.append("epochs")
        if not obj.is_active:
            obj.is_active = True; changed_fields.append("is_active")

        if changed_fields:
            obj.save(update_fields=changed_fields)

        # !!! сериализуем веса для безопасной передачи в async/JSON

        return {
            "id": obj.id,
            "date": obj.date.isoformat(),
            "model_name": obj.model_name,
            "round_count": obj.round_count,
            "max_rounds": obj.max_rounds,
            "epochs": obj.epochs,
            "global_weights": obj.global_weights,     # уже сериализовано
            "is_active": obj.is_active,
            "ready": getattr(obj, "ready", False),
            "created": created,
        }

    @database_sync_to_async
    def get_or_create_local_data(self, device):
        from .models import LocalData
        return LocalData.objects.get_or_create(device=device, created_at=now().date())[0]

    @database_sync_to_async
    def save_device_round_result(self, device, local_data, rnd, metrics, train_id=None):
        from .models import RoundResult, Train
        train = Train.objects.filter(id=train_id).first() if train_id else None
        RoundResult.objects.create(
            train=train, device=device, local_data=local_data,
            round_number=rnd, result=metrics
        )

    @database_sync_to_async
    def update_train_after_agg(self, train_id, new_weights):
        from .models import Train
        tr = Train.objects.get(pk=train_id)
        tr.global_weights = new_weights
        tr.round_count = tr.round_count + 1
        tr.save(update_fields=["global_weights","round_count"])
        return dict(id=tr.id, date=str(tr.date), model_name=tr.model_name,
                    round_count=tr.round_count, max_rounds=tr.max_rounds,
                    epochs=tr.epochs, global_weights=tr.global_weights,
                    is_active=tr.is_active, ready=tr.ready)

    @database_sync_to_async
    def mark_train_finished(self, train_id):
        from .models import Train
        tr = Train.objects.get(pk=train_id)
        tr.is_active = False
        tr.ready = True
        tr.save(update_fields=["is_active","ready"])

    @database_sync_to_async
    def save_round_history(self, train_id, round_number, avg_accuracy, avg_loss, snapshot_weights):
        # Skip saving aggregated history into RoundResult to avoid NOT NULL on local_data
        return None
        from .models import Train, RoundResult
        tr = Train.objects.get(pk=train_id)
        # агрегированная строка истории (train-wide):
        rr, _ = RoundResult.objects.update_or_create(
            train=tr, device_id=tr.id,  # фиктивно: можно завести отдельную модель AggregatedRound
            local_data_id=None,         # или позволить null=True у local_data, если хочешь хранить снапшот тут
            round_number=round_number,
            defaults=dict(avg_accuracy=avg_accuracy, avg_loss=avg_loss, result={"snapshot": True})
        )
        # Если хочешь именно выделенную модель «AggregatedRound», создай её. Здесь оставил компактный путь.

    @database_sync_to_async
    def get_average_accuracy(self, train_id, round_num):
        from .models import RoundResult, Train
        # возьмём только per-device записи этого train/round
        accs = []
        qs = RoundResult.objects.filter(train_id=train_id, round_number=round_num)
        for r in qs:
            m = r.result or {}
            if isinstance(m, str):
                try:
                    import json as _json
                    m = _json.loads(m)
                except Exception:
                    m = {}
            val = None
            if isinstance(m, dict):
                val = m.get("accuracy") or m.get("val_accuracy") or m.get("acc")
            if isinstance(val, (int, float)):
                accs.append(float(val))
        return sum(accs) / len(accs) if accs else 0.0

    @database_sync_to_async
    def fedavg_current_round(self):
        import numpy as np
        st = self.aggregations.get(self.train["id"]) if self.train else None
        weights = [w for w in (st["round_weights"].values() if st else self.round_weights.values())]
        if not weights:
            return None
        num_layers = len(weights[0])
        for w in weights:
            if len(w) != num_layers:
                raise ValueError("Inconsistent number of layers across clients")
        agg = []
        for k in range(num_layers):
            layer_stack = np.stack([w[k] for w in weights], axis=0)
            agg.append(layer_stack.mean(axis=0).tolist())
        return agg

    # ---------- утилита нормализации метрик ----------
    def _normalize_metrics(self, metrics, round_no):
        out = {"round": round_no, "loss": None, "accuracy": None, "val_loss": None, "val_accuracy": None}
        if metrics is None:
            return out
        if isinstance(metrics, dict):
            out.update({
                "loss": metrics.get("loss", metrics.get("val_loss")),
                "accuracy": metrics.get("accuracy", metrics.get("val_accuracy", metrics.get("acc"))),
                "val_loss": metrics.get("val_loss"),
                "val_accuracy": metrics.get("val_accuracy"),
            })
            return out
        if isinstance(metrics, str):
            try:
                parsed = json.loads(metrics)
                return self._normalize_metrics(parsed, round_no)
            except Exception:
                return out
        if isinstance(metrics, list):
            for item in metrics:
                if isinstance(item, dict):
                    return self._normalize_metrics(item, round_no)
        return out

