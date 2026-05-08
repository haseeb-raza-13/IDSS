# 1. Copy env file and fill in your keys
cp .env.example .env

# 2. Start all services
docker compose up --build

# 3. Register your first user
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@lab.edu","password":"yourpass","name":"Dr. Smith"}'

# 4. Open the UI
open http://localhost:3000
