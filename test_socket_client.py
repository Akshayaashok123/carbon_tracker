import time
import socketio

# Create a Socket.IO client
sio = socketio.Client()

@sio.event
def connect():
    print('Socket.IO client connected')

@sio.event
def disconnect():
    print('Socket.IO client disconnected')

@sio.on('receive_message')
def on_message(data):
    print('Received message:', data)

def main():
    try:
        sio.connect('http://127.0.0.1:5000')
        time.sleep(1)  # wait for connection
        # Emit a test message
        payload = {
            'sender': 'test_user',
            'recipient': 'test_user',
            'message': 'Hello from test client'
        }
        sio.emit('send_message', payload)
        # Wait to receive broadcast
        time.sleep(2)
    finally:
        sio.disconnect()

if __name__ == '__main__':
    main()
