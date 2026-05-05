from django.urls import path
from .views import register_view, login_view, profile_view, get_organisation, forgot_password, reset_password

urlpatterns = [
    path('org/signup/', register_view, name='signup'),
    path('org/login/', login_view, name='login'),
    path('profile/<int:org_id>/', profile_view, name='profile'),
    path('organisations/<int:org_id>/', get_organisation, name='org_details'),
    path('forgot-password/', forgot_password, name='forgot_password'),
    path('reset-password/', reset_password, name='reset_password'),
]
