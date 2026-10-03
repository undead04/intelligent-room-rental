from fastapi import APIRouter
from app.api.v1.endpoints import health, listings, locations, room_types

api_router = APIRouter()
api_router.include_router(health.router, tags=["Health Checks"])
api_router.include_router(listings.router, prefix="/listings", tags=["Listings"])
api_router.include_router(locations.router, prefix="/locations", tags=["Locations"])
api_router.include_router(room_types.router, prefix="/room-types", tags=["Room Types"])
