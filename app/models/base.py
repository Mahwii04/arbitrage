"""Base models and utilities for database models"""
from datetime import datetime
from app.database import db

class TimestampMixin:
    """Mixin for adding timestamp fields to models"""
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

class JsonMixin:
    """Mixin for adding JSON serialization to models"""
    def to_dict(self):
        """Convert model to dictionary"""
        return {column.key: getattr(self, column.key)
                for column in db.inspect(self.__class__).attrs}