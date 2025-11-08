from django.urls import path
from channels.routing import ProtocolTypeRouter, URLRouter
from main import consumers


application = ProtocolTypeRouter({
    "websocket": URLRouter([
        path("ws/device_status/", consumers.DeviceStatusConsumer.as_asgi()),
        path("ws/device_control/", consumers.DeviceControlConsumer.as_asgi()),
        path("ws/train_model/", consumers.TrainModelConsumer.as_asgi()),

    ]),
})
