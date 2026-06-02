#!/usr/bin/env python3
"""
Development setup script for AMAL Blood Donation Platform
- Creates admin user automatically
- Generates test tokens for automatic login
- Seeds test data (donors, blood requests, etc.)
"""

import os
import sys
import jwt
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(__file__))

from app.database import engine, init_db
from app.config import settings
from app.auth import get_password_hash
from app.models import User, DonorProfile, BloodRequest

def create_admin_user(session: Session):
    """Create admin user if it doesn't exist"""
    admin_email = "admin@amal.org"
    admin_password = "admin123"
    
    # Check if admin already exists
    statement = select(User).where(User.email == admin_email)
    existing_admin = session.exec(statement).first()
    
    if existing_admin:
        print(f"✓ Admin user already exists: {admin_email}")
        return existing_admin
    
    # Create admin user
    admin_user = User(
        email=admin_email,
        full_name="Admin User",
        phone_number="+1234567890",
        hashed_password=get_password_hash(admin_password),
        role="admin"
    )
    session.add(admin_user)
    session.commit()
    session.refresh(admin_user)
    print(f"✓ Created admin user: {admin_email}")
    print(f"  Password: {admin_password}")
    return admin_user

def create_test_donor(session: Session, index: int = 1):
    """Create test donor user"""
    donor_email = f"donor{index}@amal.org"
    donor_password = "donor123"
    
    # Check if donor already exists
    statement = select(User).where(User.email == donor_email)
    existing_donor = session.exec(statement).first()
    
    if existing_donor:
        print(f"✓ Donor user already exists: {donor_email}")
        return existing_donor
    
    # Create donor user
    donor_user = User(
        email=donor_email,
        full_name=f"Test Donor {index}",
        phone_number=f"+123456789{index}",
        hashed_password=get_password_hash(donor_password),
        role="user"
    )
    session.add(donor_user)
    session.commit()
    session.refresh(donor_user)
    
    # Create donor profile
    blood_types = ["A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]
    donor_profile = DonorProfile(
        user_id=donor_user.id,
        blood_type=blood_types[index % len(blood_types)],
        latitude=33.5731 + (index * 0.01),  # Casablanca area + variation
        longitude=-7.5898 + (index * 0.01),
        is_available=True,
        last_donation_date=None
    )
    session.add(donor_profile)
    session.commit()
    
    print(f"✓ Created donor user: {donor_email} (Blood Type: {blood_types[index % len(blood_types)]})")
    print(f"  Password: {donor_password}")
    return donor_user

def generate_test_tokens():
    """Generate and display test authentication tokens"""
    print("\n" + "="*60)
    print("AUTO-LOGIN TEST TOKENS")
    print("="*60)
    
    admin_token = jwt.encode(
        {
            "sub": "admin@amal.org",
            "role": "admin",
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    print(f"\n🔑 Admin Token (valid 7 days):\n{admin_token}\n")
    
    donor_token = jwt.encode(
        {
            "sub": "donor1@amal.org",
            "role": "user",
            "exp": datetime.now(timezone.utc) + timedelta(days=7)
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM
    )
    
    print(f"🔑 Donor Token (valid 7 days):\n{donor_token}\n")
    
    return admin_token, donor_token

def setup_dev_environment():
    """Main setup function"""
    print("\n" + "="*60)
    print("AMAL DEVELOPMENT SETUP")
    print("="*60)
    print(f"\nDatabase URL: {settings.DATABASE_URL}")
    print(f"Secret Key: {settings.SECRET_KEY}\n")
    
    try:
        # Initialize database
        print("Initializing database...")
        init_db()
        print("✓ Database initialized\n")
        
        # Create tables and seed data
        with Session(engine) as session:
            print("Creating test users...")
            admin_user = create_admin_user(session)
            
            # Create multiple test donors
            for i in range(1, 4):
                create_test_donor(session, i)
            
            session.commit()
        
        # Generate test tokens
        admin_token, donor_token = generate_test_tokens()
        
        print("="*60)
        print("SETUP COMPLETE!")
        print("="*60)
        print("\n📱 Access the application:")
        print("  - Backend API: http://localhost:8000")
        print("  - API Docs: http://localhost:8000/docs")
        print("  - Web Dashboard: http://localhost:5173/login")
        
        print("\n🔐 Credentials:")
        print("  Admin:")
        print("    Email: admin@amal.org")
        print("    Password: admin123")
        print("\n  Donor:")
        print("    Email: donor1@amal.org")
        print("    Password: donor123")
        
        print("\n💾 Save these tokens to .env.test for automatic login:")
        print(f"VITE_ADMIN_TOKEN={admin_token}")
        print(f"VITE_DONOR_TOKEN={donor_token}\n")
        
        return True
        
    except Exception as e:
        print(f"❌ Setup failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = setup_dev_environment()
    sys.exit(0 if success else 1)
