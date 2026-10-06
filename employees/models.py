from django.db import models
import random, string
from departments.models import Department
from designations.models import Designation
from shifts.models import Shift
from locations.models import Location
from organisation.models import CustomUser


class Customuser(models.Model):

    user = models.OneToOneField(
        CustomUser, 
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='employee'
    )

    first_name = models.CharField(max_length=255)
    last_name = models.CharField(max_length=255)

    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True
    )

    designation = models.ForeignKey(
        Designation,
        on_delete=models.SET_NULL,
        null=True
    )

    shift = models.ForeignKey(
        Shift,
        on_delete=models.SET_NULL,
        null=True
    )

    office_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True
    )

    photo = models.ImageField(
        upload_to='employee_photos/',
        null=True,
        blank=True
    )

    organisation = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE,
        related_name='employees',
        limit_choices_to={'is_organization': True}
    )

    member_password = models.CharField(
        max_length=255,
        blank=True,
        null=True
    )

    is_member_registered = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Auto-generate member_password if not already set
        if not self.member_password and hasattr(self, 'user') and self.first_name:
            from django.contrib.auth.hashers import make_password

            # First 5 digits of mobile number + First 5 letters of first name
            phone_part = self.user.mobile_number[:5] if self.user.mobile_number else ""
            name_part = self.first_name[:5]
            plain_password = f"{phone_part}{name_part}".lower()
            self.member_password = make_password(plain_password)

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.user.mobile_number})"


class Attendance(models.Model):

    STATUS_CHOICES = [
        ('Early', 'Early'),
        ('On Time', 'On Time'),
        ('Late', 'Late'),
        ('FAILED_VERIFICATION', 'FAILED_VERIFICATION'),
    ]

    employee = models.ForeignKey(
        Customuser,
        on_delete=models.CASCADE,
        related_name='attendances'
    )

    check_in = models.DateTimeField()
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)

    SOURCE_CHOICES = [
        ('self', 'self'),       # employee checked in with GPS + face
        ('manual', 'manual'),   # organisation admin marked it
    ]

    CHECK_OUT_LOCATION_CHOICES = [
        ('inside', 'inside'),
        ('outside', 'outside'),
        ('unknown', 'unknown'),  # no / unusable GPS sent at check-out
        ('manual', 'manual'),
    ]

    location_status = models.CharField(
        max_length=10,
        choices=[
            ('inside', 'inside'),
            ('outside', 'outside'),
            ('manual', 'manual')
        ],
        default='inside'
    )

    # Who created the record
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        default='self'
    )

    marked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    # GPS submitted at check-in (kept for auditing)
    check_in_latitude = models.FloatField(null=True, blank=True)
    check_in_longitude = models.FloatField(null=True, blank=True)
    check_in_accuracy = models.FloatField(null=True, blank=True)
    check_in_distance = models.FloatField(null=True, blank=True)

    # Office the check-in was matched against
    check_in_location = models.ForeignKey(
        Location,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='+'
    )

    # GPS submitted at check-out (check-out is never blocked, only flagged)
    check_out_latitude = models.FloatField(null=True, blank=True)
    check_out_longitude = models.FloatField(null=True, blank=True)
    check_out_accuracy = models.FloatField(null=True, blank=True)
    check_out_distance = models.FloatField(null=True, blank=True)

    check_out_location_status = models.CharField(
        max_length=10,
        choices=CHECK_OUT_LOCATION_CHOICES,
        null=True,
        blank=True
    )

    face_status = models.CharField(
        max_length=10,
        choices=[
            ('verified', 'verified'),
            ('failed', 'failed'),
            ('skipped', 'skipped')
        ],
        default='skipped'
    )

    hours_worked = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ['-check_in']
        indexes = [
            # Employee's own history: WHERE employee_id = ? ORDER BY check_in DESC
            models.Index(
                fields=['employee', '-check_in'],
                name='attendance_emp_checkin_idx'
            ),
            # Organisation history with a date range: WHERE check_in >= ?
            models.Index(
                fields=['-check_in'],
                name='attendance_checkin_idx'
            ),
        ]
        constraints = [
            # Only one open (not checked-out) attendance per employee
            models.UniqueConstraint(
                fields=['employee'],
                condition=models.Q(check_out__isnull=True),
                name='one_open_attendance_per_employee'
            ),
        ]

    def save(self, *args, **kwargs):
        if self.check_out and not self.hours_worked:
            self.calculate_hours()

        super().save(*args, **kwargs)

    def calculate_hours(self):
        if self.check_out:
            delta = self.check_out - self.check_in
            self.hours_worked = round(delta.total_seconds() / 3600, 2)

    def __str__(self):
        return f"{self.employee} - {self.check_in.date()}"