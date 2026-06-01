import pytest
from datetime import datetime, timedelta, date, timezone
from sqlmodel import Session, SQLModel, create_engine

from app.scheduler import is_blood_compatible, calculate_distance, is_donor_eligible, match_and_schedule_for_request
from app.models import User, DonorProfile, BloodRequest, DonationSchedule

# ==========================================
# 1. TEST DATA
# ==========================================

def test_blood_compatibility():
    # O- can donate to anyone
    assert is_blood_compatible("O-", "O-") is True
    assert is_blood_compatible("O-", "AB+") is True
    assert is_blood_compatible("O-", "A-") is True
    
    # AB+ can only donate to AB+
    assert is_blood_compatible("AB+", "AB+") is True
    assert is_blood_compatible("AB+", "O-") is False
    assert is_blood_compatible("AB+", "A+") is False
    
    # A+ compatibility
    assert is_blood_compatible("A-", "A+") is True
    assert is_blood_compatible("B+", "A+") is False


def test_distance_calculation():
    # Coordinates for two points in Tunis (approx 5km apart)
    lat1, lon1 = 36.8065, 10.1815  # Tunis Center
    lat2, lon2 = 36.8500, 10.2000  # Ariana
    dist = calculate_distance(lat1, lon1, lat2, lon2)
    assert 4.0 <= dist <= 6.0


def test_donor_eligibility():
    donor = DonorProfile(blood_type="O+", latitude=36.8, longitude=10.1)
    
    # Newly created donor (no past donation date) is eligible
    donor.is_available = True
    donor.last_donation_date = None
    assert is_donor_eligible(donor) is True
    
    # Unavailable donor is not eligible
    donor.is_available = False
    assert is_donor_eligible(donor) is False
    
    # Donor who donated 60 days ago is eligible (interval is 56 days)
    donor.is_available = True
    donor.last_donation_date = date.today() - timedelta(days=60)
    assert is_donor_eligible(donor) is True
    
    # Donor who donated 30 days ago is not eligible
    donor.last_donation_date = date.today() - timedelta(days=30)
    assert is_donor_eligible(donor) is False


def test_matching_algorithm():
    # Create in-memory SQLite database for testing matching logic
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Create users
        user_donor = User(email="donor@test.com", full_name="John Donor", phone_number="123", hashed_password="pw")
        user_recipient = User(email="recip@test.com", full_name="Jane Recip", phone_number="456", hashed_password="pw")
        session.add(user_donor)
        session.add(user_recipient)
        session.commit()
        
        # Create donor profiles
        # Compatible donor: A+ blood, 5km away, eligible
        donor1 = DonorProfile(user_id=user_donor.id, blood_type="A+", latitude=36.80, longitude=10.18, is_available=True)
        session.add(donor1)
        session.commit()
        
        # Create blood request: A+ blood, needed at 36.84, 10.20 (approx 5.5km away)
        request = BloodRequest(
            created_by_id=user_recipient.id,
            recipient_name="Baby Jane",
            blood_type="A+",
            required_units=1,
            hospital_name="Tunis Hospital",
            hospital_latitude=36.84,
            hospital_longitude=10.20,
            urgency_level="high",
            needed_by=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=2)
        )
        session.add(request)
        session.commit()
        
        # Execute matching
        scheduled_appointments = match_and_schedule_for_request(session, request)
        
        assert len(scheduled_appointments) == 1
        assert scheduled_appointments[0].donor_id == donor1.id
        assert scheduled_appointments[0].request_id == request.id
        
        # Check donor availability is set to False (temporary hold)
        session.refresh(donor1)
        assert donor1.is_available is False
        
        # Check request status is updated to fulfilled
        session.refresh(request)
        assert request.status == "fulfilled"
