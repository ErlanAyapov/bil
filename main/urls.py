from django.urls import path
from .views import main, start_training, check_training_status, AggregatedDataListView, AcceptWeightsView

urlpatterns = [
    path('', main, name='main'),
    path('aggregated_data/', AggregatedDataListView.as_view(), name='aggregated_data_list'),
    path('save_local_weights/', AcceptWeightsView.as_view(), name='accept_weights'),
    path('get_global_weights/', AcceptWeightsView.as_view(), name='get_global_weights'),
    path('start_training/', start_training, name='start_training'),
    path('check_training_status/', check_training_status, name='check_training_status'),
]