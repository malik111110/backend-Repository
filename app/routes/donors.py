from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional

from app.database import get_session
from app.auth import get_current_user
from app.models import User, DonorProfile, DonationSchedule, DonationScheduleCreate, BloodRequest, Invitation, InvitationResponse, PreScreenQuestionnaire
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/api/donations", tags=["Donations & Donors"])

def get_current_donor_profile(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
) -> DonorProfile:
    statement = select(DonorProfile).where(DonorProfile.user_id == current_user.id)
    donor_profile = session.exec(statement).first()
    if not donor_profile:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current user does not have an active donor profile. Please register as a donor."
        )
    return donor_profile

@router.get("/profile")
def get_donor_profile(donor: DonorProfile = Depends(get_current_donor_profile)):
    return {
        "success": True,
        "data": donor,
        "message": "Donor profile loaded successfully"
    }

@router.patch("/profile/availability")
def update_availability(
    is_available: bool, 
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    donor.is_available = is_available
    session.add(donor)
    session.commit()
    session.refresh(donor)
    return {
        "success": True,
        "data": donor,
        "message": "Availability status updated successfully"
    }

@router.get("/my-appointments")
def get_my_appointments(
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    statement = select(DonationSchedule).where(DonationSchedule.donor_id == donor.id)
    appointments = session.exec(statement).all()
    enriched = []
    for app in appointments:
        hospital_name = "Amal Donor Center"
        hospital_address = "Didouche Mourad St, Algiers"
        if app.request_id:
            req = session.get(BloodRequest, app.request_id)
            if req:
                hospital_name = req.hospital_name
                hospital_address = req.hospital_name
        enriched.append({
            "id": app.id,
            "hospitalName": hospital_name,
            "hospitalAddress": hospital_address,
            "date": app.scheduled_time.date().isoformat() if app.scheduled_time else None,
            "timeSlot": app.scheduled_time.strftime("%I:%M %p") if app.scheduled_time else None,
            "status": app.status.upper(),
            "unitsDonated": app.units_donated
        })
    return {
        "success": True,
        "data": enriched,
        "message": "My appointments loaded successfully"
    }

@router.post("/schedule", status_code=status.HTTP_201_CREATED)
def schedule_appointment(
    schedule_data: DonationScheduleCreate,
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    # Verify donor eligibility
    from app.scheduler import is_donor_eligible
    if not is_donor_eligible(donor):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You are currently not eligible to schedule a donation. Ensure 56 days have passed since your last donation and your availability is set to True."
        )
        
    # Check if they have an active pending schedule
    pending_statement = select(DonationSchedule).where(
        DonationSchedule.donor_id == donor.id,
        DonationSchedule.status == "scheduled"
    )
    existing_pending = session.exec(pending_statement).first()
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You already have an upcoming scheduled appointment."
        )
        
    # Check request validity if scheduled for a specific request
    if schedule_data.request_id:
        req = session.get(BloodRequest, schedule_data.request_id)
        if not req:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target blood request not found"
            )
        if req.status in ["fulfilled", "cancelled"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"This request is already {req.status}"
            )
            
    # Create appointment
    new_schedule = DonationSchedule(
        donor_id=donor.id,
        request_id=schedule_data.request_id,
        scheduled_time=schedule_data.scheduled_time,
        status="scheduled"
    )
    session.add(new_schedule)
    
    # Mark donor as temporarily unavailable to prevent double bookings
    donor.is_available = False
    session.add(donor)
    
    # If accepted a request, update request status to partially_fulfilled
    if schedule_data.request_id:
        req = session.get(BloodRequest, schedule_data.request_id)
        if req.status == "pending":
            req.status = "partially_fulfilled"
            session.add(req)
            
    session.commit()
    session.refresh(new_schedule)
    return {
        "success": True,
        "data": new_schedule,
        "message": "Appointment scheduled successfully"
    }

@router.get("/invitations")
def get_my_invitations(
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    """Retrieves all active or queued matching invitations for the donor."""
    statement = select(Invitation).where(
        Invitation.donor_id == donor.id,
        Invitation.status.in_(["pending", "queued"])
    )
    invitations = session.exec(statement).all()
    enriched = []
    for inv in invitations:
        req = session.get(BloodRequest, inv.request_id)
        if req:
            # Get count of schedules for this request to set unitsCollected
            schedules_count = session.query(DonationSchedule).filter(
                DonationSchedule.request_id == req.id,
                DonationSchedule.status.in_(["scheduled", "completed"])
            ).count()
            
            enriched.append({
                "id": inv.id,
                "requestId": inv.request_id,
                "expiresAt": inv.expires_at.isoformat(),
                "status": inv.status.upper(),
                "request": {
                    "id": req.id,
                    "hospitalName": req.hospital_name,
                    "hospitalAddress": req.hospital_name,
                    "latitude": req.hospital_latitude,
                    "longitude": req.hospital_longitude,
                    "bloodType": req.blood_type,
                    "urgency": req.urgency_level.upper(),
                    "patientCondition": "Emergency Blood Request Compatibility Match",
                    "unitsRequired": req.required_units,
                    "unitsCollected": schedules_count,
                    "createdAt": req.created_at.isoformat(),
                    "distanceKm": 1.2
                }
            })
    return {
        "success": True,
        "data": enriched,
        "message": "My invitations loaded successfully"
    }

@router.post("/invitations/{invitation_id}/respond")
def respond_to_invitation(
    invitation_id: str,
    response: InvitationResponse,
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    """
    Handles donor response to urgent invitations. 
    Acceptance creates a schedule; decline triggers immediate cascade routing.
    """
    invitation = session.get(Invitation, invitation_id)
    if not invitation or invitation.donor_id != donor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )
        
    if invitation.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot respond to invitation. Status is '{invitation.status}'"
        )
        
    req = session.get(BloodRequest, invitation.request_id)
    if not req or req.status in ["fulfilled", "cancelled"]:
        invitation.status = "cancelled"
        session.add(invitation)
        session.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The associated blood request has already been completed or cancelled."
        )

    if response.accepted:
        # 1. Update invitation status
        invitation.status = "accepted"
        session.add(invitation)
        
        # 2. Cancel all other queued/pending invitations for this request
        other_invitations = session.exec(
            select(Invitation).where(
                Invitation.request_id == req.id,
                Invitation.id != invitation.id,
                Invitation.status.in_(["pending", "queued"])
            )
        ).all()
        for other_inv in other_invitations:
            other_inv.status = "cancelled"
            session.add(other_inv)
            
        # 3. Create Donation Schedule (default scheduled_time: 2 hours from now)
        scheduled_time = datetime.now() + timedelta(hours=2)
        schedule = DonationSchedule(
            donor_id=donor.id,
            request_id=req.id,
            scheduled_time=scheduled_time,
            status="scheduled"
        )
        session.add(schedule)
        
        # 4. Mark donor as temporarily unavailable to prevent double scheduling
        donor.is_available = False
        session.add(donor)
        
        # 5. Update request status
        schedules_statement = select(DonationSchedule).where(
            DonationSchedule.request_id == req.id,
            DonationSchedule.status.in_(["scheduled", "completed"])
        )
        existing_schedules = session.exec(schedules_statement).all()
        total_scheduled = len(existing_schedules) + 1  # count the new one
        
        if total_scheduled >= req.required_units:
            req.status = "fulfilled"
        else:
            req.status = "partially_fulfilled"
        session.add(req)
        
        session.commit()
        session.refresh(schedule)
        return {
            "success": True,
            "data": {
                "message": "Invitation accepted successfully. Appointment scheduled.",
                "schedule": {
                    "id": schedule.id,
                    "donor_id": schedule.donor_id,
                    "request_id": schedule.request_id,
                    "scheduled_time": schedule.scheduled_time.isoformat(),
                    "status": schedule.status,
                    "created_at": schedule.created_at.isoformat()
                }
            },
            "message": "Invitation accepted successfully"
        }
    else:
        # Donor declined the request
        invitation.status = "declined"
        session.add(invitation)
        
        # Immediate Cascade to next candidate
        from app.scheduler import send_push_notification
        next_inv = session.exec(
            select(Invitation).where(
                Invitation.request_id == req.id,
                Invitation.priority_order == invitation.priority_order + 1,
                Invitation.status == "queued"
            )
        ).first()
        
        if next_inv:
            next_inv.status = "pending"
            next_inv.expires_at = datetime.now() + timedelta(seconds=180)
            session.add(next_inv)
            
            # Retrieve next donor info
            next_donor = session.get(DonorProfile, next_inv.donor_id)
            if next_donor:
                send_push_notification(
                    donor_id=next_donor.id,
                    title="🚨 URGENT BLOOD DONATION NEEDED (NEXT IN LINE)",
                    body=f"Critical request compatibility matches your type ({next_donor.blood_type}) at {req.hospital_name}.",
                    data={"request_id": req.id, "invitation_id": next_inv.id}
                )
        
        session.commit()
        return {
            "success": True,
            "data": None,
            "message": "Invitation declined. Cascaded matching to the next candidate."
        }

@router.post("/profile/pre-screen")
def submit_pre_screen_questionnaire(
    questionnaire: PreScreenQuestionnaire,
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    """
    Submits a medical pre-screening questionnaire.
    Generates a clearance token if passed, or blocks availability if failed.
    """
    import uuid
    # Check if any risk factor is True
    has_risk = (
        questionnaire.has_recent_tattoo_or_piercing or
        questionnaire.has_infectious_diseases or
        questionnaire.is_taking_antibiotics or
        questionnaire.has_traveled_malaria_zone_recently or
        questionnaire.is_feeling_unwell
    )
    
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    donor.health_checked_at = now
    
    if has_risk:
        donor.health_clearance_token = None
        donor.is_available = False
        session.add(donor)
        session.commit()
        session.refresh(donor)
        return {
            "success": True,
            "data": {
                "cleared": False,
                "health_checked_at": now.isoformat()
            },
            "message": "Pre-screening failed. Critical risk factor flagged. Eligibility is temporarily blocked and donor availability set to unavailable."
        }
    else:
        token = f"clearance_{uuid.uuid4()}"
        donor.health_clearance_token = token
        donor.is_available = True
        session.add(donor)
        session.commit()
        session.refresh(donor)
        return {
            "success": True,
            "data": {
                "cleared": True,
                "health_clearance_token": token,
                "health_checked_at": now.isoformat()
            },
            "message": "Pre-screening passed successfully. Health clearance token generated."
        }

@router.patch("/appointments/{appointment_id}/cancel")
def cancel_appointment(
    appointment_id: str,
    donor: DonorProfile = Depends(get_current_donor_profile),
    session: Session = Depends(get_session)
):
    appointment = session.get(DonationSchedule, appointment_id)
    if not appointment or appointment.donor_id != donor.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
    
    appointment.status = "cancelled"
    donor.is_available = True
    session.add(appointment)
    session.add(donor)
    session.commit()
    return {
        "success": True,
        "message": "Appointment cancelled successfully"
    }
