from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlmodel import Session, select
from typing import List
import json
import asyncio
from fastapi.responses import StreamingResponse
from datetime import datetime

from app.database import get_session
from app.auth import get_current_user
from app.models import User, BloodRequest, BloodRequestCreate, DonorProfile, Hospital
from app.scheduler import match_and_schedule_for_request, is_blood_compatible, calculate_distance, is_donor_eligible
from app.config import settings

router = APIRouter(prefix="/api/requests", tags=["Blood Requests"])

@router.get("/hospitals")
def list_hospitals(session: Session = Depends(get_session)):
    hospitals = session.exec(select(Hospital)).all()
    return {
        "success": True,
        "data": hospitals,
        "message": "Hospitals loaded successfully"
    }

# Active client queues for real-time SSE broadcasting
connected_clients = []

@router.get("/stream")
async def sse_stream():
    async def event_generator():
        queue = asyncio.Queue()
        connected_clients.append(queue)
        try:
            # Send initial ping to confirm connection
            yield "data: {\"event\": \"connected\"}\n\n"
            while True:
                try:
                    # Wait for a message with a 15-second timeout to send keep-alive pings
                    data = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    # Send an SSE comment as a heartbeat to keep connection alive
                    yield ": ping\n\n"
        except asyncio.CancelledError:
            if queue in connected_clients:
                connected_clients.remove(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

def broadcast_request_update(event_type: str, data: any):
    event_data = json.dumps({"event": event_type, "data": data})
    for queue in list(connected_clients):
        queue.put_nowait(event_data)

@router.post("/create", status_code=status.HTTP_201_CREATED)
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
    
    # Broadcast the new request details to all connected dashboard/mobile clients
    req_dict = {
        "id": db_request.id,
        "created_by_id": db_request.created_by_id,
        "recipient_name": db_request.recipient_name,
        "blood_type": db_request.blood_type,
        "required_units": db_request.required_units,
        "hospital_name": db_request.hospital_name,
        "hospital_latitude": db_request.hospital_latitude,
        "hospital_longitude": db_request.hospital_longitude,
        "urgency_level": db_request.urgency_level,
        "needed_by": db_request.needed_by.isoformat() if isinstance(db_request.needed_by, datetime) else db_request.needed_by,
        "status": db_request.status,
        "created_at": db_request.created_at.isoformat() if isinstance(db_request.created_at, datetime) else db_request.created_at
    }
    broadcast_request_update("request_created", req_dict)
    
    # If the request is high or critical, trigger matching immediately in a background task
    if db_request.urgency_level in ["high", "critical"]:
        background_tasks.add_task(run_immediate_matching, db_request.id)
        
    return {
        "success": True,
        "data": db_request,
        "message": "Blood request created successfully"
    }

def run_immediate_matching(request_id: str):
    """Background task to instantly run matching for a high-urgency request."""
    print(f"Instantly running matching for high-urgency request: {request_id}")
    from app.database import engine
    from app.scheduler import match_and_invite_for_request
    with Session(engine) as sess:
        req = sess.get(BloodRequest, request_id)
        if req and req.status in ["pending", "partially_fulfilled"]:
            match_and_invite_for_request(sess, req)

@router.get("/my-requests")
def get_my_requests(
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    statement = select(BloodRequest).where(BloodRequest.created_by_id == current_user.id)
    requests = session.exec(statement).all()
    return {
        "success": True,
        "data": requests,
        "message": "My requests loaded successfully"
    }

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
        "success": True,
        "data": {
            "request_id": request_id,
            "blood_type": req.blood_type,
            "total_compatible_eligible_donors": compatible_count,
            "nearby_compatible_eligible_donors": nearby_compatible_count,
            "search_radius_km": settings.MATCH_RADIUS_KM
        },
        "message": "Eligible compatible donors count calculated successfully"
    }
