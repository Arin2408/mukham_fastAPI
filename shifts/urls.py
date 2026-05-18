from django.urls import path
from .views import add_shift, list_shifts, update_shift, delete_shift, bulk_assign_shift

urlpatterns = [
    path('add-shift/', add_shift, name='add_shift'),
    path('shifts/', list_shifts, name='list_shifts'),
    path('shifts/update/<int:shift_id>/', update_shift, name='update_shift'),
    path('shifts/delete/<int:shift_id>/', delete_shift, name='delete_shift'),
    path('bulk-assign/', bulk_assign_shift, name='bulk_assign_shift'),
]