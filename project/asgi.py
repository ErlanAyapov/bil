# project/asgi.py
import os
from django.core.asgi import get_asgi_application
from channels.routing import ProtocolTypeRouter
from project.routing import application as channels_app  # Импорт вашего routing

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'project.settings')

# Важно: используйте channels_app, а не get_asgi_application()
application = ProtocolTypeRouter({
    "http": get_asgi_application(),
    "websocket": channels_app,  # Подключите ваши WebSocket-маршруты
})