# /deploy — Deployment Helper

Generate deployment commands for testing and production.

## Usage
- `/deploy dev` — Commands to rebuild and run both containers on same machine
- `/deploy prod` — Commands to deploy to production (Mac Studio + Mac Mini)
- `/deploy test` — Quick test checklist

## Instructions

### Dev (same machine)
```bash
# Backend
docker builder prune -f
docker compose -f docker-compose.backend.yml build --no-cache
docker compose -f docker-compose.backend.yml up -d

# Frontend Worker
docker compose -f docker-compose.frontworker.yml build --no-cache
docker compose -f docker-compose.frontworker.yml up -d

# Frontend Organizer (optional)
docker compose -f docker-compose.frontorganizer.yml build --no-cache
docker compose -f docker-compose.frontorganizer.yml up -d
```

Register frontend in backend admin using host IP: `http://<HOST_IP>:8091`

### Production
Provide commands for both machines:
- Mac Studio (10.210.66.103): Backend
- Mac Mini (10.210.66.130): Frontend Worker + Organizer

### Test Checklist
1. Backend admin loads at `http://<IP>:8000`
2. Create/login admin account
3. Register frontend URL
4. Frontend loads at `http://<IP>:8091`
5. Complete user flow: language → disclaimer → session → survey → chat
6. Verify streaming response appears
7. Check session recovery works
8. Test "End Session" generates summary
