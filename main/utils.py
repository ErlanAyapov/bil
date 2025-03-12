import requests
from .models import Device


def get_device_status(devic_host, device_port):
    url = f'http://{devic_host}:{device_port}/check_status/'
    response = requests.get(url)
    return response.json()


def create_handred_devices():
    for i in range(100):
        Device.objects.create(
            name=f'Шлюз {i+1}',
            ip=f'192.168.1.{i}',
            port=8000,
        )
    
def get_device_tokens():
    devices = [device for device in Device.objects.all()]
    with open('1.env', 'w') as file:
        for index, device in enumerate(devices, start=1): 
            file.write(f'GATEWAY_{index}={device.device_token}\n')