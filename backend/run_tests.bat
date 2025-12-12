@echo off
REM Script to run pytest inside the Docker container (Windows)

echo Running tests in Docker container...
echo.

REM Check if container is running
docker ps | findstr "agent-backend" >nul 2>&1
if errorlevel 1 (
    echo Error: agent-backend container is not running
    echo Please start the container with: docker compose up
    exit /b 1
)

REM Install test dependencies if not already installed
echo Installing test dependencies...
docker compose exec backend pip install -q -r requirements-test.txt

REM Run pytest with arguments passed to this script
if "%~1"=="" (
    echo Running all tests...
    echo.
    docker compose exec backend pytest tests/ -v
) else (
    echo Running: pytest %*
    echo.
    docker compose exec backend pytest %*
)

REM Capture exit code
set EXIT_CODE=%ERRORLEVEL%

REM Print summary
echo.
if %EXIT_CODE% equ 0 (
    echo [32m✅ Tests passed![0m
) else (
    echo [31m❌ Tests failed![0m
)

exit /b %EXIT_CODE%
