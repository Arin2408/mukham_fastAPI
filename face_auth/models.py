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
    # Storing image as Base64 string
    face_image_base64 = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Face data for {self.user.mobile_number}"
