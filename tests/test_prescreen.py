import pytest
from sqlmodel import Session, SQLModel, create_engine
from app.models import User, DonorProfile, PreScreenQuestionnaire
from app.routes.donors import submit_pre_screen_questionnaire

def test_prescreen_logic():
    # Setup test memory db
    engine = create_engine("sqlite:///:memory:")
    SQLModel.metadata.create_all(engine)
    
    with Session(engine) as session:
        # Create user & donor profile
        user = User(email="d@t.com", full_name="Donor", phone_number="123", hashed_password="pw")
        session.add(user)
        session.commit()
        
        donor = DonorProfile(user_id=user.id, blood_type="O+", latitude=36.8, longitude=10.1, is_available=True)
        session.add(donor)
        session.commit()
        
        # Test Questionnaire with RISK (antibiotics)
        q_fail = PreScreenQuestionnaire(
            has_recent_tattoo_or_piercing=False,
            has_infectious_diseases=False,
            is_taking_antibiotics=True,
            has_traveled_malaria_zone_recently=False,
            is_feeling_unwell=False
        )
        
        resp_fail = submit_pre_screen_questionnaire(
            questionnaire=q_fail,
            donor=donor,
            session=session
        )
        
        assert resp_fail["cleared"] is False
        assert "Pre-screening failed" in resp_fail["message"]
        
        # Verify donor details are updated
        session.refresh(donor)
        assert donor.health_clearance_token is None
        assert donor.is_available is False
        assert donor.health_checked_at is not None
        
        # Test Questionnaire with NO RISK (passing)
        q_pass = PreScreenQuestionnaire(
            has_recent_tattoo_or_piercing=False,
            has_infectious_diseases=False,
            is_taking_antibiotics=False,
            has_traveled_malaria_zone_recently=False,
            is_feeling_unwell=False
        )
        
        resp_pass = submit_pre_screen_questionnaire(
            questionnaire=q_pass,
            donor=donor,
            session=session
        )
        
        assert resp_pass["cleared"] is True
        assert resp_pass["health_clearance_token"] is not None
        
        # Verify donor is now cleared
        session.refresh(donor)
        assert donor.health_clearance_token == resp_pass["health_clearance_token"]
        assert donor.is_available is True
