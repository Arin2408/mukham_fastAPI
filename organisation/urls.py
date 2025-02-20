from django.urls import path
from .views import register_view, login_view, profile_view, get_organisation

urlpatterns = [
    path('org/signup/', register_view, name='signup'),
    path('org/login/', login_view, name='login'),
    path('profile/<int:org_id>/', profile_view, name='profile'),
    path('organisations/<int:org_id>/', get_organisation, name='org_details'),
]
