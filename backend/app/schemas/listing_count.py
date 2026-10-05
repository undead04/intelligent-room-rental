from pydantic import BaseModel


class ListingCountResponse(BaseModel):
    total_listings: int
