from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select
from typing import List, Optional, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, EmailStr
import uuid

from app.database import get_session
from app.auth import get_current_admin
from app.models import User, DonorProfile, BloodRequest, DonationSchedule, DonationScheduleRead, DonorProfileRead, BloodRequestRead, Hospital
from app.scheduler import run_auto_scheduling

class HospitalAdminCreate(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr
    password: str
    hopital_id: str

class DatabaseQuery(BaseModel):
    table: str
    action: str = "select"  # "select", "update", "upsert"
    select_fields: Optional[Any] = None
    filters: Optional[Dict[str, Any]] = None
    order_by: Optional[str] = None
    order_asc: Optional[bool] = True
    values: Optional[Dict[str, Any]] = None
    count_only: Optional[bool] = False
    maybe_single: Optional[bool] = False

router = APIRouter(prefix="/api/admin", tags=["Admin Dashboard"], dependencies=[Depends(get_current_admin)])

@router.get("/dashboard")
def get_dashboard_stats(session: Session = Depends(get_session)):
    # 1. Total users and role counts
    total_users = session.query(User).count()
    admins_count = session.query(User).filter(User.role == "admin_hopital").count()
    
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
    
    # 5. Hospital count
    total_hospitals = session.query(Hospital).count()
    
    # Patients count (users who are not admins or donors)
    patients_count = session.query(User).filter(User.role.in_(["user", "patient"])).count()
    
    return {
        "users": {
            "total": total_users,
            "admins": admins_count,
            "donors": total_donors,
            "available_donors": available_donors,
            "patients": patients_count
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
        },
        "hospitals": {
            "total": total_hospitals
        }
    }

@router.get("/requests")
def list_all_requests(
    status_filter: Optional[str] = None,
    current_admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    statement = select(BloodRequest)
    if current_admin.role == "admin_hopital" and current_admin.hopital_id:
        statement = statement.where(BloodRequest.hopital_id == current_admin.hopital_id)
        
    if status_filter:
        db_status = status_filter
        if db_status == "active":
            db_status = "pending"
        statement = statement.where(BloodRequest.status == db_status)
        
    results = session.exec(statement).all()
    
    output = []
    for req in results:
        req_dict = req.model_dump()
        user = session.get(User, req.created_by_id)
        req_dict["patient_name"] = user.full_name if user else "Patient"
        req_dict["patient_id"] = req.created_by_id
        
        # Frontend expects active instead of pending status name
        if req_dict["status"] == "pending":
            req_dict["status"] = "active"
            
        req_dict["severity"] = req.urgency_level
        req_dict["units_needed"] = req.required_units
        
        # Calculate donors_confirmed
        req_dict["donors_confirmed"] = session.query(DonationSchedule).filter(
            DonationSchedule.request_id == req.id,
            DonationSchedule.status.in_(["scheduled", "completed"])
        ).count()
        output.append(req_dict)
        
    return output

@router.patch("/requests/{request_id}/status")
def update_request_status_api(
    request_id: str,
    status_update: str,
    current_admin: User = Depends(get_current_admin),
    session: Session = Depends(get_session)
):
    valid_statuses = {"pending", "partially_fulfilled", "fulfilled", "cancelled", "active"}
    if status_update not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
        
    req = session.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    if current_admin.role == "admin_hopital" and req.hopital_id != current_admin.hopital_id:
        raise HTTPException(status_code=403, detail="Not authorized to edit this request")
        
    db_status = status_update
    if db_status == "active":
        db_status = "pending"
        
    req.status = db_status
    session.add(req)
    session.commit()
    session.refresh(req)
    return req

@router.get("/hospitals")
def list_all_hospitals(
    session: Session = Depends(get_session)
):
    statement = select(Hospital).order_by(Hospital.name)
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

@router.post("/create-hospital-admin", status_code=status.HTTP_201_CREATED)
def create_hospital_admin(
    admin_data: HospitalAdminCreate,
    session: Session = Depends(get_session)
):
    # Check if user already exists
    statement = select(User).where(User.email == admin_data.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Check if hospital exists
    hospital = session.get(Hospital, admin_data.hopital_id)
    if not hospital:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hospital not found"
        )
    
    from app.auth import get_password_hash
    db_user = User(
        email=admin_data.email,
        full_name=f"{admin_data.first_name} {admin_data.last_name}",
        first_name=admin_data.first_name,
        last_name=admin_data.last_name,
        phone_number="",
        hashed_password=get_password_hash(admin_data.password),
        role="admin_hopital",
        region=hospital.region,
        hopital_id=admin_data.hopital_id
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return {
        "id": db_user.id,
        "email": db_user.email,
        "role": db_user.role,
        "hopital_id": db_user.hopital_id
    }

@router.post("/db/query")
def db_query(query: DatabaseQuery, session: Session = Depends(get_session)):
    allowed_tables = {
        "hopitals": Hospital,
        "profiles": User,
        "blood_requests": BloodRequest,
        "donation_appointments": DonationSchedule,
        "donor_alerts": Invitation
    }
    if query.table not in allowed_tables:
        raise HTTPException(status_code=400, detail="Invalid table name")
    
    model = allowed_tables[query.table]
    
    if query.action == "select":
        stmt = select(model)
        
        # Apply filters
        if query.filters:
            for field, filter_val in query.filters.items():
                # Map field aliases
                db_field = field
                if db_field == "phone" and model == User:
                    db_field = "phone_number"
                elif db_field == "severity" and model == BloodRequest:
                    db_field = "urgency_level"
                elif db_field == "units_needed" and model == BloodRequest:
                    db_field = "required_units"
                elif db_field == "patient_id" and model == BloodRequest:
                    db_field = "created_by_id"
                
                # Check attribute exists
                if not hasattr(model, db_field):
                    continue
                
                # Handle operators
                if isinstance(filter_val, dict) and "op" in filter_val:
                    op = filter_val["op"]
                    val = filter_val["value"]
                    if op == "in":
                        stmt = stmt.where(getattr(model, db_field).in_(val))
                else:
                    stmt = stmt.where(getattr(model, db_field) == filter_val)
                    
        # Apply sorting
        if query.order_by:
            db_order_by = query.order_by
            if db_order_by == "severity" and model == BloodRequest:
                db_order_by = "urgency_level"
            elif db_order_by == "units_needed" and model == BloodRequest:
                db_order_by = "required_units"
            elif db_order_by == "patient_id" and model == BloodRequest:
                db_order_by = "created_by_id"
                
            field_attr = getattr(model, db_order_by, None)
            if field_attr is not None:
                if query.order_asc:
                    stmt = stmt.order_by(field_attr)
                else:
                    stmt = stmt.order_by(field_attr.desc())
                    
        results = session.exec(stmt).all()
        
        output_data = []
        for row in results:
            row_dict = row.model_dump()
            
            # Special logic for profiles (join with DonorProfile details)
            if query.table == "profiles":
                if row.donor_profile:
                    dp_dict = row.donor_profile.model_dump()
                    for k, v in dp_dict.items():
                        if k not in row_dict or row_dict[k] is None:
                            row_dict[k] = v
                row_dict["phone"] = row_dict.get("phone_number")
                if not row_dict.get("first_name"):
                    names = row_dict.get("full_name", "").split(" ")
                    row_dict["first_name"] = names[0] if names else ""
                    row_dict["last_name"] = " ".join(names[1:]) if len(names) > 1 else ""
            
            # Special logic for blood_requests
            if query.table == "blood_requests":
                row_dict["severity"] = row_dict.get("urgency_level")
                row_dict["units_needed"] = row_dict.get("required_units")
                row_dict["patient_id"] = row_dict.get("created_by_id")
                # Count confirmed schedules as donors_confirmed
                row_dict["donors_confirmed"] = session.query(DonationSchedule).filter(
                    DonationSchedule.request_id == row.id,
                    DonationSchedule.status.in_(["scheduled", "completed"])
                ).count()
                
            output_data.append(row_dict)
            
        if query.count_only:
            return {"count": len(output_data)}
            
        if query.maybe_single:
            return {"data": output_data[0] if output_data else None}
            
        return {"data": output_data}
        
    elif query.action == "update":
        if not query.values:
            raise HTTPException(status_code=400, detail="Values dictionary is required for update")
        
        stmt = select(model)
        if query.filters:
            for field, filter_val in query.filters.items():
                db_field = field
                if db_field == "phone" and model == User:
                    db_field = "phone_number"
                elif db_field == "severity" and model == BloodRequest:
                    db_field = "urgency_level"
                elif db_field == "units_needed" and model == BloodRequest:
                    db_field = "required_units"
                elif db_field == "patient_id" and model == BloodRequest:
                    db_field = "created_by_id"
                    
                if not hasattr(model, db_field):
                    continue
                    
                if isinstance(filter_val, dict) and "op" in filter_val:
                    op = filter_val["op"]
                    val = filter_val["value"]
                    if op == "in":
                        stmt = stmt.where(getattr(model, db_field).in_(val))
                else:
                    stmt = stmt.where(getattr(model, db_field) == filter_val)
                    
        records = session.exec(stmt).all()
        
        translated_values = {}
        for k, v in query.values.items():
            db_k = k
            if db_k == "severity" and model == BloodRequest:
                db_k = "urgency_level"
            elif db_k == "units_needed" and model == BloodRequest:
                db_k = "required_units"
            elif db_k == "patient_id" and model == BloodRequest:
                db_k = "created_by_id"
            elif db_k == "phone" and model == User:
                db_k = "phone_number"
            translated_values[db_k] = v
            
        for record in records:
            for k, v in translated_values.items():
                setattr(record, k, v)
            session.add(record)
            
        session.commit()
        return {"count": len(records)}
        
    elif query.action == "upsert":
        if not query.values:
            raise HTTPException(status_code=400, detail="Values dictionary is required for upsert")
        
        pk_field = "id"
        pk_val = query.values.get(pk_field)
        if not pk_val:
            if query.filters and "id" in query.filters:
                pk_val = query.filters["id"]
                
        record = None
        if pk_val:
            record = session.get(model, pk_val)
            
        translated_values = {}
        for k, v in query.values.items():
            db_k = k
            if db_k == "severity" and model == BloodRequest:
                db_k = "urgency_level"
            elif db_k == "units_needed" and model == BloodRequest:
                db_k = "required_units"
            elif db_k == "patient_id" and model == BloodRequest:
                db_k = "created_by_id"
            elif db_k == "phone" and model == User:
                db_k = "phone_number"
            translated_values[db_k] = v
            
        if record:
            for k, v in translated_values.items():
                setattr(record, k, v)
            session.add(record)
        else:
            if model == User:
                if "email" not in translated_values:
                    translated_values["email"] = f"user_{pk_val or uuid.uuid4()}@bloodmatch.dz"
                if "full_name" not in translated_values:
                    translated_values["full_name"] = f"{translated_values.get('first_name', '')} {translated_values.get('last_name', '')}".strip() or "Unnamed User"
                if "hashed_password" not in translated_values:
                    from app.auth import get_password_hash
                    translated_values["hashed_password"] = get_password_hash("dummy_password_123")
                if "phone_number" not in translated_values:
                    translated_values["phone_number"] = translated_values.get("phone", "")
                    
            record = model(**translated_values)
            if pk_val:
                record.id = pk_val
            session.add(record)
            
        session.commit()
        return {"success": True}

@router.post("/requests/{request_id}/broadcast")
def broadcast_request(request_id: str, session: Session = Depends(get_session)):
    req = session.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
        
    from app.scheduler import match_and_invite_for_request
    invitations_created = match_and_invite_for_request(session, req)
    return {"data": invitations_created}

@router.post("/force-match")
def force_match_route(session: Session = Depends(get_session)):
    statement = select(BloodRequest).where(BloodRequest.status.in_(["pending", "partially_fulfilled"]))
    active_requests = session.exec(statement).all()
    
    from app.scheduler import match_and_schedule_for_request, match_and_invite_for_request
    total_scheduled = 0
    for req in active_requests:
        if req.urgency_level in ["high", "critical"]:
            match_and_invite_for_request(session, req)
        else:
            created = match_and_schedule_for_request(session, req)
            total_scheduled += len(created)
            
    return {"data": total_scheduled}
