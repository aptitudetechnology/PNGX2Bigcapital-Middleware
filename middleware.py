#!/usr/bin/env python3
"""
Middleware for Bigcapital and Paperless-NGX Integration
Automates the import of financial documents from Paperless-NGX into Bigcapital
"""

import json
import logging
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import requests
from dataclasses import dataclass
import configparser


@dataclass
class DocumentData:
    """Data structure for extracted document information"""
    doc_id: int
    doc_type: str  # 'invoice' or 'receipt'
    number: Optional[str] = None
    date: Optional[str] = None
    due_date: Optional[str] = None
    customer_name: Optional[str] = None
    amount: Optional[float] = None
    tax_amount: Optional[float] = None
    subtotal: Optional[float] = None
    line_items: List[Dict] = None
    payment_method: Optional[str] = None
    
    def __post_init__(self):
        if self.line_items is None:
            self.line_items = []


class PaperlessNGXClient:
    """Client for interacting with Paperless-NGX API"""
    
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'Token {token}',
            'Content-Type': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def get_documents(self, tags: List[str] = None, correspondents: List[str] = None) -> List[Dict]:
        """Fetch documents from Paperless-NGX based on filters"""
        url = f"{self.base_url}/api/documents/"
        params = {}
        
        if tags:
            # Convert tag names to IDs if needed
            tag_ids = self._get_tag_ids(tags)
            if tag_ids:
                params['tags__id__in'] = ','.join(map(str, tag_ids))
        
        if correspondents:
            correspondent_ids = self._get_correspondent_ids(correspondents)
            if correspondent_ids:
                params['correspondent__id__in'] = ','.join(map(str, correspondent_ids))
        
        response = self.session.get(url, params=params)
        response.raise_for_status()
        return response.json().get('results', [])
    
    def get_document_content(self, doc_id: int) -> str:
        """Get the OCR content of a document"""
        url = f"{self.base_url}/api/documents/{doc_id}/"
        response = self.session.get(url)
        response.raise_for_status()
        return response.json().get('content', '')
    
    def add_tag_to_document(self, doc_id: int, tag_name: str):
        """Add a tag to a document (e.g., for marking as processed or error)"""
        # First get or create the tag
        tag_id = self._get_or_create_tag(tag_name)
        
        # Get current document tags
        doc_url = f"{self.base_url}/api/documents/{doc_id}/"
        response = self.session.get(doc_url)
        response.raise_for_status()
        doc_data = response.json()
        
        # Add new tag if not already present
        current_tags = doc_data.get('tags', [])
        if tag_id not in current_tags:
            current_tags.append(tag_id)
            
            # Update document
            update_data = {'tags': current_tags}
            response = self.session.patch(doc_url, json=update_data)
            response.raise_for_status()
    
    def _get_tag_ids(self, tag_names: List[str]) -> List[int]:
        """Convert tag names to IDs"""
        url = f"{self.base_url}/api/tags/"
        response = self.session.get(url)
        response.raise_for_status()
        
        tags = response.json().get('results', [])
        tag_map = {tag['name'].lower(): tag['id'] for tag in tags}
        
        return [tag_map[name.lower()] for name in tag_names if name.lower() in tag_map]
    
    def _get_correspondent_ids(self, correspondent_names: List[str]) -> List[int]:
        """Convert correspondent names to IDs"""
        url = f"{self.base_url}/api/correspondents/"
        response = self.session.get(url)
        response.raise_for_status()
        
        correspondents = response.json().get('results', [])
        correspondent_map = {c['name'].lower(): c['id'] for c in correspondents}
        
        return [correspondent_map[name.lower()] for name in correspondent_names 
                if name.lower() in correspondent_map]
    
    def _get_or_create_tag(self, tag_name: str) -> int:
        """Get existing tag ID or create new tag"""
        url = f"{self.base_url}/api/tags/"
        response = self.session.get(url, params={'name': tag_name})
        response.raise_for_status()
        
        results = response.json().get('results', [])
        if results:
            return results[0]['id']
        
        # Create new tag
        create_data = {'name': tag_name}
        response = self.session.post(url, json=create_data)
        response.raise_for_status()
        return response.json()['id']


class BigcapitalClient:
    """Client for interacting with Bigcapital API"""
    
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip('/')
        self.headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def find_customer(self, name: str) -> Optional[Dict]:
        """Find customer by name"""
        url = f"{self.base_url}/api/customers"
        response = self.session.get(url, params={'search': name})
        response.raise_for_status()
        
        customers = response.json().get('data', [])
        for customer in customers:
            if customer['name'].lower() == name.lower():
                return customer
        return None
    
    def create_customer(self, name: str, email: str = None) -> Dict:
        """Create a new customer"""
        url = f"{self.base_url}/api/customers"
        data = {
            'name': name,
            'email': email or f"{name.lower().replace(' ', '')}@example.com"
        }
        response = self.session.post(url, json=data)
        response.raise_for_status()
        return response.json()
    
    def create_invoice(self, invoice_data: DocumentData) -> Dict:
        """Create an invoice in Bigcapital"""
        # Find or create customer
        customer = self.find_customer(invoice_data.customer_name)
        if not customer:
            customer = self.create_customer(invoice_data.customer_name)
        
        # Prepare invoice payload
        payload = {
            'customer_id': customer['id'],
            'invoice_date': invoice_data.date,
            'due_date': invoice_data.due_date,
            'invoice_number': invoice_data.number,
            'entries': []
        }
        
        # Add line items or default entry
        if invoice_data.line_items:
            for item in invoice_data.line_items:
                payload['entries'].append({
                    'description': item.get('description', 'Service'),
                    'quantity': item.get('quantity', 1),
                    'rate': item.get('rate', invoice_data.amount or 0)
                })
        else:
            # Default single line item
            payload['entries'].append({
                'description': 'Imported from Paperless-NGX',
                'quantity': 1,
                'rate': invoice_data.amount or 0
            })
        
        url = f"{self.base_url}/api/invoices"
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()
    
    def create_receipt(self, receipt_data: DocumentData) -> Dict:
        """Create a receipt in Bigcapital"""
        # Find or create customer
        customer = self.find_customer(receipt_data.customer_name)
        if not customer:
            customer = self.create_customer(receipt_data.customer_name)
        
        payload = {
            'receipt_number': receipt_data.number,
            'customer_id': customer['id'],
            'payment_date': receipt_data.date,
            'amount': receipt_data.amount,
            'payment_method': receipt_data.payment_method or 'Cash'
        }
        
        url = f"{self.base_url}/api/receipts"
        response = self.session.post(url, json=payload)
        response.raise_for_status()
        return response.json()


class DocumentProcessor:
    """Process and extract data from documents"""
    
    @staticmethod
    def extract_invoice_data(content: str, doc_id: int) -> DocumentData:
        """Extract invoice data from OCR content"""
        data = DocumentData(doc_id=doc_id, doc_type='invoice')
        
        # Extract invoice number
        invoice_patterns = [
            r'invoice\s*#?\s*:?\s*([A-Z0-9\-]+)',
            r'inv\s*#?\s*:?\s*([A-Z0-9\-]+)',
            r'#\s*([A-Z0-9\-]+)'
        ]
        for pattern in invoice_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.number = match.group(1)
                break
        
        # Extract dates
        date_patterns = [
            r'date\s*:?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})'
        ]
        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            dates.extend(matches)
        
        if dates:
            data.date = DocumentProcessor._normalize_date(dates[0])
            if len(dates) > 1:
                data.due_date = DocumentProcessor._normalize_date(dates[1])
        
        # Extract customer name (look for "to:", "bill to:", etc.)
        customer_patterns = [
            r'(?:bill\s+to|to)\s*:?\s*([A-Za-z\s]+)',
            r'customer\s*:?\s*([A-Za-z\s]+)'
        ]
        for pattern in customer_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.customer_name = match.group(1).strip()
                break
        
        # Extract amounts
        amount_patterns = [
            r'total\s*:?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'amount\s*:?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)'
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                data.amount = float(amount_str)
                break
        
        return data
    
    @staticmethod
    def extract_receipt_data(content: str, doc_id: int) -> DocumentData:
        """Extract receipt data from OCR content"""
        data = DocumentData(doc_id=doc_id, doc_type='receipt')
        
        # Extract receipt number
        receipt_patterns = [
            r'receipt\s*#?\s*:?\s*([A-Z0-9\-]+)',
            r'rec\s*#?\s*:?\s*([A-Z0-9\-]+)'
        ]
        for pattern in receipt_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.number = match.group(1)
                break
        
        # Extract date
        date_patterns = [
            r'date\s*:?\s*(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})',
            r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})'
        ]
        for pattern in date_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.date = DocumentProcessor._normalize_date(match.group(1))
                break
        
        # Extract payer name
        payer_patterns = [
            r'from\s*:?\s*([A-Za-z\s]+)',
            r'payer\s*:?\s*([A-Za-z\s]+)',
            r'received\s+from\s*:?\s*([A-Za-z\s]+)'
        ]
        for pattern in payer_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.customer_name = match.group(1).strip()
                break
        
        # Extract amount
        amount_patterns = [
            r'amount\s*:?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'total\s*:?\s*\$?(\d+(?:,\d{3})*(?:\.\d{2})?)',
            r'\$(\d+(?:,\d{3})*(?:\.\d{2})?)'
        ]
        for pattern in amount_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(',', '')
                data.amount = float(amount_str)
                break
        
        # Extract payment method
        payment_patterns = [
            r'payment\s+method\s*:?\s*([A-Za-z\s]+)',
            r'paid\s+by\s*:?\s*([A-Za-z\s]+)'
        ]
        for pattern in payment_patterns:
            match = re.search(pattern, content, re.IGNORECASE)
            if match:
                data.payment_method = match.group(1).strip()
                break
        
        return data
    
    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """Normalize date format to YYYY-MM-DD"""
        try:
            # Try different date formats
            formats = ['%m/%d/%Y', '%d/%m/%Y', '%m-%d-%Y', '%d-%m-%Y', 
                      '%m/%d/%y', '%d/%m/%y', '%m-%d-%y', '%d-%m-%y']
            
            for fmt in formats:
                try:
                    dt = datetime.strptime(date_str, fmt)
                    return dt.strftime('%Y-%m-%d')
                except ValueError:
                    continue
            
            # If no format matches, return as-is
            return date_str
        except Exception:
            return date_str


class MiddlewareConfig:
    """Configuration management"""
    
    def __init__(self, config_path: str = 'config.ini'):
        self.config = configparser.ConfigParser()
        self.config_path = config_path
        self.load_config()
    
    def load_config(self):
        """Load configuration from file"""
        if Path(self.config_path).exists():
            self.config.read(self.config_path)
        else:
            self.create_default_config()
    
    def create_default_config(self):
        """Create default configuration file"""
        self.config['paperless'] = {
            'url': 'http://localhost:8000',
            'token': 'your-paperless-token',
            'invoice_tags': 'invoice,bill',
            'receipt_tags': 'receipt',
            'correspondents': ''
        }
        
        self.config['bigcapital'] = {
            'url': 'http://localhost:3000',
            'token': 'your-bigcapital-token',
            'auto_create_customers': 'true',
            'default_due_days': '30'
        }
        
        self.config['processing'] = {
            'processed_tag': 'bc-processed',
            'error_tag': 'bc-error',
            'check_interval': '300'
        }
        
        with open(self.config_path, 'w') as f:
            self.config.write(f)
        
        print(f"Created default config at {self.config_path}. Please update with your settings.")
    
    def get(self, section: str, key: str, fallback=None):
        """Get configuration value"""
        return self.config.get(section, key, fallback=fallback)
    
    def getboolean(self, section: str, key: str, fallback=False):
        """Get boolean configuration value"""
        return self.config.getboolean(section, key, fallback=fallback)
    
    def getint(self, section: str, key: str, fallback=0):
        """Get integer configuration value"""
        return self.config.getint(section, key, fallback=fallback)


class PaperlessBigcapitalMiddleware:
    """Main middleware class"""
    
    def __init__(self, config_path: str = 'config.ini'):
        self.config = MiddlewareConfig(config_path)
        self._setup_logging()
        
        # Initialize clients
        self.paperless = PaperlessNGXClient(
            self.config.get('paperless', 'url'),
            self.config.get('paperless', 'token')
        )
        
        self.bigcapital = BigcapitalClient(
            self.config.get('bigcapital', 'url'),
            self.config.get('bigcapital', 'token')
        )
        
        self.processor = DocumentProcessor()
        
        # Tags for filtering and marking
        self.invoice_tags = [tag.strip() for tag in 
                           self.config.get('paperless', 'invoice_tags', '').split(',') if tag.strip()]
        self.receipt_tags = [tag.strip() for tag in 
                           self.config.get('paperless', 'receipt_tags', '').split(',') if tag.strip()]
        self.processed_tag = self.config.get('processing', 'processed_tag', 'bc-processed')
        self.error_tag = self.config.get('processing', 'error_tag', 'bc-error')
    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('middleware.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def process_documents(self):
        """Main processing function"""
        self.logger.info("Starting document processing...")
        
        try:
            # Process invoices
            if self.invoice_tags:
                invoice_docs = self.paperless.get_documents(tags=self.invoice_tags)
                self.logger.info(f"Found {len(invoice_docs)} potential invoice documents")
                
                for doc in invoice_docs:
                    self._process_document(doc, 'invoice')
            
            # Process receipts
            if self.receipt_tags:
                receipt_docs = self.paperless.get_documents(tags=self.receipt_tags)
                self.logger.info(f"Found {len(receipt_docs)} potential receipt documents")
                
                for doc in receipt_docs:
                    self._process_document(doc, 'receipt')
                    
        except Exception as e:
            self.logger.error(f"Error during document processing: {str(e)}")
    
    def _process_document(self, doc: Dict, doc_type: str):
        """Process a single document"""
        doc_id = doc['id']
        
        # Skip if already processed
        if self._is_document_processed(doc):
            return
        
        try:
            self.logger.info(f"Processing {doc_type} document ID: {doc_id}")
            
            # Get document content
            content = self.paperless.get_document_content(doc_id)
            
            # Extract data based on document type
            if doc_type == 'invoice':
                data = self.processor.extract_invoice_data(content, doc_id)
            else:
                data = self.processor.extract_receipt_data(content, doc_id)
            
            # Validate extracted data
            if not self._validate_document_data(data):
                self.logger.warning(f"Invalid data extracted from document {doc_id}")
                self.paperless.add_tag_to_document(doc_id, self.error_tag)
                return
            
            # Create entry in Bigcapital
            if doc_type == 'invoice':
                result = self.bigcapital.create_invoice(data)
            else:
                result = self.bigcapital.create_receipt(data)
            
            self.logger.info(f"Successfully created {doc_type} in Bigcapital for document {doc_id}")
            
            # Mark as processed
            self.paperless.add_tag_to_document(doc_id, self.processed_tag)
            
        except Exception as e:
            self.logger.error(f"Error processing document {doc_id}: {str(e)}")
            self.paperless.add_tag_to_document(doc_id, self.error_tag)
    
    def _is_document_processed(self, doc: Dict) -> bool:
        """Check if document has already been processed"""
        doc_tags = [tag['name'] for tag in doc.get('tags', [])]
        return self.processed_tag in doc_tags or self.error_tag in doc_tags
    
    def _validate_document_data(self, data: DocumentData) -> bool:
        """Validate extracted document data"""
        if not data.customer_name:
            return False
        if not data.amount or data.amount <= 0:
            return False
        if not data.date:
            return False
        return True
    
    def run_continuously(self):
        """Run the middleware continuously with configurable interval"""
        interval = self.config.getint('processing', 'check_interval', 300)
        self.logger.info(f"Starting continuous processing with {interval}s interval")
        
        while True:
            try:
                self.process_documents()
                self.logger.info(f"Sleeping for {interval} seconds...")
                time.sleep(interval)
            except KeyboardInterrupt:
                self.logger.info("Stopping middleware...")
                break
            except Exception as e:
                self.logger.error(f"Unexpected error: {str(e)}")
                time.sleep(60)  # Wait 1 minute before retrying


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Paperless-NGX to Bigcapital Middleware')
    parser.add_argument('--config', default='config.ini', help='Configuration file path')
    parser.add_argument('--once', action='store_true', help='Run once instead of continuously')
    
    args = parser.parse_args()
    
    middleware = PaperlessBigcapitalMiddleware(args.config)
    
    if args.once:
        middleware.process_documents()
    else:
        middleware.run_continuously()


if __name__ == '__main__':
    main()
