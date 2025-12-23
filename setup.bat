@echo off
REM Data Exploration Agent - Setup Script (Windows)
REM This script sets up the project after cloning from git

echo.
echo Setting up Data Exploration Agent...
echo.

REM Check if .env exists
if exist .env (
    echo .env file already exists
    goto start_docker
)

echo Creating .env file from .env.example...
copy .env.example .env >nul
echo.
echo IMPORTANT: Please update .env with your API keys!
echo Required:
echo - OPENAI_API_KEY ^(get from https://platform.openai.com/api-keys^)
echo - SUPABASE_URL and keys ^(get from https://supabase.com/dashboard^)
echo.
echo Optional:
echo - LANGSMITH_TRACING should be 'false' unless you have a LangSmith account
echo.
echo Press any key when ready...
pause >nul

:start_docker

REM Start Docker containers
echo.
echo Starting Docker containers...
docker compose up -d

REM Wait for database to be ready
echo.
echo Waiting for database to be ready...
timeout /t 5 /nobreak >nul

REM Run migrations
echo.
echo Running database migrations...
docker exec -it agent-backend alembic upgrade head

echo.
echo Setup complete!
echo.
echo Application URLs:
echo    - Application: http://localhost:8080
echo    - API Documentation: http://localhost:8080/docs
echo.
echo Useful commands:
echo    - View logs: docker compose logs -f
echo    - Stop: docker compose down
echo    - Restart: docker compose restart
echo.
pause
