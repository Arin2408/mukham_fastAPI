# from django.urls import path
# from .views import register_face, get_face_details, check_face_status, verify_face

# urlpatterns = [
#     path('check-status/', check_face_status, name='check-face-status'),
#     path('register/', register_face, name='register-face'),
#     path('verify/', verify_face, name='verify-face'),
#     path('details/<str:mobile_number>/', get_face_details, name='get-face-details'),
# ]
from django.urls import path

from .views import (
    register_face,
    get_face_details,
    check_face_status,
    verify_face,
    create_liveness_session,
    get_liveness_result
)


urlpatterns = [
    path(
        'check-status/',
        check_face_status,
        name='check-face-status'
    ),

    path(
        'register/',
        register_face,
        name='register-face'
    ),

    path(
        'verify/',
        verify_face,
        name='verify-face'
    ),

    path(
        'details/<str:mobile_number>/',
        get_face_details,
        name='get-face-details'
    ),

    path(
        'liveness/create/',
        create_liveness_session,
        name='create-liveness-session'
    ),

    path(
        'liveness/result/',
        get_liveness_result,
        name='get-liveness-result'
    ),
]