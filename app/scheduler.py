import math
from datetime import datetime, timedelta, date
from typing import List, Dict, Set
from sqlmodel import Session, select
from apscheduler.schedulers.background import BackgroundScheduler

from app.config import settings
from app.database import engine
from app.models import DonorProfile, BloodRequest, DonationSchedule, Invitation
from app.notifications import send_push_notification

# ==========================================
# 1. BLOOD TYPE COMPATIBILITY RULES
# ==========================================

COMPATIBILITY_MAP: Dict[str, Set[str]] = {
    "A+": {"A+", "A-", "O+", "O-"},
    "A-": {"A-", "O-"},
    "B+": {"B+", "B-", "O+", "O-"},
    "B-": {"B-", "O-"},
    "AB+": {"A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"},
    "AB-": {"AB-", "A-", "B-", "O-"},
    "O+": {"O+", "O-"},
    "O-": {"O-"}
}

def is_blood_compatible(donor_type: str, recipient_type: str) -> bool:
    """Returns True if the donor's blood type is compatible with the recipient's."""
    allowed_donors = COMPATIBILITY_MAP.get(recipient_type, set())
    return donor_type in allowed_donors


# ==========================================
# 2. HAVERSINE DISTANCE CALCULATOR
# ==========================================

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great circle distance in kilometers between two points 
    on the earth (specified in decimal degrees)
    """
    # Convert decimal degrees to radians 
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])

    # Haversine formula 
    dlat = lat2 - lat1 
    dlon = lon2 - lon1 
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a)) 
    r = 6371 # Radius of earth in kilometers.
    return c * r


# ==========================================
# 3. ELIGIBILITY VALIDATION
# ==========================================

def is_donor_eligible(donor: DonorProfile) -> bool:
    """Checks if the donor is eligible to donate based on last donation date and availability."""
    if not donor.is_available:
        return False
    
    if donor.last_donation_date:
        days_since_last_donation = (date.today() - donor.last_donation_date).days
        if days_since_last_donation < settings.MIN_DONATION_INTERVAL_DAYS:
            return False
            
    return True


# ==========================================
# 4. MATCHING ENGINE & AUTO-SCHEDULER (PostGIS & SQLite fallback)
# ==========================================

from sqlalchemy import func

def get_compatible_nearby_donors(session: Session, request_blood_type: str, hospital_lat: float, hospital_lon: float) -> List[tuple[DonorProfile, float]]:
    """
    Returns a sorted list of compatible, eligible nearby donors with their distances.
    Supports SQLite fallback for local testing and PostGIS for production environments.
    """
    if settings.DATABASE_URL.startswith("sqlite"):
        statement = select(DonorProfile).where(DonorProfile.is_available == True)
        all_donors = session.exec(statement).all()
        eligible_donors = [d for d in all_donors if is_donor_eligible(d)]
        matches = []
        for donor in eligible_donors:
            if not is_blood_compatible(donor.blood_type, request_blood_type):
                continue
            dist = calculate_distance(
                donor.latitude, donor.longitude,
                hospital_lat, hospital_lon
            )
            if dist <= settings.MATCH_RADIUS_KM:
                matches.append((donor, dist))
    else:
        allowed_donors = list(COMPATIBILITY_MAP.get(request_blood_type, set()))
        statement = select(DonorProfile).where(
            DonorProfile.is_available == True,
            DonorProfile.blood_type.in_(allowed_donors),
            func.ST_DistanceSphere(
                func.ST_MakePoint(DonorProfile.longitude, DonorProfile.latitude),
                func.ST_MakePoint(hospital_lon, hospital_lat)
            ) <= (settings.MATCH_RADIUS_KM * 1000.0)
        )
        donors_in_radius = session.exec(statement).all()
        eligible_donors = [d for d in donors_in_radius if is_donor_eligible(d)]
        matches = []
        for donor in eligible_donors:
            dist = calculate_distance(
                donor.latitude, donor.longitude,
                hospital_lat, hospital_lon
            )
            matches.append((donor, dist))
            
    matches.sort(key=lambda x: x[1])
    return matches


def match_and_invite_for_request(session: Session, request: BloodRequest) -> int:
    """
    Finds the closest compatible eligible donors (up to 5) and creates a 
    priority cascade invitation list for urgent dispatch.
    """
    # Check if we already have pending invitations for this request to avoid duplicates
    existing_invs = session.exec(
        select(Invitation).where(Invitation.request_id == request.id)
    ).all()
    if existing_invs:
        return 0

    # 1. Fetch closest compatible eligible donors using helper
    matches = get_compatible_nearby_donors(
        session,
        request.blood_type,
        request.hospital_latitude,
        request.hospital_longitude
    )

    # 2. Queue top 5 donors
    top_matches = matches[:5]
    invitations_created = 0
    now = datetime.now()

    for idx, (donor, dist) in enumerate(top_matches):
        status = "pending" if idx == 0 else "queued"
        expires_at = now + timedelta(seconds=180) if idx == 0 else now + timedelta(days=1)
        
        invitation = Invitation(
            request_id=request.id,
            donor_id=donor.id,
            status=status,
            priority_order=idx,
            created_at=now,
            expires_at=expires_at
        )
        session.add(invitation)
        invitations_created += 1
        
        # Trigger immediate push to primary candidate
        if idx == 0:
            send_push_notification(
                donor_id=donor.id,
                title="🚨 URGENT BLOOD DONATION REQUEST NEEDED",
                body=f"A patient compatible with your blood type ({donor.blood_type}) is in critical need at {request.hospital_name}. Respond now!",
                data={"request_id": request.id, "invitation_id": invitation.id}
            )

    if invitations_created > 0:
        session.commit()
        
    return invitations_created


def match_and_schedule_for_request(session: Session, request: BloodRequest) -> List[DonationSchedule]:
    """
    Finds the best eligible donors for a specific request and schedules them directly.
    Returns the list of scheduled appointments created. (Used for non-critical/regular flow)
    """
    # Fetch compatible nearby donors
    matches = get_compatible_nearby_donors(
        session,
        request.blood_type,
        request.hospital_latitude,
        request.hospital_longitude
    )
    
    schedules_statement = select(DonationSchedule).where(
        DonationSchedule.request_id == request.id,
        DonationSchedule.status.in_(["scheduled", "completed"])
    )
    existing_schedules = session.exec(schedules_statement).all()
    units_already_scheduled = len(existing_schedules)
    units_needed = request.required_units - units_already_scheduled
    
    created_schedules = []
    
    for donor, dist in matches:
        if units_needed <= 0:
            break
            
        donor_schedules_statement = select(DonationSchedule).where(
            DonationSchedule.donor_id == donor.id,
            DonationSchedule.status == "scheduled"
        )
        donor_upcoming = session.exec(donor_schedules_statement).first()
        if donor_upcoming:
            continue
            
        scheduled_time = datetime.now() + timedelta(days=1)
        
        new_schedule = DonationSchedule(
            donor_id=donor.id,
            request_id=request.id,
            scheduled_time=scheduled_time,
            status="scheduled"
        )
        session.add(new_schedule)
        
        donor.is_available = False
        session.add(donor)
        
        created_schedules.append(new_schedule)
        units_needed -= 1
        
    if len(created_schedules) > 0:
        total_fulfilled = units_already_scheduled + len(created_schedules)
        if total_fulfilled >= request.required_units:
            request.status = "fulfilled"
        else:
            request.status = "partially_fulfilled"
        session.add(request)
        session.commit()
        
    return created_schedules


def run_auto_scheduling():
    """
    Main job run by the scheduler. Finds all pending/partially fulfilled requests
    and matches them with available donors.
    """
    print(f"[{datetime.now()}] Running auto-scheduling matching engine...")
    with Session(engine) as session:
        statement = select(BloodRequest).where(BloodRequest.status.in_(["pending", "partially_fulfilled"]))
        active_requests = session.exec(statement).all()
        
        urgency_priority = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        active_requests.sort(key=lambda r: (urgency_priority.get(r.urgency_level.lower(), 4), r.needed_by))
        
        total_schedules_created = 0
        total_invitations_created = 0
        
        for request in active_requests:
            if request.urgency_level in ["high", "critical"]:
                # Time-critical cascade routing
                invs = match_and_invite_for_request(session, request)
                total_invitations_created += invs
            else:
                # Direct scheduler
                created = match_and_schedule_for_request(session, request)
                total_schedules_created += len(created)
            
        print(f"[{datetime.now()}] Auto-scheduling completed. Created {total_schedules_created} schedules & {total_invitations_created} invitations.")


def process_invitation_timeouts():
    """
    Scans for expired pending invitations (older than 180s) and cascades matching 
    notifications to the next closest candidate in queue.
    """
    now = datetime.now()
    with Session(engine) as session:
        expired_invitations = session.exec(
            select(Invitation).where(
                Invitation.status == "pending",
                Invitation.expires_at < now
            )
        ).all()
        
        for invitation in expired_invitations:
            invitation.status = "expired"
            session.add(invitation)
            print(f"[{now}] Invitation {invitation.id} for donor {invitation.donor_id} expired. Cascading...")
            
            # Find next donor in queue (priority_order = current + 1)
            next_invitation = session.exec(
                select(Invitation).where(
                    Invitation.request_id == invitation.request_id,
                    Invitation.priority_order == invitation.priority_order + 1,
                    Invitation.status == "queued"
                )
            ).first()
            
            if next_invitation:
                next_invitation.status = "pending"
                next_invitation.expires_at = now + timedelta(seconds=180)
                session.add(next_invitation)
                
                # Fetch request details to populate message
                req = session.get(BloodRequest, invitation.request_id)
                donor = session.get(DonorProfile, next_invitation.donor_id)
                if req and donor:
                    send_push_notification(
                        donor_id=donor.id,
                        title="🚨 URGENT BLOOD DONATION NEEDED (NEXT IN LINE)",
                        body=f"Previous candidate expired. Critical need for your blood type ({donor.blood_type}) at {req.hospital_name}.",
                        data={"request_id": req.id, "invitation_id": next_invitation.id}
                    )
            else:
                print(f"[{now}] No further candidates queued in cascade for request {invitation.request_id}")
                
        if expired_invitations:
            session.commit()


# ==========================================
# 5. INITIALIZE BACKGROUND SCHEDULER
# ==========================================

scheduler = BackgroundScheduler()

def start_scheduler():
    if not scheduler.running:
        # Run matching engine every settings.SCHEDULER_INTERVAL_MINUTES
        scheduler.add_job(
            run_auto_scheduling, 
            "interval", 
            minutes=settings.SCHEDULER_INTERVAL_MINUTES,
            id="blood_matching_job"
        )
        # Process invitation timeouts every 10 seconds for real-time cascade responsiveness
        scheduler.add_job(
            process_invitation_timeouts,
            "interval",
            seconds=10,
            id="invitation_timeout_job"
        )
        scheduler.start()
        print(f"Background scheduler started. Matching interval: {settings.SCHEDULER_INTERVAL_MINUTES}m. Timeout cascade: 10s.")

def shutdown_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        print("Background scheduler shut down.")

