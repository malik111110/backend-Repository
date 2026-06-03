from fastapi import APIRouter, Depends, HTTPException, status
# pyrefly: ignore [missing-import]
from sqlmodel import Session, select
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime

from app.database import get_session
from app.auth import get_current_admin
from app.models import User, DonorProfile, BloodRequest, DonationSchedule, TeamMember, TeamMemberCreate, Hospital
from app.scheduler import run_auto_scheduling

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"], dependencies=[Depends(get_current_admin)])

@router.get("/hospitals")
def list_hospitals(session: Session = Depends(get_session)):
    hospitals = session.exec(select(Hospital)).all()
    return {
        "success": True,
        "data": hospitals,
        "message": "Hospitals loaded successfully"
    }

class HospitalAdminCreate(BaseModel):
    first_name: str
    last_name: str
    email: str
    password: str
    hopital_id: str

@router.post("/create-hospital-admin")
def create_hospital_admin(
    admin_data: HospitalAdminCreate,
    session: Session = Depends(get_session)
):
    from app.auth import get_password_hash
    # Check if user already exists
    statement = select(User).where(User.email == admin_data.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Create hospital admin user
    db_user = User(
        email=admin_data.email,
        full_name=f"{admin_data.first_name} {admin_data.last_name}",
        phone_number="0500000000",
        hashed_password=get_password_hash(admin_data.password),
        role="admin_hopital",
        first_name=admin_data.first_name,
        last_name=admin_data.last_name,
        hopital_id=admin_data.hopital_id
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return {
        "success": True,
        "data": db_user,
        "message": "Hospital admin created successfully"
    }

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
        "success": True,
        "data": {
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
        },
        "message": "Dashboard statistics loaded successfully"
    }

@router.get("/requests")
def list_all_requests(
    status_filter: Optional[str] = None,
    session: Session = Depends(get_session)
):
    if status_filter:
        statement = select(BloodRequest).where(BloodRequest.status == status_filter)
    else:
        statement = select(BloodRequest)
    requests = session.exec(statement).all()
    return {
        "success": True,
        "data": requests,
        "message": "Requests loaded successfully"
    }

@router.get("/donors")
def list_all_donors(session: Session = Depends(get_session)):
    donors = session.exec(select(DonorProfile)).all()
    enriched = []
    for d in donors:
        user = session.get(User, d.user_id)
        enriched.append({
            "id": d.id,
            "user_id": d.user_id,
            "full_name": user.full_name if user else "Unknown",
            "email": user.email if user else "Unknown",
            "phone": user.phone_number if user else "Unknown",
            "blood_type": d.blood_type,
            "latitude": d.latitude,
            "longitude": d.longitude,
            "is_available": d.is_available,
            "last_donation": d.last_donation_date.isoformat() if d.last_donation_date else None,
            "wilaya": "Alger",
            "address": "Bab El Oued, Alger",
            "occupation": "Donneur Amal",
            "age": 28,
            "gender": "M",
            "total_donations": len(d.schedules) if d.schedules else 0,
            "notes": "Profil actif sur la plateforme.",
            "preferred_contact": "Téléphone",
            "weight_kg": 75,
            "last_screening": d.health_checked_at.isoformat() if d.health_checked_at else None,
            "emergency_contact_name": "Proche",
            "emergency_contact_phone": "Non spécifié"
        })
    return {
        "success": True,
        "data": enriched,
        "message": "Donors loaded successfully"
    }

@router.get("/appointments")
def list_all_appointments(session: Session = Depends(get_session)):
    appointments = session.exec(select(DonationSchedule)).all()
    enriched = []
    for app in appointments:
        donor = session.get(DonorProfile, app.donor_id)
        user = session.get(User, donor.user_id) if donor else None
        enriched.append({
            "id": app.id,
            "donor_id": app.donor_id,
            "donor_name": user.full_name if user else "Unknown",
            "blood_type": donor.blood_type if donor else "O-",
            "scheduled_time": app.scheduled_time.isoformat() if app.scheduled_time else None,
            "status": app.status,
            "units_expected": 1,
            "units_donated": app.units_donated,
            "room": "Salle collecte 1",
            "assigned_nurse": "Nurse Samia",
            "notes": "Rendez-vous planifié",
            "request_id": app.request_id
        })
    return {
        "success": True,
        "data": enriched,
        "message": "Appointments loaded successfully"
    }

@router.post("/schedule/auto")
def trigger_auto_scheduling():
    """Manually trigger the matching and scheduling engine."""
    run_auto_scheduling()
    return {
        "success": True,
        "data": None,
        "message": "Automatic matching and scheduling engine executed successfully."
    }

@router.patch("/appointments/{appointment_id}")
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
    return {
        "success": True,
        "data": appointment,
        "message": f"Appointment status successfully updated to {status_update}."
    }

@router.get("/team")
def list_all_team_members(session: Session = Depends(get_session)):
    members = session.exec(select(TeamMember)).all()
    return {
        "success": True,
        "data": members,
        "message": "Team members loaded successfully"
    }

@router.post("/team", status_code=status.HTTP_201_CREATED)
def add_team_member(member_data: TeamMemberCreate, session: Session = Depends(get_session)):
    existing = session.exec(select(TeamMember).where(TeamMember.email == member_data.email)).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A team member with this email is already registered."
        )
    member = TeamMember.model_validate(member_data)
    session.add(member)
    session.commit()
    session.refresh(member)
    return {
        "success": True,
        "data": member,
        "message": "Team member added successfully"
    }

class AdminAppointmentCreate(BaseModel):
    donor_id: str
    scheduled_time: datetime

@router.post("/appointments", status_code=status.HTTP_201_CREATED)
def create_appointment_as_admin(
    appointment_data: AdminAppointmentCreate,
    session: Session = Depends(get_session)
):
    donor = session.get(DonorProfile, appointment_data.donor_id)
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
        
    new_schedule = DonationSchedule(
        donor_id=donor.id,
        scheduled_time=appointment_data.scheduled_time,
        status="scheduled"
    )
    session.add(new_schedule)
    
    donor.is_available = False
    session.add(donor)
    
    session.commit()
    session.refresh(new_schedule)
    
    return {
        "success": True,
        "data": new_schedule,
        "message": "Rendez-vous créé avec succès."
    }
