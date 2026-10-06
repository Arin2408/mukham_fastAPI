from rest_framework import status
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from .models import Department
from .serializers import DepartmentSerializer
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.db.models import Count, Q
from employees.models import Attendance, Customuser

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def add_department(request):
        # Ensure the department is associated with the user's organization
    request.data['org'] = request.user.org_id
    serializer = DepartmentSerializer(data=request.data)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def list_departments(request):
    # Filter departments by the user's organization
    departments = Department.objects.filter(org=request.user.org_id)
    serializer = DepartmentSerializer(departments, many=True)
    return Response(serializer.data)

@api_view(['PUT'])
@permission_classes([IsAuthenticated])
@authentication_classes([JWTAuthentication])
def update_department(request, department_id):
    try:
        department = Department.objects.get(department_id=department_id, org=request.user.org_id)
    except Department.DoesNotExist:
        return Response({"error": "Department not found"}, status=status.HTTP_404_NOT_FOUND)

    serializer = DepartmentSerializer(department, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(serializer.data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def delete_department(request, department_id):
    try:
        department = Department.objects.get(department_id=department_id, org=request.user.org_id)
    except Department.DoesNotExist:
        return Response({"error": "Department not found"}, status=status.HTTP_404_NOT_FOUND)

    department.delete()
    return Response({"message": "Department deleted successfully"}, status=status.HTTP_204_NO_CONTENT)

@api_view(['GET'])
@authentication_classes([JWTAuthentication])
@permission_classes([IsAuthenticated])
def department_leaderboard(request):
    # Count total and on-time attendance per department in a single query
    departments = Department.objects.filter(org=request.user.org_id).annotate(
        total_attendance=Count('customuser__attendances'),
        on_time_count=Count(
            'customuser__attendances',
            filter=Q(customuser__attendances__status__in=['Early', 'On Time'])
        ),
    )
    leaderboard_data = []

    for dept in departments:
        total_attendance = dept.total_attendance
        on_time_count = dept.on_time_count

        punctuality_score = (on_time_count / total_attendance * 100) if total_attendance > 0 else 0

        leaderboard_data.append({
            "department_id": dept.department_id,
            "department_name": dept.details,
            "punctuality_score": round(punctuality_score, 1),
            "total_attendances": total_attendance
        })

    # Sort by score descending
    leaderboard_data.sort(key=lambda x: x['punctuality_score'], reverse=True)

    return Response(leaderboard_data)