from fastapi import APIRouter

from app.api.v1.controllers import (
    health_controller,
    listings_controller,
    location_controller,
    room_type_controller,
)

api_router = APIRouter()
api_router.include_router(health_controller.router, tags=["Health Checks"])
api_router.include_router(listings_controller.router, prefix="/listings", tags=["Listings"])
api_router.include_router(location_controller.router, prefix="/locations", tags=["Locations"])
api_router.include_router(room_type_controller.router, prefix="/room-types", tags=["Room Types"])
