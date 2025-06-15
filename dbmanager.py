#!/usr/bin/env python3
"""
Database manager utility for the Paperless-Bigcapital middleware.
Provides database connection management and common operations.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from contextlib import contextmanager
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import ThreadedConnectionPool
import configparser

logger = logging.getLogger(__name__)

class DatabaseManager:
    """Manages PostgreSQL database connections and operations."""
    
    def __init__(self, config_path: str = None):
        """Initialize database manager with configuration."""
        self.pool = None
        self.config = self._load_config(config_path)
        self._initialize_pool()
    
    def _load_config(self, config_path: str = None) -> configparser.ConfigParser:
        """Load database configuration from config file or environment variables."""
        config = configparser.ConfigParser()
        
        if config_path and os.path.exists(config_path):
            config.read(config_path)
        
        # Override with environment variables if they exist
        db_config = {
            'host': os.getenv('DB_HOST', config.get('database', 'host', fallback='localhost')),
            'port': int(os.getenv('DB_PORT', config.get('database', 'port', fallback='5432'))),
            'name': os.getenv('DB_NAME', config.get('database', 'name', fallback='middleware_db')),
            'user': os.getenv('DB_USER', config.get('database', 'user', fallback='middleware_user')),
            'password': os.getenv('DB_PASSWORD', config.get('database', 'password', fallback='middleware_password')),
            'pool_size': int(os.getenv('DB_POOL_SIZE', config.get('database', 'pool_size', fallback='5'))),
            'max_overflow': int(os.getenv('DB_MAX_OVERFLOW', config.get('database', 'max_overflow', fallback='10'))),
            'pool_timeout': int(os.getenv('DB_POOL_TIMEOUT', config.get('database', 'pool_timeout', fallback='30'))),
            'pool_recycle': int(os.getenv('DB_POOL_RECYCLE', config.get('database', 'pool_recycle', fallback='3600')))
        }
        
        # Update config object
        if not config.has_section('database'):
            config.add_section('database')
        
        for key, value in db_config.items():
            config.set('database', key, str(value))
        
        return config
    
    def _initialize_pool(self):
        """Initialize the connection pool."""
        try:
            db_config = self.config['database']
            
            self.pool = ThreadedConnectionPool(
                minconn=1,
                maxconn=int(db_config['pool_size']) + int(db_config['max_overflow']),
                host=db_config['host'],
                port=int(db_config['port']),
                database=db_config['name'],
                user=db_config['user'],
                password=db_config['password'],
                cursor_factory=RealDictCursor
            )
            
            logger.info("Database connection pool initialized successfully")
            
            # Test connection
            with self.get_connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute("SELECT 1")
                    result = cursor.fetchone()
                    logger.info("Database connection test successful")
                    
        except Exception as e:
            logger.error(f"Failed to initialize database connection pool: {e}")
            raise
    
    @contextmanager
    def get_connection(self):
        """Get a database connection from the pool."""
        conn = None
        try:
            conn = self.pool.getconn()
            yield conn
        finally:
            if conn:
                self.pool.putconn(conn)
    
    def execute_query(self, query: str, params: tuple = None) -> List[Dict[str, Any]]:
        """Execute a SELECT query and return results."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                return cursor.fetchall()
    
    def execute_non_query(self, query: str, params: tuple = None) -> int:
        """Execute an INSERT, UPDATE, or DELETE query."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, params)
                conn.commit()
                return cursor.rowcount
    
    def execute_many(self, query: str, params_list: List[tuple]) -> int:
        """Execute a query multiple times with different parameters."""
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.executemany(query, params_list)
                conn.commit()
                return cursor.rowcount
    
    def insert_document(self, document_data: Dict[str, Any]) -> int:
        """Insert a document record and return the ID."""
        query = """
        INSERT INTO documents (
            paperless_id, title, correspondent, document_type, tags, 
            created_date, modified_date, added_date, file_name, 
            download_url, thumbnail_url, content, status
        ) VALUES (
            %(paperless_id)s, %(title)s, %(correspondent)s, %(document_type)s, %(tags)s,
            %(created_date)s, %(modified_date)s, %(added_date)s, %(file_name)s,
            %(download_url)s, %(thumbnail_url)s, %(content)s, %(status)s
        ) RETURNING id
        """
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, document_data)
                conn.commit()
                return cursor.fetchone()['id']
    
    def insert_extracted_data(self, document_id: int, extracted_data: Dict[str, Any]) -> int:
        """Insert extracted data and return the ID."""
        query = """
        INSERT INTO extracted_data (
            document_id, vendor_name, vendor_address, vendor_phone, vendor_email,
            invoice_number, invoice_date, due_date, total_amount, tax_amount,
            subtotal_amount, currency, payment_terms, raw_data, confidence_score
        ) VALUES (
            %(document_id)s, %(vendor_name)s, %(vendor_address)s, %(vendor_phone)s, %(vendor_email)s,
            %(invoice_number)s, %(invoice_date)s, %(due_date)s, %(total_amount)s, %(tax_amount)s,
            %(subtotal_amount)s, %(currency)s, %(payment_terms)s, %(raw_data)s, %(confidence_score)s
        ) RETURNING id
        """
        
        extracted_data['document_id'] = document_id
        
        with self.get_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, extracted_data)
                conn.commit()
                return cursor.fetchone()['id']
    
    def insert_line_items(self, extracted_data_id: int, line_items: List[Dict[str, Any]]) -> int:
        """Insert line items for an extracted data record."""
        if not line_items:
            return 0
        
        query = """
        INSERT INTO line_items (
            extracted_data_id, item_description, quantity, unit_price, 
            line_total, tax_rate, item_code
        ) VALUES (
            %(extracted_data_id)s, %(item_description)s, %(quantity)s, %(unit_price)s,
            %(line_total)s, %(tax_rate)s, %(item_code)s
        )
        """
        
        # Add extracted_data_id to each line item
        for item in line_items:
            item['extracted_data_id'] = extracted_data_id
        
        return self.execute_many(query, [tuple(item.values()) for item in line_items])
    
    def update_document_status(self, document_id: int, status: str, error_message: str = None):
        """Update document processing status."""
        query = """
        UPDATE documents 
        SET status = %s, error_message = %s, processed_date = CURRENT_TIMESTAMP
        WHERE id = %s
        """
        
        self.execute_non_query(query, (status, error_message, document_id))
    
    def get_unprocessed_documents(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get unprocessed documents."""
        query = """
        SELECT * FROM documents 
        WHERE status = 'pending' 
        ORDER BY added_date ASC 
        LIMIT %s
        """
        
        return self.execute_query(query, (limit,))
    
    def get_document_by_paperless_id(self, paperless_id: int) -> Optional[Dict[str, Any]]:
        """Get document by Paperless-NGX ID."""
        query = "SELECT * FROM documents WHERE paperless_id = %s"
        results = self.execute_query(query, (paperless_id,))
        return results[0] if results else None
    
    def get_processing_stats(self) -> Dict[str, int]:
        """Get processing statistics."""
        query = """
        SELECT 
            status,
            COUNT(*) as count
        FROM documents 
        GROUP BY status
        """
        
        results = self.execute_query(query)
        return {row['status']: row['count'] for row in results}
    
    def close(self):
        """Close the connection pool."""
        if self.pool:
            self.pool.closeall()
            logger.info("Database connection pool closed")

# Singleton instance
_db_manager = None

def get_db_manager(config_path: str = None) -> DatabaseManager:
    """Get the singleton database manager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(config_path)
    return _db_manager

if __name__ == "__main__":
    # Test the database manager
    logging.basicConfig(level=logging.INFO)
    
    try:
        db = get_db_manager()
        stats = db.get_processing_stats()
        print(f"Processing stats: {stats}")
        
        unprocessed = db.get_unprocessed_documents(limit=5)
        print(f"Unprocessed documents: {len(unprocessed)}")
        
    except Exception as e:
        logger.error(f"Database test failed: {e}")
    finally:
        if _db_manager:
            _db_manager.close()
