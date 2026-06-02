import uuid
from datetime import datetime, date, timezone
from typing import Optional, List, Generic, TypeVar, Any
# pyrefly: ignore [missing-import]
from sqlmodel import SQLModel, Field, Relationship

# ==========================================
# 1. USER MODELS
# ==========================================

class UserBase(SQLModel):
    email: str = Field(unique=True, index=True)
    full_name: str
    phone_number: str

class User(UserBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    hashed_password: str
    role: str = Field(default="user")  # "admin" or "user"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    # Relationships
    donor_profile: Optional["DonorProfile"] = Relationship(back_populates="user", sa_relationship_kwargs={"uselist": False})
    blood_requests: List["BloodRequest"] = Relationship(back_populates="created_by")

class UserCreate(UserBase):
    password: str
    is_donor: bool = False
    blood_type: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None

class UserRead(UserBase):
    id: str
    role: str
    created_at: datetime

class Token(SQLModel):
    access_token: str
    token_type: str

class TokenData(SQLModel):
    email: Optional[str] = None
    role: Optional[str] = None


# ==========================================
# 2. DONOR PROFILE MODELS
# ==========================================

class DonorProfileBase(SQLModel):
    blood_type: str  # "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"
    latitude: float
    longitude: float
    is_available: bool = True
    last_donation_date: Optional[date] = None
    health_clearance_token: Optional[str] = None
    health_checked_at: Optional[datetime] = None

class DonorProfile(DonorProfileBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    user_id: str = Field(foreign_key="user.id", unique=True)
    
    # Relationships
    user: User = Relationship(back_populates="donor_profile")
    schedules: List["DonationSchedule"] = Relationship(back_populates="donor")

class DonorProfileCreate(DonorProfileBase):
    pass

class DonorProfileRead(DonorProfileBase):
    id: str
    user_id: str

class PreScreenQuestionnaire(SQLModel):
    has_recent_tattoo_or_piercing: bool
    has_infectious_diseases: bool
    is_taking_antibiotics: bool
    has_traveled_malaria_zone_recently: bool
    is_feeling_unwell: bool



# ==========================================
# 3. BLOOD REQUEST MODELS (RECIPIENTS)
# ==========================================

class BloodRequestBase(SQLModel):
    recipient_name: str
    blood_type: str
    required_units: int
    hospital_name: str
    hospital_latitude: float
    hospital_longitude: float
    urgency_level: str  # "low", "medium", "high", "critical"
    needed_by: datetime

class BloodRequest(BloodRequestBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    created_by_id: str = Field(foreign_key="user.id")
    status: str = Field(default="pending")  # "pending", "partially_fulfilled", "fulfilled", "cancelled"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    # Relationships
    created_by: User = Relationship(back_populates="blood_requests")
    schedules: List["DonationSchedule"] = Relationship(back_populates="request")

class BloodRequestCreate(BloodRequestBase):
    pass

class BloodRequestRead(BloodRequestBase):
    id: str
    created_by_id: str
    status: str
    created_at: datetime


# ==========================================
# 4. DONATION SCHEDULE MODELS (APPOINTMENTS)
# ==========================================

class DonationScheduleBase(SQLModel):
    scheduled_time: datetime
    status: str = Field(default="scheduled")  # "scheduled", "completed", "cancelled", "no_show"
    units_donated: Optional[int] = None

class DonationSchedule(DonationScheduleBase, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    donor_id: str = Field(foreign_key="donorprofile.id")
    request_id: Optional[str] = Field(default=None, foreign_key="bloodrequest.id", nullable=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    
    # Relationships
    donor: DonorProfile = Relationship(back_populates="schedules")
    request: Optional[BloodRequest] = Relationship(back_populates="schedules")

class DonationScheduleCreate(SQLModel):
    request_id: Optional[str] = None
    scheduled_time: datetime

class DonationScheduleRead(DonationScheduleBase):
    id: str
    donor_id: str
    request_id: Optional[str]
    created_at: datetime


# ==========================================
# 5. INVITATION MODELS (TIME-CRITICAL OUTREACH)
# ==========================================

class Invitation(SQLModel, table=True):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()), primary_key=True)
    request_id: str = Field(foreign_key="bloodrequest.id")
    donor_id: str = Field(foreign_key="donorprofile.id")
    status: str = Field(default="pending")  # "pending", "accepted", "declined", "expired", "cancelled"
    priority_order: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    expires_at: datetime

    # Relationships
    donor: DonorProfile = Relationship()
    request: BloodRequest = Relationship()

class InvitationRead(SQLModel):
    id: str
    request_id: str
    donor_id: str
    status: str
    priority_order: int
    created_at: datetime
    expires_at: datetime

class InvitationResponse(SQLModel):
    accepted: bool


# ==========================================
# 6. STANDARDIZED API RESPONSE MODELS
# ==========================================

T = TypeVar('T')

class ApiResponse(Generic[T], SQLModel):
    success: bool
    data: Optional[T] = None
    message: Optional[str] = None
    error: Optional[str] = None


# ==========================================
# 7. TEAM MEMBER MODELS
# ==========================================

class TeamMemberBase(SQLModel):
    first_name: str
    last_name: str
    role: str
    department: str
    email: str = Field(unique=True, index=True)
    phone: str
    shift: str
    status: str = Field(default="pending")  # "active" or "pending"

class TeamMember(TeamMemberBase, table=True):
    id: str = Field(default_factory=lambda: f"tm-{uuid.uuid4().hex[:8]}", primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

class TeamMemberCreate(TeamMemberBase):
    pass

class TeamMemberRead(TeamMemberBase):
    id: str
    created_at: datetime


