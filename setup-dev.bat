@echo off
REM Quick dev environment setup script for Windows

echo 🚀 Starting AMAL Development Environment Setup...
echo.

REM Step 1: Start Docker containers
echo 📦 Starting Docker containers (PostgreSQL)...
docker-compose up -d

REM Wait for database to be ready
echo ⏳ Waiting for database to be ready...
timeout /t 10 /nobreak

REM Step 2: Install/verify Python dependencies
echo.
echo 📚 Verifying Python dependencies...
pip install -r requirements.txt

REM Step 3: Run setup script
echo.
echo 🔧 Setting up development database and creating test users...
python setup_dev.py

echo.
echo ✅ Development setup complete!
echo.
echo Next steps:
echo 1. Start the backend server: python -m uvicorn app.main:app --reload
echo 2. Or just run: uvicorn app.main:app --reload
echo.
pause
