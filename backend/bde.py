import sqlite3
import os
from datetime import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for, send_file
from flask_socketio import SocketIO, emit
import json
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your-secret-key-here'
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database setup
DB_PATH = 'middleware.db'

def init_database():
    """Initialize the SQLite database with required tables"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Documents table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paperless_id INTEGER UNIQUE NOT NULL,
            title TEXT NOT NULL,
            content TEXT,
            created_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            modified_date DATETIME DEFAULT CURRENT_TIMESTAMP,
            document_type TEXT DEFAULT 'invoice',
            customer_name TEXT,
            amount DECIMAL(10,2),
            status TEXT DEFAULT 'pending',
            file_path TEXT,
            file_type TEXT,
            bigcapital_account_code TEXT,
            bigcapital_customer_id INTEGER,
            tags TEXT,
            processed_date DATETIME,
            error_message TEXT
        )
    ''')
    
    # Logs table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            level TEXT NOT NULL,
            message TEXT NOT NULL,
            document_id INTEGER,
            FOREIGN KEY (document_id) REFERENCES documents (id)
        )
    ''')
    
    # Configuration table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuration (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Bigcapital account codes table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS account_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            account_type TEXT NOT NULL,
            is_active BOOLEAN DEFAULT TRUE
        )
    ''')
    
    # Insert sample data if tables are empty
    cursor.execute('SELECT COUNT(*) FROM documents')
    if cursor.fetchone()[0] == 0:
        sample_documents = [
            (1234, 'Invoice - Acme Corp', 'Sample invoice content', 'invoice', 'Acme Corp', 1250.00, 'processed', '/docs/invoice_1234.pdf', 'pdf', '4000', 1),
            (1235, 'Receipt - Tech Solutions', 'Sample receipt content', 'receipt', 'Tech Solutions', 850.00, 'processed', '/docs/receipt_1235.pdf', 'pdf', '1000', 2),
            (1236, 'Invoice - Global Inc', 'Sample invoice content', 'invoice', 'Global Inc', 2100.00, 'error', '/docs/invoice_1236.pdf', 'pdf', None, None),
            (1237, 'Receipt - StartupXYZ', 'Sample receipt content', 'receipt', 'StartupXYZ', 450.00, 'pending', '/docs/receipt_1237.pdf', 'pdf', None, None),
        ]
        
        cursor.executemany('''
            INSERT INTO documents (paperless_id, title, content, document_type, customer_name, amount, status, file_path, file_type, bigcapital_account_code, bigcapital_customer_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_documents)
    
    # Insert sample account codes
    cursor.execute('SELECT COUNT(*) FROM account_codes')
    if cursor.fetchone()[0] == 0:
        sample_accounts = [
            ('1000', 'Cash', 'asset'),
            ('1100', 'Accounts Receivable', 'asset'),
            ('1200', 'Inventory', 'asset'),
            ('2000', 'Accounts Payable', 'liability'),
            ('3000', 'Owner\'s Equity', 'equity'),
            ('4000', 'Sales Revenue', 'revenue'),
            ('4100', 'Service Revenue', 'revenue'),
            ('5000', 'Cost of Goods Sold', 'expense'),
            ('6000', 'Operating Expenses', 'expense'),
            ('6100', 'Office Supplies', 'expense'),
        ]
        
        cursor.executemany('''
            INSERT INTO account_codes (code, name, account_type)
            VALUES (?, ?, ?)
        ''', sample_accounts)
    
    conn.commit()
    conn.close()

# Initialize database on startup
init_database()

@app.route('/')
def index():
    """Serve the main dashboard"""
    return render_template('dashboard.html')

@app.route('/api/documents')
def get_documents():
    """Get all documents for the documents table"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT id, paperless_id, title, document_type, customer_name, 
               amount, status, created_date, file_type
        FROM documents 
        ORDER BY created_date DESC
    ''')
    
    documents = []
    for row in cursor.fetchall():
        documents.append({
            'id': row[0],
            'paperless_id': row[1],
            'title': row[2],
            'type': row[3].title(),
            'customer': row[4] or 'Unknown',
            'amount': f'${row[5]:.2f}' if row[5] else '$0.00',
            'status': row[6],
            'date': row[7][:10] if row[7] else '',
            'file_type': row[8] or 'pdf'
        })
    
    conn.close()
    return jsonify(documents)

@app.route('/document/edit/<int:document_id>')
def edit_document(document_id):
    """Render the document editor page"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get document details
    cursor.execute('''
        SELECT id, paperless_id, title, content, document_type, customer_name,
               amount, status, file_path, file_type, bigcapital_account_code,
               bigcapital_customer_id, tags, created_date, modified_date
        FROM documents WHERE id = ?
    ''', (document_id,))
    
    document = cursor.fetchone()
    if not document:
        return "Document not found", 404
    
    # Get account codes for dropdown
    cursor.execute('SELECT code, name, account_type FROM account_codes WHERE is_active = TRUE ORDER BY code')
    account_codes = cursor.fetchall()
    
    conn.close()
    
    doc_data = {
        'id': document[0],
        'paperless_id': document[1],
        'title': document[2],
        'content': document[3],
        'document_type': document[4],
        'customer_name': document[5],
        'amount': document[6],
        'status': document[7],
        'file_path': document[8],
        'file_type': document[9],
        'bigcapital_account_code': document[10],
        'bigcapital_customer_id': document[11],
        'tags': document[12],
        'created_date': document[13],
        'modified_date': document[14]
    }
    
    return render_template('document_editor.html', document=doc_data, account_codes=account_codes)

@app.route('/api/document/<int:document_id>/save', methods=['POST'])
def save_document(document_id):
    """Save document changes"""
    data = request.json
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        cursor.execute('''
            UPDATE documents 
            SET document_type = ?, customer_name = ?, amount = ?, 
                bigcapital_account_code = ?, bigcapital_customer_id = ?,
                tags = ?, modified_date = CURRENT_TIMESTAMP
            WHERE id = ?
        ''', (
            data.get('document_type'),
            data.get('customer_name'),
            data.get('amount'),
            data.get('bigcapital_account_code'),
            data.get('bigcapital_customer_id'),
            data.get('tags'),
            document_id
        ))
        
        conn.commit()
        
        # Log the update
        cursor.execute('''
            INSERT INTO logs (level, message, document_id)
            VALUES (?, ?, ?)
        ''', ('INFO', f'Document {document_id} updated successfully', document_id))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Document updated successfully'})
        
    except Exception as e:
        conn.rollback()
        conn.close()
        logger.error(f"Error saving document {document_id}: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/document/<int:document_id>/file')
def get_document_file(document_id):
    """Serve document file (PDF/image)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('SELECT file_path, file_type FROM documents WHERE id = ?', (document_id,))
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return "Document not found", 404
    
    file_path, file_type = result
    
    # For demo purposes, we'll return a placeholder response
    # In production, you'd serve the actual file
    if file_type == 'pdf':
        # Return a simple PDF placeholder or redirect to actual file
        return f"PDF file would be served here: {file_path}", 200, {'Content-Type': 'application/pdf'}
    else:
        # Return image placeholder
        return f"Image file would be served here: {file_path}", 200, {'Content-Type': 'image/jpeg'}

@app.route('/api/stats')
def get_stats():
    """Get dashboard statistics"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Get counts by status
    cursor.execute("SELECT status, COUNT(*) FROM documents GROUP BY status")
    status_counts = dict(cursor.fetchall())
    
    # Get today's processed count
    cursor.execute("""
        SELECT COUNT(*) FROM documents 
        WHERE status = 'processed' AND DATE(modified_date) = DATE('now')
    """)
    processed_today = cursor.fetchone()[0]
    
    # Get last run time
    cursor.execute("SELECT MAX(modified_date) FROM documents WHERE status = 'processed'")
    last_run = cursor.fetchone()[0]
    
    conn.close()
    
    return jsonify({
        'processed': processed_today,
        'errors': status_counts.get('error', 0),
        'pending': status_counts.get('pending', 0),
        'lastRun': last_run
    })

@app.route('/api/logs')
def get_logs():
    """Get recent logs"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT timestamp, level, message, document_id
        FROM logs 
        ORDER BY timestamp DESC 
        LIMIT 50
    ''')
    
    logs = []
    for row in cursor.fetchall():
        logs.append({
            'timestamp': row[0],
            'level': row[1],
            'message': row[2],
            'document_id': row[3]
        })
    
    conn.close()
    return jsonify(logs)

#backend document editor

# Socket.IO events
@socketio.on('connect')
def handle_connect():
    emit('service_status', {'running': False})

@socketio.on('toggle_service')
def handle_toggle_service(data):
    # Here you would actually start/stop the service
    # For now, just emit the status back
    emit('service_status', {'running': data['running']}, broadcast=True)

@socketio.on('save_config')
def handle_save_config(data):
    # Save configuration to database
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        config_json = json.dumps(data)
        cursor.execute('''
            INSERT OR REPLACE INTO configuration (key, value)
            VALUES (?, ?)
        ''', ('main_config', config_json))
        
        conn.commit()
        conn.close()
        
        emit('config_saved', {'success': True})
        
    except Exception as e:
        conn.close()
        emit('config_saved', {'success': False, 'error': str(e)})

if __name__ == '__main__':
    # Ensure templates directory exists
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)
