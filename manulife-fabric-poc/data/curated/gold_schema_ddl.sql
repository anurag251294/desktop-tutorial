-- =============================================================================
-- Manulife Fabric POC — Gold Layer Schema Definitions
-- =============================================================================
-- These DDL statements define the star schema for the curated Gold layer.
-- In Fabric, tables are created as Delta tables via PySpark notebooks.
-- This file serves as a reference for the target schema.
-- =============================================================================

-- ---------------------------------------------------------------------------
-- DIMENSION TABLES
-- ---------------------------------------------------------------------------

-- dim_customer
-- Business-friendly customer dimension with derived attributes
CREATE TABLE IF NOT EXISTS gold.dim_customer (
    customer_key        BIGINT          NOT NULL,   -- Surrogate key
    customer_id         STRING          NOT NULL,   -- Natural key
    full_name           STRING          NOT NULL,
    first_name          STRING,
    last_name           STRING,
    email               STRING,
    phone               STRING,
    date_of_birth       DATE,
    age                 INT,
    age_band            STRING,                     -- 18-25, 26-35, 36-45, 46-55, 56-65, 65+
    gender              STRING,
    city                STRING,
    province            STRING,
    postal_code         STRING,
    country             STRING,
    customer_segment    STRING,                     -- Retail, High Net Worth, Institutional
    registration_date   DATE,
    tenure_years        INT,
    is_active           BOOLEAN,
    _load_timestamp     TIMESTAMP
);

-- dim_product
-- Insurance and investment product catalogue
CREATE TABLE IF NOT EXISTS gold.dim_product (
    product_key         BIGINT          NOT NULL,
    product_id          STRING          NOT NULL,
    product_name        STRING          NOT NULL,
    product_category    STRING,                     -- Insurance, Investment, Annuity
    product_line        STRING,
    description         STRING,
    min_coverage        DECIMAL(18,2),
    max_coverage        DECIMAL(18,2),
    base_premium_rate   DECIMAL(10,4),
    risk_tier           STRING,
    launch_date         DATE,
    is_active           BOOLEAN,
    _load_timestamp     TIMESTAMP
);

-- dim_advisor
-- Financial advisor / broker dimension
CREATE TABLE IF NOT EXISTS gold.dim_advisor (
    advisor_key             BIGINT      NOT NULL,
    advisor_id              STRING      NOT NULL,
    full_name               STRING      NOT NULL,
    first_name              STRING,
    last_name               STRING,
    email                   STRING,
    branch_office           STRING,
    region                  STRING,         -- Ontario, Quebec, BC, Alberta, Atlantic, Prairies
    certification_level     STRING,         -- Junior, Senior, Principal
    specialization          STRING,
    hire_date               DATE,
    tenure_years            INT,
    is_active               BOOLEAN,
    aum_total               DECIMAL(18,2),
    _load_timestamp         TIMESTAMP
);

-- dim_date
-- Standard date dimension with fiscal calendar support
CREATE TABLE IF NOT EXISTS gold.dim_date (
    date_key            INT             NOT NULL,   -- YYYYMMDD format
    full_date           DATE            NOT NULL,
    year                INT,
    quarter             INT,
    quarter_name        STRING,                     -- Q1, Q2, Q3, Q4
    month               INT,
    month_name          STRING,                     -- January, February, ...
    month_short         STRING,                     -- Jan, Feb, ...
    day_of_month        INT,
    day_of_week         INT,
    day_name            STRING,                     -- Monday, Tuesday, ...
    week_of_year        INT,
    is_weekend          BOOLEAN,
    is_month_end        BOOLEAN,
    fiscal_year         INT,                        -- Assuming Dec year-end
    fiscal_quarter      INT,
    _load_timestamp     TIMESTAMP
);

-- dim_policy
-- Policy dimension with status and classification
CREATE TABLE IF NOT EXISTS gold.dim_policy (
    policy_key          BIGINT          NOT NULL,
    policy_id           STRING          NOT NULL,
    policy_number       STRING,
    policy_type         STRING,                     -- Life, Health, Auto, Home, Travel, Disability
    status              STRING,                     -- Active, Lapsed, Cancelled, Matured
    payment_frequency   STRING,                     -- Monthly, Quarterly, Annual
    risk_category       STRING,                     -- Low, Medium, High
    effective_date      DATE,
    expiry_date         DATE,
    policy_duration_months INT,
    _load_timestamp     TIMESTAMP
);

-- dim_fund
-- Investment fund dimension
CREATE TABLE IF NOT EXISTS gold.dim_fund (
    fund_key            BIGINT          NOT NULL,
    fund_name           STRING          NOT NULL,
    fund_type           STRING,                     -- Equity, Bond, Balanced, Money Market, Real Estate
    risk_rating         INT,                        -- 1-5
    risk_label          STRING,                     -- Low, Low-Medium, Medium, Medium-High, High
    region              STRING,                     -- North America, Europe, Asia Pacific, Global
    _load_timestamp     TIMESTAMP
);

-- ---------------------------------------------------------------------------
-- FACT TABLES
-- ---------------------------------------------------------------------------

-- fact_claims
-- Grain: one row per claim
CREATE TABLE IF NOT EXISTS gold.fact_claims (
    claim_id            STRING          NOT NULL,
    customer_key        BIGINT          NOT NULL,   -- FK → dim_customer
    policy_key          BIGINT          NOT NULL,   -- FK → dim_policy
    product_key         BIGINT          NOT NULL,   -- FK → dim_product
    advisor_key         BIGINT,                     -- FK → dim_advisor (nullable)
    claim_date_key      INT             NOT NULL,   -- FK → dim_date
    resolution_date_key INT,                        -- FK → dim_date (nullable)
    claim_number        STRING,
    claim_type          STRING,
    claim_amount        DECIMAL(18,2),
    approved_amount     DECIMAL(18,2),
    processing_days     INT,
    status              STRING,
    is_approved         BOOLEAN,
    is_denied           BOOLEAN,
    denial_reason       STRING,
    _load_timestamp     TIMESTAMP
);

-- fact_transactions
-- Grain: one row per financial transaction
CREATE TABLE IF NOT EXISTS gold.fact_transactions (
    transaction_id      STRING          NOT NULL,
    customer_key        BIGINT          NOT NULL,   -- FK → dim_customer
    policy_key          BIGINT,                     -- FK → dim_policy (nullable)
    transaction_date_key INT            NOT NULL,   -- FK → dim_date
    transaction_type    STRING,
    amount              DECIMAL(18,2),
    payment_method      STRING,
    status              STRING,
    reference_number    STRING,
    _load_timestamp     TIMESTAMP
);

-- fact_investments
-- Grain: one row per investment holding snapshot
CREATE TABLE IF NOT EXISTS gold.fact_investments (
    investment_id       STRING          NOT NULL,
    customer_key        BIGINT          NOT NULL,   -- FK → dim_customer
    advisor_key         BIGINT          NOT NULL,   -- FK → dim_advisor
    fund_key            BIGINT          NOT NULL,   -- FK → dim_fund
    inception_date_key  INT             NOT NULL,   -- FK → dim_date
    valuation_date_key  INT             NOT NULL,   -- FK → dim_date
    investment_amount   DECIMAL(18,2),
    current_value       DECIMAL(18,2),
    unrealized_gain_loss DECIMAL(18,2),
    return_ytd_pct      DECIMAL(8,4),
    return_1yr_pct      DECIMAL(8,4),
    _load_timestamp     TIMESTAMP
);

-- fact_policy_premiums
-- Grain: one row per policy (premium snapshot)
CREATE TABLE IF NOT EXISTS gold.fact_policy_premiums (
    policy_key          BIGINT          NOT NULL,   -- FK → dim_policy
    customer_key        BIGINT          NOT NULL,   -- FK → dim_customer
    product_key         BIGINT          NOT NULL,   -- FK → dim_product
    advisor_key         BIGINT,                     -- FK → dim_advisor
    effective_date_key  INT             NOT NULL,   -- FK → dim_date
    premium_amount      DECIMAL(18,2),
    annualized_premium  DECIMAL(18,2),
    coverage_amount     DECIMAL(18,2),
    _load_timestamp     TIMESTAMP
);


-- ---------------------------------------------------------------------------
-- DOCUMENT CHUNKS (for unstructured content)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS gold.document_chunks (
    chunk_id            STRING          NOT NULL,
    document_name       STRING          NOT NULL,
    document_type       STRING,                     -- policy_terms, guidelines, faq, commentary, handbook
    section_header      STRING,
    chunk_text          STRING,
    chunk_index         INT,
    token_count         INT,
    embedding           ARRAY<FLOAT>,               -- Vector embedding (1536 dims for ada-002)
    _load_timestamp     TIMESTAMP
);
