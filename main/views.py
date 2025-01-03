from django.shortcuts import render
from utils import send_notification


# Create your views here.
def main(request):
    
    return render(request, 'main/main.html')