from django.urls import path
from .views import add_designation, list_designations, update_designation, delete_designation

urlpatterns = [
    path('designations/add/', add_designation, name='add_designation'),
    path('designations/', list_designations, name='list_designations'),
    path('designations/update/<int:designation_id>/', update_designation, name='update_designation'),
    path('designations/delete/<int:designation_id>/', delete_designation, name='delete_designation'),
]