"""
Gmail API integration for parsing Zomato/Swiggy food orders.
Extracts meal types from confirmation emails and estimates carbon footprint.
"""

import os
import json
import re
from datetime import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.api_core import retry
from googleapiclient.discovery import build
import base64

# Gmail API scopes
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

# Zomato/Swiggy carbon impact mapping (kg CO₂ per meal)
FOOD_CARBON_ESTIMATES = {
    # Keywords to detect and their estimated CO₂ impact
    'vegan': 0.8, 'salad': 0.9, 'vegetable': 1.0,
    'paneer': 1.8, 'vegetarian': 1.5, 'veg': 1.5,
    'chicken': 2.5, 'fish': 2.3, 'seafood': 2.4,
    'mutton': 4.5, 'lamb': 5.2, 'beef': 5.2,
    'butter chicken': 3.2, 'tandoori': 2.8,
    'biryani': 2.2, 'dal': 1.2, 'curry': 2.0,
    'pizza': 1.8, 'pasta': 1.5, 'burger': 3.0,
    'chaat': 1.5, 'samosa': 1.2, 'dosa': 1.3,
    'thali': 2.0, 'rice': 0.5, 'bread': 0.4,
}

TOKEN_FILE = 'data/gmail_token.json'
CREDENTIALS_FILE = 'data/gmail_credentials.json'

def get_gmail_flow():
    """Create OAuth 2.0 flow for Gmail."""
    return InstalledAppFlow.from_client_secrets_file(
        CREDENTIALS_FILE, SCOPES
    )

def get_gmail_service():
    """Get authenticated Gmail service."""
    creds = None
    
    # Load saved credentials
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        return build('gmail', 'v1', credentials=creds)
    
    if not creds:
        return None
    
    return build('gmail', 'v1', credentials=creds)

def save_credentials(creds):
    """Save credentials to disk."""
    cfg = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': creds.scopes,
    }
    with open(TOKEN_FILE, 'w') as f:
        json.dump(cfg, f)

def get_message_body(service, user_id, msg_id):
    """Extract text body from Gmail message."""
    try:
        message = service.users().messages().get(
            userId=user_id, id=msg_id, format='full'
        ).execute()
        
        headers = message['payload']['headers']
        if 'parts' in message['payload']:
            parts = message['payload']['parts']
            for part in parts:
                if part['mimeType'] == 'text/plain':
                    data = part['body'].get('data', '')
                    if data:
                        return base64.urlsafe_b64decode(data).decode('utf-8')
        else:
            data = message['payload']['body'].get('data', '')
            if data:
                return base64.urlsafe_b64decode(data).decode('utf-8')
    except Exception as e:
        print(f"Error getting message body: {e}")
    
    return ""

def extract_delivery_platform(text):
    """Detect if email is from Zomato or Swiggy."""
    text_lower = text.lower()
    if 'zomato' in text_lower:
        return 'Zomato'
    elif 'swiggy' in text_lower:
        return 'Swiggy'
    return None

def extract_meal_info(text):
    """
    Extract meal details from order confirmation email.
    Returns: (platform, restaurant, meal_list, estimated_carbon)
    """
    platform = extract_delivery_platform(text)
    if not platform:
        return None, None, [], 1.5  # Default if can't detect
    
    text_lower = text.lower()
    restaurant = "Unknown Restaurant"
    meal_list = []
    
    # Try to extract restaurant name
    # Zomato format: "Order from [Restaurant Name]"
    zomato_match = re.search(r'order from ([^\n,]+)', text_lower)
    if zomato_match:
        restaurant = zomato_match.group(1).strip().title()
    
    # Swiggy format: "Order from [Restaurant]"
    swiggy_match = re.search(r'from ([^\n,]+)', text_lower)
    if swiggy_match and platform == 'Swiggy':
        restaurant = swiggy_match.group(1).strip().title()
    
    # Extract items (usually listed with bullet points or numbers)
    item_patterns = [
        r'[-•]\s*([^-•\n]+)',  # Bullet/dash format
        r'(\d+\.\s*[^\n]+)',     # Numbered format
        r'Item:\s*([^\n]+)',      # "Item:" prefix
    ]
    
    for pattern in item_patterns:
        matches = re.findall(pattern, text_lower)
        meal_list.extend([m.strip() for m in matches if m.strip()])
    
    # Remove duplicates and clean
    meal_list = list(set(meal_list))[:5]  # Top 5 items
    
    # Estimate carbon footprint based on detected keywords
    total_carbon = 1.5  # Default base
    detected_items = []
    
    for item in meal_list + [restaurant.lower()]:
        for keyword, carbon_value in FOOD_CARBON_ESTIMATES.items():
            if keyword in item:
                detected_items.append(f"{keyword}: {carbon_value}kg")
                total_carbon = max(total_carbon, carbon_value)
                break
    
    return platform, restaurant, detected_items, total_carbon

def fetch_recent_orders(service, user_id='me', max_results=10):
    """
    Fetch recent Zomato/Swiggy order emails.
    Returns list of (date, platform, restaurant, items, carbon_estimate) tuples
    """
    try:
        # Search for Zomato/Swiggy confirmation emails
        query = 'from:(zomato OR swiggy) subject:(order confirmed OR order confirmation)'
        
        results = service.users().messages().list(
            userId=user_id, q=query, maxResults=max_results
        ).execute()
        
        messages = results.get('messages', [])
        orders = []
        
        for msg in messages:
            msg_id = msg['id']
            
            # Get message details
            full_msg = service.users().messages().get(
                userId=user_id, id=msg_id, format='metadata', 
                metadataHeaders=['Date', 'Subject', 'From']
            ).execute()
            
            headers = {h['name']: h['value'] for h in full_msg['payload']['headers']}
            subject = headers.get('Subject', '')
            date_str = headers.get('Date', '')
            from_addr = headers.get('From', '')
            
            # Get full message body for item extraction
            body = get_message_body(service, user_id, msg_id)
            
            # Extract meal info
            platform, restaurant, items, carbon = extract_meal_info(body)
            
            if platform:
                orders.append({
                    'date': date_str,
                    'platform': platform,
                    'restaurant': restaurant,
                    'items': items,
                    'carbon_estimate': carbon,
                    'subject': subject,
                    'from': from_addr,
                })
        
        return orders
    
    except Exception as e:
        print(f"Error fetching orders: {e}")
        return []

def verify_gmail_connection(service):
    """Verify that Gmail API is properly connected."""
    try:
        if not service:
            return False
        profile = service.users().getProfile(userId='me').execute()
        return 'emailAddress' in profile
    except Exception as e:
        print(f"Gmail verification failed: {e}")
        return False
