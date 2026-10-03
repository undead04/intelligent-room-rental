from pgvector.sqlalchemy import Vector
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.core.database import Base


class ListingEmbedding(Base):
    __tablename__ = "listing_embeddings"
    __table_args__ = (
        UniqueConstraint("listing_id", "model_name", name="uq_listing_embedding_model"),
    )

    id = Column(Integer, primary_key=True)
    listing_id = Column(
        String(150),
        ForeignKey("listings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    model_name = Column(String(150), nullable=False, index=True)
    dimension = Column(Integer, nullable=False)
    # Keep the dimension open so different embedding models can coexist.
    # The dimension column remains the source of truth for validation.
    vector = Column(Vector(), nullable=False)
    content_hash = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    listing = relationship("Listing", back_populates="embeddings")
