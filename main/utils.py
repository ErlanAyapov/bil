import firebase_admin
from firebase_admin import credentials, messaging
# import os
# Инициализация Firebase
cred = credentials.Certificate("../bil7-dfc73-firebase-adminsdk-azxfl-574a75e22d.json")
firebase_admin.initialize_app(cred)

# Функция для отправки уведомлений
def send_notification(registration_token, title, body):
    # Создаем сообщение
    message = messaging.Message(
        notification=messaging.Notification(
            title=title,
            body=body,
        ),
        token=registration_token,  # Токен устройства
    )

    # Отправляем сообщение
    response = messaging.send(message)
    print('Successfully sent message:', response)

