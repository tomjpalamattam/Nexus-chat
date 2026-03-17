import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Conversation, Message
from .llm import stream_response


class ChatConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.user    = self.scope['user']
        self.session = self.scope['session']
        await self.accept()

    async def disconnect(self, close_code):
        pass

    async def receive(self, text_data):
        data         = json.loads(text_data)
        user_message = data.get('message', '').strip()
        if not user_message:
            return

        conversation = await self.get_conversation()
        if not conversation:
            await self.send_error('Conversation not found.')
            return

        await self.save_message(conversation, 'user', user_message)

        api_config = await database_sync_to_async(conversation.get_api_config)()
        if not api_config:
            await self.send_error('No API key configured.')
            return

        history = await self.get_history(conversation)

        # ── choose RAG agent or plain LLM ─────────────────────────────────
        provider = await database_sync_to_async(lambda: conversation.provider)()
        use_rag  = provider is not None and await self.provider_has_docs(provider)

        full_response = ''

        if use_rag:
            from rag.agent import stream_agent_response
            thread_id = f'conv_{conversation.pk}'
            async for chunk in stream_agent_response(
                api_config,
                provider,
                history,
                user_message,
                conversation.system_prompt,
                thread_id,
            ):
                full_response += chunk
                await self.send(text_data=json.dumps({'type': 'chunk', 'content': chunk}))
        else:
            async for chunk in stream_response(
                api_config,
                history,
                user_message,
                conversation.system_prompt,
            ):
                full_response += chunk
                await self.send(text_data=json.dumps({'type': 'chunk', 'content': chunk}))

        await self.save_message(conversation, 'assistant', full_response)
        await self.send(text_data=json.dumps({'type': 'done'}))

    @database_sync_to_async
    def get_conversation(self):
        try:
            conv = Conversation.objects.get(pk=self.conversation_id)
            if self.user.is_authenticated:
                return conv if conv.user == self.user else None
            else:
                return conv if conv.session_key == self.session.session_key else None
        except Conversation.DoesNotExist:
            return None

    @database_sync_to_async
    def get_history(self, conversation):
        return list(
            Message.objects.filter(conversation=conversation).values('role', 'content')
        )

    @database_sync_to_async
    def save_message(self, conversation, role, content):
        return Message.objects.create(conversation=conversation, role=role, content=content)

    @database_sync_to_async
    def provider_has_docs(self, provider):
        from rag.models import ProviderDocument
        return ProviderDocument.objects.filter(
            provider=provider,
            status=ProviderDocument.Status.READY,
        ).exists()

    async def send_error(self, message):
        await self.send(text_data=json.dumps({'type': 'error', 'message': message}))
