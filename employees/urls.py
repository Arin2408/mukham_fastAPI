from django.urls import path
from .views import signup_view, login_view, list_users, update_user, delete_user, mark_attendance, attendance_history, employee_details

urlpatterns = [
    path('signup/', signup_view, name='signup'),
    path('employee/login/', login_view, name='login'),
    path('list/', list_users, name='list_users'),
    path('employee-details/', employee_details, name='employee-details'),
    path('mark-attendance/', mark_attendance, name='mark-attendance'),
    path('attendance-history/', attendance_history, name='attendance-history'),
    path('update/<int:user_id>/', update_user, name='update_user'),
    path('delete/<int:user_id>/', delete_user, name='delete_user'),
]