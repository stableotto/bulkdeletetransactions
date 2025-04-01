import stripe
from config import STRIPE_SECRET_KEY, STRIPE_PUBLIC_KEY, supabase, BASE_URL

stripe.api_key = STRIPE_SECRET_KEY

def create_customer_portal_session(customer_id: str) -> str:
    """Create a Stripe Customer Portal session."""
    try:
        session = stripe.billing_portal.Session.create(
            customer=customer_id,
            return_url=f'{BASE_URL}/',
            configuration=None  # Remove this line if you have a custom configuration
        )
        return session.url
    except stripe.error.InvalidRequestError as e:
        print(f"Error creating portal session: {str(e)}")
        if "customer" in str(e):
            # Customer doesn't exist or isn't valid
            return '/pricing'  # Redirect to pricing page instead
        raise

def create_checkout_session(price_id: str, customer_id: str = None, user_id: str = None) -> str:
    """Create a Stripe Checkout session."""
    try:
        session_data = {
            'payment_method_types': ['card'],
            'line_items': [{
                'price': price_id,
                'quantity': 1,
            }],
            'mode': 'subscription',
            'success_url': f'{BASE_URL}/success?session_id={{CHECKOUT_SESSION_ID}}',
            'cancel_url': f'{BASE_URL}/pricing',
            'client_reference_id': user_id,  # Add the user_id here
        }

        if customer_id:
            session_data['customer'] = customer_id
        
        print(f"Creating checkout session with data: {session_data}")
        session = stripe.checkout.Session.create(**session_data)
        print(f"Created checkout session: {session}")
        return session.url
    except Exception as e:
        print(f"Error creating checkout session: {str(e)}")
        raise

def handle_successful_payment(session_id: str):
    """Handle a successful payment by updating user subscription status."""
    try:
        print(f"Starting handle_successful_payment with session_id: {session_id}")
        session = stripe.checkout.Session.retrieve(
            session_id,
            expand=['subscription', 'customer']
        )
        print(f"Retrieved session data: {session}")
        customer_id = session.customer
        print(f"Customer ID: {customer_id}")
        
        # Get the user associated with this customer
        user_data = supabase.table('users').select('id').eq('stripe_customer_id', customer_id).execute()
        print(f"Found user data: {user_data.data}")
        
        if not user_data.data:
            print("No user found, checking if we need to create/update user")
            # Try to find user by session user_id
            user_id = session.get('client_reference_id')  # We'll add this in checkout session creation
            if user_id:
                # Update user with new stripe customer id
                supabase.table('users').update({
                    'stripe_customer_id': customer_id
                }).eq('id', user_id).execute()
            else:
                print("No user ID found in session")
                return False
        else:
            user_id = user_data.data[0]['id']
        
        print(f"Working with user_id: {user_id}")
        
        # For subscriptions, we need to get the subscription ID
        if hasattr(session, 'subscription') and session.subscription:
            print(f"Found subscription in session: {session.subscription}")
            subscription_data = {
                'user_id': user_id,
                'stripe_customer_id': customer_id,
                'stripe_subscription_id': session.subscription,
                'plan_type': 'monthly',  # TODO: Update this based on Price ID or Subscription details if multiple plans exist
                'status': 'active'
            }
            
            print(f"Attempting to save subscription data: {subscription_data}")
            result = supabase.table('subscriptions').upsert(subscription_data).execute()
            print(f"Supabase insert result: {result}")
        else:
            print("No subscription found in session")
        
        return True
    except Exception as e:
        print(f"Error in handle_successful_payment: {str(e)}")
        print(f"Full error details: {type(e).__name__}")
        return False 