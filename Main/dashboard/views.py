import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from django.contrib import messages
from django.http import JsonResponse
from accounts.models import User, APIConfiguration
from accounts.forms import RegisterForm, CreateUserForm, APIConfigForm
from chat.models import Conversation, Message


class BtierRequiredMixin(LoginRequiredMixin):
    """Only B-tier users can access the dashboard."""
    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if request.user.tier not in [User.Tier.A, User.Tier.B]:
            return redirect('chat_home')
        return super().dispatch(request, *args, **kwargs)


class DashboardHomeView(BtierRequiredMixin, View):
    def get(self, request):
        user = request.user
        c_users = User.objects.filter(parent=user)
        conversations = Conversation.objects.filter(provider=user).order_by('-updated_at')[:5]
        api_configs = APIConfiguration.objects.filter(owner=user)
        return render(request, 'dashboard/home.html', {
            'c_users': c_users,
            'c_user_count': c_users.count(),
            'recent_conversations': conversations,
            'conv_count': Conversation.objects.filter(provider=user).count(),
            'api_configs': api_configs,
            'has_default_key': api_configs.filter(is_default=True, is_active=True).exists(),
        })


class DashboardUsersView(BtierRequiredMixin, View):
    def get(self, request):
        users = User.objects.filter(parent=request.user).order_by('-date_joined')
        return render(request, 'dashboard/users.html', {'users': users})


class DashboardCreateUserView(BtierRequiredMixin, View):
    def get(self, request):
        return render(request, 'dashboard/create_user.html', {'form': CreateUserForm()})

    def post(self, request):
        form = CreateUserForm(request.POST)
        if form.is_valid():
            new_user = form.save(commit=False)
            new_user.tier = User.Tier.C
            new_user.parent = request.user
            new_user.save()
            messages.success(request, f'User {new_user.username} created.')
            return redirect('dashboard_users')
        return render(request, 'dashboard/create_user.html', {'form': form})


class DashboardToggleUserView(BtierRequiredMixin, View):
    def post(self, request, pk):
        user = get_object_or_404(User, pk=pk, parent=request.user)
        user.is_active = not user.is_active
        user.save()
        return JsonResponse({'is_active': user.is_active})


class DashboardAPIKeysView(BtierRequiredMixin, View):
    def get(self, request):
        configs = APIConfiguration.objects.filter(owner=request.user)
        return render(request, 'dashboard/api_keys.html', {
            'configs': configs,
            'form': APIConfigForm(),
        })


class DashboardAddAPIKeyView(BtierRequiredMixin, View):
    def post(self, request):
        form = APIConfigForm(request.POST)
        if form.is_valid():
            config = form.save(commit=False)
            config.owner = request.user
            config.save()
            messages.success(request, f'API key "{config.label}" added.')
        else:
            messages.error(request, 'Invalid form data.')
        return redirect('dashboard_api_keys')


class DashboardDeleteAPIKeyView(BtierRequiredMixin, View):
    def post(self, request, pk):
        config = get_object_or_404(APIConfiguration, pk=pk, owner=request.user)
        config.delete()
        messages.success(request, 'API key deleted.')
        return redirect('dashboard_api_keys')


class DashboardSetDefaultAPIKeyView(BtierRequiredMixin, View):
    def post(self, request, pk):
        config = get_object_or_404(APIConfiguration, pk=pk, owner=request.user)
        config.is_default = True
        config.save()
        return JsonResponse({'status': 'ok'})


class DashboardConversationsView(BtierRequiredMixin, View):
    def get(self, request):
        conversations = Conversation.objects.filter(
            provider=request.user
        ).order_by('-updated_at')
        return render(request, 'dashboard/conversations.html', {
            'conversations': conversations,
        })


class DashboardConversationDetailView(BtierRequiredMixin, View):
    def get(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, provider=request.user)
        msgs = conversation.messages.all()
        return render(request, 'dashboard/conversation_detail.html', {
            'conversation': conversation,
            'messages': msgs,
        })