from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import Session, select

from app.database import get_session
from app.auth import get_password_hash, verify_password, create_access_token, get_current_user
from app.models import User, UserCreate, UserRead, Token, DonorProfile

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(user_data: UserCreate, session: Session = Depends(get_session)):
    # Check if user already exists
    statement = select(User).where(User.email == user_data.email)
    existing_user = session.exec(statement).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
        
    # Check donor details validity if registration is for a donor
    if user_data.is_donor:
        if not user_data.blood_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Blood type is required for donors"
            )
        if user_data.latitude is None or user_data.longitude is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Latitude and Longitude are required for donors"
            )
            
    # Create user
    # If the email is admin@amal.org, automatically make them an admin for easy setup
    role = "admin_hopital" if user_data.email.lower() == "admin@amal.org" else "user"
    
    db_user = User(
        email=user_data.email,
        full_name=user_data.full_name,
        phone_number=user_data.phone_number,
        hashed_password=get_password_hash(user_data.password),
        role=role
    )
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    
    # Create donor profile if applicable
    if user_data.is_donor:
        db_donor = DonorProfile(
            user_id=db_user.id,
            blood_type=user_data.blood_type,
            latitude=user_data.latitude,
            longitude=user_data.longitude,
            is_available=True
        )
        session.add(db_donor)
        session.commit()
        
    return db_user

@router.post("/login", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(get_session)):
    statement = select(User).where(User.email == form_data.username)
    user = session.exec(statement).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    access_token = create_access_token(data={"sub": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "role": current_user.role,
        "first_name": current_user.first_name or current_user.full_name.split(" ")[0],
        "last_name": current_user.last_name or (" ".join(current_user.full_name.split(" ")[1:]) if len(current_user.full_name.split(" ")) > 1 else ""),
        "email": current_user.email,
        "phone": current_user.phone_number,
        "region": current_user.region,
        "hopital_id": current_user.hopital_id,
        "latitude": getattr(current_user.donor_profile, "latitude", None) if current_user.donor_profile else None,
        "longitude": getattr(current_user.donor_profile, "longitude", None) if current_user.donor_profile else None
    }

from pydantic import BaseModel
from typing import Optional

class ProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone: Optional[str] = None
    birth_date: Optional[str] = None
    blood_type: Optional[str] = None
    wilaya: Optional[str] = None

@router.patch("/profile")
def update_profile(
    profile_data: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session)
):
    if profile_data.first_name is not None:
        current_user.first_name = profile_data.first_name
    if profile_data.last_name is not None:
        current_user.last_name = profile_data.last_name
    if profile_data.phone is not None:
        current_user.phone_number = profile_data.phone
    if profile_data.wilaya is not None:
        current_user.region = profile_data.wilaya
    
    # If they have a donor profile, update their blood_type
    if profile_data.blood_type is not None:
        if current_user.donor_profile:
            current_user.donor_profile.blood_type = profile_data.blood_type
            session.add(current_user.donor_profile)
        
    # Re-calculate full_name if first_name/last_name are modified
    first = current_user.first_name or ""
    last = current_user.last_name or ""
    if first or last:
        current_user.full_name = f"{first} {last}".strip()
        
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    
    return {
        "id": current_user.id,
        "role": current_user.role,
        "first_name": current_user.first_name or current_user.full_name.split(" ")[0],
        "last_name": current_user.last_name or (" ".join(current_user.full_name.split(" ")[1:]) if len(current_user.full_name.split(" ")) > 1 else ""),
        "email": current_user.email,
        "phone": current_user.phone_number,
        "region": current_user.region,
        "hopital_id": current_user.hopital_id,
        "latitude": getattr(current_user.donor_profile, "latitude", None) if current_user.donor_profile else None,
        "longitude": getattr(current_user.donor_profile, "longitude", None) if current_user.donor_profile else None
    }

