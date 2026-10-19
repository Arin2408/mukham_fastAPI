"""Regression tests for the fixes in SECURITY_AUDIT_REPORT.md."""
from datetime import date, datetime, timezone

import pytest

from app.models.employee import Employee
from app.models.face import EmployeeFaceData
from app.models.location import Location
from app.models.security_tracking import LivenessSession
from app.models.task import Task
from app.core.security import create_card_code, create_face_token
from app.services import account_service, face_service, storage

from app.core.security import hash_password

from .conftest import auth, make_employee, make_org


# --- Sign-in -------------------------------------------------------------

def test_new_employee_password_is_mobile_and_name(client, db):
    org = make_org(db)
    response = client.post(
        "/api/v1/employees",
        json={
            "mobile_number": "7000000001",
            "email": "7000000001@example.com",
            "first_name": "Ashwini",
            "last_name": "Rao",
            "manager": None,
        },
        headers=auth(org),
    )
    assert response.status_code == 201
    password = response.json()["member_password"]
    assert password == "70000ashwi"

    login = client.post("/api/v1/member/login", json={"mobile_number": "7000000001", "password": password})
    assert login.status_code == 200


def test_admin_sign_in_does_not_reveal_which_numbers_exist(client, db):
    make_org(db, mobile="9000000001", password="right-password")

    unknown = client.post("/api/v1/org/login", json={"mobile_number": "9111111111", "password": "x"})
    wrong = client.post("/api/v1/org/login", json={"mobile_number": "9000000001", "password": "x"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json()["message"] == wrong.json()["message"]


def test_password_guessing_is_limited_per_account(client, db):
    make_org(db, mobile="9000000001", password="right-password")
    body = {"mobile_number": "9000000001", "password": "guess"}

    for _ in range(10):
        assert client.post("/api/v1/org/login", json=body).status_code == 401

    blocked = client.post("/api/v1/org/login", json=body)
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "too_many_requests"
    assert int(blocked.headers["Retry-After"]) > 0

    # The employee sign-in shares the same count for that number...
    member = client.post("/api/v1/member/login", json=body)
    assert member.status_code == 429
    # ...but other accounts are unaffected.
    other = client.post("/api/v1/org/login", json={"mobile_number": "9222222222", "password": "x"})
    assert other.status_code == 401


def test_reset_emails_are_limited_per_address(client, db):
    body = {"email": "someone@example.com"}
    for _ in range(3):
        assert client.post("/api/v1/forgot-password", json=body).status_code == 200
    assert client.post("/api/v1/forgot-password", json=body).status_code == 429


def test_public_number_lookup_is_limited(client, db):
    for _ in range(60):
        client.post("/api/v1/face/check-status", json={"mobile_number": "9000000001"})
    response = client.post("/api/v1/face/check-status", json={"mobile_number": "9000000001"})
    assert response.status_code == 429


def test_oversized_login_password_is_refused(client, db):
    response = client.post(
        "/api/v1/org/login",
        json={"mobile_number": "9000000001", "password": "x" * 10_000},
    )
    assert response.status_code == 422


# --- Face checks ----------------------------------------------------------

def test_employee_cannot_replace_their_face_with_a_photo(client, db, monkeypatch):
    org = make_org(db)
    employee = make_employee(db, org)
    called = []
    monkeypatch.setattr(face_service.rekognition, "compare_faces", lambda **kw: called.append(kw))

    response = client.post(
        "/api/v1/face/register",
        json={"mobile_number": employee.mobile_number, "face_image_base64": "aGVsbG8="},
        headers=auth(employee),
    )

    assert response.status_code == 403
    assert called == []


def _liveness_check(monkeypatch, confidence, similarity=99.0):
    """AWS answers: the check finished with this liveness score; faces match."""
    compared = []
    monkeypatch.setattr(
        face_service.rekognition,
        "get_face_liveness_session_results",
        lambda **kw: {
            "Status": "SUCCEEDED",
            "Confidence": confidence,
            "ReferenceImage": {"Bytes": b"live-frame"},
        },
    )

    def compare(**kw):
        compared.append(kw)
        return {"FaceMatches": [{"Similarity": similarity}]}

    monkeypatch.setattr(face_service.rekognition, "compare_faces", compare)
    return compared


def _saved_face(db, monkeypatch, mobile):
    now = datetime.now(timezone.utc)
    db.add(EmployeeFaceData(mobile_number=mobile, face_image_key="k", created_at=now, updated_at=now))
    db.commit()
    monkeypatch.setattr(face_service, "load_face_image", lambda record: b"saved-face")


@pytest.mark.parametrize("mode", ["register", "verify"])
def test_photo_held_to_the_camera_is_refused(db, monkeypatch, mode):
    org = make_org(db)
    employee = make_employee(db, org)
    if mode == "verify":
        _saved_face(db, monkeypatch, employee.mobile_number)
    compared = _liveness_check(monkeypatch, confidence=12.5)

    result = face_service.get_liveness_result(db, "session-1", employee.mobile_number, mode)

    assert result["status_code"] == 400
    assert result["body"]["verified"] is False
    assert compared == []
    if mode == "register":
        assert db.query(EmployeeFaceData).count() == 0


def test_live_face_at_the_minimum_score_is_accepted(db, monkeypatch):
    org = make_org(db)
    employee = make_employee(db, org)
    _saved_face(db, monkeypatch, employee.mobile_number)
    compared = _liveness_check(monkeypatch, confidence=90.0)

    result = face_service.get_liveness_result(db, "session-1", employee.mobile_number, "verify")

    assert result["status_code"] == 200
    assert result["body"]["verified"] is True
    assert compared[0]["SimilarityThreshold"] == 90


def test_check_in_with_a_photo_gets_no_face_token(client, db, monkeypatch):
    org = make_org(db)
    employee = make_employee(db, org)
    _saved_face(db, monkeypatch, employee.mobile_number)
    db.add(LivenessSession(
        session_id="session-1",
        mobile_number=employee.mobile_number,
        created_at=datetime.now(timezone.utc),
    ))
    db.commit()
    _liveness_check(monkeypatch, confidence=40.0)

    response = client.post(
        "/api/v1/face/liveness/result",
        json={"session_id": "session-1", "mobile_number": employee.mobile_number, "mode": "verify"},
        headers=auth(employee),
    )

    assert response.status_code == 400
    assert "face_token" not in response.json()


def test_liveness_mode_must_be_register_or_verify(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    response = client.post(
        "/api/v1/face/liveness/result",
        json={"session_id": "abc", "mobile_number": employee.mobile_number, "mode": "anything"},
        headers=auth(employee),
    )
    assert response.status_code == 422


def test_face_image_size_is_capped(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    response = client.post(
        "/api/v1/face/register",
        json={"mobile_number": employee.mobile_number, "face_image_base64": "A" * 7_000_001},
        headers=auth(org),
    )
    assert response.status_code == 422


def test_face_errors_do_not_reveal_server_details(monkeypatch):
    def boom():
        raise RuntimeError("connection to db-internal.example:5432 failed")

    monkeypatch.setattr(face_service.rekognition, "create_face_liveness_session", boom)
    result = face_service.create_liveness_session()

    assert result["status_code"] == 500
    assert "db-internal" not in str(result["body"])


# --- Organisations stay separate -------------------------------------------

def test_department_cannot_use_another_organisations_office(client, db):
    mine, theirs = make_org(db, mobile="9000000001"), make_org(db, mobile="9000000002")
    for org in (mine, theirs):
        db.add(Location(location_name="Office", latitude=0, longitude=0, radius_meters=100, org_id=org.org_id))
    db.commit()
    my_office, their_office = (
        db.query(Location).filter(Location.org_id == org.org_id).one().location_id for org in (mine, theirs)
    )

    refused = client.post(
        "/api/v1/departments/add",
        json={"details": "Sales", "location": their_office},
        headers=auth(mine),
    )
    assert refused.status_code == 400

    allowed = client.post(
        "/api/v1/departments/add",
        json={"details": "Sales", "location": my_office},
        headers=auth(mine),
    )
    assert allowed.status_code == 201


def test_organisation_cannot_read_another_organisations_employee(client, db):
    mine, theirs = make_org(db, mobile="9000000001"), make_org(db, mobile="9000000002")
    their_employee = make_employee(db, theirs)

    response = client.get(f"/api/v1/employees/{their_employee.org_id}", headers=auth(mine))
    assert response.status_code == 404


def test_employee_cannot_use_admin_routes_or_others_tasks(client, db):
    org = make_org(db)
    me = make_employee(db, org, mobile="8000000001")
    colleague = make_employee(db, org, mobile="8000000002")
    db.add(Task(org_id=org.org_id, employee_id=colleague.org_id, title="Theirs", assigned_date=date.today()))
    db.commit()
    task_id = db.query(Task).one().task_id

    assert client.get("/api/v1/employees", headers=auth(me)).status_code == 403
    assert client.get("/api/v1/dashboard/summary", headers=auth(me)).status_code == 403
    assert client.get(f"/api/v1/tasks/{task_id}", headers=auth(me)).status_code == 404
    assert client.patch(
        f"/api/v1/tasks/{task_id}/status", json={"status": "completed"}, headers=auth(me)
    ).status_code == 404


def test_signed_out_requests_are_refused(client, db):
    assert client.get("/api/v1/employees").status_code in (401, 403)
    bad = {"Authorization": "Bearer not-a-token"}
    assert client.get("/api/v1/employees", headers=bad).status_code == 401


# --- Responses ---------------------------------------------------------------

def test_security_headers_are_sent(client, db):
    response = client.get("/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_oversized_requests_are_refused(client, db):
    response = client.post("/api/v1/org/login", content=b"x" * (13 * 1024 * 1024))
    assert response.status_code == 413


def test_debug_routes_are_not_reachable_from_other_computers(client, db):
    # The test client is not 127.0.0.1; with DEBUG off the routes don't exist at all.
    assert client.get("/api/v1/debug/users").status_code == 404


def test_unexpected_errors_return_a_plain_message(client, db, monkeypatch):
    from app.api.v1 import health

    def broken(*args, **kwargs):
        raise RuntimeError("password=hunter2 at /srv/app/secret.py")

    monkeypatch.setattr(health, "text", broken)
    response = TestClientNoRaise().get("/api/v1/health/db")
    assert response.status_code == 500
    assert "hunter2" not in response.text
    assert "secret.py" not in response.text


def TestClientNoRaise():
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


# --- Change password ---------------------------------------------------------

def _sign_in_admin(client, mobile, password):
    response = client.post("/api/v1/org/login", json={"mobile_number": mobile, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def test_admin_changes_password_and_other_devices_are_signed_out(client, db):
    make_org(db, mobile="9000000001", password="old-password")
    this_phone = _sign_in_admin(client, "9000000001", "old-password")
    other_phone = _sign_in_admin(client, "9000000001", "old-password")

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "new-password-1", "refresh": this_phone["refresh"]},
        headers={"Authorization": f"Bearer {this_phone['access']}"},
    )
    assert response.status_code == 200, response.text

    # The other device can no longer renew its session; this one can.
    assert client.post("/api/v1/auth/refresh", json={"refresh": other_phone["refresh"]}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh": this_phone["refresh"]}).status_code == 200

    # Only the new password works now.
    assert client.post("/api/v1/org/login", json={"mobile_number": "9000000001", "password": "old-password"}).status_code == 401
    _sign_in_admin(client, "9000000001", "new-password-1")


def test_employee_changes_their_member_password(client, db):
    org = make_org(db)
    employee = make_employee(db, org, member_password="first-pass")

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "first-pass", "new_password": "second-pass"},
        headers=auth(employee),
    )
    assert response.status_code == 200, response.text

    old = client.post("/api/v1/member/login", json={"mobile_number": employee.mobile_number, "password": "first-pass"})
    new = client.post("/api/v1/member/login", json={"mobile_number": employee.mobile_number, "password": "second-pass"})
    assert old.status_code == 400
    assert new.status_code == 200


def test_change_password_needs_the_current_password(client, db):
    org = make_org(db, password="old-password")
    wrong = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "not-it", "new_password": "new-password-1"},
        headers=auth(org),
    )
    same = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "old-password"},
        headers=auth(org),
    )
    short = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "short"},
        headers=auth(org),
    )
    signed_out = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "new-password-1"},
    )
    assert wrong.status_code == 400
    assert same.status_code == 400
    assert short.status_code == 422
    assert signed_out.status_code in (401, 403)


def test_change_password_keeps_this_phones_notifications_only(client, db):
    from app.models.notification import PushDevice

    org = make_org(db, password="old-password")
    db.add_all([
        PushDevice(user_id=org.org_id, token="ExponentPushToken[this]", platform="android"),
        PushDevice(user_id=org.org_id, token="ExponentPushToken[other]", platform="ios"),
    ])
    db.commit()

    response = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "old-password", "new_password": "new-password-1", "push_token": "ExponentPushToken[this]"},
        headers=auth(org),
    )
    assert response.status_code == 200
    db.expire_all()
    assert [d.token for d in db.query(PushDevice).all()] == ["ExponentPushToken[this]"]


# --- Photos ------------------------------------------------------------------

def test_each_face_photo_gets_a_new_address(db, monkeypatch):
    org = make_org(db)
    employee = make_employee(db, org)
    saved, deleted = [], []

    class FakeStore:
        def save(self, key, data, content_type):
            saved.append(key)

        def delete(self, key):
            deleted.append(key)

    monkeypatch.setattr(face_service, "media_store", FakeStore())
    monkeypatch.setattr(face_service, "resize_photo", lambda b: b)

    face_service.sync_employee_photo(db, employee.mobile_number, b"one")
    face_service.sync_employee_photo(db, employee.mobile_number, b"two")

    assert len(set(saved)) == 2
    # Random names that don't reveal the phone number.
    assert all(employee.mobile_number not in key for key in saved)
    # The first photo is removed once the second replaces it.
    assert deleted == [saved[0]]


def test_photos_and_faces_are_kept_in_the_database(client, db, monkeypatch):
    if not storage.uses_database():
        pytest.skip("MEDIA_STORAGE is not database here")
    org = make_org(db)
    employee = make_employee(db, org)
    monkeypatch.setattr(face_service, "resize_photo", lambda b: b)

    face_service.sync_employee_photo(db, employee.mobile_number, b"photo-bytes")
    photo = db.get(Employee, employee.org_id).photo
    response = client.get(f"/media/{photo}")
    assert response.status_code == 200
    assert response.content == b"photo-bytes"
    assert response.headers["content-type"] == "image/jpeg"

    # Enrolled face images are kept too, but never served.
    storage.face_store.save(f"{employee.mobile_number}.jpg", b"face-bytes", "image/jpeg")
    assert storage.face_store.read(f"{employee.mobile_number}.jpg") == b"face-bytes"
    assert client.get(f"/media/faces/{employee.mobile_number}.jpg").status_code == 404


# --- Department, designation and shift must match ------------------------------

def _org_with_two_departments(db):
    from datetime import time

    from app.models.department import Department
    from app.models.designation import Designation
    from app.models.shift import Shift

    org = make_org(db)
    db.add(Location(location_name="Office", latitude=0, longitude=0, radius_meters=100, org_id=org.org_id))
    db.commit()
    office = db.query(Location).one().location_id
    ids = {}
    for name in ("IT", "BPO"):
        department = Department(org_id=org.org_id, details=name, location_id=office)
        db.add(department)
        db.flush()
        designation = Designation(department_id=department.department_id, details=f"{name} role")
        shift = Shift(
            shift_name=f"{name} day",
            shift_start_time=time(9),
            shift_end_time=time(18),
            department_id=department.department_id,
        )
        db.add_all([designation, shift])
        db.flush()
        ids[name] = (department.department_id, designation.designation_id, shift.shift_id)
    db.commit()
    return org, ids


def _new_employee(department, designation, shift):
    return {
        "mobile_number": "7000000009",
        "email": "new@example.com",
        "first_name": "Asha",
        "last_name": "Rao",
        "department": department,
        "designation": designation,
        "shift": shift,
        "manager": None,
    }


def test_designation_and_shift_must_be_from_the_employees_department(client, db):
    org, ids = _org_with_two_departments(db)
    bpo, it = ids["BPO"], ids["IT"]

    wrong_designation = client.post("/api/v1/employees", json=_new_employee(bpo[0], it[1], bpo[2]), headers=auth(org))
    wrong_shift = client.post("/api/v1/employees", json=_new_employee(bpo[0], bpo[1], it[2]), headers=auth(org))
    right = client.post("/api/v1/employees", json=_new_employee(bpo[0], bpo[1], bpo[2]), headers=auth(org))

    assert wrong_designation.status_code == 400
    assert "another department" in wrong_designation.json()["message"]
    assert wrong_shift.status_code == 400
    assert right.status_code == 201


def test_employee_saved_with_a_wrong_designation_can_still_be_renamed(client, db):
    org, ids = _org_with_two_departments(db)
    bpo, it = ids["BPO"], ids["IT"]
    employee = make_employee(db, org)
    record = db.query(Employee).filter(Employee.user_id == employee.org_id).one()
    record.department_id, record.designation_id, record.shift_id = bpo[0], it[1], it[2]
    db.commit()

    renamed = client.put(f"/api/v1/employees/{employee.org_id}", json={"first_name": "Asha"}, headers=auth(org))
    assert renamed.status_code == 200

    # Changing their department, designation or shift needs a matching set.
    still_wrong = client.put(f"/api/v1/employees/{employee.org_id}", json={"shift": bpo[2]}, headers=auth(org))
    fixed = client.put(
        f"/api/v1/employees/{employee.org_id}",
        json={"designation": bpo[1], "shift": bpo[2]},
        headers=auth(org),
    )
    assert still_wrong.status_code == 400
    assert fixed.status_code == 200


# --- Bypasses closed before handover (2026-10-17) --------------------------

def test_employee_cannot_use_the_admin_sign_in(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    # Even if their account password were known (it is random otherwise).
    employee.password = hash_password("known-password")
    db.commit()

    response = client.post(
        "/api/v1/org/login",
        json={"mobile_number": employee.mobile_number, "password": "known-password"},
    )

    assert response.status_code == 401


def test_employee_password_reset_still_needs_the_face_check(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    old_account_password = employee.password
    _, _, body = account_service.prepare_password_reset(db, employee.email)
    token = body.split("token=")[1].split()[0]

    reset = client.post("/api/v1/reset-password", json={"token": token, "password": "brand-new-pass"})
    assert reset.status_code == 200

    db.refresh(employee)
    assert employee.password == old_account_password
    admin_login = client.post(
        "/api/v1/org/login",
        json={"mobile_number": employee.mobile_number, "password": "brand-new-pass"},
    )
    assert admin_login.status_code == 401
    # The new password is the employee password: sign-in then asks for the face.
    member_login = client.post(
        "/api/v1/member/login",
        json={"mobile_number": employee.mobile_number, "password": "brand-new-pass"},
    )
    assert member_login.status_code == 200
    assert "access" not in member_login.json()
    # The link works once.
    again = client.post("/api/v1/reset-password", json={"token": token, "password": "another-pass-1"})
    assert again.status_code == 400


def test_still_photo_face_check_is_gone(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    response = client.post(
        "/api/v1/face/verify",
        json={"mobile_number": employee.mobile_number, "face_image_base64": "aGVsbG8="},
        headers=auth(employee),
    )
    assert response.status_code in (404, 405)


def test_check_in_with_fake_gps_is_refused(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    response = client.post(
        "/api/v1/attendance/mark",
        json={
            "action": "checkin",
            "latitude": 12.9,
            "longitude": 77.6,
            "accuracy": 10,
            "face_token": create_face_token(employee.mobile_number),
            "is_mocked": True,
        },
        headers=auth(employee),
    )
    assert response.status_code == 400
    assert "Fake location" in response.text


def test_id_cards_cannot_be_listed_by_number(client, db):
    org = make_org(db)
    employee = make_employee(db, org)
    other_org = make_org(db, mobile="9000000002")
    eid = employee.org_id

    assert client.get(f"/api/v1/employees/{eid}/card").status_code == 401
    assert client.get(f"/api/v1/employees/{eid}/card", headers=auth(other_org)).status_code == 404
    assert client.get(f"/api/v1/employees/{eid}/card", headers=auth(org)).status_code == 200
    mine = client.get(f"/api/v1/employees/{eid}/card", headers=auth(employee))
    assert mine.status_code == 200

    code = mine.json()["card_code"]
    assert code == create_card_code(eid)
    public = client.get(f"/api/v1/cards/{code}")
    assert public.status_code == 200
    assert "mobile_number" not in public.json()
    assert client.get(f"/api/v1/cards/{eid}").status_code == 404
    assert client.get(f"/api/v1/cards/{eid}-forged").status_code == 404
    assert client.get(f"/api/v1/cards/{eid + 1}-{code.split('-')[1]}").status_code == 404


def test_dashboard_reports_setup_progress(client, db):
    org = make_org(db)
    make_employee(db, org)
    response = client.get("/api/v1/dashboard/summary", headers=auth(org))
    assert response.status_code == 200
    assert response.json()["setup"] == {
        "locations": 0, "departments": 0, "designations": 0,
        "shifts": 0, "employees": 1, "faces": 0,
    }


# --- Managers assign tasks to their direct reports --------------------------

def _reports_to(db, employee_user, manager_user):
    row = db.query(Employee).filter(Employee.user_id == employee_user.org_id).one()
    row.manager_id = manager_user.org_id
    db.commit()


def _task(employee_user, title="Check stock"):
    return {"employee_id": employee_user.org_id, "title": title, "assigned_date": "2026-10-18"}


def test_manager_assigns_and_manages_tasks_for_direct_reports_only(client, db):
    org = make_org(db)
    manager = make_employee(db, org, mobile="8000000001")
    report = make_employee(db, org, mobile="8000000002")
    grand_report = make_employee(db, org, mobile="8000000003")
    outsider = make_employee(db, org, mobile="8000000004")
    _reports_to(db, report, manager)
    _reports_to(db, grand_report, report)

    team = client.get("/api/v1/team", headers=auth(manager)).json()
    assert [m["employee_id"] for m in team] == [report.org_id]
    profile = client.get("/api/v1/employee-details", headers=auth(manager)).json()
    assert profile["team_size"] == 1

    created = client.post("/api/v1/tasks", json=_task(report), headers=auth(manager))
    assert created.status_code == 201
    task = created.json()
    assert task["assigned_by_manager"] is True
    assert task["created_by_id"] == manager.org_id

    # Not someone further down, and not someone outside the team.
    assert client.post("/api/v1/tasks", json=_task(grand_report), headers=auth(manager)).status_code == 400
    assert client.post("/api/v1/tasks", json=_task(outsider), headers=auth(manager)).status_code == 400

    team_tasks = client.get("/api/v1/tasks?scope=team", headers=auth(manager)).json()
    assert [t["task_id"] for t in team_tasks] == [task["task_id"]]
    # The report sees it as their own task.
    mine = client.get("/api/v1/tasks", headers=auth(report)).json()
    assert [t["task_id"] for t in mine] == [task["task_id"]]

    edited = client.put(f"/api/v1/tasks/{task['task_id']}", json={"title": "Count stock"}, headers=auth(manager))
    assert edited.status_code == 200
    # The manager can't move it to someone outside the team.
    moved = client.put(f"/api/v1/tasks/{task['task_id']}", json={"employee_id": outsider.org_id}, headers=auth(manager))
    assert moved.status_code == 400
    # The assignee can't edit or delete it, only change its status.
    assert client.put(f"/api/v1/tasks/{task['task_id']}", json={"title": "x"}, headers=auth(report)).status_code == 403
    assert client.delete(f"/api/v1/tasks/{task['task_id']}", headers=auth(report)).status_code == 403
    status = client.patch(f"/api/v1/tasks/{task['task_id']}/status", json={"status": "in_progress"}, headers=auth(report))
    assert status.status_code == 200

    assert client.delete(f"/api/v1/tasks/{task['task_id']}", headers=auth(manager)).status_code == 200


def test_manager_cannot_change_the_admins_tasks(client, db):
    org = make_org(db)
    manager = make_employee(db, org, mobile="8000000001")
    report = make_employee(db, org, mobile="8000000002")
    _reports_to(db, report, manager)
    admin_task = client.post("/api/v1/tasks", json=_task(report), headers=auth(org)).json()

    # Visible to the manager, but only the admin can change it.
    assert client.get(f"/api/v1/tasks/{admin_task['task_id']}", headers=auth(manager)).status_code == 200
    assert client.put(f"/api/v1/tasks/{admin_task['task_id']}", json={"title": "x"}, headers=auth(manager)).status_code == 403
    assert client.delete(f"/api/v1/tasks/{admin_task['task_id']}", headers=auth(manager)).status_code == 403
    status = client.patch(f"/api/v1/tasks/{admin_task['task_id']}/status", json={"status": "completed"}, headers=auth(manager))
    assert status.status_code == 403


def test_employee_without_a_team_cannot_assign_tasks(client, db):
    org = make_org(db)
    employee = make_employee(db, org, mobile="8000000001")
    other = make_employee(db, org, mobile="8000000002")

    assert client.get("/api/v1/team", headers=auth(employee)).json() == []
    assert client.get("/api/v1/tasks?scope=team", headers=auth(employee)).json() == []
    assert client.post("/api/v1/tasks", json=_task(other), headers=auth(employee)).status_code == 403
