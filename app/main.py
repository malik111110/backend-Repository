from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.scheduler import start_scheduler, shutdown_scheduler
from app.routes import auth, donors, requests, admin

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite Database tables
    init_db()
    # Start APScheduler background matching task
    start_scheduler()
    yield
    # Shutdown background matching task
    shutdown_scheduler()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for Amal blood transferring and donation platform supporting mobile applications and admin dashboard.",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS for Web Admin app integration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth.router)
app.include_router(donors.router)
app.include_router(requests.router)
app.include_router(admin.router)

@app.get("/")
def read_root():
    return {
        "message": "Welcome to Amal Blood Donation & Transfer API",
        "docs_url": "/docs",
        "status": "healthy"
    }
