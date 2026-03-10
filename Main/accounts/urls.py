from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('login/', views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('register/', views.RegisterView.as_view(), name='register'),
    path('users/', views.ManageUsersView.as_view(), name='manage_users'),
    path('users/create/', views.CreateUserView.as_view(), name='create_user'),
]