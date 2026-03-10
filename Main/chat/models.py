from django.db import models
from accounts.models import User, APIConfiguration


class Conversation(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    session_key = models.CharField(max_length=40, blank=True, null=True)
    provider = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hosted_conversations', null=True, blank=True)
    title = models.CharField(max_length=255, default='New Chat')
    system_prompt = models.TextField(blank=True, default='You are a helpful assistant.')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def get_api_config(self):
        """Walk up the parent chain to find an active default API config."""
        user = self.provider or self.user
        while user is not None:
            config = APIConfiguration.objects.filter(
                owner=user, is_default=True, is_active=True
            ).first()
            if config:
                return config
            user = user.parent
        return None

    def __str__(self):
        return f"{self.user.username if self.user else 'anonymous'}: {self.title}"


class Message(models.Model):
    class Role(models.TextChoices):
        USER = 'user', 'User'
        ASSISTANT = 'assistant', 'Assistant'
        SYSTEM = 'system', 'System'

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"