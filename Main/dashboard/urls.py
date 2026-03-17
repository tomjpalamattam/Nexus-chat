from django.urls import path
from . import views

urlpatterns = [
    path('', views.DashboardHomeView.as_view(), name='dashboard_home'),
    path('users/', views.DashboardUsersView.as_view(), name='dashboard_users'),
    path('users/create/', views.DashboardCreateUserView.as_view(), name='dashboard_create_user'),
    path('users/<int:pk>/toggle/', views.DashboardToggleUserView.as_view(), name='dashboard_toggle_user'),
    path('api-keys/', views.DashboardAPIKeysView.as_view(), name='dashboard_api_keys'),
    path('api-keys/add/', views.DashboardAddAPIKeyView.as_view(), name='dashboard_add_api_key'),
    path('api-keys/<int:pk>/delete/', views.DashboardDeleteAPIKeyView.as_view(), name='dashboard_delete_api_key'),
    path('api-keys/<int:pk>/set-default/', views.DashboardSetDefaultAPIKeyView.as_view(), name='dashboard_set_default_api_key'),
    path('conversations/', views.DashboardConversationsView.as_view(), name='dashboard_conversations'),
    path('conversations/<int:pk>/', views.DashboardConversationDetailView.as_view(), name='dashboard_conversation_detail'),
    path('conversations/<int:pk>/delete/', views.DashboardDeleteConversationView.as_view(), name='dashboard_delete_conversation'),
]