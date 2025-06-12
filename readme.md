# Paperless-NGX to Bigcapital Middleware

A robust middleware solution that automatically imports financial documents (invoices and receipts) from Paperless-NGX into Bigcapital, streamlining your bookkeeping workflow.

## Features

- **Automated Document Processing**: Monitors Paperless-NGX for new invoices and receipts
- **Intelligent Data Extraction**: Uses OCR content to extract key financial data
- **Customer Management**: Automatically creates customers in Bigcapital if they don't exist
- **Error Handling**: Comprehensive error handling with document tagging for failed processes
- **Flexible Configuration**: Easy configuration via INI file
- **Docker Support**: Ready-to-deploy Docker container
- **Logging**: Detailed logging for monitoring and troubleshooting
- **Continuous Processing**: Can run as a service or one-time batch process

## Prerequisites

- Python 3.8+ (if running directly)
- Docker and Docker Compose (if using containerized deployment)
- Access to Paperless-NGX instance with API token
- Access to Bigcapital instance with API token

## Quick Start

### Method 1: Docker Deployment (Recommended)

1. **Clone or download the middleware files**
2. **Configure your settings**:
   ```bash
   cp config.ini.template config.ini
   # Edit config.ini with your API endpoints and tokens
   ```

3. **Build and run with Docker Compose**:
   ```bash
   docker-compose up -d
   ```

### Method 2: Direct Python Installation

1. **Create virtual environment**:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies**:
   ```bash
   pip install requests configparser
   ```

3. **Configure settings**:
   ```bash
   cp config.ini.template config.ini
   # Edit config.ini with your settings
   ```

4. **Run the middleware**:
   ```bash
   # Run once
   python middleware.py --once
   
   # Run continuously
   python middleware.py
   ```

## Configuration

### API Tokens

**Paperless-NGX Token**:
1. Log into your Paperless-NGX instance
2. Go to Settings → API Tokens
3. Create a new token and copy it to your config file

**Bigcapital Token**:
1. Log into your Bigcapital instance
2. Go to Settings → API & Integrations
3. Generate an API token and copy it to your config file

### Document Tagging Strategy

The middleware uses tags to identify and track documents:

**Identification Tags** (configure in `config.ini`):
- `invoice_tags`: Tags that identify invoices (e.g., "invoice", "bill", "accounts-receivable")
- `receipt_tags`: Tags that identify receipts (e.g., "receipt", "payment")

**Processing Tags** (automatically applied):
- `bc-processed`: Applied to successfully processed documents
- `bc-error`: Applied to documents that failed processing

### Example Workflow

1. **Document Upload**: Upload an invoice to Paperless-NGX
2. **Tagging**: Tag the document with "invoice" 
3. **Processing**: Middleware detects the tagged document
4. **Extraction**: OCR content is parsed for invoice data
5. **Import**: Invoice is created in Bigcapital
6. **Marking**: Document is tagged as "bc-processed"

## Data Extraction

The middleware extracts the following data points:

### For Invoices:
- Invoice number
- Invoice date
- Due date
- Customer name
- Line items (description, quantity, rate)
- Total amount
- Tax amount (if present)

### For Receipts:
- Receipt number
- Receipt date
- Payer name
- Payment amount
- Payment method

## Error Handling

Documents that fail processing are tagged with `bc-error` and logged for manual review. Common failure scenarios:

- Missing required data (customer name, amount, date)
- API connection issues
- Invalid data formats
- Customer creation failures

Check the logs (`middleware.log`) for detailed error information.

## Monitoring

### Log Files
- `middleware.log`: Main application log
- Docker logs: `docker-compose logs -f paperless-bigcapital-middleware`

### Health Checks
The Docker container includes health checks. Monitor status with:
```bash
docker-compose ps
```

## Advanced Configuration

### Custom OCR Patterns

You can modify the `DocumentProcessor` class to add custom regex patterns for your specific document formats:

```python
# Example: Add custom invoice number pattern
invoice_patterns = [
    r'invoice\s*#?\s*:?\s*([A-Z0-9\-]+)',
    r'your-custom-pattern-here'
]
```

### Customer Matching

The middleware matches customers by exact name comparison. For better matching, consider:

1. Standardizing customer names in Paperless-NGX correspondents
2. Using consistent naming conventions
3. Pre-creating customers in Bigcapital

### Scheduling

For production use, consider running the middleware:

**As a Service**:
```bash
# Using systemd (Linux)
sudo systemctl enable paperless-bigcapital-middleware
sudo systemctl start paperless-bigcapital-middleware
```

**With Cron** (for periodic processing):
```bash
# Run every 5 minutes
*/5 * * * * /path/to/middleware/run.sh --once
```

## Troubleshooting

### Common Issues

**API Connection Errors**:
- Verify API URLs are accessible
- Check API tokens are valid
- Ensure network connectivity between services

**No Documents Processed**:
- Verify tags are correctly configured
- Check if documents already have processing tags
- Review log files for errors

**Data Extraction Issues**:
- Check OCR quality in Paperless-NGX
- Review document format and content
- Modify extraction patterns if needed

**Customer Creation Failures**:
- Verify Bigcapital API permissions
- Check customer data format requirements
- Review duplicate customer handling

### Debug Mode

Enable debug logging in `config.ini`:
```ini
[processing]
log_level = DEBUG
```

### Manual Processing

To process specific documents:
1. Remove existing processing tags from the document
2. Ensure correct identification tags are present
3. Run middleware with `--once` flag

## Security Considerations

- Store API tokens securely (use environment variables in production)
- Restrict API token permissions to minimum required
- Use HTTPS for all API communications
- Regularly rotate API tokens
- Monitor access logs

## Contributing

To extend the middleware:

1. **Add new document types**: Extend `DocumentProcessor` class
2. **Improve extraction**: Add regex patterns or use ML-based extraction
3. **Add integrations**: Create new client classes for other accounting systems
4. **Enhance error handling**: Add retry mechanisms and better error recovery

## API Reference

### Paperless-NGX API Endpoints Used
- `/api/documents/` - List and filter documents
- `/api/documents/{id}/` - Get document details and content
- `/api/tags/` - Manage tags
- `/api/correspondents/` - Manage correspondents

### Bigcapital API Endpoints Used
- `/api/customers` - Customer management
- `/api/invoices` - Invoice creation
- `/api/receipts` - Receipt creation

## Changelog

### v1.0.0
- Initial release
- Basic invoice and receipt processing
- Docker support
- Configuration management
- Error handling and logging

## License

This middleware is provided as-is for integration between Paperless-NGX and Bigcapital. Please ensure compliance with both systems' terms of service.

## Support

For issues and questions:
1. Check the troubleshooting section
2. Review log files for error details
3. Verify configuration settings
4. Test API connectivity manually
