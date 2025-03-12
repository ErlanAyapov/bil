import os
import json
import logging
import datetime
import numpy as np
from django.views import View
from .utils import get_device_status
from django.http import JsonResponse
from django.views.generic import ListView
from django.shortcuts import render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from .models import Device, LocalData, AggregetedData, RoundResult, PredictResult


logger = logging.getLogger(__name__)

# Create your views here.
def main(request): 
    return render(request, 'base.html')

def start_training(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        status = data.get('status', 'STOP')
        # status = request.POST.get('status', 'STOP')
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
                updated_lines.append(f"TRAIN_STATUS={status}\n")
                train_status_found = True
            else:
                updated_lines.append(line)

        # Если TRAIN_STATUS не найден, добавляем его
        if not train_status_found:
            updated_lines.append(f"TRAIN_STATUS={status}\n")

        # Запись обновленного содержимого обратно в .env файл
        with open(dotenv_path, 'w') as file:
            file.writelines(updated_lines)

        print(f"Training status updated to {status} in .env file.")

        # Здесь можно добавить логику для запуска обучения
        # return JsonResponse({'status': 'Training started', 'train_status': 'RUN'})
        return JsonResponse({'status': 'Training started', 'train_status': status})
    
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
    
def list_container_load(request):
    agg_data = AggregetedData.objects.all()
    return render(request, 'main/list_content.html', {'object_list': agg_data})

def check_training_status(request):
    status = get_train_status()
    return JsonResponse({'train_status': status})

def update_device_status(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        device_token = data.get('device_token')
        if not device_token:
            return JsonResponse({'status': 'error', 'message': 'Not all required fields are filled'}, status=400)
        device = Device.objects.get(device_token=device_token)
        device.update_status()
        return JsonResponse({'status': 'ok'}, status=200)
    return JsonResponse({'status': 'error'}, status=400)
 
def save_predict_results(request):
    # Проверяем, что запрос — это POST
    if request.method == 'POST':
        try:
            # Извлекаем JSON-данные из тела запроса
            data = json.loads(request.body)
            device_token = data.get('device_token')
            results = data.get('results')

            # Проверяем, что обязательные поля присутствуют
            if not device_token or not results:
                return JsonResponse({'status': 'error', 'message': 'Missing required fields'}, status=400)

            # Находим устройство по device_token
            try:
                device = Device.objects.get(device_token=device_token)
            except Device.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Device not found'}, status=404)

            # Сохраняем результаты предикта в базу данных
            PredictResult.objects.create(device=device, results=results)

            # Возвращаем успешный ответ
            return JsonResponse({'status': 'ok', 'message': 'Results saved successfully'}, status=200)

        except json.JSONDecodeError:
            # Ошибка, если JSON невалиден
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
        except Exception as e:
            # Обработка других возможных ошибок
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)
    else:
        # Ошибка, если метод запроса не POST
        return JsonResponse({'status': 'error', 'message': 'Only POST method is allowed'}, status=405)
    
def check_predict_status(request):
    if request.method == 'GET':
        # Здесь можно добавить логику определения статуса
        status = "RUN"  # Пример статуса, замените на свою логику
        return JsonResponse({'predict_status': status})
    else:
        return JsonResponse({'error': 'Only GET method is allowed'}, status=405)
    
def subcribe_device_federeated_learning(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        device_token = data.get('device_token') 
        # device_name = request.POST.get('device')
        # ip = request.POST.get('ip')
        # port = request.POST.get('port')

        if not device_token:
            return JsonResponse({'status': 'error', 'message': 'Not all required fields are filled'}, status=400)

        device = Device.objects.get(device_token=device_token)
        
        global_data, _ = AggregetedData.objects.get_or_create(created_at=datetime.date.today())
        data = {'status': 'ok', 
            # 'device_created': created, 
            'message': '', 
            'data':{
                   'epoch':global_data.epoch_count,
                   'round':global_data.round_count
            }
        }  
        if device not in global_data.subscribed_devices.all():
            global_data.subscribed_devices.add(device)
            global_data.save()
            data['message'] = 'Device is sucessfully subscribed'
        data['message'] = 'Device already subscribed'
        return JsonResponse(data, status=200)
    return JsonResponse({'status': 'error'}, status=400)


def update_global_aggregated_data(request):
    try:
        if request.method == 'POST':
            global_data, _ = AggregetedData.objects.get_or_create(created_at=datetime.date.today())
            rounds = request.POST.get('rounds')
            epochs = request.POST.get('epochs')
            isactive = request.POST.get('isactive')
            global_data.round_count = rounds
            global_data.epoch_count = epochs
            global_data.is_active = isactive
            global_data.save()
            return JsonResponse({'status': 'ok', 'message': 'Global data updated'}, status=200)
        return JsonResponse({'status': 'error'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def get_chart_data(request):
    try:
        # Получаем только сегодняшние агрегированные данные
        today = datetime.date.today()
        aggregated_data = AggregetedData.objects.filter(created_at=today).first()

        if not aggregated_data:
            return JsonResponse({'success': False, 'error': 'No data for today'}, status=404)

        local_datas = aggregated_data.local_datas.all()
        loss_datasets = []
        accuracy_datasets = []

        for local_data in local_datas:
            device_name = local_data.device.name
            round_results = local_data.round_results.all()

            # Извлекаем данные для графика Loss
            x_labels = [result.round_number for result in round_results]
            loss_values = [result.result.get('val_loss') for result in round_results]

            # Извлекаем данные для графика Accuracy
            accuracy_values = [result.result.get('val_accuracy') for result in round_results]

            # Добавляем данные в соответствующие списки датасетов
            loss_datasets.append({
                'label': device_name,
                'data': loss_values,
                'borderColor': f'rgba({hash(device_name) % 256}, {hash(device_name + "1") % 256}, {hash(device_name + "2") % 256}, 1)',
                'backgroundColor': f'rgba({hash(device_name) % 256}, {hash(device_name + "1") % 256}, {hash(device_name + "2") % 256}, 0.2)',
                'fill': True
            })
            accuracy_datasets.append({
                'label': device_name,
                'data': accuracy_values,
                'borderColor': f'rgba({hash(device_name) % 256}, {hash(device_name + "1") % 256}, {hash(device_name + "2") % 256}, 1)',
                'backgroundColor': f'rgba({hash(device_name) % 256}, {hash(device_name + "1") % 256}, {hash(device_name + "2") % 256}, 0.2)',
                'fill': True
            })

        return JsonResponse({
            'success': True,
            'loss': {
                'labels': x_labels,
                'datasets': loss_datasets
            },
            'accuracy': {
                'labels': x_labels,
                'datasets': accuracy_datasets
            }
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

def check_device_status(request):
    try:
        if request.method == 'GET':
            device_id = request.GET.get('device_id')
            device = Device.objects.get(id=device_id)
            status = get_device_status(device.ip, device.port)
            return JsonResponse(status)
        return JsonResponse({'status': 'error', 'message': 'Not allowed method'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
    
def monitoring_devices(request):
    try:
        if request.method == 'GET':
            devices = Device.objects.all()
            return render(request, 'main/monitoring_devices.html', {'devices': devices})
        return JsonResponse({'status': 'error', 'message': 'Not allowed method'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

class AggregatedDataListView(ListView):
    model = AggregetedData
    template_name = 'main/aggregated_data_list.html'
    ordering = ['-created_at']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['train_status'] = get_train_status()
        return context


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
            device_token = data.get('device_token')
            weight = data.get('weight')
            # ip = data.get('ip')
            # port = data.get('port') 
            round_data = {
                'val_loss': data.get('val_loss', 1),
                'val_accuracy': data.get('val_acc', 0),
                'round_idx': data.get('round_idx', 0),
            }
  
            if not device_token:
                return JsonResponse({'status': 'error', 'message': 'Not all required fields are filled'}, status=400)

            # Если weight — это массив NumPy, конвертируем в list
            if isinstance(weight, np.ndarray):
                weight = weight.tolist()

            logger.info(f"Weight after conversion: {weight}")

            try:
                device = Device.objects.get(device_token=device_token)
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

                round_result = RoundResult.objects.create(
                    device=device, 
                    local_data=local_data, 
                    round_number=round_data.get('round_idx', 0), 
                    result=round_data
                )

                return JsonResponse({'status': 'ok', 'local_data_created': local_data_created, 'global_data': global_data.data}, status=200)
            except Exception as e:
                logger.error(f"Error saving weights: {e}")
                return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
        return JsonResponse({'status': 'error'}, status=400)
