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

### Prerequisites

- Docker and Docker Compose
- Node.js (for local development)
- Python 3.11+ (for local development)

### Running with Docker

1. Clone the repository
2. Navigate to the project directory
3. Update .env file with your keys
4. Run the following command to start the application

```bash
docker compose up
```

The application will be available at:

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- API Documentation: http://localhost:8000/docs

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
