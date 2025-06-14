from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time
import logging
from datetime import datetime
import random

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Global state
middleware_state = {
    'is_running': False,
    'stats': {
        'processed': 0,
        'errors': 0,
        'pending': 0,
        'last_run': None
    },
    'logs': [],
    'documents': [
        {'id': 1234, 'type': 'Invoice', 'customer': 'Acme Corp', 'amount': '$1,250.00', 'status': 'processed', 'date': '2024-12-14'},
        {'id': 1235, 'type': 'Receipt', 'customer': 'Tech Solutions', 'amount': '$850.00', 'status': 'processed', 'date': '2024-12-14'},
        {'id': 1236, 'type': 'Invoice', 'customer': 'Global Inc', 'amount': '$2,100.00', 'status': 'error', 'date': '2024-12-14'},
        {'id': 1237, 'type': 'Receipt', 'customer': 'StartupXYZ', 'amount': '$450.00', 'status': 'pending', 'date': '2024-12-14'}
    ]
}

# Default configuration
default_config = {
    'paperless': {
        'url': 'http://localhost:8000',
        'token': '',
        'invoice_tags': 'invoice,bill,accounts-receivable',
        'receipt_tags': 'receipt,payment'
    },
    'bigcapital': {
        'url': 'http://localhost:3000',
        'token': '',
        'auto_create_customers': True,
        'default_due_days': 30
    },
    'processing': {
        'processed_tag': 'bc-processed',
        'error_tag': 'bc-error',
        'check_interval': 300,
        'log_level': 'INFO'
    }
}

# Load configuration from file or use defaults
def load_config():
    try:
        with open('config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return default_config.copy()

def save_config(config):
    with open('config.json', 'w') as f:
        json.dump(config, f, indent=2)

current_config = load_config()

# Background task to simulate middleware processing
def background_task():
    while True:
        if middleware_state['is_running']:
            # Update stats
            middleware_state['stats']['processed'] += random.randint(0, 2)
            if random.random() > 0.9:
                middleware_state['stats']['errors'] += 1
            middleware_state['stats']['pending'] = random.randint(0, 10)
            middleware_state['stats']['last_run'] = datetime.now().strftime('%H:%M:%S')
            
            # Add new log entry
            log_types = ['INFO', 'WARNING', 'ERROR']
            messages = [
                'Processing document ID: 123',
                'Successfully created invoice in Bigcapital',
                'Document tagged as processed',
                'Failed to extract data from document',
                'API connection successful',
                'Customer created automatically'
            ]
            
            new_log = {
                'timestamp': datetime.now().strftime('%H:%M:%S'),
                'level': random.choice(log_types),
                'message': random.choice(messages),
                'id': int(time.time() * 1000)
            }
            
            middleware_state['logs'].insert(0, new_log)
            if len(middleware_state['logs']) > 50:
                middleware_state['logs'] = middleware_state['logs'][:50]
            
            # Emit updates to connected clients
            socketio.emit('stats_update', middleware_state['stats'])
            socketio.emit('log_update', new_log)
        
        time.sleep(3)

# Start background task
thread = threading.Thread(target=background_task)
thread.daemon = True
thread.start()

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    return jsonify({
        'is_running': middleware_state['is_running'],
        'stats': middleware_state['stats'],
        'services': {
            'paperless': 'connected',
            'bigcapital': 'connected',
            'middleware': 'active' if middleware_state['is_running'] else 'stopped'
        }
    })

@app.route('/api/start', methods=['POST'])
def start_middleware():
    middleware_state['is_running'] = True
    socketio.emit('status_change', {'is_running': True})
    return jsonify({'success': True, 'message': 'Middleware started'})

@app.route('/api/stop', methods=['POST'])
def stop_middleware():
    middleware_state['is_running'] = False
    socketio.emit('status_change', {'is_running': False})
    return jsonify({'success': True, 'message': 'Middleware stopped'})

@app.route('/api/documents')
def get_documents():
    return jsonify(middleware_state['documents'])

@app.route('/api/logs')
def get_logs():
    return jsonify(middleware_state['logs'])

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    global current_config
    
    if request.method == 'GET':
        return jsonify(current_config)
    
    elif request.method == 'POST':
        try:
            new_config = request.json
            current_config = new_config
            save_config(current_config)
            return jsonify({'success': True, 'message': 'Configuration saved'})
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    # Simulate connection test
    time.sleep(1)  # Simulate delay
    return jsonify({'success': True, 'message': 'All connections successful'})

@app.route('/api/export-logs', methods=['GET'])
def export_logs():
    # In a real implementation, this would generate a file
    return jsonify({'success': True, 'message': 'Logs exported successfully'})

@app.route('/api/process-now', methods=['POST'])
def process_now():
    # Trigger immediate processing
    return jsonify({'success': True, 'message': 'Processing started'})

# WebSocket events
@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('status_change', {'is_running': middleware_state['is_running']})
    emit('stats_update', middleware_state['stats'])

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Setup logging
    logging.basicConfig(level=logging.INFO)
    
    print("Starting Paperless-Bigcapital Middleware Web Interface...")
    print("Access the interface at: http://localhost:5000")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
