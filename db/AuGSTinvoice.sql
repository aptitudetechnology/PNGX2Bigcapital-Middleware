-- Australian GST Invoice Documents table
CREATE TABLE documents (
    id SERIAL PRIMARY KEY,
    paperless_id INTEGER UNIQUE,
    document_type VARCHAR(50), -- 'tax_invoice', 'adjustment_note', 'recipient_created_tax_invoice'
    
    -- Supplier (Your business) details
    supplier_name VARCHAR(255) NOT NULL,
    supplier_abn VARCHAR(11) NOT NULL, -- Australian Business Number (11 digits)
    supplier_acn VARCHAR(9), -- Australian Company Number (9 digits, optional)
    supplier_address TEXT,
    supplier_phone VARCHAR(50),
    supplier_email VARCHAR(255),
    
    -- Customer details
    customer_name VARCHAR(255) NOT NULL,
    customer_abn VARCHAR(11), -- Required for B2B transactions over $82.50
    customer_address TEXT,
    customer_contact_person VARCHAR(255),
    customer_phone VARCHAR(50),
    customer_email VARCHAR(255),
    
    -- Invoice details
    invoice_number VARCHAR(100) NOT NULL UNIQUE,
    invoice_date DATE NOT NULL,
    due_date DATE,
    
    -- Financial details
    subtotal_amount DECIMAL(10,2) NOT NULL, -- Amount before GST
    gst_amount DECIMAL(10,2) NOT NULL, -- GST amount (10% in Australia)
    total_amount DECIMAL(10,2) NOT NULL, -- Total including GST
    currency VARCHAR(3) DEFAULT 'AUD',
    
    -- GST specific fields
    gst_rate DECIMAL(5,2) DEFAULT 10.00, -- GST rate percentage
    gst_treatment VARCHAR(50) DEFAULT 'taxable', -- 'taxable', 'gst_free', 'input_taxed'
    tax_period VARCHAR(7), -- Format: 'YYYY-MM' for BAS reporting
    
    -- Payment tracking
    paid_amount DECIMAL(10,2) DEFAULT 0.00,
    balance_due DECIMAL(10,2) GENERATED ALWAYS AS (total_amount - paid_amount) STORED,
    payment_terms VARCHAR(100),
    payment_method VARCHAR(50),
    
    -- Status and processing
    status VARCHAR(50) DEFAULT 'draft', -- 'draft', 'sent', 'paid', 'overdue', 'cancelled'
    bigcapital_id INTEGER,
    
    -- Line items stored as JSONB for flexibility
    line_items JSONB, -- Array of line items with description, quantity, unit_price, gst_rate, amount
    
    -- Account mappings and metadata
    account_mappings JSONB,
    metadata JSONB,
    
    -- Audit fields
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR(100),
    updated_by VARCHAR(100),
    
    -- Constraints
    CONSTRAINT valid_abn_supplier CHECK (LENGTH(supplier_abn) = 11 AND supplier_abn ~ '^[0-9]+$'),
    CONSTRAINT valid_abn_customer CHECK (customer_abn IS NULL OR (LENGTH(customer_abn) = 11 AND customer_abn ~ '^[0-9]+$')),
    CONSTRAINT valid_amounts CHECK (subtotal_amount >= 0 AND gst_amount >= 0 AND total_amount >= 0),
    CONSTRAINT valid_gst_calculation CHECK (ABS(total_amount - (subtotal_amount + gst_amount)) < 0.01)
);

-- Indexes for performance
CREATE INDEX idx_documents_invoice_number ON documents(invoice_number);
CREATE INDEX idx_documents_supplier_abn ON documents(supplier_abn);
CREATE INDEX idx_documents_customer_abn ON documents(customer_abn);
CREATE INDEX idx_documents_invoice_date ON documents(invoice_date);
CREATE INDEX idx_documents_tax_period ON documents(tax_period);
CREATE INDEX idx_documents_status ON documents(status);

-- Separate table for line items (alternative to JSONB approach)
CREATE TABLE document_line_items (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity DECIMAL(10,3) NOT NULL,
    unit_price DECIMAL(10,2) NOT NULL,
    line_total DECIMAL(10,2) NOT NULL,
    gst_rate DECIMAL(5,2) NOT NULL DEFAULT 10.00,
    gst_amount DECIMAL(10,2) NOT NULL,
    gst_treatment VARCHAR(50) DEFAULT 'taxable',
    product_code VARCHAR(100),
    created_at TIMESTAMP DEFAULT NOW(),
    
    CONSTRAINT valid_line_quantities CHECK (quantity > 0),
    CONSTRAINT valid_line_amounts CHECK (unit_price >= 0 AND line_total >= 0 AND gst_amount >= 0),
    CONSTRAINT unique_line_per_document UNIQUE (document_id, line_number)
);

-- Function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Trigger to automatically update updated_at
CREATE TRIGGER update_documents_updated_at 
    BEFORE UPDATE ON documents 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- View for GST reporting (BAS)
CREATE VIEW gst_summary AS
SELECT 
    tax_period,
    SUM(CASE WHEN gst_treatment = 'taxable' THEN subtotal_amount ELSE 0 END) as taxable_sales,
    SUM(CASE WHEN gst_treatment = 'taxable' THEN gst_amount ELSE 0 END) as gst_on_sales,
    SUM(CASE WHEN gst_treatment = 'gst_free' THEN total_amount ELSE 0 END) as gst_free_sales,
    COUNT(*) as invoice_count
FROM documents 
WHERE status != 'cancelled' 
  AND tax_period IS NOT NULL
GROUP BY tax_period
ORDER BY tax_period DESC;
