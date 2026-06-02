from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse

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

# Standardized Error Exception Handlers
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "data": None,
            "message": exc.detail,
            "error": exc.detail
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    error_msg = "; ".join([f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()])
    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "data": None,
            "message": "Validation Error",
            "error": error_msg
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "data": None,
            "message": "Internal Server Error",
            "error": str(exc)
        }
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
