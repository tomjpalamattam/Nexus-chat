from django.contrib.auth.models import AbstractUser
from django.db import models

from django.utils.text import slugify

class User(AbstractUser):
    class Tier(models.TextChoices):
        A = 'A', 'Super Admin'
        B = 'B', 'Provider'
        C = 'C', 'End User'

    tier = models.CharField(max_length=1, choices=Tier.choices, default=Tier.C)
    parent = models.ForeignKey(
        'self',
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='children',
    )
    slug = models.SlugField(unique=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.username)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.get_tier_display()})"

class APIConfiguration(models.Model):

    class Provider(models.TextChoices):
        OPENAI = 'openai', 'OpenAI'
        OPENAI_COMPATIBLE = 'openai_compatible', 'OpenAI-Compatible'

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='api_configs')
    label = models.CharField(max_length=100)
    provider = models.CharField(max_length=30, choices=Provider.choices, default=Provider.OPENAI)
    api_key = models.CharField(max_length=500)
    base_url = models.CharField(max_length=255, blank=True, help_text='For OpenAI-compatible endpoints')
    model_name = models.CharField(max_length=100, default='gpt-4o-mini')
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_default', '-created_at']

    def save(self, *args, **kwargs):
        # only one default per owner at a time
        if self.is_default:
            APIConfiguration.objects.filter(
                owner=self.owner, is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.owner.username} — {self.label}"