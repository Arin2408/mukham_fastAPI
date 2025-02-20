from django.urls import path
from .views import list_departments, add_department, update_department, delete_department

urlpatterns = [
    path('departments/', list_departments, name='list_departments'),  
    path('departments/add/', add_department, name='add_department'),  
    path('departments/update/<int:department_id>/', update_department, name='update_department'),  
    path('departments/delete/<int:department_id>/', delete_department, name='delete_department'),  
]