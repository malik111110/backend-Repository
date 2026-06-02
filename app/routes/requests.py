from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel import Session, select
from typing import List

from app.database import get_session
from app.auth import get_current_user
from app.models import User, BloodRequest, BloodRequestCreate, BloodRequestRead, DonorProfile
from app.scheduler import match_and_schedule_for_request, is_blood_compatible, calculate_distance, is_donor_eligible
from app.config import settings

router = APIRouter(prefix="/api/requests", tags=["Blood Requests"])

@router.post("/create", response_model=BloodRequestRead, status_code=status.HTTP_201_CREATED)
def create_blood_request(
    request_data: BloodRequestCreate,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    # Validate blood type
    valid_types = {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"}
    if request_data.blood_type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid blood type. Must be one of {valid_types}"
        )
        
    # Validate urgency level
    valid_urgency = {"low", "medium", "high", "critical"}
    if request_data.urgency_level.lower() not in valid_urgency:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid urgency level. Must be one of {valid_urgency}"
        )
        
    # Create request
    db_request = BloodRequest(
        created_by_id=current_user.id,
        recipient_name=request_data.recipient_name,
        blood_type=request_data.blood_type,
        required_units=request_data.required_units,
        hospital_name=request_data.hospital_name,
        hospital_latitude=request_data.hospital_latitude,
        hospital_longitude=request_data.hospital_longitude,
        urgency_level=request_data.urgency_level.lower(),
        needed_by=request_data.needed_by,
        status="pending"
    )
    session.add(db_request)
    session.commit()
    session.refresh(db_request)
    
    # If the request is high or critical, trigger matching immediately in a background task
    if db_request.urgency_level in ["high", "critical"]:
        background_tasks.add_task(run_immediate_matching, db_request.id)
        
    return db_request

def run_immediate_matching(request_id: str):
    """Background task to instantly run matching for a high-urgency request."""
    print(f"Instantly running matching for high-urgency request: {request_id}")
    from app.database import engine
    from app.scheduler import match_and_invite_for_request
    with Session(engine) as sess:
        req = sess.get(BloodRequest, request_id)
        if req and req.status in ["pending", "partially_fulfilled"]:
            match_and_invite_for_request(sess, req)

@router.get("/my-requests", response_model=List[BloodRequestRead])
def get_my_requests(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    statement = select(BloodRequest).where(BloodRequest.created_by_id == current_user.id)
    requests = session.exec(statement).all()
    return requests

@router.get("/{request_id}/eligible-donors-count")
def get_eligible_donors_count_for_request(
    request_id: str,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    req = session.get(BloodRequest, request_id)
    if not req:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Blood request not found"
        )
        
    # Ensure current user owns the request or is admin
    if req.created_by_id != current_user.id and current_user.role != "admin_hopital":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view details for this request."
        )
        
    # Query all active compatible donor profiles
    from app.scheduler import get_compatible_nearby_donors, COMPATIBILITY_MAP
    
    allowed_donors = list(COMPATIBILITY_MAP.get(req.blood_type, set()))
    global_statement = select(DonorProfile).where(
        DonorProfile.is_available == True,
        DonorProfile.blood_type.in_(allowed_donors)
    )
    all_compatible = session.exec(global_statement).all()
    compatible_count = len([d for d in all_compatible if is_donor_eligible(d)])
    
    # Use spatial query for nearby compatible count
    matches = get_compatible_nearby_donors(
        session,
        req.blood_type,
        req.hospital_latitude,
        req.hospital_longitude
    )
    nearby_compatible_count = len(matches)
                
    return {
        "request_id": request_id,
        "blood_type": req.blood_type,
        "total_compatible_eligible_donors": compatible_count,
        "nearby_compatible_eligible_donors": nearby_compatible_count,
        "search_radius_km": settings.MATCH_RADIUS_KM
    }
