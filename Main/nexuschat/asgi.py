import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nexuschat.settings')

from django.core.asgi import get_asgi_application
django_asgi_app = get_asgi_application()  # this must run before any app imports

from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
import chat.routing

application = ProtocolTypeRouter({
    'http': django_asgi_app,
    'websocket': AuthMiddlewareStack(
        URLRouter(chat.routing.websocket_urlpatterns)
    ),
})