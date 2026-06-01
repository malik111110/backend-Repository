# Amal Blood Donation & Transfer Backend API

Welcome to the **Amal** backend application. This system manages the business logic, user administration, and automated matching/scheduling rules for a blood transferring and donation platform. 

The API supports two frontend apps:
1. **Mobile Application**: For donors to check eligibility, register profiles, and schedule donation slots, and for recipients to create blood requests.
2. **Web Admin Dashboard**: For administrators to monitor blood stock, accept/complete/cancel donation schedules, and view platform metrics.

---

## 🚀 Key Features

* **JWT-Based Authentication**: Separate roles (`admin` and `user`).
* **Donor Availability & Eligibility Engine**: Automatically enforces the 56-day (8-week) interval rule between whole-blood donations.
* **Automatic Matching & Scheduling System**:
  * Calculates physical distance between the donor and hospital using the **Haversine formula**.
  * Performs **ABO/Rh Blood Compatibility** validation.
  * Auto-schedules appointments for compatible, nearby donors (default `< 30km` radius) when a request is pending.
* **Real-time Urgent Dispatch**: Automatically triggers the matching engine immediately when a **high** or **critical** urgency blood request is created.
* **Periodic Engine Runs**: Utilizes a background scheduler (`APScheduler`) to periodically scan for and schedule pending requests.

---

## 🛠️ Tech Stack

* **Language**: Python 3.14+
* **Framework**: FastAPI (Modern async ASGI framework)
* **ORM / Database**: SQLModel (SQLAlchemy + Pydantic)
* **Scheduler**: APScheduler
* **Testing**: Pytest & HTTPX

---

## 📂 Project Structure

```text
amal/
├── app/
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── admin.py       # Web Admin Dashboard endpoints
│   │   ├── auth.py        # Authentication & Registration
│   │   ├── donors.py      # Donor profiles & schedule booking
│   │   └── requests.py    # Blood requests & match status
│   ├── __init__.py
│   ├── auth.py            # Password hashing, JWT logic & dependencies
│   ├── config.py          # Settings & system environment variables
│   ├── database.py        # SQLite engine & database sessions
│   ├── models.py          # SQLModel definitions & API validation schemas
│   ├── scheduler.py       # Auto-matching engine & background jobs
│   └── main.py            # FastAPI initialization & Lifespan setup
├── tests/
│   └── test_matching.py   # Unit & integration tests for scheduling rules
├── requirements.txt       # Project dependencies
└── README.md              # Documentation
```

---

## ⚙️ Setup & Local Running

1. **Clone/Navigate to the project directory**:
   ```bash
   cd /Users/digitalcenter/Amal
   ```

2. **Activate the Virtual Environment**:
   ```bash
   source .venv/bin/activate
   ```

3. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the Server**:
   ```bash
   PYTHONPATH=. uvicorn app.main:app --reload --port 8000
   ```
   *The database `amal.db` (SQLite) is initialized automatically on startup.*

5. **API Documentation**:
   * Interactive OpenAPI Docs (Swagger): [http://localhost:8000/docs](http://localhost:8000/docs)
   * Redoc Alternative Docs: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧬 Compatibility Rules

The matching algorithm maps recipient types to compatible donor types based on standard medical compatibility rules:

| Recipient Type | Compatible Donor Blood Types |
|:--------------|:---------------------------|
| **A+**        | A+, A-, O+, O-             |
| **A-**        | A-, O-                     |
| **B+**        | B+, B-, O+, O-             |
| **B-**        | B-, O-                     |
| **AB+**       | *Universal Recipient* (All types compatible) |
| **AB-**       | AB-, A-, B-, O-            |
| **O+**        | O+, O-                     |
| **O-**        | *Universal Donor* (O- only)|

---

## 📡 API Reference Guide

### 1. Authentication (`/api/auth`)

#### Register User / Donor
* **Endpoint**: `POST /api/auth/register`
* **Description**: Registers a new user. If `is_donor` is `true`, a donor profile is created. If the email registered is `admin@amal.org`, the user is granted the `admin` role automatically.
* **Request Body**:
  ```json
  {
    "email": "donor.john@example.com",
    "password": "strongpassword123",
    "full_name": "John Doe",
    "phone_number": "+21699888777",
    "is_donor": true,
    "blood_type": "O-",
    "latitude": 36.8065,
    "longitude": 10.1815
  }
  ```

#### Login User
* **Endpoint**: `POST /api/auth/login`
* **Description**: Authenticate and retrieve a JWT Access Token.
* **Request Format**: Form Data (`username` and `password`).
* **Response**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer"
  }
  ```

---

### 2. Donor Endpoints (`/api/donations`)
*Requires authorization bearer token of a registered donor.*

#### Get Donor Profile
* **Endpoint**: `GET /api/donations/profile`
* **Response**:
  ```json
  {
    "id": "donor-uuid-...",
    "user_id": "user-uuid-...",
    "blood_type": "O-",
    "latitude": 36.8065,
    "longitude": 10.1815,
    "is_available": true,
    "last_donation_date": null
  }
  ```

#### Toggle Availability
* **Endpoint**: `PATCH /api/donations/profile/availability?is_available=false`
* **Description**: Temporarily opts-out of the scheduling engine.

#### Schedule a Donation Appointment
* **Endpoint**: `POST /api/donations/schedule`
* **Description**: Registers a donation slot. Can be linked to an active `request_id` or scheduled as a voluntary walk-in donation.
* **Request Body**:
  ```json
  {
    "request_id": "request-uuid-...",
    "scheduled_time": "2026-06-05T10:00:00"
  }
  ```

---

### 3. Blood Request Endpoints (`/api/requests`)
*Requires authorization bearer token of any user.*

#### Create Blood Request
* **Endpoint**: `POST /api/requests/create`
* **Description**: Submits a request for blood. If the urgency level is `high` or `critical`, the matching engine runs immediately in a background task to reserve nearby compatible donors.
* **Request Body**:
  ```json
  {
    "recipient_name": "Sarah Connor",
    "blood_type": "A+",
    "required_units": 2,
    "hospital_name": "Pasteur Clinic",
    "hospital_latitude": 36.8354,
    "hospital_longitude": 10.2312,
    "urgency_level": "critical",
    "needed_by": "2026-06-03T18:00:00"
  }
  ```

#### Get Eligible/Nearby Donor Statistics
* **Endpoint**: `GET /api/requests/{request_id}/eligible-donors-count`
* **Description**: Provides statistics on how many eligible and compatible donors exist in the system overall and how many fall within the `< 30km` search radius of the hospital.

---

### 4. Admin Dashboard Endpoints (`/api/admin`)
*Requires authorization bearer token of an Admin (`role: admin`).*

#### Dashboard Overview
* **Endpoint**: `GET /api/admin/dashboard`
* **Description**: Provides overall platform KPI counters for active users, available donors, and blood request statuses.

#### Update Appointment Status
* **Endpoint**: `PATCH /api/admin/appointments/{appointment_id}?status_update=completed&units_donated=1`
* **Description**: Updates appointment status (`completed`, `cancelled`, `no_show`). If marked `completed`, the system:
  1. Updates the donor's `last_donation_date` to today (restarting the 56-day lock).
  2. Sets donor `is_available` to `true`.
  3. Updates the associated request's status based on units gathered.

#### Force Match Scheduler
* **Endpoint**: `POST /api/admin/schedule/auto`
* **Description**: Manually triggers the automatic matching algorithm across all active blood requests.

---

## 🧪 Running Automated Tests

Tests verify the eligibility engine, compatibility calculations, distance estimations, and the transaction matches:
```bash
PYTHONPATH=. .venv/bin/pytest tests/
```
