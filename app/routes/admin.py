from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional
from datetime import date, datetime

from app.database import get_session
from app.auth import get_current_admin
from app.models import User, DonorProfile, BloodRequest, DonationSchedule, DonationScheduleRead, DonorProfileRead, BloodRequestRead
from app.scheduler import run_auto_scheduling

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"], dependencies=[Depends(get_current_admin)])

@router.get("/dashboard")
def get_dashboard_stats(session: Session = Depends(get_session)):
    # 1. Total users and role counts
    total_users = session.query(User).count()
    admins_count = session.query(User).filter(User.role == "admin").count()
    
    # 2. Donors count and availability
    total_donors = session.query(DonorProfile).count()
    available_donors = session.query(DonorProfile).filter(DonorProfile.is_available == True).count()
    
    # 3. Request stats
    total_requests = session.query(BloodRequest).count()
    pending_requests = session.query(BloodRequest).filter(BloodRequest.status == "pending").count()
    partially_fulfilled_requests = session.query(BloodRequest).filter(BloodRequest.status == "partially_fulfilled").count()
    fulfilled_requests = session.query(BloodRequest).filter(BloodRequest.status == "fulfilled").count()
    
    # 4. Schedule/Appointment stats
    total_schedules = session.query(DonationSchedule).count()
    upcoming_schedules = session.query(DonationSchedule).filter(DonationSchedule.status == "scheduled").count()
    completed_donations = session.query(DonationSchedule).filter(DonationSchedule.status == "completed").count()
    
    return {
        "users": {
            "total": total_users,
            "admins": admins_count,
            "donors": total_donors,
            "available_donors": available_donors
        },
        "requests": {
            "total": total_requests,
            "pending": pending_requests,
            "partially_fulfilled": partially_fulfilled_requests,
            "fulfilled": fulfilled_requests
        },
        "schedules": {
            "total": total_schedules,
            "upcoming": upcoming_schedules,
            "completed": completed_donations
        }
    }

@router.get("/requests", response_model=List[BloodRequestRead])
def list_all_requests(
    status_filter: Optional[str] = None,
    session: Session = Depends(get_session)
):
    if status_filter:
        statement = select(BloodRequest).where(BloodRequest.status == status_filter)
    else:
        statement = select(BloodRequest)
    return session.exec(statement).all()

@router.get("/donors", response_model=List[DonorProfileRead])
def list_all_donors(session: Session = Depends(get_session)):
    statement = select(DonorProfile)
    return session.exec(statement).all()

@router.post("/schedule/auto")
def trigger_auto_scheduling():
    """Manually trigger the matching and scheduling engine."""
    run_auto_scheduling()
    return {"message": "Automatic matching and scheduling engine executed successfully."}

@router.patch("/appointments/{appointment_id}", response_model=DonationScheduleRead)
def update_appointment_status(
    appointment_id: str,
    status_update: str,  # "completed", "cancelled", "no_show"
    units_donated: Optional[int] = None,
    session: Session = Depends(get_session)
):
    valid_statuses = {"completed", "cancelled", "no_show"}
    if status_update not in valid_statuses:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Status must be one of {valid_statuses}"
        )
        
    appointment = session.get(DonationSchedule, appointment_id)
    if not appointment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Appointment not found"
        )
        
    donor = session.get(DonorProfile, appointment.donor_id)
    
    old_status = appointment.status
    appointment.status = status_update
    
    if status_update == "completed":
        appointment.units_donated = units_donated or 1
        if donor:
            # Update last donation date to today
            donor.last_donation_date = date.today()
            # Set availability to True so they are available for future scheduling (once eligible again)
            donor.is_available = True
            session.add(donor)
            
    elif status_update in ["cancelled", "no_show"]:
        # If it was active ("scheduled"), free up the donor immediately
        if old_status == "scheduled" and donor:
            donor.is_available = True
            session.add(donor)
            
        # Re-evaluate associated request if there was one
        if appointment.request_id:
            req = session.get(BloodRequest, appointment.request_id)
            if req and req.status == "fulfilled":
                req.status = "partially_fulfilled"
                session.add(req)
                
    session.add(appointment)
    session.commit()
    session.refresh(appointment)
    return appointment
