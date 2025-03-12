from django.contrib import admin
from .models import Device, LocalData, AggregetedData, RoundResult, PredictResult

admin.site.register(Device)
admin.site.register(LocalData)
admin.site.register(RoundResult)
admin.site.register(PredictResult)
admin.site.register(AggregetedData)
# Register your models here.
