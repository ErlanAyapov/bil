from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
import json
import datetime
import logging
import numpy as np
from .models import Device, LocalData, AggregetedData
from django.views.generic import ListView
import os
from django.shortcuts import render, redirect

logger = logging.getLogger(__name__)

# Create your views here.
def main(request): 
    return render(request, 'main/main.html')

def start_training(request):
    if request.method == 'POST':
        # Путь к .env файлу
        dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')

        # Чтение текущего содержимого .env файла
        with open(dotenv_path, 'r') as file:
            lines = file.readlines()

        # Обновление значения TRAIN_STATUS
        updated_lines = []
        train_status_found = False
        for line in lines:
            if line.startswith("TRAIN_STATUS="):
                updated_lines.append("TRAIN_STATUS=RUN\n")
                train_status_found = True
            else:
                updated_lines.append(line)

        # Если TRAIN_STATUS не найден, добавляем его
        if not train_status_found:
            updated_lines.append("TRAIN_STATUS=RUN\n")

        # Запись обновленного содержимого обратно в .env файл
        with open(dotenv_path, 'w') as file:
            file.writelines(updated_lines)

        print("Training status updated to RUN in .env file.")

        # Здесь можно добавить логику для запуска обучения
        # return JsonResponse({'status': 'Training started', 'train_status': 'RUN'})
        return redirect('aggregated_data_list')
    
    return JsonResponse({'status': 'Invalid request'}, status=400)

def get_train_status(): 
    dotenv_path = os.path.join(os.path.dirname(__file__), '..', '.env')
    try:
        with open(dotenv_path, 'r') as file:
            for line in file:
                if line.startswith("TRAIN_STATUS="):
                    return line.strip().split("=")[1]
    except FileNotFoundError:
        pass
    return "STOP"

def check_training_status(request):
    status = get_train_status()
    return JsonResponse({'train_status': status})

class AggregatedDataListView(ListView):
    model = AggregetedData
    template_name = 'main/aggregated_data_list.html'
    ordering = ['-created_at']


@method_decorator(csrf_exempt, name='dispatch')
class AcceptWeightsView(View):
    def get(self, request):
        if "get_global_weights" in request.path:
            try:
                global_data = AggregetedData.objects.get(created_at=datetime.date.today())
                return JsonResponse({'status': 'ok', 'weights': global_data.data}, status=200)
            except AggregetedData.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Global weights not found'}, status=404)
        return JsonResponse({'status': 'error'}, status=400)

    def post(self, request):
        logger.info(f"Request path: {request.path}")

        try:
            data = json.loads(request.body)
            logger.info(f"Received data: {data}")
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

        if "save_local_weights" in request.path:
            device_name = data.get('device')
            weight = data.get('weight')
            ip = data.get('ip')
            port = data.get('port')

            logger.info(f"Device: {device_name}, weight: {weight}, ip: {ip}, port: {port}")

            if not device_name or weight is None or not ip or not port:
                return JsonResponse({'status': 'error', 'message': 'Not all required fields are filled'}, status=400)

            # Если weight — это массив NumPy, конвертируем в list
            if isinstance(weight, np.ndarray):
                weight = weight.tolist()

            logger.info(f"Weight after conversion: {weight}")

            try:
                device, device_created = Device.objects.get_or_create(name=device_name, ip=ip, port=port)
                local_data, local_data_created = LocalData.objects.get_or_create(device=device, created_at=datetime.date.today())
                if isinstance(weight, str):  
                    try:
                        weight = json.loads(weight)  # <-- Распарсим JSON, если пришла строка
                    except json.JSONDecodeError:
                        return JsonResponse({'status': 'error', 'message': 'Invalid weight format'}, status=400)

                local_data.data = weight  # Теперь это точно JSON-совместимый list
                local_data.save()

                global_data, _ = AggregetedData.objects.get_or_create(created_at=datetime.date.today())
                global_data.local_datas.add(local_data)
                global_data.save(aggregate=True)

                return JsonResponse({'status': 'ok', 'device_created': device_created, 'local_data_created': local_data_created, 'global_data': global_data.data}, status=200)
            except Exception as e:
                logger.error(f"Error saving weights: {e}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        return JsonResponse({'status': 'error'}, status=400)
