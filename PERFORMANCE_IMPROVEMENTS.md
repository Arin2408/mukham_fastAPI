# Mukham Backend — Performance Improvements

This document lists the performance problems found in the current Django codebase and the recommended fix for each.
The existing PostgreSQL database and the Next.js frontend are kept. The only database change is one additive migration (indexes + a constraint), and the frontend changes are small (see items 2, 6, 11). None of this depends on the FastAPI migration.
These fixes address most of the current slowness and also carry over into a FastAPI version if the migration still goes ahead.

Under each item, **✅ What was done** records completed work, **⏳ Left** records follow-ups, and **⏸️** marks items that are skipped or deferred.

Items are ordered by expected impact.

---

## 1. Face registration compares against every stored face, one AWS call at a time

**Where:** `face_auth/views.py` — `is_duplicate_face()` (called from `register_face` and `get_liveness_result` in `register` mode)

**Problem:**
To prevent the same face being registered twice, the code loads every row of `EmployeeFaceData` (across all organisations), decodes each base64 image, and calls `rekognition.compare_faces()` sequentially for each one.
Each AWS call takes roughly 0.3–1 s, so registration time grows linearly with the number of employees — with a few hundred employees a single registration takes minutes and can hit request timeouts.

**Solution:** Use an AWS Rekognition **Face Collection**.
- Create one collection (or one per organisation, e.g. `mukham-org-<org_id>`).
- On registration, call `IndexFaces` with `ExternalImageId=<mobile_number>` to store the face in the collection.
- For the duplicate check, call `SearchFacesByImage` once with `FaceMatchThreshold=90`. If a match comes back with a different `ExternalImageId`, it is a duplicate.
- Optionally, verification can also use `SearchFacesByImage` / `CompareFaces` against the collection instead of decoding the stored image.
- One-time backfill: run a script that indexes all existing `EmployeeFaceData` images into the collection.

Result: N sequential AWS calls → 1 call, regardless of employee count.

**⏸️ Status: Skipped for now** (decision: the Rekognition Collection change is not being done at this stage). Registration time will keep growing with the number of registered faces until this is done.

---

## 2. Backend and frontend both run development servers

**Where:**
- `mukham_backend/Dockerfile` — `CMD ["python", "manage.py", "runserver", "0.0.0.0:8001"]`
- `mukham/settings.py` — `DEBUG = os.getenv('DEBUG', 'True') == 'True'`
- `mukham_frontend/Dockerfile` — `CMD ["npm", "run", "dev"]`, with `RUN npm run build` commented out

**Problem:**
- `runserver` is a single-process development server, not meant for production load.
- `DEBUG=True` makes Django record every SQL query in memory and adds overhead to every request.
- `next dev` compiles each page on demand on first visit, and ships unminified, non-optimised bundles.

**Solution:**
- Backend: run with Gunicorn using multiple workers, e.g.
  `gunicorn mukham.wsgi:application --bind 0.0.0.0:8001 --workers 4 --timeout 60`
  (rule of thumb: `2 × CPU cores + 1` workers). Add `gunicorn` to `requirements.txt`.
- Default `DEBUG` to `False`; enable it only in local `.env`.
- Frontend: uncomment `RUN npm run build` and change the command to `CMD ["npm", "run", "start"]`.

**✅ What was done (Step 1):**
- `Dockerfile` (backend): replaced `runserver` with Gunicorn — `gthread` workers, configurable through `GUNICORN_WORKERS` (default 4), `GUNICORN_THREADS` (default 4), `GUNICORN_TIMEOUT` (default 60). Removed the MySQL build packages (`build-essential`, `default-libmysqlclient-dev`) since they are no longer needed, which also makes the image smaller.
- `requirements.txt`: added `gunicorn==23.0.0`.
- `mukham/settings.py`: `DEBUG` now defaults to `False`. Local development still gets `DEBUG=True` from `.env`.
- `mukham_frontend/Dockerfile`: now runs `npm ci` → `npm run build` → `npm run start`. Because `NEXT_PUBLIC_*` values are baked in at build time and `.env.local` is excluded by `.dockerignore`, they are passed as build args:
  `docker build --build-arg NEXT_PUBLIC_API_URL=... --build-arg NEXT_PUBLIC_AWS_REGION=... --build-arg NEXT_PUBLIC_AWS_IDENTITY_POOL_ID=... .`
- Verified: `npm run build` completes successfully; `manage.py check` passes with `DEBUG=False`.
- Note: Gunicorn does not run on Windows, so local development on Windows keeps using `python manage.py runserver`. Gunicorn is used inside Docker / on Linux servers.
- Note: with `DEBUG=False`, Django admin CSS/JS is not served. If the admin panel is used in production, add `STATIC_ROOT` + `collectstatic` (or WhiteNoise).

---

## 3. A new PostgreSQL connection is opened on every request

**Where:** `mukham/settings.py` — `DATABASES['default']` has no `CONN_MAX_AGE`

**Problem:** Django's default `CONN_MAX_AGE=0` opens and closes a database connection for every request. Connecting to PostgreSQL (especially a remote/managed one) adds noticeable latency to every API call.

**Solution:**
- Add `'CONN_MAX_AGE': 60` and `'CONN_HEALTH_CHECKS': True` to the default database config, **or** use Django 5.1's built-in psycopg connection pool:
  `'OPTIONS': {'pool': {'min_size': 2, 'max_size': 10}}`.
- Add `psycopg[binary]` to `requirements.txt` (it is currently missing; `mysqlclient` / `PyMySQL` are listed instead and can be removed).
- Remove the unused `sqlite_source` database entry once the migration from SQLite is confirmed done.

**✅ What was done (Step 1):**
- `mukham/settings.py`: added `CONN_MAX_AGE` (default 60 s, configurable with `DB_CONN_MAX_AGE`) and `CONN_HEALTH_CHECKS = True`, so each worker reuses its PostgreSQL connection and drops it automatically if it goes stale.
- Used `CONN_MAX_AGE` rather than Django's built-in pool because the pool requires psycopg 3, while the project uses `psycopg2-binary`. This can be revisited later.
- `requirements.txt`: added `psycopg2-binary==2.9.13` (the version already in `.venv`), removed the unused `mysqlclient` and `PyMySQL`.
- `mukham/settings.py`: removed the unused `sqlite_source` database (the SQLite file is no longer in the repo).
- Verified: `CONN_MAX_AGE` is applied and the app connects to PostgreSQL.

---

## 4. N+1 queries in list endpoints

**Where:**
- `employees/views.py` — `list_users` uses `EmployeeListSerializer`, which reads `user`, `department`, `designation`, `shift`, `office_location` per employee.
- `employees/serializers.py` — `AttendanceSerializer` reads `employee` and `employee.user` per attendance row.
- `employees/serializers.py` — `UserProfileSerializer` uses `depth = 1` plus `obj.organisation` / `obj.user`.
- `employees/serializers.py` — `EmployeeDetailSerializer.get_attendance_history` runs a separate query per employee.

**Problem:** For each row returned, the serializer triggers extra queries. Listing 100 employees runs ~500 queries; listing 1,000 attendance rows runs ~2,000 queries.

**Solution:** Load related rows in the same query.
- Employee list:
  ```python
  Customuser.objects.filter(organisation_id=org_id)
      .exclude(user__is_organization=True)
      .select_related("user", "department", "designation", "shift", "office_location")
  ```
- Attendance history:
  ```python
  Attendance.objects.filter(...).select_related("employee", "employee__user")
  ```
- Profile / login responses: `select_related("user", "organisation", "department", "designation", "shift", "office_location")` when fetching the employee.
- Any serializer that returns many employees with attendance: use `prefetch_related(Prefetch("attendances", queryset=...))` instead of a per-object query.

**✅ What was done (Step 2):**
- `employees/views.py`: added `EMPLOYEE_RELATED` and a helper `get_employee_profile(user)` that loads an employee together with `user`, `organisation`, `department`, `designation`, `shift` and `office_location` in one JOIN query.
- `list_users`: the employee list now uses `select_related("user", "department", "designation", "shift", "office_location")`.
- `employee_attendance` (attendance history): uses `select_related("employee", "employee__user")`. For employees it filters by `employee_id=request.user.pk` directly instead of first loading `request.user.employee`.
- `login_view_employee`, `member_login_view`, `employee_details`, the `list_users` profile fallback and `mark_attendance` now use `get_employee_profile()` / `select_related(*EMPLOYEE_RELATED)` instead of the lazy `user.employee` accessor. Error handling changed from `except AttributeError` to `except Customuser.DoesNotExist`; responses are unchanged.
- `EmployeeDetailSerializer` and `CustomuserSerializer` are not used by any view, so they were left as they are.
- Verified with temporary test data (50 employees, 1,000 attendance rows, created inside a transaction and rolled back):

  | Endpoint | Queries before | Queries after | Time before | Time after |
  |---|---|---|---|---|
  | `GET /api/list/` (org, 50 employees) | 251 | 1 | — | 12 ms |
  | `GET /api/attendance-history/` (org, 1,000 rows) | 2,001 | 1 | 1,857 ms | 85 ms |
  | `GET /api/attendance-history/` (employee, 20 rows) | 41 | 1 | 37 ms | 5 ms |
  | `POST /api/mark-attendance/` (employee) | — | 3 | — | 8 ms |

  Response contents are unchanged.

---

## 5. Department leaderboard runs two COUNT queries per department

**Where:** `departments/views.py` — `department_leaderboard`

**Problem:** Inside a loop over departments it runs one `count()` for total attendance and another for on-time attendance — `2 × number_of_departments` queries.

**Solution:** Compute everything in one aggregated query:
```python
from django.db.models import Count, Q

departments = (
    Department.objects.filter(org=request.user.org_id)
    .annotate(
        total_attendances=Count("customuser__attendances"),
        on_time=Count(
            "customuser__attendances",
            filter=Q(customuser__attendances__status__in=["Early", "On Time"]),
        ),
    )
)
```
Then calculate the punctuality score from the annotated values in Python. (Check the reverse relation name from `Department` to `Customuser`; it is `customuser` by default.)

**✅ What was done (Step 2):**
- `departments/views.py` — `department_leaderboard` now annotates `total_attendance` and `on_time_count` in a single query (using the existing `Count` / `Q` imports). The score calculation, rounding, sorting and response format are unchanged.
- Verified: with 5 departments, queries went from 11 → 1, and the scores and totals match the old per-department `count()` results exactly.

---

## 6. Attendance history is not paginated

**Where:** `employees/views.py` — `employee_attendance` (`/api/attendance-history/`)

**Problem:** For an organisation admin this returns **every attendance record of every employee, ever**, in one response. The response size and query time grow without limit as data accumulates.

**Solution:**
- Add pagination (DRF `LimitOffsetPagination` or `PageNumberPagination`), or at minimum a date-range filter (`?from=YYYY-MM-DD&to=YYYY-MM-DD`) with a sensible default such as the last 30 days.
- Update the frontend attendance pages to request pages / ranges.
- Add a composite index to support the query pattern:
  `models.Index(fields=["employee", "-check_in"])` on `Attendance`.

**✅ What was done (Step 4):**
- `employees/views.py` — `employee_attendance` accepts optional query params (newest first):
  - `?from=YYYY-MM-DD` / `?to=YYYY-MM-DD`: local (IST) dates, inclusive, converted to a `check_in` range so the index can be used.
  - `?limit=N&offset=M`: `limit` from 1 to `MAX_ATTENDANCE_PAGE_SIZE` (1000).
  - Invalid values return `400`.
  - **With no params the full list is returned exactly as before**, and the response is still a plain JSON array, so older clients keep working.
- `employees/models.py` + migration `employees/0010_attendance_indexes_and_open_constraint.py`: added indexes `attendance_emp_checkin_idx (employee_id, check_in DESC)` for an employee's own history and `attendance_checkin_idx (check_in DESC)` for organisation history with a date range.
- Frontend:
  - `app/attendance/page.js` (admin "Live History") now loads only the last 30 days (`HISTORY_DAYS` constant) and the heading shows "(last 30 days)". **Behaviour change:** the per-employee "entries" and "hours" totals on this page now cover the last 30 days instead of all time. Change `HISTORY_DAYS` if a different window is wanted.
  - `app/member/page.jsx` loads `?limit=60` (the newest 60 sessions). The open session, if any, is always the newest record, so restoring it after a page refresh still works.
- Verified: no params → full list; `limit`/`offset` return the correct slices; `from`/`to` filter correctly; invalid params → 400; `npm run build` passes.

**⏳ Left:** the admin page has no "load older" / date picker yet. If older history is needed there, add a date-range selector that passes `from`/`to`.

---

## 7. Face images stored as base64 text in PostgreSQL

**Where:** `face_auth/models.py` — `EmployeeFaceData.face_image_base64 = TextField()`

**Problem:**
- Base64 is ~33% larger than the raw image, and every row is a large TOAST value in Postgres.
- Every verification reads and decodes the full image from the database.
- The same image is also saved again as `Customuser.photo` on disk, so it is stored twice.

**Solution:**
- Once the Rekognition Collection (item 1) is in place, verification no longer needs the stored image bytes — compare against the collection instead.
- Move the reference image to S3 (or keep only the file in `photo`) and store only the key/path in the database.
- Keep the existing column during transition and remove it with a later migration once nothing reads it.

**⏸️ Status: Deferred, to be done together with item 1.**
Every face verification (`/api/face/verify/`, `/api/face/liveness/result/`) still needs the stored reference image, because without the Rekognition Collection (item 1, skipped) the comparison is image-to-image. Moving the image out of Postgres on its own would not make things faster:
- **S3:** adds a network fetch (S3 GET) to every verification, so it would be *slower* than reading one row from Postgres.
- **Local disk:** breaks as soon as more than one backend server/container runs, because each one has its own disk.
- The base64 decode itself takes well under a millisecond (it is logged as "Face image decode time").

Once item 1 is done, verification compares against the collection, the stored image is no longer read on the hot path, and it can then be moved to S3 (or dropped) safely.

---

## 8. Hot-path `print()` and `sys.stdout.flush()` calls

**Where:** throughout `employees/views.py`, `face_auth/views.py`, `employees/serializers.py`

**Problem:** Synchronous, unbuffered console writes (with explicit `flush()`) on every request add latency and produce noisy, unstructured logs. Some print user data (mobile numbers, names).

**Solution:** Replace with Python's `logging` module (`logger = logging.getLogger(__name__)`), use `logger.debug` for diagnostic lines, and set the log level to `INFO` or `WARNING` in production via `LOGGING` in `settings.py`.

**✅ What was done (Step 5):**
- All 65 `print()` / `sys.stdout.flush()` / `traceback.print_exc()` calls in `employees/views.py`, `employees/serializers.py`, `organisation/views.py` and `face_auth/views.py` were removed or converted to `logging`, using lazy `%s` formatting so disabled levels cost almost nothing:
  - timings and diagnostics → `logger.debug`
  - outcomes (face registered / matched / not matched, liveness status) → `logger.info`
  - AWS client errors → `logger.warning`
  - unexpected exceptions → `logger.exception` (includes the stack trace)
- Removed log lines that were both slow and unsafe:
  - `organisation/views.py` org login printed the **plaintext password** on every attempt.
  - On every failed org login it loaded and printed **every user's mobile number** (`CustomUser.objects.all()`), a full table scan.
  - Employee login and signup printed names and mobile numbers.
- `face_auth/views.py` duplicate-face check: the skip message now uses `other.user_id` (already the mobile number) instead of `other.user.mobile_number`, which ran an extra query.
- `mukham/settings.py`: added `LOGGING` with a single console handler and a timestamped format. App loggers use `LOG_LEVEL` (default `DEBUG` when `DEBUG=True`, otherwise `INFO`; can be overridden by env). Third-party libraries (boto3, urllib3) only log warnings and above. The `django` logger is configured explicitly so request warnings are not printed twice.
- Verified: no `print(` left in app code; with `DEBUG=False` only INFO/WARNING lines appear; responses unchanged.

---

## 9. Too many authentication classes evaluated per request

**Where:** `mukham/settings.py` — `REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES']`

**Problem:** JWT, Token, Basic, and Session authentication are all enabled globally. Views without an explicit `@authentication_classes` try each in turn; `SessionAuthentication` also enforces CSRF and touches the session table, and `BasicAuthentication` runs a full password hash check if a Basic header is present.

**Solution:** Set the default to `JWTAuthentication` only (the frontend uses JWT exclusively). Remove `rest_framework.authtoken` from `INSTALLED_APPS` if no client uses DRF tokens.

**✅ What was done (Step 5):**
- `mukham/settings.py`: `DEFAULT_AUTHENTICATION_CLASSES` is now only `JWTAuthentication`. Confirmed first that the frontend only sends `Authorization: Bearer <jwt>` (`context/AuthContext.jsx`) and that no backend code uses Token / Basic / Session auth.
- Django Admin is not affected; it uses its own session login, not DRF.
- `rest_framework.authtoken` was **left in `INSTALLED_APPS`**: removing it gives no speed benefit and would leave an orphaned `authtoken_token` table. It can be removed in a later cleanup.
- Verified: valid JWT works as before; no token / a Basic header / an invalid Bearer token → `401`.

---

## 10. Media files are served by Django only in DEBUG mode

**Where:** `mukham/urls.py` — `if settings.DEBUG: urlpatterns += static(...)`

**Problem:** Once `DEBUG=False` (item 2), employee photos under `/media/` stop being served. Serving media through Django is also slow compared with a web server or CDN.

**Solution:** Serve `/media/` from nginx (or a cloud load balancer / CDN), or move uploads to S3 via `django-storages` and return S3 URLs.

**✅ What was done (Step 1):**
- `mukham/settings.py`: added a `SERVE_MEDIA` flag (default `True`).
- `mukham/urls.py`: replaced the `if settings.DEBUG: static(...)` block with an explicit `/media/` route that works when `DEBUG=False`, enabled by `SERVE_MEDIA`. Employee photos keep working after DEBUG is turned off.
- Verified: with `DEBUG=False`, `GET /media/employee_photos/<file>.jpg` returns 200.

**⏳ Left:** this is a stop-gap — Django still serves the files. When nginx / a CDN / S3 is set up, have it serve `/media/` and set `SERVE_MEDIA=False`.

---

## 11. Attendance double-submit creates a check-in followed by an instant check-out

**Where:** `employees/views.py` — `mark_attendance`

**Problem:** The endpoint toggles: if an open record exists it checks out, otherwise it checks in. Two quick requests (double tap, retry on slow network) check the employee in and then immediately out, and concurrent requests can create two open records. This causes extra writes and confusing data, and forces users to retry.

**Solution:**
- Add a partial unique constraint so only one open attendance record can exist per employee:
  ```python
  class Meta:
      constraints = [
          models.UniqueConstraint(
              fields=["employee"],
              condition=Q(check_out__isnull=True),
              name="one_open_attendance_per_employee",
          )
      ]
  ```
- Require an explicit `action` (`checkin` / `checkout`) from the frontend instead of toggling, and wrap the read-then-write in `transaction.atomic()` with `select_for_update()` on the open record.

**✅ What was done (Step 4):**
- `employees/models.py` + migration `0010`: added `UniqueConstraint one_open_attendance_per_employee` (a partial unique index on `employee_id WHERE check_out IS NULL`).
- `employees/views.py` — `mark_attendance` now supports an explicit `action`:
  - `"checkin"`: never checks out. If an open record already exists, it is returned with `200` instead of being closed, so a double tap is harmless.
  - `"checkout"`: only checks out (`404` if nothing is open, as before).
  - no `action`: old toggle behaviour, kept for backward compatibility.
- The open-record lookup and check-out run inside `transaction.atomic()` with `select_for_update()`.
- The insert is wrapped in `transaction.atomic()`. If a parallel request already created an open record, the constraint raises `IntegrityError` and the existing open record is returned instead of a second one being created or the user getting a 500.
- Frontend: all check-in calls now send `action: "checkin"` (`app/member/page.jsx`, `app/dashboard2/page.jsx`, admin `app/attendance/page.js`), and all check-out calls send `action: "checkout"` (`app/dashboard2/page.jsx` and the admin page previously sent no action).
- Verified (rolled-back test data): double check-in → `201` then `200` with the same record and exactly one open row; checkout closes it; checkout with nothing open → `404`; legacy toggle still works; a simulated race is blocked by the constraint and returns the existing record.

**⚠️ Before deploying migration `0010` to another database (staging / production):** make sure no employee has more than one open record, otherwise the migration will fail:
```sql
SELECT employee_id, COUNT(*) FROM employees_attendance
WHERE check_out IS NULL GROUP BY employee_id HAVING COUNT(*) > 1;
```
If rows come back, close the extra older records (set `check_out`) before running `migrate`. (Checked on the local database: none.)

---

## 12. Reuse of boto3 client and AWS timeouts

**Where:** `face_auth/views.py` — module-level `rekognition` client and `aws_config`

**Status:** The client is already created once at module level with keep-alive, which is correct.

**Suggestion:** Reduce `read_timeout` from 20 s to ~8 s and `total_max_attempts` to 2 (already set) so a slow AWS call fails fast instead of holding a Gunicorn worker. With Gunicorn, consider `--worker-class gthread --threads 4` so workers waiting on AWS do not block other requests.

**✅ What was done (Step 5):**
- `face_auth/views.py`: `connect_timeout` 10 s → 3 s and `read_timeout` 20 s → 8 s (`total_max_attempts` stays at 2). The worst case for a stuck AWS call drops from about 60 s to about 22 s.
- `Dockerfile` (done in Step 1): Gunicorn runs with `--worker-class gthread --threads 4`, so a request waiting on AWS ties up one thread rather than a whole worker process.

**⏳ Left:** watch the AWS timing logs (`LOG_LEVEL=DEBUG` shows "Liveness result AWS time" / "Face compare AWS time"). If real calls regularly take more than about 5 s from your server region, raise `read_timeout` a little.

---

## 13. Geofencing gaps in check-in / check-out

> This is a correctness / attendance-integrity issue rather than a speed issue. It is listed here so all backend follow-ups are tracked in one place.

**Where:** `employees/views.py` — `mark_attendance` (geofence block, the `if not employee_id:` branch) and `GEOFENCE_RADIUS_METERS = 100`; `locations/models.py` — `Location`; frontend check-in/check-out calls in `app/member/page.jsx`, `app/dashboard2/page.jsx`, `app/attendance/page.js`

**Current state:** geofencing **is** enforced on the server for employee self check-in. The request must include latitude/longitude, the server calculates the distance (Haversine) to the employee's assigned office (or the organisation's first location), and rejects the check-in with `403` if it is more than 100 m away.

**Problems:**
1. **Admin manual check-in skips the location check.** When an organisation admin marks attendance (request has `employee_id`), no coordinates are checked, and the admin can send any `location_status`.
2. **Check-out has no location check.** An employee can end their session from anywhere, so the recorded `check_out` time and `hours_worked` cannot be trusted.
3. **The radius is the same for every office.** `GEOFENCE_RADIUS_METERS = 100` is hardcoded and is not stored per `Location`, so a large campus and a small office get the same 100 m.
4. **GPS coordinates come from the browser and can be spoofed.** The server does the calculation, but it cannot verify that the latitude/longitude are genuine; a location-spoofing tool or a manually crafted request can pass any coordinates. GPS accuracy is also not checked (a reading with ±2 km accuracy is treated the same as ±5 m).
5. **Fallback to "first location" when none is assigned.** For an employee without an assigned office, the check is against whichever location the query happens to return first, which may not be the employee's office. With several office locations this can wrongly reject a valid check-in.

**Solution:**
1. **Admin manual check-in:** decide whether it is a deliberate override. If it is, keep it but record it explicitly. Add a `marked_by` (admin user) field and a `source` value such as `manual` on `Attendance`, and stop trusting `location_status` from the request (store `manual` instead). This keeps manual entries auditable and separate from GPS-verified ones.
2. **Check-out:** have the frontend send the current latitude/longitude with `action: "checkout"` and run the same distance check on the server. Either reject outside the radius, or accept it but store `checkout_location_status = outside` so admins can see it. A new nullable field is an additive migration.
3. **Per-location radius:** add `radius_meters = PositiveIntegerField(default=100)` to `Location` (additive migration, existing rows get 100). Use `office_location.radius_meters` instead of the constant, and add a radius input to the location form in the admin UI.
4. **Spoofing / accuracy:** it cannot be fully prevented from a web browser, but the risk can be reduced:
   - Send `coords.accuracy` from the browser and reject readings worse than a threshold (e.g. > 100 m).
   - Keep requiring face liveness for self check-in, so the person must be physically present in front of the camera. This is already the case; it is the strongest control available.
   - Validate the coordinate range (lat −90..90, lon −180..180) and reject the obviously fake `0,0`.
   - Store the submitted coordinates and accuracy on the `Attendance` row, so suspicious patterns can be audited later (e.g. identical coordinates every day).
   - Optional: compare the request IP / network against an allow-list of office networks where that is practical.
   - If stronger guarantees are needed later, a native mobile app can use platform integrity / mock-location detection, which a browser cannot.
5. **No assigned office:** reject the check-in with a clear message ("No office location assigned — contact your admin"), or check against **all** of the organisation's locations and accept the nearest one within its radius, instead of using an arbitrary first location.

**Additional problem found while implementing:**

6. **Any employee could bypass both the geofence and the face check.** The checks were skipped whenever the request contained `employee_id`, without checking that the caller was an admin. An employee could add `employee_id` to their own request and check in from anywhere without face verification.

**✅ What was done:**

*Database (migrations `locations/0003_location_radius_meters.py` and `employees/0011_attendance_geofence_audit_fields.py`; both additive, existing rows keep working):*
- `Location.radius_meters`: per-office radius, default 100 m, allowed 10–5000 m. Existing locations get 100 m, the same as before. Latitude/longitude now validate their range (−90..90 / −180..180).
- New `Attendance` fields:
  - `source` (`self` / `manual`) and `marked_by` (the admin who marked it).
  - Check-in GPS: `check_in_latitude`, `check_in_longitude`, `check_in_accuracy`, `check_in_distance`, and `check_in_location` (the office matched).
  - Check-out GPS: `check_out_latitude`, `check_out_longitude`, `check_out_accuracy`, `check_out_distance`, `check_out_location_status` (`inside` / `outside` / `unknown` / `manual`).
  - `location_status` gains a `manual` value.

*Backend (`employees/views.py` — `mark_attendance` + new helpers `parse_gps`, `find_office`, `record_check_out_location`, `GeofenceError`):*
1. **Manual entries:** the manual path is only taken when the caller is an organisation admin (`is_manual`). This fixes problem 6: an employee sending `employee_id` now goes through the GPS and face checks like any self check-in. Manual entries are stored with `source='manual'`, `marked_by=<admin>`, `location_status='manual'`, `face_status='skipped'`. The `location_status` / `face_status` values sent by the client are ignored for manual entries.
2. **Check-out:** GPS sent with a check-out is stored and the check-out is flagged `inside` / `outside`, measured against the office used at check-in. Check-out is **never blocked**, so an employee who forgot to check out can still end the session; no / invalid / imprecise GPS is stored as `unknown`. Admin check-outs are `manual`.
3. **Per-location radius:** the hardcoded `GEOFENCE_RADIUS_METERS` was removed. The check uses the matched office's `radius_meters`, and the rejection message names the office and its radius.
4. **Spoofing / accuracy:**
   - Coordinates are validated: they must be numeric and finite, inside the valid range, and not `0,0`.
   - Readings with `accuracy` worse than `GEOFENCE_MAX_ACCURACY_METERS` (new setting, default 100 m, env-configurable) are rejected with a clear message.
   - Submitted coordinates, accuracy and distance are stored on every record for auditing.
   - Face verification is still required for self check-in.
   - Requests without `accuracy` (older app versions) are still accepted.
5. **No assigned office:** instead of the arbitrary "first" location, the server checks all of the organisation's locations and uses the one the employee is most inside of. If the organisation has no locations, it returns a clear 400.

*API:*
- `AttendanceSerializer` responses now also include `source`, `location_status`, `check_in_distance`, `check_out_location_status` and `check_out_distance` (read-only; existing fields unchanged).
- `LocationSerializer` includes `radius_meters`, which is optional on create (defaults to 100).
- `employee-details` now exposes `office_location.radius_meters` to the app.

*Frontend:*
- New `lib/geo.js`: shared constants plus `getCurrentCoords()` (never throws; returns `null` if location is unavailable) and `officeRadius()`.
- `app/member/page.jsx` and `app/dashboard2/page.jsx`:
  - The client pre-check uses the office's own radius instead of a hardcoded 100 m.
  - Imprecise GPS is rejected early with a helpful message.
  - The pre-check is skipped when no office is assigned, so the server picks the nearest location.
  - `accuracy` is sent with check-in.
  - GPS is sent with check-out, and check-out still works without it.
  - `dashboard2` no longer sends an "outside attempt" request, which the backend always rejected anyway.
- `app/geolocation/page.jsx` (admin): new **Check-in Radius** field when adding a location, plus an inline radius editor with Save on each saved location, so the radius can be changed without deleting the location (which would unassign its employees).
- `app/attendance/page.js` (admin): a new **Flags** column in the expanded logs shows **Manual**, **Out away (Xm)** and **Out: no GPS**.

*Verified:*
- 40 backend checks pass (rolled-back test data). They cover: check-in inside/outside the radius; changing a radius; accuracy too low; missing accuracy (older app); 7 kinds of invalid coordinates; check-out flagged inside / outside / unknown and never blocked; nearest-location matching for employees without an office; an organisation with no locations; the `employee_id` bypass attempt (no GPS, far away, failed face); admin manual check-in/out; cross-organisation admin attempt; location API radius create / update / validation; and the radius exposed in the profile.
- The earlier attendance tests (pagination, double check-in, race) still pass.
- `npm run build` passes; `next lint` reports no new warnings.

**⚠️ Behaviour changes to know about:**
- **Desktop / laptop browsers** often report location accuracy worse than 100 m (Wi-Fi based), so they will now be rejected. If employees check in from laptops, raise `GEOFENCE_MAX_ACCURACY_METERS` in the backend `.env` **and** `GPS_MAX_ACCURACY_METERS` in `lib/geo.js` (keep them equal).
- Admin manual entries can no longer be forced to `Late` / `FAILED_VERIFICATION` by sending `location_status` / `face_status`; their status is calculated from the time, like everyone else's.
- Attendance rows created before this change have `source='self'` and no GPS data, because there is no way to tell which old rows were manual.

**⏳ Left (limits of a web app):** GPS spoofing cannot be fully prevented in a browser. The controls above (accuracy check, stored coordinates for audit, required face liveness) reduce the risk. Stronger guarantees need a native mobile app with mock-location / device-integrity checks, or office-network (IP) checks.

---

## Suggested order of work

| Step | Items | Effort | Status |
|------|-------|--------|--------|
| 1 | Production servers, DEBUG off, connection reuse, media serving (2, 3, 10) | ~0.5 day | ✅ Done |
| 2 | N+1 fixes and leaderboard aggregation (4, 5) | ~0.5 day | ✅ Done |
| 3 | Rekognition Collection + backfill script (1) | ~1–2 days | ⏸️ Skipped for now |
| 4 | Attendance pagination + index, attendance constraint (6, 11) | ~1 day (includes frontend change) | ✅ Done |
| 5 | Logging cleanup, auth classes, AWS timeouts (8, 9, 12) | ~0.5 day | ✅ Done |
| 6 | Move face images out of Postgres (7) | ~1 day | ⏸️ Deferred until item 1 |
| 7 | Geofencing gaps: check-out check, per-location radius, manual-entry audit, accuracy checks (13) | ~1–2 days (includes migration + frontend change) | ✅ Done |

**Measure before and after:** record p50 / p95 latency for login, employee list, attendance history, mark-attendance, and face register/verify before starting, then after each step, so the improvement from each change is visible.

---

## Deployment checklist for the completed work

1. **Database:** run the duplicate-open-attendance check from item 11 on the target database, then `python manage.py migrate` (applies `employees/0010`, `locations/0003` and `employees/0011`; all additive).
2. **Backend environment variables** (all optional; defaults shown):
   - `DEBUG=False`: must be set to `True` explicitly in local `.env` for development.
   - `DB_CONN_MAX_AGE=60`
   - `SERVE_MEDIA=True`: set `False` once nginx / CDN / S3 serves `/media/`.
   - `LOG_LEVEL`: `DEBUG` if `DEBUG=True`, else `INFO`.
   - `GUNICORN_WORKERS=4`, `GUNICORN_THREADS=4`, `GUNICORN_TIMEOUT=60`
   - `GEOFENCE_MAX_ACCURACY_METERS=100`: keep equal to `GPS_MAX_ACCURACY_METERS` in the frontend's `lib/geo.js`.
3. **Backend image:** `pip install -r requirements.txt` (now includes `gunicorn` and `psycopg2-binary`; the MySQL packages were removed).
4. **Frontend image:** build with `--build-arg NEXT_PUBLIC_API_URL=... --build-arg NEXT_PUBLIC_AWS_REGION=... --build-arg NEXT_PUBLIC_AWS_IDENTITY_POOL_ID=...`.
5. **Deploy the backend before (or together with) the frontend.** The new frontend sends `action` and history params, which the old backend would ignore (falling back to the toggle and the full list). The new backend works with the old frontend.
6. Note: the local `.env` has `AAWS_DEFAULT_REGION` (typo, extra `A`), so the code falls back to its default `ap-south-1`. Fix the name if a different region is intended.

