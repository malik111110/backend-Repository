# Frontend API Contracts & Security Specifications

This guide outlines the API contracts and communication schemas for the frontend teams (Mobile & Web Admin applications). 

> [!IMPORTANT]
> **Core Architectural Principle: "Never trust the client; the server is the only source of truth."**  
> All inputs, authorization states, checkups, and scheduling logic are validated strictly on the server. The client application is responsible *only* for rendering user interfaces and capturing raw input variables.

---

## 🔒 1. Authentication & Security Policies

### Authorization Header
All protected endpoints require the HTTP `Authorization` header populated with a JWT bearer token:
```http
Authorization: Bearer <jwt_access_token>
```

### Role Enforcement (Server-Side)
The server inspects the JWT payload claims for the `role` field. Even if a user modifies their local mobile storage to show an "Admin Panel", the backend strictly blocks any non-admin request with a `403 Forbidden` response.

---

## 📡 2. Core API Endpoint Contracts

### 🔑 Authentication (`/api/auth`)

#### User & Donor Registration
* **Endpoint**: `POST /api/auth/register`
* **Content-Type**: `application/json`
* **JSON Payload Schema**:
  ```json
  {
    "email": "string (required, unique, format: email)",
    "password": "string (required, minlength: 8)",
    "full_name": "string (required)",
    "phone_number": "string (required)",
    "is_donor": "boolean (required)",
    "blood_type": "string (optional, required if is_donor is true. Enum: A+, A-, B+, B-, AB+, AB-, O+, O-)",
    "latitude": "float (optional, required if is_donor is true. Range: -90.0 to 90.0)",
    "longitude": "float (optional, required if is_donor is true. Range: -180.0 to 180.0)"
  }
  ```
* **Server-Side Truth Enforcements**:
  * Prevents double registration of identical emails.
  * Rejects registration if `is_donor` is `true` but location coordinates or blood types are missing or formatted incorrectly.

#### User & Donor Login
* **Endpoint**: `POST /api/auth/login`
* **Content-Type**: `application/x-www-form-urlencoded`
* **Form-Data Payload Schema**:
  ```ini
  username=email_string
  password=password_string
  ```
* **Response Payload (200 OK)**:
  ```json
  {
    "access_token": "eyJhbGciOi...",
    "token_type": "bearer"
  }
  ```

---

### 🩸 Donor Operations (`/api/donations`)
*Requires Donor Authorization Bearer Token.*

#### Submit Pre-Screening Questionnaire
* **Endpoint**: `POST /api/donations/profile/pre-screen`
* **Content-Type**: `application/json`
* **JSON Payload Schema**:
  ```json
  {
    "has_recent_tattoo_or_piercing": "boolean (required)",
    "has_infectious_diseases": "boolean (required)",
    "is_taking_antibiotics": "boolean (required)",
    "has_traveled_malaria_zone_recently": "boolean (required)",
    "is_feeling_unwell": "boolean (required)"
  }
  ```
* **Server-Side Truth Enforcements**:
  * **Zero Trust of User Status**: The client cannot directly request to toggle the donor's `is_available` flag or self-certify health status. 
  * The server parses these 5 parameters. If **any** parameter is `true`, the server automatically revokes existing clearance tokens, forces the donor's `is_available` profile flag to `false`, and locks scheduling privileges.
* **Response Payload (200 OK - PASS)**:
  ```json
  {
    "cleared": true,
    "message": "Pre-screening passed successfully. Health clearance token generated.",
    "health_clearance_token": "clearance_uuid_string",
    "health_checked_at": "YYYY-MM-DDTHH:MM:SS"
  }
  ```

#### Respond to Matching Invitations
* **Endpoint**: `POST /api/donations/invitations/{invitation_id}/respond`
* **Content-Type**: `application/json`
* **JSON Payload Schema**:
  ```json
  {
    "accepted": "boolean (required)"
  }
  ```
* **Server-Side Truth Enforcements**:
  * The server verifies the invitation belongs to the logged-in donor (prevents spoofing other IDs).
  * Enforces state constraints: invitation must be `"pending"` (not expired or already accepted).
  * Automatically handles cascade priority promotions instantly if the user selects `accepted: false`.

---

### 🏥 Blood Requests (`/api/requests`)
*Requires User Authorization Bearer Token.*

#### Create Blood Request
* **Endpoint**: `POST /api/requests/create`
* **Content-Type**: `application/json`
* **JSON Payload Schema**:
  ```json
  {
    "recipient_name": "string (required)",
    "blood_type": "string (required, Enum: A+, A-, B+, B-, AB+, AB-, O+, O-)",
    "required_units": "integer (required, minimum: 1)",
    "hospital_name": "string (required)",
    "hospital_latitude": "float (required)",
    "hospital_longitude": "float (required)",
    "urgency_level": "string (required, Enum: low, medium, high, critical)",
    "needed_by": "string (required, ISO 8601 Datetime format)"
  }
  ```
* **Server-Side Truth Enforcements**:
  * Rejects request creation if `needed_by` date is in the past.
  * Performs server-side urgency validation. If the request urgency is marked `"high"` or `"critical"`, the server triggers the immediate background matching engine to lock compatible candidates.

---

### 💻 Web Admin Control (`/api/admin`)
*Requires Administrator Authorization Bearer Token.*

#### Update Appointment Lifecycle Status
* **Endpoint**: `PATCH /api/admin/appointments/{appointment_id}?status_update=completed&units_donated=1`
* **Server-Side Truth Enforcements**:
  * Only accounts containing `"role": "admin"` in their JWT are permitted.
  * Validates status parameters (`completed`, `cancelled`, `no_show`).
  * If `"completed"`, the server automatically stamps the donor's `last_donation_date` to `date.today()`, which triggers the 56-day cooldown matching lockout on subsequent engine passes.

---

## 🛠️ Error Codes Standard

The API strictly implements standard HTTP status codes:

| HTTP Code | Error Trigger | Frontend Handling Guideline |
| :--- | :--- | :--- |
| **`400 Bad Request`** | Validation failure, invalid coordinates format, blood type typo, or donor is ineligible (e.g. < 56 days interval). | Display custom error message detail returned from the API payload. |
| **`401 Unauthorized`**| Missing authorization header, expired JWT token, or incorrect password. | Clear local token cache and redirect user to the login screen. |
| **`403 Forbidden`**  | A regular user attempts to pull dashboard statistics or alter appointment statuses. | Restrict UI panels and log security alerts. |
| **`404 Not Found`**  | Target invitation ID or request ID does not exist in the database. | Inform user the record was cancelled or relocated. |
| **`500 Internal Error`**| Database or networking crash. | Show generic fallback page. |
