import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

# QuickBooks Configuration
QB_CONFIG = {
    'client_id': os.getenv('QB_CLIENT_ID'),
    'client_secret': os.getenv('QB_CLIENT_SECRET'),
    'redirect_uri': os.getenv('QB_REDIRECT_URI', 'http://localhost:5001/callback'),
    'environment': os.getenv('QB_ENVIRONMENT', 'sandbox')
}

# Add checks for required QuickBooks config
if not QB_CONFIG['client_id']:
    raise ValueError("Missing QB_CLIENT_ID environment variable.")
if not QB_CONFIG['client_secret']:
    raise ValueError("Missing QB_CLIENT_SECRET environment variable.")

# Stripe Configuration
STRIPE_PUBLIC_KEY = os.getenv('STRIPE_PUBLIC_KEY')
STRIPE_SECRET_KEY = os.getenv('STRIPE_SECRET_KEY')
STRIPE_WEBHOOK_SECRET = os.getenv('STRIPE_WEBHOOK_SECRET')

# Add checks for required Stripe config
if not STRIPE_SECRET_KEY:
    raise ValueError("Missing STRIPE_SECRET_KEY environment variable.")
if not STRIPE_WEBHOOK_SECRET:
    raise ValueError("Missing STRIPE_WEBHOOK_SECRET environment variable.")

# Supabase Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Add checks for required Supabase config
if not SUPABASE_URL:
    raise ValueError("Missing SUPABASE_URL environment variable.")
if not SUPABASE_KEY:
    raise ValueError("Missing SUPABASE_KEY environment variable.")

# Application Base URL (for redirects, etc.)
BASE_URL = os.getenv('BASE_URL', 'http://localhost:5001') # Default for local dev

# Initialize Supabase client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Database Models
class User:
    def __init__(self, id: str, email: str, stripe_customer_id: str = None):
        self.id = id
        self.email = email
        self.stripe_customer_id = stripe_customer_id

    @staticmethod
    def from_dict(data: dict):
        return User(
            id=data.get('id'),
            email=data.get('email'),
            stripe_customer_id=data.get('stripe_customer_id')
        )

    def to_dict(self):
        return {
            'id': self.id,
            'email': self.email,
            'stripe_customer_id': self.stripe_customer_id
        }

class DeleteCredits:
    def __init__(self, user_id: str, credits: int, last_reset: str):
        self.user_id = user_id
        self.credits = credits
        self.last_reset = last_reset

    @staticmethod
    def from_dict(data: dict):
        return DeleteCredits(
            user_id=data.get('user_id'),
            credits=data.get('credits'),
            last_reset=data.get('last_reset')
        )

    def to_dict(self):
        return {
            'user_id': self.user_id,
            'credits': self.credits,
            'last_reset': self.last_reset
        } 