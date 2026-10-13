from django.db import models

class EmployeeFaceData(models.Model):
    # Linking to the main auth user via mobile_number
    # The to_field='mobile_number' ensures we link to the mobile_number column in CustomUser
    user = models.OneToOneField(
        'organisation.CustomUser', 
        on_delete=models.CASCADE,
        to_field='mobile_number',
        db_column='mobile_number',
        primary_key=True,
        related_name='face_data'
    )
    # Key of the face image in FastAPI's private face store
    # (fastapi_backend/app/services/storage.py). Images are no longer
    # kept in the database.
    face_image_key = models.CharField(max_length=255, blank=True, default='', db_default='')
    # Legacy: base64 image from before the move to the face store.
    # Emptied by fastapi_backend/scripts/move_files_to_storage.py.
    face_image_base64 = models.TextField(blank=True, default='', db_default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Face data for {self.user.mobile_number}"
