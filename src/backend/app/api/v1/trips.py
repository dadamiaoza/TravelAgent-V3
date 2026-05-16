"""Trip-related API endpoints. Defined incrementally per dev phase."""
from fastapi import APIRouter

router = APIRouter(prefix="/trips", tags=["trips"])

# Endpoints will be added here per phase:
#   POST /trips           - create trip
#   POST /trips/{id}/generate - generate itinerary
#   GET  /trips/{id}       - get trip detail
#   PATCH /itinerary-items/{id} - edit node
#   POST /trips/{id}/sources    - import guide
#   POST /trips/{id}/parse      - parse guide
#   POST /trips/{id}/reoptimize - re-optimize route
#   POST /trips/{id}/fact-check - refresh freshness
