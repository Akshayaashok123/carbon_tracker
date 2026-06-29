import time
import socketio
import requests
import json

# Configuration
SERVER_URL = 'http://127.0.0.1:5000'
SOCKET_URL = SERVER_URL
API_CHATS = f'{SERVER_URL}/api/chats'

# Create Socket.IO client
sio = socketio.Client()

@sio.event
def connect():
    print('Socket.IO client connected')

@sio.event
def disconnect():
    print('Socket.IO client disconnected')

def main():
    try:
        sio.connect(SOCKET_URL)
        # Prepare test payload
        payload = {
            'sender': 'test_user',
            'recipient': 'test_user',
            'text': 'Hello from automated test',
            'timestamp': ''  # server will add timestamp if needed
        }
        # Emit message
        sio.emit('send_message', payload)
        print('Sent test message')
        # Wait for server processing
        time.sleep(2)
        # Fetch chat history via HTTP API
        resp = requests.get(API_CHATS)
        if resp.status_code == 200:
            chats = resp.json()
            # Look for our test message
            found = any(c.get('sender') == 'test_user' and c.get('text') == 'Hello from automated test' for c in chats)
            print('Message present in chat history:', found)
        else:
            print('Failed to fetch chats, status', resp.status_code)
    finally:
        sio.disconnect()

if __name__ == '__main__':
    main()
