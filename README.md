# terifai

A conversation voice bot that "steals your voice". Through conversation with you, it will:

- Learn about you and who you are
- Mimic your speaking style
- And clone your voice

The purpose of this project is to educate, especially people who are the most exposed to voice phishing attacks.

## Development

### Prerequisites
- [Rye](https://rye-up.com/guide/installation/) for Python dependency management
- [Bun](https://bun.sh/) for frontend development

### Initial Setup

1. Clone and setup the repository:
   ```bash
   git clone <repository-url>
   cd terifai
   rye sync
   ```

2. Setup the frontend:
   ```bash
   cd frontend
   bun install
   ```

### Running the Application

#### Bot Only
To run just the conversation bot:
```bash
rye run bot
```


#### Full Application (Backend + Frontend)
1. Start the backend server (in one terminal):
   ```bash
   # For production mode (using Fly.io for bot instances)
   rye run server

   # For local development (running bots locally)
   rye run server --local
   ```

   The `--local` flag runs bot instances directly on your machine instead of spawning Fly.io machines. This is useful for:
   - Local development without Fly.io credentials
   - Debugging bot behavior
   - Testing without cloud resources

2. Start the frontend (in another terminal):
   ```bash
   cd frontend
   bun run dev
   ```

The application will be running at:
- Backend: http://localhost:8000
- Frontend: http://localhost:3000

### Deployment

#### Server
fly automaically deploys every commit to the `main` branch, but you can manually deploy with `fly deploy`

#### Frontend
Vercel handles the frontend deployment. It already automatically deploys every commit to the `main` branch.

If you want to deploy manually, check their docs.

#### Cloning Voice Jobs
This happens in modal, so make sure you have a modal account and are logged in.
```bash
$ cd backend
$ modal deploy jobs.py --env=dev # for dev deployment
$ modal deploy jobs.py --env=main # for prod deployment
```

### Development Tools

#### Linting
- Backend: Run `rye lint` from the root directory
- Frontend: Run `bun lint` from the `frontend` directory
