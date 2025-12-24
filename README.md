# Data Exploration Agent

An intelligent data exploration agent built with LangGraph, FastAPI, and Next.js.

## Features

- AI-powered data analysis and exploration
- Interactive chat interface
- Real-time streaming responses
- Docker-based deployment

## Tech Stack

### Backend

- FastAPI
- LangGraph
- PostgreSQL
- Redis

### Frontend

- Next.js
- TypeScript
- React

## Getting Started

> **🚨 Having issues after git pull?** See [QUICK_FIX.md](QUICK_FIX.md) for common errors and solutions.

### Prerequisites

- Docker and Docker Compose
- Node.js (for local development)
- Python 3.11+ (for local development)

### Quick Setup (Recommended)

**For Linux/Mac:**

```bash
chmod +x setup.sh
./setup.sh
```

**For Windows:**

```bash
setup.bat
```

### Manual Setup

If you prefer to set up manually:

1. Clone the repository
2. Navigate to the project directory
3. Copy `.env.example` to `.env` and update with your keys:
   ```bash
   cp .env.example .env
   ```
4. Start the Docker containers:
   ```bash
   docker compose up -d
   ```
5. **Run database migrations** (IMPORTANT - Required for first-time setup):
   ```bash
   docker exec -it agent-backend alembic upgrade head
   ```

The application will be available at:

- Frontend: http://localhost:8080 (via Nginx)
- Backend API: http://localhost:8080/api (via Nginx)
- API Documentation: http://localhost:8000/docs (direct backend access)

### Database Setup

This project uses **Alembic** for database migrations. Tables are NOT automatically created.

**After pulling from git, always run:**

```bash
docker exec -it agent-backend alembic upgrade head
```

**To create a new migration:**

```bash
docker exec -it agent-backend alembic revision --autogenerate -m "description"
```

**Common Issues:**

- ❌ "table not found" error → You forgot to run migrations
- ❌ Database connection error → Check `.env` file has correct credentials

**For more help, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md)**

### Image Dir Setup

To use image analysis tools with actual images, you need to set up the `images` directory.

1. Create a directory named `images` in the resource directory : `backend/app/resource/images`.
2. Follow steps on this [Caesure](https://github.com/DataManagementLab/caesura) to download the images. (We will use Artworks DB as it is synced to the art.db)
3. Place your images in the newly created `images` directory.

## Project Structure

```
.
├── backend/          # FastAPI backend
│   ├── app/
│   │   ├── agents/   # LangGraph agents
│   │   ├── api/      # API routes
│   │   └── services/ # Business logic
├── frontend/         # Next.js frontend
│   ├── app/          # App router pages
│   ├── components/   # React components
│   └── lib/          # Utilities and services
├── nginx/            # Nginx configuration
└── docker-compose.yml
```

## License

MIT
