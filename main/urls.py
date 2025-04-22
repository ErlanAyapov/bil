from django.urls import path
from .views import *

urlpatterns = [
    path('', main, name='main'),
    path('training/', training, name='training'),
    path('aggregated_data/', AggregatedDataListView.as_view(), name='aggregated_data_list'),
    path('save_local_weights/', AcceptWeightsView.as_view(), name='accept_weights'),
    path('get_global_weights/', AcceptWeightsView.as_view(), name='get_global_weights'),
    path('start_training/', start_training, name='start_training'),
    path('check_training_status/', check_training_status, name='check_training_status'),
    path('list_container_load/', list_container_load, name='list_container_load'),
    path('subscribe_device/', subcribe_device_federeated_learning, name='subscribe_device'),
    path('update_global_data/', update_global_aggregated_data, name='update_global_data'),
    path('get_chart_data/', get_chart_data, name='get_chart_data'),
    path('update_device_status/', update_device_status, name='update_device_status'),
    path('check_device_status/', check_device_status, name='check_device_status'),
    path('monitoring_devices/', monitoring_devices, name='monitoring_devices'),
    path('dashboard/', dashboard, name='dashboard'),
    path('check_predict_status/', check_predict_status, name='check_predict_status'),
    path('save_predict_results/', save_predict_results, name='save_predict_results')
]