from django.contrib import admin
from .models import Device, LocalData, AggregetedData

admin.site.register(Device)
admin.site.register(LocalData)
admin.site.register(AggregetedData)
# Register your models here.
