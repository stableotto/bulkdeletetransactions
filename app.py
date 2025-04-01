from flask import Flask, request, redirect, render_template, jsonify, session, url_for
import requests
import base64
import os
from config import QB_CONFIG, supabase, User, DeleteCredits, STRIPE_PUBLIC_KEY
from stripe_utils import create_customer_portal_session, create_checkout_session, handle_successful_payment
import secrets
from datetime import timedelta

app = Flask(__name__, static_folder='static', template_folder='templates')

# Debug session configuration
app.config['DEBUG'] = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'

# Secure session configuration
app.secret_key = os.getenv('FLASK_SECRET_KEY')
if not app.secret_key:
    raise ValueError("Missing FLASK_SECRET_KEY environment variable.")

# Configure session based on environment
is_production = os.getenv('FLASK_ENV', 'development') == 'production'
app.config.update(
    SESSION_COOKIE_SECURE=is_production,  # Only require HTTPS in production
    SESSION_COOKIE_HTTPONLY=True,         # Prevent JavaScript access to session cookie
    SESSION_COOKIE_SAMESITE='Lax',        # Protect against CSRF
    PERMANENT_SESSION_LIFETIME=timedelta(hours=24),  # Session expires after 24 hours
    SESSION_COOKIE_NAME='bulkdelete_session',  # Custom session cookie name
    SERVER_NAME='localhost:5001'  # Required for url_for with _external=True
)

@app.before_request
def make_session_permanent():
    session.permanent = True  # Set session to use PERMANENT_SESSION_LIFETIME
    # Debug session info
    if app.config['DEBUG']:
        print(f"Session contents: {dict(session)}")
        print(f"Request cookies: {request.cookies}")

def get_user_credits(user_id: str) -> DeleteCredits:
    """Get user's delete credits from the database."""
    credits_data = supabase.table('delete_credits').select('*').eq('user_id', user_id).execute()
    if not credits_data.data:
        # Initialize credits for new user
        supabase.table('delete_credits').insert({
            'user_id': user_id,
            'credits': 20,
            'last_reset': 'now()'
        }).execute()
        return DeleteCredits(user_id, 20, 'now()')
    return DeleteCredits.from_dict(credits_data.data[0])

def check_and_update_credits(user_id: str, amount: int) -> bool:
    """Check if user has enough credits and update them if they do."""
    # First check if user has an active subscription
    subscription_data = supabase.table('subscriptions').select('*').eq('user_id', user_id).eq('status', 'active').execute()
    
    # Add debug print
    print(f"Checking subscription for user {user_id}: {subscription_data.data}")
    
    if subscription_data.data:
        print("User has active subscription, allowing delete")
        return True  # User has unlimited deletes
    
    # If no subscription, check credits
    credits = get_user_credits(user_id)
    if credits.credits < amount:
        print(f"User has insufficient credits: {credits.credits}")
        return False
    
    # Update credits
    supabase.table('delete_credits').update({
        'credits': credits.credits - amount
    }).eq('user_id', user_id).execute()
    
    return True

def refresh_access_token():
    current_refresh_token = session.get('refresh_token')
    if not current_refresh_token:
        print("No refresh token found in session.")
        return False

    try:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(
                f"{QB_CONFIG['client_id']}:{QB_CONFIG['client_secret']}".encode()
            ).decode()
        }
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': current_refresh_token
        }
        print(f"Refreshing token with refresh_token from session: {current_refresh_token[:10]}...")
        response = requests.post('https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer', 
                               headers=headers, data=data)
        if response.status_code != 200:
            error_msg = f"Token refresh failed: {response.status_code} - {response.text}"
            print(error_msg)
            return False
        
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']
        print(f"Stored new access token in session: {session['access_token'][:10]}...")
        return True
    except Exception as e:
        print(f"Error refreshing token: {e}")
        return False

@app.route('/')
def index():
    user_id = session.get('user_id')
    if not user_id:
        return render_template('index.html', authenticated=False)
    
    credits = get_user_credits(user_id)
    subscription_data = supabase.table('subscriptions').select('*').eq('user_id', user_id).eq('status', 'active').execute()
    has_subscription = bool(subscription_data.data)
    
    return render_template('index.html', 
                         authenticated=True, 
                         credits=credits.credits,
                         has_subscription=has_subscription,
                         stripe_public_key=STRIPE_PUBLIC_KEY)

@app.route('/pricing')
def pricing():
    return render_template('pricing.html', 
                         stripe_public_key=STRIPE_PUBLIC_KEY,
                         monthly_price_id=os.getenv('STRIPE_PRICE_MONTHLY'),
                         annual_price_id=os.getenv('STRIPE_PRICE_ANNUAL'))

@app.route('/create-checkout-session', methods=['POST'])
def create_checkout():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    price_id = request.json.get('price_id')
    if not price_id:
        return jsonify({'error': 'No price ID provided'}), 400
    
    # Get user's Stripe customer ID
    user_data = supabase.table('users').select('stripe_customer_id').eq('id', user_id).execute()
    customer_id = user_data.data[0].get('stripe_customer_id') if user_data.data else None
    
    try:
        checkout_url = create_checkout_session(price_id, customer_id, user_id)
        return jsonify({'url': checkout_url})
    except Exception as e:
        print(f"Error in create_checkout: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/create-portal-session', methods=['POST'])
def create_portal():
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'error': 'Not authenticated'}), 401
    
    user_data = supabase.table('users').select('stripe_customer_id').eq('id', user_id).execute()
    if not user_data.data or not user_data.data[0].get('stripe_customer_id'):
        return jsonify({'error': 'No Stripe customer found'}), 400
    
    portal_url = create_customer_portal_session(user_data.data[0]['stripe_customer_id'])
    return jsonify({'url': portal_url})

@app.route('/success')
def success():
    session_id = request.args.get('session_id')
    if not session_id:
        return redirect('/')
    
    if handle_successful_payment(session_id):
        return render_template('success.html')
    return redirect('/')

@app.route('/webhook', methods=['POST'])
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET
        )
    except ValueError as e:
        return 'Invalid payload', 400
    except stripe.error.SignatureVerificationError as e:
        return 'Invalid signature', 400
    
    if event['type'] == 'checkout.session.completed':
        session_id = event['data']['object']['id']
        handle_successful_payment(session_id)
    
    return '', 200

@app.route('/auth')
def auth():
    try:
        # Clear any existing OAuth state
        session.pop('oauth_state', None)
        
        # Generate new OAuth state
        oauth_state = secrets.token_urlsafe(16)
        session['oauth_state'] = oauth_state
        
        # Force session to be saved
        session.modified = True
        
        # Debug session after setting state
        if app.config['DEBUG']:
            print(f"Session after setting oauth_state: {dict(session)}")
            print(f"Cookie Settings: SECURE={app.config['SESSION_COOKIE_SECURE']}, HTTPONLY={app.config['SESSION_COOKIE_HTTPONLY']}, SAMESITE={app.config['SESSION_COOKIE_SAMESITE']}")
        
        # Verify state was stored
        if 'oauth_state' not in session:
            print("Warning: OAuth state not stored in session")
            return "Session storage failed", 500
        
        print(f"Generated and stored OAuth state: {oauth_state}")
        
        # Use url_for to generate the callback URL
        callback_url = url_for('callback', _external=True)
        
        auth_uri = (
            f"https://appcenter.intuit.com/connect/oauth2?"
            f"client_id={QB_CONFIG['client_id']}&response_type=code&"
            f"scope=com.intuit.quickbooks.accounting&"
            f"redirect_uri={callback_url}&state={oauth_state}"
        )
        print(f"Redirecting to auth URI with state: {oauth_state}")
        
        response = redirect(auth_uri)
        # Debug response
        if app.config['DEBUG']:
            print(f"Response headers: {dict(response.headers)}")
        return response
        
    except Exception as e:
        print(f"Error in /auth: {str(e)}")
        return "Authentication initialization failed", 500

@app.route('/callback')
def callback():
    print("Reached /callback endpoint")
    
    if app.config['DEBUG']:
        print(f"Incoming request cookies: {request.cookies}")
        print(f"Current session: {dict(session)}")
    
    # Get callback parameters
    auth_code = request.args.get('code')
    received_realm_id = request.args.get('realmId')
    received_state = request.args.get('state')
    
    print(f"Callback received - state: {received_state}, code: {auth_code}, realmId: {received_realm_id}")
    
    # Verify we have a session
    if not session:
        print("Error: No session found in callback")
        return "Session error. Please try again.", 500
    
    # Get and verify OAuth state
    expected_state = session.get('oauth_state')
    print(f"Session state check - Expected: {expected_state}, Received: {received_state}")
    
    if not expected_state:
        print("Error: No oauth_state found in session")
        print("Current session data:", dict(session))
        return "Session expired. Please try again.", 401
    
    if expected_state != received_state:
        print(f"State mismatch - Expected: {expected_state}, Received: {received_state}")
        return "Invalid state parameter. Please try again.", 403
    
    # Clear the oauth_state after successful verification
    session.pop('oauth_state', None)
    
    if not auth_code:
        return "No authorization code received", 400

    try:
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(
                f"{QB_CONFIG['client_id']}:{QB_CONFIG['client_secret']}".encode()
            ).decode()
        }
        data = {
            'grant_type': 'authorization_code',
            'code': auth_code,
            'redirect_uri': QB_CONFIG['redirect_uri']
        }
        response = requests.post('https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer', 
                               headers=headers, data=data)
        if response.status_code != 200:
            error_msg = f"Token exchange failed: {response.status_code} - {response.text}"
            print(error_msg)
            return error_msg, 500
        
        token_data = response.json()
        session['access_token'] = token_data['access_token']
        session['refresh_token'] = token_data['refresh_token']
        session['realm_id'] = received_realm_id
        
        # Create or update user in Supabase
        user_data = {
            'id': received_realm_id,
            'email': None,
            'stripe_customer_id': None
        }
        supabase.table('users').upsert(user_data).execute()
        
        # Initialize user's credits if they don't exist
        credits_data = supabase.table('delete_credits').select('*').eq('user_id', received_realm_id).execute()
        if not credits_data.data:
            supabase.table('delete_credits').insert({
                'user_id': received_realm_id,
                'credits': 20,
                'last_reset': 'now()'
            }).execute()
        
        # Store the user ID in the session
        session['user_id'] = received_realm_id
        
        print(f"Stored tokens and realm_id in session. Access token: {session['access_token'][:10]}...")
        return redirect('http://localhost:5001/', code=302)
    except Exception as e:
        print(f"Unexpected error in callback: {e}")
        return "Authentication failed due to an unexpected error", 500

@app.route('/check-auth', methods=['GET'])
def check_auth():
    access_token_in_session = session.get('access_token')
    realm_id_in_session = session.get('realm_id')
    print(f"Checking auth from session: token={bool(access_token_in_session)}, realm_id={bool(realm_id_in_session)}")
    if access_token_in_session and realm_id_in_session:
        return jsonify({'authenticated': True}), 200
    else:
        return jsonify({'authenticated': False}), 401

@app.route('/api/qb', methods=['POST'])
def qb_api():
    if 'access_token' not in session or 'realm_id' not in session:
        return jsonify({'error': 'Not authenticated or session expired'}), 401

    current_access_token = session['access_token']
    current_realm_id = session['realm_id']
    user_id = session.get('user_id')

    # Validate basic request structure
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Missing request data'}), 400
    
    # Validate required fields
    required_fields = ['action', 'entity_type']
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        return jsonify({'error': f'Missing required fields: {", ".join(missing_fields)}'}), 400
    
    action = data.get('action')
    entity_type = data.get('entity_type')
    entity_id = data.get('entity_id')  # Optional, depends on action
    
    # Validate action type
    valid_actions = ['query', 'read', 'create', 'update', 'delete', 'void']
    if action not in valid_actions:
        return jsonify({'error': f'Invalid action. Must be one of: {", ".join(valid_actions)}'}), 400
    
    # Validate entity type
    valid_entities = ['Invoice', 'Bill', 'Payment', 'Purchase', 'JournalEntry', 'Transfer']
    if entity_type not in valid_entities:
        return jsonify({'error': f'Invalid entity_type. Must be one of: {", ".join(valid_entities)}'}), 400

    # Special validation for actions that require an entity_id
    if action in ['read', 'update', 'delete', 'void'] and not entity_id:
        return jsonify({'error': f'{action} action requires an entity_id'}), 400

    # Check credits for delete/void operations
    if action in ['delete', 'void']:
        if not user_id:
            return jsonify({'error': 'User session required for this operation'}), 401
        
        if not check_and_update_credits(user_id, 1):
            return jsonify({'error': 'Insufficient credits or no active subscription'}), 403

    # Construct the appropriate QuickBooks API endpoint based on action and entity
    if action == 'query':
        api_url = f"https://{QB_CONFIG['environment']}.quickbooks.api.intuit.com/v3/company/{current_realm_id}/query"
        # Sanitize the query to prevent injection
        query = data.get('query', '').strip()
        if not query:
            return jsonify({'error': 'Query action requires a query parameter'}), 400
        payload = {'query': query}
        method = 'POST'
    else:
        # Handle CRUD operations
        api_url = f"https://{QB_CONFIG['environment']}.quickbooks.api.intuit.com/v3/company/{current_realm_id}/{entity_type.lower()}"
        if entity_id:
            api_url = f"{api_url}/{entity_id}"
        
        if action == 'delete':
            api_url = f"{api_url}?operation=delete"
        elif action == 'void':
            api_url = f"{api_url}?operation=void"
        
        payload = data.get('payload', {})
        # Map actions to HTTP methods
        method_map = {
            'read': 'GET',
            'create': 'POST',
            'update': 'POST',  # QuickBooks uses POST for updates with sparse update
            'delete': 'POST',  # QuickBooks uses POST with operation=delete
            'void': 'POST'     # QuickBooks uses POST with operation=void
        }
        method = method_map.get(action, 'POST')

    # Set up headers with proper API version and content type
    headers = {
        'Authorization': f'Bearer {current_access_token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'BulkDeleteTransactions/1.0'  # Identify your application
    }

    try:
        # Make the API request
        response = requests.request(method, api_url, headers=headers, json=payload, timeout=30)
        
        # Handle specific QuickBooks error cases
        if response.status_code != 200:
            qb_error = response.json().get('Fault', {}).get('Error', [{}])[0]
            error_code = qb_error.get('code', '')
            error_message = qb_error.get('Message', '')
            error_detail = qb_error.get('Detail', '')

            # Map common QB error codes to user-friendly messages
            if error_code == '610':
                return jsonify({'error': f'{entity_type} cannot be deleted due to linked transactions'}), 400
            elif 'Object Not Found' in error_message:
                return jsonify({'error': f'{entity_type} not found'}), 404
            elif 'used' in error_detail.lower():
                return jsonify({'error': f'{entity_type} cannot be modified because it is used in other transactions'}), 400
            elif 'reconciled' in error_detail.lower():
                return jsonify({'error': f'{entity_type} cannot be modified because it is reconciled'}), 400
            elif response.status_code == 401:
                # Clear session on authentication failure
                session.clear()
                return jsonify({'error': 'QuickBooks authentication failed. Please re-authenticate.'}), 401
            
            # Generic error response
            return jsonify({
                'error': f'QuickBooks API Error: {error_message}',
                'detail': error_detail,
                'code': error_code
            }), response.status_code

        # Log successful operation
        print(f"Successfully performed {action} on {entity_type}" + (f" {entity_id}" if entity_id else ""))
        
        # Return successful response
        return jsonify(response.json()), 200

    except requests.exceptions.Timeout:
        return jsonify({'error': 'Request to QuickBooks API timed out'}), 504
    except requests.exceptions.ConnectionError:
        return jsonify({'error': 'Could not connect to QuickBooks API'}), 503
    except Exception as e:
        print(f"Unexpected error in /api/qb: {str(e)}")
        return jsonify({'error': 'An unexpected error occurred'}), 500

if __name__ == '__main__':
    # Read debug flag from environment variable, default to False
    debug_mode = os.getenv('FLASK_DEBUG', 'false').lower() == 'true'
    # Use 0.0.0.0 to allow external access and proper URL generation
    app.run(
        host='0.0.0.0',  # Required for proper external URL generation
        port=5001,
        debug=debug_mode
    )