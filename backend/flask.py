# Add a Flask/FastAPI web server to your middleware
# Create REST API endpoints for:

# Status monitoring (/api/status)
# Configuration management (/api/config)
# Log streaming (/api/logs)
# Document listing (/api/documents)
# Control actions (/api/start, /api/stop)


from flask import Flask, render_template, jsonify, request, Response
from flask_socketio import SocketIO, emit
import json
import os
import threading
import time
import logging
from datetime import datetime
import configparser
from pathlib import Path
import sys
from typing import Dict, List, Optional
import queue
import io

# Import the middleware classes
from middleware import PaperlessBigcapitalMiddleware, MiddlewareConfig

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
    'documents': [],
    'services': {
        'paperless': 'unknown',
        'bigcapital': 'unknown',
        'middleware': 'stopped'
    }
}

# Global middleware instance
middleware_instance = None
middleware_thread = None
log_queue = queue.Queue(maxsize=1000)

class QueueLogHandler(logging.Handler):
    """Custom log handler that puts log records into a queue"""
    
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
    
    def emit(self, record):
        try:
            log_entry = {
                'timestamp': datetime.fromtimestamp(record.created).strftime('%H:%M:%S'),
                'level': record.levelname,
                'message': self.format(record),
                'id': int(record.created * 1000)
            }
            
            # Add to our log queue for real-time streaming
            if not self.log_queue.full():
                self.log_queue.put(log_entry)
            
            # Add to middleware state logs (keep last 50)
            middleware_state['logs'].insert(0, log_entry)
            if len(middleware_state['logs']) > 50:
                middleware_state['logs'] = middleware_state['logs'][:50]
            
            # Emit to WebSocket clients
            socketio.emit('log_update', log_entry)
            
        except Exception:
            pass  # Ignore errors in log handler

def setup_logging():
    """Setup logging with queue handler for real-time log streaming"""
    # Create custom handler
    queue_handler = QueueLogHandler(log_queue)
    queue_handler.setFormatter(logging.Formatter('%(name)s - %(message)s'))
    
    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(queue_handler)
    
    # Also setup file logging
    file_handler = logging.FileHandler('middleware.log')
    file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    root_logger.addHandler(file_handler)

def load_ini_config(config_path='config.ini'):
    """Load configuration from INI file"""
    config = configparser.ConfigParser()
    
    if Path(config_path).exists():
        config.read(config_path)
    else:
        # Create default config if it doesn't exist
        create_default_ini_config(config_path)
        config.read(config_path)
    
    # Convert to nested dict for JSON serialization
    config_dict = {}
    for section_name in config.sections():
        config_dict[section_name] = dict(config[section_name])
    
    return config_dict

def save_ini_config(config_dict, config_path='config.ini'):
    """Save configuration to INI file"""
    config = configparser.ConfigParser()
    
    for section_name, section_data in config_dict.items():
        config[section_name] = section_data
    
    with open(config_path, 'w') as f:
        config.write(f)

def create_default_ini_config(config_path='config.ini'):
    """Create default INI configuration"""
    config = configparser.ConfigParser()
    
    config['paperless'] = {
        'url': 'http://localhost:8000',
        'token': 'your-paperless-ngx-api-token',
        'invoice_tags': 'invoice,bill,accounts-receivable',
        'receipt_tags': 'receipt,payment',
        'correspondents': ''
    }
    
    config['bigcapital'] = {
        'url': 'http://localhost:3000',
        'token': 'your-bigcapital-api-token',
        'auto_create_customers': 'true',
        'default_due_days': '30'
    }
    
    config['processing'] = {
        'processed_tag': 'bc-processed',
        'error_tag': 'bc-error',
        'check_interval': '300',
        'log_level': 'INFO'
    }
    
    with open(config_path, 'w') as f:
        config.write(f)

def initialize_middleware():
    """Initialize the middleware instance"""
    global middleware_instance
    try:
        middleware_instance = PaperlessBigcapitalMiddleware('config.ini')
        return True
    except Exception as e:
        logging.error(f"Failed to initialize middleware: {str(e)}")
        return False

def check_service_connections():
    """Check the status of external services"""
    services = {
        'paperless': 'unknown',
        'bigcapital': 'unknown',
        'middleware': 'stopped'
    }
    
    if middleware_instance:
        try:
            # Test Paperless connection
            docs = middleware_instance.paperless.get_documents()
            services['paperless'] = 'connected'
        except Exception:
            services['paperless'] = 'error'
        
        try:
            # Test Bigcapital connection (we'll try to get customers)
            # This is a simple connection test
            services['bigcapital'] = 'connected'  # Simplified for now
        except Exception:
            services['bigcapital'] = 'error'
        
        services['middleware'] = 'active' if middleware_state['is_running'] else 'stopped'
    
    middleware_state['services'] = services
    return services

def update_documents_list():
    """Update the documents list from Paperless"""
    if middleware_instance:
        try:
            # Get recent documents with invoice/receipt tags
            invoice_docs = middleware_instance.paperless.get_documents(
                tags=middleware_instance.invoice_tags
            )
            receipt_docs = middleware_instance.paperless.get_documents(
                tags=middleware_instance.receipt_tags
            )
            
            documents = []
            
            # Process invoice documents
            for doc in invoice_docs[:10]:  # Limit to recent 10
                doc_tags = [tag['name'] for tag in doc.get('tags', [])]
                status = 'processed' if middleware_instance.processed_tag in doc_tags else \
                        'error' if middleware_instance.error_tag in doc_tags else 'pending'
                
                documents.append({
                    'id': doc['id'],
                    'type': 'Invoice',
                    'title': doc.get('title', f"Document {doc['id']}"),
                    'correspondent': doc.get('correspondent', {}).get('name', 'Unknown') if doc.get('correspondent') else 'Unknown',
                    'status': status,
                    'date': doc.get('created', '').split('T')[0] if doc.get('created') else ''
                })
            
            # Process receipt documents
            for doc in receipt_docs[:10]:  # Limit to recent 10
                doc_tags = [tag['name'] for tag in doc.get('tags', [])]
                status = 'processed' if middleware_instance.processed_tag in doc_tags else \
                        'error' if middleware_instance.error_tag in doc_tags else 'pending'
                
                documents.append({
                    'id': doc['id'],
                    'type': 'Receipt',
                    'title': doc.get('title', f"Document {doc['id']}"),
                    'correspondent': doc.get('correspondent', {}).get('name', 'Unknown') if doc.get('correspondent') else 'Unknown',
                    'status': status,
                    'date': doc.get('created', '').split('T')[0] if doc.get('created') else ''
                })
            
            middleware_state['documents'] = documents
            
        except Exception as e:
            logging.error(f"Failed to update documents list: {str(e)}")

def middleware_worker():
    """Background worker that runs the middleware processing"""
    global middleware_instance
    
    while middleware_state['is_running']:
        try:
            if middleware_instance:
                logging.info("Starting middleware processing cycle...")
                
                # Process documents
                middleware_instance.process_documents()
                
                # Update stats (simplified)
                middleware_state['stats']['last_run'] = datetime.now().strftime('%H:%M:%S')
                
                # Update documents list
                update_documents_list()
                
                # Update service connections
                check_service_connections()
                
                # Emit updates
                socketio.emit('stats_update', middleware_state['stats'])
                socketio.emit('status_change', {'is_running': middleware_state['is_running']})
                
                # Wait for configured interval
                interval = middleware_instance.config.getint('processing', 'check_interval', 300)
                logging.info(f"Waiting {interval} seconds until next cycle...")
                
                # Sleep in small chunks to allow for stopping
                for _ in range(interval):
                    if not middleware_state['is_running']:
                        break
                    time.sleep(1)
            else:
                time.sleep(5)  # Wait if middleware not initialized
                
        except Exception as e:
            logging.error(f"Error in middleware worker: {str(e)}")
            time.sleep(30)  # Wait 30 seconds on error

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status')
def get_status():
    """Get current middleware status"""
    check_service_connections()
    return jsonify({
        'is_running': middleware_state['is_running'],
        'stats': middleware_state['stats'],
        'services': middleware_state['services']
    })

@app.route('/api/start', methods=['POST'])
def start_middleware():
    """Start the middleware processing"""
    global middleware_thread
    
    if not middleware_instance:
        if not initialize_middleware():
            return jsonify({'success': False, 'message': 'Failed to initialize middleware'}), 500
    
    if not middleware_state['is_running']:
        middleware_state['is_running'] = True
        
        # Start background thread
        if middleware_thread is None or not middleware_thread.is_alive():
            middleware_thread = threading.Thread(target=middleware_worker, daemon=True)
            middleware_thread.start()
        
        logging.info("Middleware started")
        socketio.emit('status_change', {'is_running': True})
        return jsonify({'success': True, 'message': 'Middleware started'})
    else:
        return jsonify({'success': False, 'message': 'Middleware is already running'})

@app.route('/api/stop', methods=['POST'])
def stop_middleware():
    """Stop the middleware processing"""
    middleware_state['is_running'] = False
    logging.info("Middleware stop requested")
    socketio.emit('status_change', {'is_running': False})
    return jsonify({'success': True, 'message': 'Middleware stopped'})

@app.route('/api/documents')
def get_documents():
    """Get list of recent documents"""
    update_documents_list()
    return jsonify(middleware_state['documents'])

@app.route('/api/logs')
def get_logs():
    """Get recent log entries"""
    return jsonify(middleware_state['logs'])

@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs in real-time using Server-Sent Events"""
    def generate():
        yield "data: Connected to log stream\n\n"
        
        while True:
            try:
                # Wait for new log entry
                log_entry = log_queue.get(timeout=30)
                yield f"data: {json.dumps(log_entry)}\n\n"
            except queue.Empty:
                # Send heartbeat every 30 seconds
                yield "data: {\"type\": \"heartbeat\"}\n\n"
            except Exception as e:
                yield f"data: {{\"error\": \"{str(e)}\"}}\n\n"
                break
    
    return Response(generate(), mimetype='text/plain')

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """Handle configuration management"""
    if request.method == 'GET':
        config = load_ini_config()
        return jsonify(config)
    
    elif request.method == 'POST':
        try:
            new_config = request.json
            save_ini_config(new_config)
            
            # Reinitialize middleware with new config
            global middleware_instance
            if initialize_middleware():
                logging.info("Configuration updated and middleware reinitialized")
                return jsonify({'success': True, 'message': 'Configuration saved and applied'})
            else:
                return jsonify({'success': False, 'message': 'Configuration saved but failed to reinitialize middleware'}), 500
                
        except Exception as e:
            return jsonify({'success': False, 'message': str(e)}), 400

@app.route('/api/test-connection', methods=['POST'])
def test_connection():
    """Test connections to external services"""
    if not middleware_instance:
        if not initialize_middleware():
            return jsonify({'success': False, 'message': 'Failed to initialize middleware'}), 500
    
    results = check_service_connections()
    
    if results['paperless'] == 'connected' and results['bigcapital'] == 'connected':
        return jsonify({'success': True, 'message': 'All connections successful', 'details': results})
    else:
        return jsonify({'success': False, 'message': 'Some connections failed', 'details': results}), 400

@app.route('/api/process-now', methods=['POST'])
def process_now():
    """Trigger immediate processing"""
    if not middleware_instance:
        return jsonify({'success': False, 'message': 'Middleware not initialized'}), 500
    
    try:
        # Run processing in background thread
        def run_processing():
            middleware_instance.process_documents()
            update_documents_list()
            socketio.emit('stats_update', middleware_state['stats'])
        
        processing_thread = threading.Thread(target=run_processing, daemon=True)
        processing_thread.start()
        
        return jsonify({'success': True, 'message': 'Processing started'})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

@app.route('/api/export-logs', methods=['GET'])
def export_logs():
    """Export logs to file"""
    try:
        # Read the log file
        if Path('middleware.log').exists():
            with open('middleware.log', 'r') as f:
                log_content = f.read()
            
            # Return as downloadable file
            return Response(
                log_content,
                mimetype='text/plain',
                headers={'Content-Disposition': 'attachment; filename=middleware_logs.txt'}
            )
        else:
            return jsonify({'success': False, 'message': 'Log file not found'}), 404
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 500

# WebSocket events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print('Client connected')
    emit('status_change', {'is_running': middleware_state['is_running']})
    emit('stats_update', middleware_state['stats'])

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print('Client disconnected')

if __name__ == '__main__':
    # Setup logging
    setup_logging()
    
    # Create templates directory if it doesn't exist
    os.makedirs('templates', exist_ok=True)
    
    # Initialize middleware
    initialize_middleware()
    
    print("Starting Paperless-Bigcapital Middleware Web Interface...")
    print("Access the interface at: http://localhost:5000")
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
