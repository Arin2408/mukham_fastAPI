from django.urls import path
from .views import signup_view, login_view, list_users, update_user, delete_user

urlpatterns = [
    path('signup/', signup_view, name='signup'),
    path('login/', login_view, name='login'),
    path('list/', list_users, name='list_users'),
    path('update/<int:user_id>/', update_user, name='update_user'),
    path('delete/<int:user_id>/', delete_user, name='delete_user'),
]