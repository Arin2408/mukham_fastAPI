from django.urls import path
from .views import location_list_create, location_detail

urlpatterns = [
    path('locations/', location_list_create, name='location_list_create'),  
    path('locations/<int:location_id>/', location_detail, name='location_detail'),  
]