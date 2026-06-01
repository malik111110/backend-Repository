# Amal Platform - User Stories & Requirements

This document outlines the user stories, acceptance criteria, and technical mappings for the **Amal** Blood Donation and Transfer system.

---

## 📱 Mobile Application (Donors & Recipients)

### Role: Donor (User)

#### Story 1: Donor Registration & Blood Type Setup
> **As a** blood donor,  
> **I want to** register an account and specify my blood type and geo-location,  
> **So that** I can be registered in the system as an available donor.
* **Acceptance Criteria**:
  * The registration endpoint validates the required blood type (`A+`, `A-`, `B+`, etc.).
  * Validates coordinates (latitude and longitude) to map the donor's base location.
  * Automatically instantiates a `DonorProfile` upon registration.
* **Technical Route**: `POST /api/auth/register` (with `is_donor: true`).

#### Story 2: Check Donation Eligibility
> **As a** donor,  
> **I want to** view my eligibility status and see when I can next donate,  
> **So that** I comply with health and safety regulations (minimum 56 days between donations).
* **Acceptance Criteria**:
  * The system calculates the difference in days between today and the donor's `last_donation_date`.
  * If the difference is less than 56 days, the donor is marked ineligible to schedule.
  * If the donor's availability toggle is set to `false`, they are marked ineligible.
* **Technical Route**: `GET /api/donations/profile`.

#### Story 3: Voluntary Appointment Scheduling
> **As a** donor,  
> **I want to** voluntarily schedule a future donation slot at any hospital/blood clinic,  
> **So that** I can plan my donation in advance.
* **Acceptance Criteria**:
  * The donor must be eligible to schedule (passed 56 days interval).
  * The donor cannot schedule if they already have an active `"scheduled"` appointment.
  * Once booked, their availability flag is temporarily set to `false` to prevent double booking.
* **Technical Route**: `POST /api/donations/schedule` (with no `request_id`).

#### Story 4: Retrieve My Upcoming Appointments
> **As a** donor,  
> **I want to** view a list of my upcoming scheduled donations,  
> **So that** I can keep track of my commitments.
* **Acceptance Criteria**:
  * Lists all appointments associated with the donor's profile.
  * Displays the date, time, and status (`scheduled`, `completed`, `cancelled`).
* **Technical Route**: `GET /api/donations/my-appointments`.

---

### Role: Recipient (User)

#### Story 5: Create a Blood Request
> **As a** user in need of blood for a patient,  
> **I want to** create a blood request specifying recipient details, blood type, hospital location, and urgency,  
> **So that** compatible donors can be found.
* **Acceptance Criteria**:
  * Validates blood type and urgency level (`low`, `medium`, `high`, `critical`).
  * If the urgency is `high` or `critical`, the matching engine runs **immediately** in the background to reserve nearby donors.
  * Low/medium urgency requests are queued for batch run (every 15 minutes).
* **Technical Route**: `POST /api/requests/create`.

#### Story 6: Track My Requests
> **As a** requester,  
> **I want to** monitor the fulfillment status of my requests,  
> **So that** I know if donors have been scheduled.
* **Acceptance Criteria**:
  * Returns list of blood requests initiated by the user.
  * Shows status (`pending`, `partially_fulfilled`, `fulfilled`, `cancelled`).
* **Technical Route**: `GET /api/requests/my-requests`.

#### Story 7: Real-time Compatible Donor Count
> **As a** requester,  
> **I want to** see how many compatible and nearby donors exist for my request,  
> **So that** I have an expectation of how quickly the request might be fulfilled.
* **Acceptance Criteria**:
  * Calculates how many active donors are compatible and eligible (within the 30km radius of the target hospital).
  * Returns count instantly to the requester.
* **Technical Route**: `GET /api/requests/{request_id}/eligible-donors-count`.

---

## 💻 Web Admin Dashboard (Administrators)

### Role: Administrator

#### Story 8: Dashboard Health Indicators
> **As an** administrator,  
> **I want to** view overall stats for the platform (total users, active donor count, pending requests, and scheduled appointments),  
> **So that** I can get an immediate overview of the system's supply and demand.
* **Acceptance Criteria**:
  * Displays total counts of users, admins, donors, and available donors.
  * Summarizes request statuses and appointment success rates.
* **Technical Route**: `GET /api/admin/dashboard`.

#### Story 9: Force Automatic Match Runs
> **As an** administrator,  
> **I want to** manually trigger the matching engine on-demand,  
> **So that** I do not have to wait for the periodic 15-minute background job.
* **Acceptance Criteria**:
  * Instantly runs matching for all pending/partially fulfilled requests.
  * Reserves eligible donors and updates request status.
* **Technical Route**: `POST /api/admin/schedule/auto`.

#### Story 10: Manage Appointment Statuses (Donation Lifecycle)
> **As an** administrator at a hospital or blood bank,  
> **I want to** mark a scheduled donation as completed, cancelled, or no-show,  
> **So that** donor records and request counts remain accurate.
* **Acceptance Criteria**:
  * **When Completed**:
    * Records the units of blood donated.
    * Sets donor's `last_donation_date` to today (re-triggering the 56-day cooldown).
    * Re-enables donor availability (`is_available = true`).
  * **When Cancelled / No-show**:
    * Re-enables donor availability (`is_available = true`) immediately so they can be matched again.
    * Reverts associated request status to `partially_fulfilled` or `pending` if the reservation is lost.
* **Technical Route**: `PATCH /api/admin/appointments/{appointment_id}`.

---

## ⚡ Time-Critical Optimization Stories (When Every Minute Counts)

### Role: Donor (User)

#### Story 11: Emergency Push Notification & 1-Tap RSVP
> **As a** registered donor,  
> **I want to** receive an immediate high-priority push notification when an urgent blood request is created near me, and accept/reject it with a single tap,  
> **So that** I don't waste time navigating app menus while someone is in critical danger.
* **Acceptance Criteria**:
  * Broadcasts push notifications immediately to the top 5 closest matched eligible donors.
  * Allows responding with a 1-tap accept or decline from the lock screen.
  * If no response is received in 180 seconds, the invitation expires and cascades to the next closest candidate.
* **Technical Route**: `POST /api/donations/schedule` (under < 180s constraint).

#### Story 12: Mobile Pre-Screening Questionnaire
> **As a** donor,  
> **I want to** complete a medical pre-screening questionnaire on my mobile phone before traveling to the hospital,  
> **So that** I don't make a wasted trip if I am medically ineligible to donate.
* **Acceptance Criteria**:
  * Evaluates health risk answers (medication, travel history, recent surgeries).
  * Automatically sets profile `is_available` to `false` if risk factors are flagged.
  * Generates a temporary clearance token if screening is successful.
* **Technical Route**: `GET /api/donations/profile` & `PATCH /api/donations/profile/availability`.

#### Story 13: Emergency Pass & Navigation Route Guidance
> **As an** approved donor on my way to donate for a critical request,  
> **I want to** view live GPS navigation to the hospital and access a digital Priority Pass,  
> **So that** I can avoid heavy traffic and gain fast-track access to the clinic parking and donation room.
* **Acceptance Criteria**:
  * Generates direct map deep-link parameters centered on hospital latitude/longitude.
  * Renders a digital pass in-app featuring patient request ID and hospital routing details.
* **Technical Route**: `GET /api/donations/my-appointments` (linking GPS markers).

---

### Role: Administrator

#### Story 14: Digital QR Code Fast-Track Check-In
> **As a** hospital blood bank coordinator,  
> **I want to** check in a donor instantly by scanning their mobile QR code,  
> **So that** we bypass administrative triage desks and send them directly to the extraction table.
* **Acceptance Criteria**:
  * Staff scans donor's app QR code containing the `appointment_id`.
  * Instantly fetches donor profile, pre-screening questionnaire pass status, and updates appointment state to "arrived".
* **Technical Route**: `PATCH /api/admin/appointments/{appointment_id}` (check-in event).

