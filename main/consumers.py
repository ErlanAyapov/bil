# consumers.py
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async


import json, pickle, asyncio, logging
import numpy as np
from django.utils.timezone import now
from django.conf import settings
from cryptography.fernet import Fernet, InvalidToken
import weakref
from django.db import transaction
from channels.db import database_sync_to_async

logger = logging.getLogger(__name__)

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
            return Device.objects.get(device_token=device_token)
        except (InvalidToken, Exception):
            return None
        
    async def send_error(self, message):
        await self.send(json.dumps({
            "type": "error",
            "message": message
        }))

    @database_sync_to_async
    def get_all_devices(self):
        from .models import Device
        return list(Device.objects.values(
            "device_token",
            "name"
        ))

    async def receive(self, text_data):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send_error("Invalid JSON")
            return

        msg_type = data.get("type")

        if msg_type == "heartbeat":
            await self.send(json.dumps({"type": "pong"}))
            return

        if msg_type == "prediction" or "prediction" in data:
            await self._handle_prediction(data)
            return

        await self.send_error("Unsupported message type")

    async def broadcast_all(self, message):
        for client in list(self.connected_clients):
            try:
                await client.send(json.dumps(message))
            except Exception:
                continue

    async def _handle_prediction(self, data):
        device_token = data.get("device_token")
        if not device_token:
            await self.send_error("device_token is required")
            return

        device = await self.get_device(device_token)
        if not device:
            await self.send_error("Device not found")
            return

        prediction = data.get("prediction", 0)
        status = "danger" if prediction not in (0, "0", None) else "safe"
        confidence = data.get("confidence")
        prediction_label = data.get("prediction_label", "-")
        ip_data = data.get("ip_data") or {}

        await self._touch_device(device)
        await self._store_prediction(device, data)

        await self.send(json.dumps({"type": "ack", "status": "ok"}))

        payload_msg = {
            "type": "status_update",
            "device_token": device_token,
            "status": status,
            "device_name": device.name,
            "device_id": device.id,
            "prediction": prediction,
            "confidence": confidence,
            "prediction_label": prediction_label,
            "ip_data": ip_data,
            "mode": data.get("mode"),
            "samples": data.get("samples"),
            "source": data.get("source"),
        }
        await self.broadcast_all(payload_msg)

    @database_sync_to_async
    def _touch_device(self, device):
        device.last_seen = now()
        device.is_online = True
        device.save(update_fields=["last_seen", "is_online"])

    @database_sync_to_async
    def _store_prediction(self, device, payload):
        from .models import PredictResult

        PredictResult.objects.create(
            device=device,
            results={
                "prediction": payload.get("prediction"),
                "prediction_label": payload.get("prediction_label"),
                "confidence": payload.get("confidence"),
                "samples": payload.get("samples"),
                "ip_data": payload.get("ip_data"),
                "mode": payload.get("mode"),
                "source": payload.get("source"),
                "timestamp": payload.get("timestamp"),
            }
        )


class DeviceControlConsumer(AsyncWebsocketConsumer):
    """Control plane for advanced device agents (see client_sample/device_agent.py)."""

    device_clients = {}
    device_lock = asyncio.Lock()
    ui_clients = weakref.WeakSet()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = None
        self.current_mode = None
        self.is_ui = False

    async def connect(self):
        await self.accept()

    async def disconnect(self, close_code):
        if self.device:
            await self._deregister_device(self.device.id)
            await self._broadcast_ui({
                "type": "device_offline",
                "device_id": self.device.id,
                "device_name": getattr(self.device, "name", ""),
            })
        if self in self.ui_clients:
            self.ui_clients.discard(self)

    async def receive(self, text_data):
        try:
            data = json.loads(text_data or "{}")
        except json.JSONDecodeError:
            await self.send(json.dumps({"type": "error", "message": "Invalid JSON"}))
            return

        msg_type = data.get("type")

        if msg_type == "heartbeat":
            await self.send(json.dumps({"type": "pong"}))
            return
        if msg_type == "hello":
            await self._handle_hello(data)
            return
        if msg_type == "inference_event":
            await self._handle_inference_event(data)
            return
        if msg_type == "status":
            await self._handle_status_payload(data)
            return
        if msg_type == "mode_changed":
            self.current_mode = data.get("mode")
            await self._broadcast_ui({
                "type": "mode_changed",
                "device_id": getattr(self.device, "id", None),
                "mode": self.current_mode,
            })
            return
        if msg_type == "run_ack":
            await self._broadcast_ui({
                "type": "run_ack",
                "device_id": getattr(self.device, "id", None),
                "mode": data.get("mode"),
            })
            return
        if msg_type == "ui_subscribe":
            self.is_ui = True
            self.ui_clients.add(self)
            await self._send_ui_snapshot()
            return
        if msg_type == "command":
            await self._handle_ui_command(data)
            return

        await self.send(json.dumps({"type": "error", "message": f"Unknown command: {msg_type}"}))

    async def _handle_hello(self, data):
        device = await self.get_device(data.get("device_token"))
        if not device:
            await self.send(json.dumps({"type": "error", "message": "Device not found"}))
            return

        self.device = device
        self.current_mode = data.get("mode")
        await self._touch_device(device)
        await self._register_device(device.id)

        await self.send(json.dumps({
            "type": "hello_ack",
            "device_id": device.id,
            "device_name": device.name,
            "mode": self.current_mode,
            "capabilities": data.get("capabilities") or {},
        }))
        await self._broadcast_ui({
            "type": "device_online",
            "device_id": device.id,
            "device_name": device.name,
            "mode": self.current_mode,
            "capabilities": data.get("capabilities") or {},
        })

    async def _handle_status_payload(self, data):
        if not self.device:
            await self.send(json.dumps({"type": "error", "message": "Device not authenticated"}))
            return

        await self._touch_device(self.device)
        await self.send(json.dumps({"type": "ack", "status": "ok"}))
        await self._broadcast_ui({
            "type": "status",
            "device_id": self.device.id,
            "payload": data,
        })

    async def _handle_inference_event(self, data):
        await self._broadcast_ui({
            "type": "inference_event",
            "device_id": getattr(self.device, "id", None),
            "event": data.get("event"),
            "mode": data.get("mode"),
            "payload": data.get("payload"),
            "ts": data.get("ts"),
        })
        await self.send(json.dumps({"type": "ack", "status": "event_received"}))

    async def _handle_ui_command(self, data):
        if not self.is_ui:
            await self.send(json.dumps({"type": "error", "message": "Commands available only for UI subscribers"}))
            return
        try:
            device_id = int(data.get("device_id"))
        except (TypeError, ValueError):
            await self.send(json.dumps({"type": "error", "message": "device_id is required"}))
            return
        command = (data.get("command") or "").strip()
        if not command:
            await self.send(json.dumps({"type": "error", "message": "command is required"}))
            return
        params = data.get("params") or {}
        message = {"type": command}
        if isinstance(params, dict):
            message.update(params)

        success = await self.send_command(device_id, message)
        await self.send(json.dumps({
            "type": "command_response",
            "device_id": device_id,
            "command": command,
            "success": bool(success),
        }))

    async def _send_ui_snapshot(self):
        summary = []
        async with self.device_lock:
            for dev_id, consumer in self.device_clients.items():
                summary.append({
                    "device_id": dev_id,
                    "device_name": getattr(consumer.device, "name", ""),
                    "mode": consumer.current_mode,
                })
        await self.send(json.dumps({"type": "devices_snapshot", "items": summary}))

    async def _broadcast_ui(self, message):
        for client in list(self.ui_clients):
            try:
                await client.send(json.dumps(message))
            except Exception:
                continue

    @classmethod
    async def send_command(cls, device_id, payload):
        async with cls.device_lock:
            consumer = cls.device_clients.get(device_id)
        if not consumer:
            return False
        try:
            await consumer.send(json.dumps(payload))
            return True
        except Exception:
            return False

    async def _register_device(self, device_id):
        async with self.device_lock:
            self.device_clients[device_id] = self

    async def _deregister_device(self, device_id):
        async with self.device_lock:
            if self.device_clients.get(device_id) is self:
                self.device_clients.pop(device_id, None)

    @database_sync_to_async
    def _touch_device(self, device):
        device.last_seen = now()
        device.is_online = True
        device.save(update_fields=["last_seen", "is_online"])

    @database_sync_to_async
    def get_device(self, token):
        from .models import Device
        if not token:
            return None
        try:
            return Device.objects.get(device_token=token)
        except (InvalidToken, Exception):
            return None

    async def send_error(self, message):
        await self.send(json.dumps({
            "type": "error",
            "message": message
        }))


class TrainModelConsumer(AsyncWebsocketConsumer):
    import weakref as _weakref
    connected_clients = _weakref.WeakSet()  # слабые ссылки, чтобы не удерживать объекты
    aggregations = {}
    agg_init_lock = asyncio.Lock()

    AGG_TIMEOUT_SEC = 20

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.device = None
        self.lock = asyncio.Lock()
        self.training_clients = set()
        self.round_weights = {}
        self.round_deadline = None
        self.current_model = None
        self.train = None
        self.timeout_task = None
        self.is_ui = False

    # -------------- lifecycle --------------
    async def connect(self):
        await self.accept()
        self.connected_clients.add(self)

    async def disconnect(self, code):
        self.connected_clients.discard(self)
        if self.is_ui and self.channel_layer:
            await self.channel_layer.group_discard("ui_training", self.channel_name)

    async def _ensure_ui_channel(self):
        if self.is_ui or not self.channel_layer:
            return
        await self.channel_layer.group_add("ui_training", self.channel_name)
        self.is_ui = True

    # -------------- helpers: UI emit + broadcast --------------
    async def ui_message(self, event):
        # handler для group_send(type="ui.message", ...)
        await self.send(json.dumps(event["message"]))

    async def ui_emit(self, message: dict):
        """Отправить только в UI-группу."""
        if self.channel_layer:
            await self.channel_layer.group_send("ui_training", {"type": "ui.message", "message": message})

    async def ui_log(self, text: str):
        await self.ui_emit({"type": "train_log", "text": text})

    async def broadcast_all(self, message: dict):
        """Рассылка всем подключенным сокетам (устройствам и UI) + в UI-группу."""
        # прямые соединения
        for c in list(self.connected_clients):
            try:
                await c.send(json.dumps(message))
            except Exception:
                pass
        # UI-группа (на случай, если часть UI только в группе)
        await self.ui_emit(message)

    # -------------- receive --------------
    async def receive(self, text_data):
        data = json.loads(text_data or "{}")
        t = data.get("type")

        if t == "hello":
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return

            # если уже есть активная Train и глобальные веса — отдать
            if self.train and self.train.get("global_weights"):
                await self.send(json.dumps({
                    "type": "global_weights",
                    "payload": pickle.dumps(self.train["global_weights"]).hex(),
                    "round":   self.train["round_count"],
                    "accuracy": None,
                    "model": self.train["model_name"],
                    "train_id": self.train["id"],
                }))
            await self.ui_log(f"Подключен {self.device.name}")

        elif t == "subscribe":
            self.device = await self.get_device(data.get("device_token"))
            if not self.device:
                await self.close(code=4001); return

            msg = {
                "type": "subscribe",
                "device_token": self.device.device_token,
                "device_name": data.get("client") or self.device.name,
                "device_id": self.device.id,
            }
            await self.broadcast_all(msg)

        elif t == "ui_sync":
            await self._ensure_ui_channel()
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
            await self._ensure_ui_channel()
            model = (data.get("model") or "dnn").lower()
            max_rounds = int(data.get("rounds") or 50)
            epochs = int(data.get("epochs") or 10)

            self.train = await self.get_or_create_today_train(model, max_rounds, epochs)
            self.current_model = self.train["model_name"]

            loop = asyncio.get_running_loop()
            agg = await self._get_agg_state(self.train["id"])
            async with agg["lock"]:
                agg["training_clients"] = {c.device.id for c in self.connected_clients if getattr(c, "device", None)}
                agg["round_weights"] = {}
                agg["round_deadline"] = loop.time() + self.AGG_TIMEOUT_SEC
            await self._schedule_timeout_shared(self.train["id"], self.train["round_count"])

            payload_msg = {
                "type": "start_training",
                "model": self.current_model,
                "round": self.train["round_count"],
                "rounds": self.train["max_rounds"],
                "train_id": self.train["id"],
            }
            await self.broadcast_all(payload_msg)
            await self.ui_log(f"? Старт обучения: {self.current_model}, раунд с {self.train['round_count']}")

            if self.train.get("global_weights"):
                payload_msg = {
                    "type": "global_weights",
                    "payload": pickle.dumps(self.train["global_weights"]).hex(),
                    "round":   self.train["round_count"],
                    "accuracy": None,
                    "model": self.current_model,
                    "train_id": self.train["id"],
                }
                await self.broadcast_all(payload_msg)

        elif t == "weights":
            # Получены локальные веса/метрики от клиента
            print(f"Received weights message from device_token={data.get('device_token')}")
            print(f"train_id: {data.get('train_id')}")
            self.train = await self.get_train_by_id(data.get("train_id"))
            await self.process_weights(data)

        else:
            await self.close(code=4002)

    # -------------- core per-message --------------
    async def process_weights(self, data):
        if not self.device or not self.train:
            return

        weights  = pickle.loads(bytes.fromhex(data["payload"]))
        round_no = int(data.get("round") or self.train["round_count"])
        metrics  = self._normalize_metrics(data.get("metrics"), round_no)

        print(f"Received weights from {self.device.name} for round {round_no}")
        print(f"Metrics: {metrics}")
        print(f"Weights layers: {len(weights)}")

        # 1) сохранить per-device метрики/строку
        local_data = await self.get_or_create_local_data(self.device)
        await self.save_device_round_result(self.device, local_data, round_no, metrics, train_id=self.train["id"])

        # 2) UI: онлайн-обновление графика Loss (если есть)
        if isinstance(metrics, dict) and (metrics.get("loss") is not None):
            await self.ui_emit({"type": "train_loss", "round": round_no, "loss": metrics.get("loss")})

        # 3) сложить веса в буфер текущего раунда
        have_snapshot = set()
        goal_snapshot = set()
        time_expired = False
        ready = False
        agg = await self._get_agg_state(self.train["id"])
        async with agg["lock"]:
            agg["round_weights"][self.device.id] = [np.asarray(a) for a in weights]

            have = set(agg["round_weights"].keys())
            goal = set(agg.get("training_clients") or [])
            if not goal:
                goal = {getattr(c.device, "id", None) for c in list(self.connected_clients) if getattr(c, "device", None)}
                goal.discard(None)

            loop = asyncio.get_running_loop()
            if not agg.get("round_deadline"):
                agg["round_deadline"] = loop.time() + self.AGG_TIMEOUT_SEC
                await self._schedule_timeout_shared(self.train["id"], self.train["round_count"])
            time_expired = bool(agg.get("round_deadline")) and (loop.time() >= agg["round_deadline"])
            have_snapshot = set(have)
            goal_snapshot = set(goal)
            ready = (len(goal_snapshot) > 0 and have_snapshot >= goal_snapshot) or time_expired

        # 4) UI: онлайн-агрегированная confusion по уже полученным устройствам (не ждём FedAvg)
        aggregated = await self.get_aggregated_confusion(self.train["id"], round_no)
        if aggregated and aggregated.get("confusion"):
            await self.ui_emit({
                "type": "confusion_matrix",
                "labels": aggregated.get("classes"),
                "matrix": aggregated.get("confusion"),
                "support": aggregated.get("support"),
            })

        print(f"ready to aggregate? {ready} (have {len(have_snapshot)}/{len(goal_snapshot)}, expired={time_expired})")
        if ready:
            if have_snapshot:
                await self._set_training_clients(self.train["id"], have_snapshot)
            await self.aggregate_and_broadcast_all(round_no, metrics)
            # подготовка к следующему сбору
            agg = await self._get_agg_state(self.train["id"])
            async with agg["lock"]:
                agg["round_weights"].clear()
                agg["round_deadline"] = asyncio.get_running_loop().time() + self.AGG_TIMEOUT_SEC
            await self._schedule_timeout_shared(self.train["id"], self.train["round_count"])

    async def aggregate_and_broadcast_all(self, round_num, metrics):
        """
        FedAvg буфера > обновляем Train, пишем историю, шлём global_weights и UI-метрики.
        """
        print(f"Aggregating weights for round {round_num}...")
        if not self.train:
            return

        # 1) FedAvg
        new_weights = await self.fedavg_current_round()
        if new_weights is None:
            await self.ui_log("? Нет валидных весов для агрегации"); return

        # 2) агрегированная матрица за раунд (если есть)
        aggregated = await self.get_aggregated_confusion(self.train["id"], round_num)
        new_global_confusion = aggregated if aggregated else None

        # 3) Обновим Train (веса + счётчик + глобальная матрица)
        self.train = await self.update_train_after_agg(self.train["id"], new_weights, new_global_confusion)

        # 4) Средняя accuracy по раунду (из RoundResult per-device)
        avg_accuracy = await self.get_average_accuracy(self.train["id"], round_num)
        avg_loss = metrics.get("loss") if isinstance(metrics, dict) else None
        print(f"Aggregated round {round_num}: avg_accuracy={avg_accuracy}, avg_loss={avg_loss}")

        # 5) История — опционально (оставлено как в исходнике)
        await self.save_round_history(
            train_id=self.train["id"],
            round_number=self.train["round_count"],
            avg_accuracy=avg_accuracy,
            avg_loss=avg_loss,
            snapshot_weights=new_weights
        )

        # 6) Разослать обновлённые веса и метрики
        payload_msg = {
            "type": "global_weights",
            "payload": pickle.dumps(new_weights).hex(),
            "round":   self.train["round_count"],
            "accuracy": avg_accuracy,
            "model": self.train["model_name"],
            "train_id": self.train["id"],
        }
        if new_global_confusion and new_global_confusion.get("confusion"):
            payload_msg.update({
                "confusion": new_global_confusion.get("confusion"),
                "classes": new_global_confusion.get("classes"),
                "support": new_global_confusion.get("support"),
            })
        await self.broadcast_all(payload_msg)
        # Обновить loss-график для UI, если значение есть
        if avg_loss is not None:
            await self.ui_emit({"type": "train_loss", "round": self.train["round_count"], "loss": avg_loss})

        # Актуальная агрегированная confusion после FedAvg — отдельно в UI
        if new_global_confusion and new_global_confusion.get("confusion"):
            await self.ui_emit({
                "type": "confusion_matrix",
                "labels": new_global_confusion.get("classes"),
                "matrix": new_global_confusion.get("confusion"),
                "support": new_global_confusion.get("support"),
            })

        await self.ui_log(f"[agg] Раунд завершён > {self.train['round_count']} (avg_acc={avg_accuracy})")

        # 7) Остановка/продолжение
        if self.train["round_count"] >= self.train["max_rounds"]:
            await self.mark_train_finished(self.train["id"])
            # финальная матрица есть в Train.global_confusion — отдаём в UI
            final_conf = self.train.get("global_confusion") or new_global_confusion
            msg = {
                "type": "training_complete",
                "rounds": self.train["max_rounds"],
                "final_accuracy": avg_accuracy,
                "train_id": self.train["id"],
            }
            if final_conf and final_conf.get("confusion"):
                msg.update({
                    "labels": final_conf.get("classes"),
                    "matrix": final_conf.get("confusion"),
                    "support": final_conf.get("support"),
                })
            await self.broadcast_all(msg)
            await self.ui_log("? Обучение завершено")
            return

        # следующий раунд
        await self.broadcast_all({
            "type": "start_training",
            "round": self.train["round_count"],
            "model": self.train["model_name"],
            "train_id": self.train["id"],
        })

    # -------------- shared timeout (как было) --------------
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

    async def _set_training_clients(self, train_id: int, client_ids):
        st = await self._get_agg_state(train_id)
        async with st["lock"]:
            st["training_clients"] = set(client_ids or [])

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
        current_round = self.train["round_count"] if self.train else None
        if current_round != round_no:
            return
        if st["round_weights"]:
            have = set(st["round_weights"].keys())
            if have:
                await self._set_training_clients(train_id, have)
            await self.ui_log(f"[timeout] Aggregating on timeout for round {round_no}. Collected: {len(st['round_weights'])} clients")
            await self.aggregate_and_broadcast_all(round_no, {"timeout": True})

    # -------------- DB/helpers (как у вас, с правками сигнатур) --------------
    @database_sync_to_async
    def get_device(self, token):
        from .models import Device
        if not token:
            return None
        try:
            return Device.objects.get(device_token=token)
        except Exception:
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
                "global_weights": obj.global_weights,
                "is_active": obj.is_active,
                "ready": getattr(obj, "ready", False),
                "created": False,
                "global_confusion": getattr(obj, "global_confusion", None),
            }
        except Train.DoesNotExist:
            return None

    @database_sync_to_async
    def get_or_create_today_train(self, model_name: str, max_rounds: int, epochs: int):
        from .models import Train
        today = now().date()
        try:
            obj = Train.objects.select_for_update().get(date=today, model_name=model_name)
            created = False
        except Train.DoesNotExist:
            obj = Train(
                date=today, model_name=model_name,
                max_rounds=max_rounds, epochs=epochs,
                is_active=True, round_count=0,
            )
            obj.save()
            created = True

        changed_fields = []
        if obj.max_rounds != max_rounds: obj.max_rounds = max_rounds; changed_fields.append("max_rounds")
        if obj.epochs != epochs: obj.epochs = epochs; changed_fields.append("epochs")
        if not obj.is_active: obj.is_active = True; changed_fields.append("is_active")
        if changed_fields: obj.save(update_fields=changed_fields)

        return {
            "id": obj.id,
            "date": obj.date.isoformat(),
            "model_name": obj.model_name,
            "round_count": obj.round_count,
            "max_rounds": obj.max_rounds,
            "epochs": obj.epochs,
            "global_weights": obj.global_weights,
            "is_active": obj.is_active,
            "ready": getattr(obj, "ready", False),
            "created": created,
            "global_confusion": getattr(obj, "global_confusion", None),
        }

    @database_sync_to_async
    def get_or_create_local_data(self, device):
        from .models import LocalData
        return LocalData.objects.get_or_create(device=device, created_at=now().date())[0]

    @database_sync_to_async
    def save_device_round_result(self, device, local_data, rnd, metrics, train_id=None):
        from .models import RoundResult
        RoundResult.objects.create(
            train_id=train_id, device=device, local_data=local_data,
            round_number=rnd, result=metrics
        )

    @database_sync_to_async
    def update_train_after_agg(self, train_id, new_weights, new_global_confusion):
        from .models import Train
        tr = Train.objects.get(pk=train_id)
        tr.global_weights = new_weights
        # сохраняем глобальную confusion, если рассчитана
        if new_global_confusion is not None:
            tr.global_confusion = new_global_confusion
            tr.save(update_fields=["global_weights", "round_count", "global_confusion"])
        else:
            tr.save(update_fields=["global_weights", "round_count"])
        tr.round_count = tr.round_count + 1
        tr.save(update_fields=["round_count"])
        return dict(
            id=tr.id, date=str(tr.date), model_name=tr.model_name,
            round_count=tr.round_count, max_rounds=tr.max_rounds,
            epochs=tr.epochs, global_weights=tr.global_weights,
            is_active=tr.is_active, ready=getattr(tr, "ready", False),
            global_confusion=getattr(tr, "global_confusion", None)
        )

    @database_sync_to_async
    def mark_train_finished(self, train_id):
        from .models import Train
        tr = Train.objects.get(pk=train_id)
        tr.is_active = False
        tr.ready = True
        tr.save(update_fields=["is_active","ready"])

    @database_sync_to_async
    def save_round_history(self, train_id, round_number, avg_accuracy, avg_loss, snapshot_weights):
        # Оставлено выключенным (как в исходнике)
        return None

    @database_sync_to_async
    def get_average_accuracy(self, train_id, round_num):
        from .models import RoundResult
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
    def get_aggregated_confusion(self, train_id, round_num):
        from .models import RoundResult
        import numpy as _np
        qs = RoundResult.objects.filter(train_id=train_id, round_number=round_num)
        confusion_sum = None
        support_sum = None
        classes = None
        for r in qs:
            m = r.result or {}
            if isinstance(m, str):
                try:
                    import json as _json
                    m = _json.loads(m)
                except Exception:
                    m = {}
            conf = m.get("confusion")
            supp = m.get("support")
            cls = m.get("classes")
            if conf is not None:
                try:
                    arr = _np.array(conf, dtype=float)
                    confusion_sum = arr if confusion_sum is None else (confusion_sum + arr)
                except Exception:
                    pass
            if supp is not None:
                try:
                    arrs = _np.array(supp, dtype=float)
                    support_sum = arrs if support_sum is None else (support_sum + arrs)
                except Exception:
                    pass
            if cls is not None and classes is None:
                classes = cls
        if confusion_sum is None:
            return None
        return {"confusion": confusion_sum.tolist(),
                "support": support_sum.tolist() if support_sum is not None else None,
                "classes": classes}

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

    # ---------- нормализация метрик ----------
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
            if "confusion" in metrics: out["confusion"] = metrics.get("confusion")
            if "support" in metrics:   out["support"] = metrics.get("support")
            if "classes" in metrics:   out["classes"] = metrics.get("classes")
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



