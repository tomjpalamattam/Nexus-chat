from django.urls import path
from . import views

urlpatterns = [
    path('', views.ChatHomeView.as_view(), name='chat_home'),
    path('new/', views.NewConversationView.as_view(), name='new_conversation'),
    path('<int:pk>/', views.ConversationView.as_view(), name='conversation'),
    path('<slug:provider_slug>/', views.PublicChatView.as_view(), name='public_chat'),
]