from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from .models import User
from .forms import CreateUserForm


class LoginView(View):
    def get(self, request):
        if request.user.is_authenticated:
            return redirect('chat_home')
        return render(request, 'accounts/login.html')

    def post(self, request):
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect(request.GET.get('next', 'chat_home'))
        messages.error(request, 'Invalid username or password.')
        return render(request, 'accounts/login.html')


class ManageUsersView(LoginRequiredMixin, View):
    def get(self, request):
        user = request.user
        if user.tier == User.Tier.A:
            users = User.objects.exclude(pk=user.pk).order_by('tier', 'username')
        elif user.tier == User.Tier.B:
            users = User.objects.filter(parent=user).order_by('username')
        else:
            return redirect('chat_home')
        return render(request, 'accounts/manage_users.html', {'users': users})


class CreateUserView(LoginRequiredMixin, View):
    def get(self, request):
        if request.user.tier not in [User.Tier.A, User.Tier.B]:
            return redirect('chat_home')
        return render(request, 'accounts/create_user.html', {'form': CreateUserForm()})

    def post(self, request):
        if request.user.tier not in [User.Tier.A, User.Tier.B]:
            return redirect('chat_home')
        form = CreateUserForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            new_user.parent = request.user
            # A-tier can create B or C, B-tier can only create C
            if request.user.tier == User.Tier.A:
                new_user.tier = request.POST.get('tier', User.Tier.B)
            else:
                new_user.tier = User.Tier.C
            new_user.save()
            messages.success(request, f'User {new_user.username} created.')
            return redirect('manage_users')
        return render(request, 'accounts/create_user.html', {'form': form})
    
class RegisterView(View):
    def get(self, request):
        from .forms import RegisterForm
        return render(request, 'accounts/register.html', {'form': RegisterForm()})

    def post(self, request):
        from .forms import RegisterForm
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.tier = User.Tier.C
            user.save()
            login(request, user)
            return redirect(request.GET.get('next', 'chat_home'))
        return render(request, 'accounts/register.html', {'form': form})