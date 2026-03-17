from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views import View
from .models import Conversation, Message
from accounts.models import User


class ChatHomeView(LoginRequiredMixin, View):
    def get(self, request):
        latest = Conversation.objects.filter(user=request.user).first()
        if latest:
            return redirect('conversation', pk=latest.pk)
        return redirect('new_conversation')


class NewConversationView(LoginRequiredMixin, View):
    def get(self, request):
        conv = Conversation.objects.create(user=request.user)
        return redirect('conversation', pk=conv.pk)


class ConversationView(LoginRequiredMixin, View):
    def get(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
        conversations = Conversation.objects.filter(user=request.user)
        messages = conversation.messages.all()
        api_config = conversation.get_api_config()
        return render(request, 'chat/conversation.html', {
            'conversation': conversation,
            'conversations': conversations,
            'messages': messages,
            'has_api_key': api_config is not None,
            'api_config': api_config,
        })


class DeleteConversationView(LoginRequiredMixin, View):
    def post(self, request, pk):
        conversation = get_object_or_404(Conversation, pk=pk, user=request.user)
        conversation.delete()
        # Redirect to the next available conversation or new chat
        next_conv = Conversation.objects.filter(user=request.user).first()
        if next_conv:
            return redirect('conversation', pk=next_conv.pk)
        return redirect('new_conversation')


class PublicChatView(View):
    def get(self, request, provider_slug):
        provider = get_object_or_404(User, slug=provider_slug, tier=User.Tier.B)

        if not request.session.session_key:
            request.session.create()

        if request.user.is_authenticated:
            conversation = Conversation.objects.filter(
                user=request.user, provider=provider,
            ).first()
            if not conversation:
                conversation = Conversation.objects.create(
                    user=request.user,
                    provider=provider,
                    system_prompt=f'You are a helpful assistant for {provider.username}.',
                )
        else:
            conversation = Conversation.objects.filter(
                session_key=request.session.session_key, provider=provider,
            ).first()
            if not conversation:
                conversation = Conversation.objects.create(
                    session_key=request.session.session_key,
                    provider=provider,
                    system_prompt=f'You are a helpful assistant for {provider.username}.',
                )

        messages = conversation.messages.all()
        api_config = conversation.get_api_config()

        return render(request, 'chat/public_chat.html', {
            'provider': provider,
            'conversation': conversation,
            'messages': messages,
            'has_api_key': api_config is not None,
        })