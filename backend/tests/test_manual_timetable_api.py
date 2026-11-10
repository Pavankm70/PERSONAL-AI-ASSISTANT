import pytest
from app.db.models import User, Timetable, TimetablePeriod
from app.core.security import create_access_token

def test_get_empty_timetable(client, auth_headers):
    res = client.get("/api/timetable", headers=auth_headers)
    assert res.status_code == 200
    assert res.json() is None

def test_create_timetable_with_periods(client, auth_headers, test_user):
    payload = {
        "name": "B.Tech Computer Science - Sem 5",
        "academic_year": "2026-2027",
        "semester": "Semester 5",
        "section": "A",
        "periods": [
            {
                "day_of_week": "Monday",
                "subject_name": "Java Programming",
                "subject_code": "CS301",
                "start_time": "09:00",
                "end_time": "10:00",
                "room": "LH-101",
                "faculty": "Dr. Alan",
                "class_type": "Lecture",
                "notes": "Bring laptop"
            },
            {
                "day_of_week": "Monday",
                "subject_name": "Database Management Systems",
                "subject_code": "CS302",
                "start_time": "10:00",
                "end_time": "11:00",
                "room": "LH-102",
                "faculty": "Dr. Sharma",
                "class_type": "Lecture"
            },
            {
                "day_of_week": "Wednesday",
                "subject_name": "DBMS Lab",
                "subject_code": "CS302L",
                "start_time": "14:00",
                "end_time": "16:00",
                "room": "Lab 2",
                "faculty": "Dr. Sharma",
                "class_type": "Lab"
            },
            {
                "day_of_week": "Friday",
                "subject_name": "Computer Networks",
                "subject_code": "CS303",
                "start_time": "11:00",
                "end_time": "12:00",
                "room": "LH-103",
                "faculty": "Prof. Alan",
                "class_type": "Lecture"
            }
        ]
    }
    res = client.post("/api/timetable", headers=auth_headers, json=payload)
    assert res.status_code in (200, 201)
    data = res.json()
    assert data["name"] == "B.Tech Computer Science - Sem 5"
    assert data["academic_year"] == "2026-2027"
    assert data["semester"] == "Semester 5"
    assert data["section"] == "A"
    assert len(data["periods"]) == 4
    
    monday_periods = [p for p in data["periods"] if p["day_of_week"] == "Monday"]
    assert len(monday_periods) == 2
    assert monday_periods[0]["subject_name"] == "Java Programming"

def test_get_timetable_returns_saved_data(client, auth_headers):
    # First create timetable
    payload = {
        "name": "Spring 2026",
        "academic_year": "2026",
        "semester": "Semester 4",
        "section": "B",
        "periods": [
            {
                "day_of_week": "Tuesday",
                "subject_name": "Operating Systems",
                "subject_code": "CS204",
                "start_time": "10:00",
                "end_time": "11:00",
                "room": "Room 201",
                "faculty": "Dr. Miller",
                "class_type": "Lecture"
            }
        ]
    }
    c_res = client.post("/api/timetable", headers=auth_headers, json=payload)
    assert c_res.status_code in (200, 201)
    tt_id = c_res.json()["id"]

    # Now get timetable
    get_res = client.get("/api/timetable", headers=auth_headers)
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["id"] == tt_id
    assert data["name"] == "Spring 2026"
    assert len(data["periods"]) == 1
    assert data["periods"][0]["subject_name"] == "Operating Systems"

def test_update_timetable(client, auth_headers):
    # Create
    create_payload = {
        "name": "Initial Name",
        "periods": [
            {
                "day_of_week": "Monday",
                "subject_name": "Old Class",
                "start_time": "09:00",
                "end_time": "10:00"
            }
        ]
    }
    c_res = client.post("/api/timetable", headers=auth_headers, json=create_payload)
    tt_id = c_res.json()["id"]

    # Update
    update_payload = {
        "name": "Updated Name",
        "semester": "Semester 6",
        "periods": [
            {
                "day_of_week": "Thursday",
                "subject_name": "New Class",
                "subject_code": "CS401",
                "start_time": "11:00",
                "end_time": "12:00",
                "room": "LH-500",
                "class_type": "Lecture"
            }
        ]
    }
    u_res = client.put(f"/api/timetable/{tt_id}", headers=auth_headers, json=update_payload)
    assert u_res.status_code == 200
    u_data = u_res.json()
    assert u_data["name"] == "Updated Name"
    assert u_data["semester"] == "Semester 6"
    assert len(u_data["periods"]) == 1
    assert u_data["periods"][0]["subject_name"] == "New Class"
    assert u_data["periods"][0]["day_of_week"] == "Thursday"

def test_add_update_delete_period(client, auth_headers):
    # Create timetable
    c_res = client.post("/api/timetable", headers=auth_headers, json={"name": "Test TT", "periods": []})
    tt_id = c_res.json()["id"]

    # Add period
    add_payload = {
        "day_of_week": "Wednesday",
        "subject_name": "Software Engineering",
        "subject_code": "CS305",
        "start_time": "14:00",
        "end_time": "15:00",
        "room": "LH-201",
        "faculty": "Prof. Davis",
        "class_type": "Lecture"
    }
    add_res = client.post(f"/api/timetable/{tt_id}/periods", headers=auth_headers, json=add_payload)
    assert add_res.status_code in (200, 201)
    p_data = add_res.json()
    p_id = p_data["id"]
    assert p_data["subject_name"] == "Software Engineering"
    assert p_data["day_of_week"] == "Wednesday"

    # Update period
    update_payload = {
        "subject_name": "Advanced Software Engineering",
        "room": "LH-301",
        "start_time": "14:30",
        "end_time": "15:30"
    }
    up_res = client.put(f"/api/timetable/{tt_id}/periods/{p_id}", headers=auth_headers, json=update_payload)
    assert up_res.status_code == 200
    assert up_res.json()["subject_name"] == "Advanced Software Engineering"
    assert up_res.json()["room"] == "LH-301"
    assert up_res.json()["start_time"] == "14:30"

    # Delete period
    del_res = client.delete(f"/api/timetable/{tt_id}/periods/{p_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify period deleted
    get_res = client.get(f"/api/timetable/{tt_id}", headers=auth_headers)
    assert len(get_res.json()["periods"]) == 0

def test_delete_timetable_cascades(client, auth_headers, db_session, test_user):
    c_res = client.post("/api/timetable", headers=auth_headers, json={
        "name": "To Delete",
        "periods": [
            {
                "day_of_week": "Friday",
                "subject_name": "Biology",
                "start_time": "08:00",
                "end_time": "09:00"
            }
        ]
    })
    tt_id = c_res.json()["id"]

    # Delete timetable
    del_res = client.delete(f"/api/timetable/{tt_id}", headers=auth_headers)
    assert del_res.status_code == 200
    assert del_res.json()["success"] is True

    # Verify periods also wiped from DB
    remaining_periods = db_session.query(TimetablePeriod).filter(TimetablePeriod.timetable_id == tt_id).all()
    assert len(remaining_periods) == 0

    # Verify GET /api/timetable returns None
    get_res = client.get("/api/timetable", headers=auth_headers)
    assert get_res.json() is None

def test_time_validation_invalid_interval(client, auth_headers):
    # End time before start time
    invalid_payload = {
        "name": "Invalid Timetable",
        "periods": [
            {
                "day_of_week": "Monday",
                "subject_name": "Time Traveler Class",
                "start_time": "14:00",
                "end_time": "13:00"
            }
        ]
    }
    res = client.post("/api/timetable", headers=auth_headers, json=invalid_payload)
    assert res.status_code == 400
    assert "must be later than start time" in res.json()["detail"]

def test_tenant_isolation(client, db_session, test_user, auth_headers):
    # Create User B
    user_b = User(
        id="usr_test_tenant_b",
        email="user.b@university.edu",
        full_name="User B",
        timezone="UTC",
        onboarding_complete=True
    )
    db_session.add(user_b)
    db_session.commit()
    user_b_token = create_access_token({"sub": user_b.id, "email": user_b.email})
    headers_b = {"Authorization": f"Bearer {user_b_token}"}

    # User A creates a timetable
    c_res = client.post("/api/timetable", headers=auth_headers, json={
        "name": "User A Timetable",
        "periods": [
            {
                "day_of_week": "Monday",
                "subject_name": "User A Secrets",
                "start_time": "09:00",
                "end_time": "10:00"
            }
        ]
    })
    tt_a_id = c_res.json()["id"]
    p_a_id = c_res.json()["periods"][0]["id"]

    # User B requests timetable: should return None (not User A's timetable!)
    res_b_get = client.get("/api/timetable", headers=headers_b)
    assert res_b_get.status_code == 200
    assert res_b_get.json() is None

    # User B attempts to access User A's timetable by ID: 404
    res_b_id = client.get(f"/api/timetable/{tt_a_id}", headers=headers_b)
    assert res_b_id.status_code == 404

    # User B attempts to update User A's timetable: 404
    res_b_put = client.put(f"/api/timetable/{tt_a_id}", headers=headers_b, json={"name": "Hacked"})
    assert res_b_put.status_code == 404

    # User B attempts to delete User A's timetable: 404
    res_b_del = client.delete(f"/api/timetable/{tt_a_id}", headers=headers_b)
    assert res_b_del.status_code == 404

    # User B attempts to add period to User A's timetable: 404
    res_b_add_p = client.post(f"/api/timetable/{tt_a_id}/periods", headers=headers_b, json={
        "day_of_week": "Tuesday",
        "subject_name": "Injected Period",
        "start_time": "10:00",
        "end_time": "11:00"
    })
    assert res_b_add_p.status_code == 404

    # User B attempts to delete User A's period: 404
    res_b_del_p = client.delete(f"/api/timetable/{tt_a_id}/periods/{p_a_id}", headers=headers_b)
    assert res_b_del_p.status_code == 404
