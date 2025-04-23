from django.shortcuts import render
from django.contrib.auth import authenticate, login as auth_login
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.views import View
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.contrib.auth.models import User

class LoginView(View):
    def get(self, request):
        return render(request, 'account/login.html')

    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')

        # Validate username and password
        if not username:
            context = {'username': username, 'password': password, 'error': 'Қолданушы атын енгізіңіз'}
            messages.error(request, 'Username is required')
            return render(request, 'account/login.html', context)
        if not password:
            context = {'username': username, 'password': password, 'error': 'Құпия сөзді енгізіңіз'}
            messages.error(request, 'Password is required')
            return render(request, 'account/login.html', context)
        users = User.objects.filter(username=username)
        if not users.exists():
            context = {'username': username, 'password': password, 'error': 'Мұндай қолданушы табылмады'}
            messages.error(request, 'Invalid username or password')
            return render(request, 'account/login.html', context)
        
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            return HttpResponseRedirect(reverse('dashboard'))
        else:
            messages.error(request, 'Invalid username or password')
            context = {'username': username, 'password': password, 'error': 'Құпия сөз дұрыс емес'}
            return render(request, 'account/login.html', context)