from datetime import datetime
from typing import Optional
from app.database import db

class SubscriptionRequest(db.Model):
    __tablename__ = 'subscription_requests'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tier_requested = db.Column(db.String(50), nullable=False)
    payment_token = db.Column(db.String(20), nullable=False)
    wallet_address = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='payment_reported')
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    verified_at = db.Column(db.DateTime)
    rejected_at = db.Column(db.DateTime)

    user = db.relationship('User', backref='subscription_requests')
    
    def __init__(
        self,
        user_id: int,
        tier_requested: str,
        payment_token: str,
        wallet_address: str,
        status: str = 'payment_reported',
        created_at: Optional[datetime] = None,
        verified_at: Optional[datetime] = None,
        rejected_at: Optional[datetime] = None,
        **kwargs
    ):
        self.user_id = user_id
        self.tier_requested = tier_requested
        self.payment_token = payment_token
        self.wallet_address = wallet_address
        self.status = status
        if created_at:
            self.created_at = created_at
        if verified_at:
            self.verified_at = verified_at
        if rejected_at:
            self.rejected_at = rejected_at
