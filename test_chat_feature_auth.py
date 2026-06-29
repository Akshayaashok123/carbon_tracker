import time
import socketio
import requests
import json

# Configuration
SERVER_URL = 'http://127.0.0.1:5000'
SOCKET_URL = SERVER_URL
API_DEV_LOGIN = f'{SERVER_URL}/auth/dev-login'
API_CHATS = f'{SERVER_URL}/api/chats'

# Use a requests session to persist cookies
session = requests.Session()

# Dev login (adjust name/department as needed)
login_payload = {
    'name': 'test_user',
    'department': 'Dev'
}
resp = session.post(API_DEV_LOGIN, json=login_payload)
if resp.status_code != 200:
    print('Dev login failed, status', resp.status_code, resp.text)
    exit(1)
print('Dev login successful')

# Extract cookie header for Socket.IO (Flask-Session uses cookie named "session")
cookie_header = '; '.join([f"{c.name}={c.value}" for c in session.cookies])

# Create Socket.IO client with the cookie for authentication
sio = socketio.Client()

@sio.event
def connect():
    print('Socket.IO client connected')

@sio.event
def disconnect():
    print('Socket.IO client disconnected')

def main():
    try:
        # Pass cookie via headers
        sio.connect(SOCKET_URL, headers={'Cookie': cookie_header})
        # Prepare test payload
        payload = {
            'sender': 'test_user',
            'recipient': 'test_user',
            'text': 'Hello from automated auth test',
        }
        # Emit message
        sio.emit('send_message', payload)
        print('Sent test message')
        # Wait for server to process
        time.sleep(2)
        # Fetch chat history via authenticated HTTP request
        resp = session.get(API_CHATS)
        if resp.status_code == 200:
            chats = resp.json()
            found = any(c.get('sender') == 'test_user' and c.get('text') == 'Hello from automated auth test' for c in chats)
            print('Message present in chat history:', found)
        else:
            print('Failed to fetch chats, status', resp.status_code)
    finally:
        sio.disconnect()

if __name__ == '__main__':
    main()
