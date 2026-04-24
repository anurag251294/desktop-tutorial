# Manulife Fabric POC -- Semantic Model Specification

**Version:** 1.0
**Last Updated:** 2026-04-24
**Authors:** Anurag Dhuria, Microsoft Partner Engineering
**Status:** Draft -- POC
**Target Platform:** Microsoft Fabric / Power BI Semantic Model (Direct Lake or Import mode)

---

## Table of Contents

1. [Overview](#1-overview)
2. [Star Schema Design](#2-star-schema-design)
3. [Fact Tables](#3-fact-tables)
4. [Dimension Tables](#4-dimension-tables)
5. [Relationships](#5-relationships)
6. [Business Measures (DAX)](#6-business-measures-dax)
7. [KPI Definitions](#7-kpi-definitions)
8. [Hierarchies](#8-hierarchies)
9. [Naming Conventions](#9-naming-conventions)
10. [AI-Readiness Recommendations](#10-ai-readiness-recommendations)
11. [Sample Business Questions](#11-sample-business-questions)
12. [Appendix](#appendix)

---

## 1. Overview

### Purpose

This document defines the semantic model for the Manulife Fabric POC. The model is designed to support:

- Self-service Power BI reporting across insurance, investment, and claims data
- Natural language querying via the Fabric Data Agent
- AI-powered Q&A with Copilot and custom orchestration layers
- Enterprise-grade KPI tracking for Manulife's insurance and wealth management lines of business

### Scope

The semantic model covers the following business domains:

| Domain | Description |
|---|---|
| **Claims** | Insurance claim submissions, approvals, denials, and processing metrics |
| **Transactions** | Premium payments, policy transactions, and payment method tracking |
| **Investments** | Wealth management portfolio data, fund performance, and AUM tracking |
| **Policy Premiums** | Policy-level premium and coverage data |

### Data Flow

```
Bronze (Raw CSVs)
    |
    v
Silver (Cleaned, typed, deduplicated)
    |
    v
Gold (Star schema Delta tables in Lakehouse)
    |
    v
Semantic Model (Power BI dataset with DAX measures)
    |
    v
Data Agent / Copilot / Power BI Reports
```

### Mode Recommendation

For this POC, **Direct Lake** mode is recommended when the Gold layer tables reside in a Fabric Lakehouse. This avoids data duplication and provides near-real-time refresh. Fall back to **Import** mode if Direct Lake limitations are encountered (e.g., unsupported DAX patterns).

---

## 2. Star Schema Design

```
                    +----------------+
                    |   dim_date     |
                    +----------------+
                           |
                           | date_key
                           |
+---------------+   +------------------+   +----------------+
|  dim_customer |---|  fact_claims     |---|  dim_product    |
+---------------+   +------------------+   +----------------+
       |                   |
       |            +------------------+
       |            |  dim_advisor     |
       |            +------------------+
       |
       |            +------------------+   +----------------+
       +------------|fact_transactions |---|  dim_policy     |
       |            +------------------+   +----------------+
       |
       |            +------------------+   +----------------+
       +------------|fact_investments  |---|  dim_fund       |
       |            +------------------+   +----------------+
       |
       |            +----------------------+
       +------------|fact_policy_premiums   |
                    +----------------------+
```

---

## 3. Fact Tables

### 3.1 fact_claims

Tracks individual insurance claim events including submission, approval/denial, and processing duration.

| Column | Data Type | Description | Example |
|---|---|---|---|
| claim_id | INT (Identity) | Unique claim identifier (primary key) | 100001 |
| policy_key | INT | Foreign key to dim_policy | 5001 |
| customer_key | INT | Foreign key to dim_customer | 2001 |
| product_key | INT | Foreign key to dim_product | 301 |
| advisor_key | INT | Foreign key to dim_advisor | 401 |
| date_key | INT | Foreign key to dim_date (claim submission date) | 20260115 |
| claim_amount | DECIMAL(18,2) | Amount claimed by the policyholder | 12500.00 |
| approved_amount | DECIMAL(18,2) | Amount approved for payout (0 if denied) | 10000.00 |
| processing_days | INT | Number of business days from submission to decision | 14 |
| is_approved | BIT | 1 = claim approved, 0 = not approved | 1 |
| is_denied | BIT | 1 = claim denied, 0 = not denied | 0 |

**Grain:** One row per claim submission.

**Notes:**
- `is_approved` and `is_denied` are not strict inverses; a claim may be in-progress (both = 0).
- `approved_amount` may be less than `claim_amount` for partial approvals.

---

### 3.2 fact_transactions

Records financial transactions against customer policies (premium payments, withdrawals, etc.).

| Column | Data Type | Description | Example |
|---|---|---|---|
| transaction_id | INT (Identity) | Unique transaction identifier (primary key) | 200001 |
| customer_key | INT | Foreign key to dim_customer | 2001 |
| policy_key | INT | Foreign key to dim_policy | 5001 |
| date_key | INT | Foreign key to dim_date (transaction date) | 20260201 |
| transaction_type | VARCHAR(50) | Type of transaction | Premium Payment |
| amount | DECIMAL(18,2) | Transaction amount (positive = inflow) | 450.00 |
| payment_method | VARCHAR(30) | Method of payment | Pre-Authorized Debit |

**Grain:** One row per transaction event.

**Valid transaction_type values:** Premium Payment, Withdrawal, Dividend Reinvestment, Fee, Adjustment, Surrender, Loan Repayment.

**Valid payment_method values:** Pre-Authorized Debit, Credit Card, Wire Transfer, Cheque, EFT, Online Banking.

---

### 3.3 fact_investments

Tracks investment portfolio positions, current valuations, and returns.

| Column | Data Type | Description | Example |
|---|---|---|---|
| investment_id | INT (Identity) | Unique investment position identifier (primary key) | 300001 |
| customer_key | INT | Foreign key to dim_customer | 2001 |
| advisor_key | INT | Foreign key to dim_advisor | 401 |
| date_key | INT | Foreign key to dim_date (valuation date) | 20260331 |
| fund_key | INT | Foreign key to dim_fund | 601 |
| investment_amount | DECIMAL(18,2) | Original invested amount (book value) | 50000.00 |
| current_value | DECIMAL(18,2) | Current market value of the position | 54250.00 |
| unrealized_gain_loss | DECIMAL(18,2) | current_value - investment_amount | 4250.00 |
| return_ytd_pct | DECIMAL(8,4) | Year-to-date return as a percentage | 8.50 |

**Grain:** One row per customer-fund-valuation date combination.

---

### 3.4 fact_policy_premiums

Tracks premium billing and coverage amounts at the policy level.

| Column | Data Type | Description | Example |
|---|---|---|---|
| policy_key | INT | Foreign key to dim_policy (composite key part) | 5001 |
| customer_key | INT | Foreign key to dim_customer (composite key part) | 2001 |
| product_key | INT | Foreign key to dim_product | 301 |
| date_key | INT | Foreign key to dim_date (billing period date) | 20260115 |
| premium_amount | DECIMAL(18,2) | Premium billed for the period | 325.00 |
| coverage_amount | DECIMAL(18,2) | Total coverage/benefit amount on the policy | 500000.00 |

**Grain:** One row per policy per billing period.

---

## 4. Dimension Tables

### 4.1 dim_customer

| Column | Data Type | Description | Example |
|---|---|---|---|
| customer_key | INT (Identity) | Surrogate key (primary key) | 2001 |
| customer_id | VARCHAR(20) | Business identifier | CUST-0045821 |
| full_name | VARCHAR(150) | Customer full name | Jean-Pierre Tremblay |
| city | VARCHAR(100) | City of residence | Toronto |
| province | VARCHAR(50) | Province code or name | ON |
| postal_code | VARCHAR(10) | Canadian postal code | M5V 3A1 |
| segment | VARCHAR(50) | Customer segment | High Net Worth |
| age_band | VARCHAR(20) | Age range bucket | 45-54 |
| registration_date | DATE | Date customer was onboarded | 2019-03-15 |

**Valid segment values:** Mass Market, Mass Affluent, High Net Worth, Ultra High Net Worth.

**Valid age_band values:** 18-24, 25-34, 35-44, 45-54, 55-64, 65-74, 75+.

---

### 4.2 dim_product

| Column | Data Type | Description | Example |
|---|---|---|---|
| product_key | INT (Identity) | Surrogate key (primary key) | 301 |
| product_id | VARCHAR(20) | Business identifier | PROD-TL-001 |
| product_name | VARCHAR(200) | Product display name | Manulife Term Life 20 |
| category | VARCHAR(100) | Product category | Life Insurance |
| product_line | VARCHAR(100) | Product line within category | Term Life |
| risk_tier | VARCHAR(20) | Risk classification | Standard |

**Valid category values:** Life Insurance, Health Insurance, Disability Insurance, Critical Illness, Segregated Funds, Mutual Funds, GIC, Annuity.

**Valid risk_tier values:** Low, Standard, High, Preferred.

---

### 4.3 dim_advisor

| Column | Data Type | Description | Example |
|---|---|---|---|
| advisor_key | INT (Identity) | Surrogate key (primary key) | 401 |
| advisor_id | VARCHAR(20) | Business identifier | ADV-00312 |
| full_name | VARCHAR(150) | Advisor full name | Sarah Chen |
| branch | VARCHAR(100) | Branch office name | Toronto Downtown |
| region | VARCHAR(50) | Geographic region | Ontario |
| certification_level | VARCHAR(50) | Highest certification | CFP |
| specialization | VARCHAR(100) | Primary area of expertise | Wealth Management |

**Valid certification_level values:** Licensed, CLU, CFP, CFA, CIM, FCSI.

**Valid specialization values:** Life Insurance, Group Benefits, Wealth Management, Retirement Planning, Estate Planning.

---

### 4.4 dim_date

| Column | Data Type | Description | Example |
|---|---|---|---|
| date_key | INT | Surrogate key in YYYYMMDD format (primary key) | 20260115 |
| full_date | DATE | Calendar date | 2026-01-15 |
| year | INT | Calendar year | 2026 |
| quarter | INT | Calendar quarter (1-4) | 1 |
| month | INT | Calendar month (1-12) | 1 |
| month_name | VARCHAR(20) | Month display name | January |
| day_of_week | VARCHAR(15) | Day name | Thursday |
| is_weekend | BIT | 1 = Saturday or Sunday | 0 |
| fiscal_year | INT | Manulife fiscal year (Dec year-end = calendar year) | 2026 |
| fiscal_quarter | INT | Manulife fiscal quarter | 1 |

**Date range:** 2020-01-01 through 2027-12-31 (8 years for trend analysis).

**Note:** Manulife's fiscal year ends December 31, so fiscal_year = calendar year and fiscal_quarter = calendar quarter.

---

### 4.5 dim_policy

| Column | Data Type | Description | Example |
|---|---|---|---|
| policy_key | INT (Identity) | Surrogate key (primary key) | 5001 |
| policy_id | VARCHAR(20) | Internal identifier | POL-00098321 |
| policy_number | VARCHAR(30) | Customer-facing policy number | ML-2024-098321 |
| policy_type | VARCHAR(50) | Policy type | Individual |
| status | VARCHAR(30) | Current policy status | Active |
| payment_frequency | VARCHAR(20) | How often premiums are billed | Monthly |
| risk_category | VARCHAR(30) | Underwriting risk classification | Standard |

**Valid status values:** Active, Lapsed, Cancelled, Matured, Pending, Surrendered.

**Valid payment_frequency values:** Monthly, Quarterly, Semi-Annual, Annual, Single Premium.

**Valid risk_category values:** Preferred, Standard, Substandard, Declined.

---

### 4.6 dim_fund

| Column | Data Type | Description | Example |
|---|---|---|---|
| fund_key | INT (Identity) | Surrogate key (primary key) | 601 |
| fund_name | VARCHAR(200) | Fund display name | Manulife Canadian Equity Fund |
| fund_type | VARCHAR(50) | Asset class | Equity |
| risk_rating | VARCHAR(20) | Risk classification (1-5 or Low-High) | Medium |
| region | VARCHAR(50) | Geographic investment focus | Canada |

**Valid fund_type values:** Equity, Fixed Income, Balanced, Money Market, Target Date, Real Estate, Alternative.

**Valid risk_rating values:** Low, Low-Medium, Medium, Medium-High, High.

**Valid region values:** Canada, US, Global, International, Emerging Markets.

---

## 5. Relationships

All relationships use single-direction filtering (from Dimension to Fact) unless noted otherwise. This is the recommended best practice for star schemas.

| # | From Table (One side) | From Column | To Table (Many side) | To Column | Cardinality | Cross-filter Direction | Active |
|---|---|---|---|---|---|---|---|
| R1 | dim_customer | customer_key | fact_claims | customer_key | 1:* | Single | Yes |
| R2 | dim_product | product_key | fact_claims | product_key | 1:* | Single | Yes |
| R3 | dim_advisor | advisor_key | fact_claims | advisor_key | 1:* | Single | Yes |
| R4 | dim_date | date_key | fact_claims | date_key | 1:* | Single | Yes |
| R5 | dim_policy | policy_key | fact_claims | policy_key | 1:* | Single | Yes |
| R6 | dim_customer | customer_key | fact_transactions | customer_key | 1:* | Single | Yes |
| R7 | dim_policy | policy_key | fact_transactions | policy_key | 1:* | Single | Yes |
| R8 | dim_date | date_key | fact_transactions | date_key | 1:* | Single | Yes |
| R9 | dim_customer | customer_key | fact_investments | customer_key | 1:* | Single | Yes |
| R10 | dim_advisor | advisor_key | fact_investments | advisor_key | 1:* | Single | Yes |
| R11 | dim_date | date_key | fact_investments | date_key | 1:* | Single | Yes |
| R12 | dim_fund | fund_key | fact_investments | fund_key | 1:* | Single | Yes |
| R13 | dim_customer | customer_key | fact_policy_premiums | customer_key | 1:* | Single | Yes |
| R14 | dim_product | product_key | fact_policy_premiums | product_key | 1:* | Single | Yes |
| R15 | dim_date | date_key | fact_policy_premiums | date_key | 1:* | Single | Yes |
| R16 | dim_policy | policy_key | fact_policy_premiums | policy_key | 1:* | Single | Yes |

### Relationship Notes

- **No bidirectional filters** are used. This prevents ambiguous filter propagation and ensures predictable DAX behavior.
- **dim_date** connects to all four fact tables. If you need independent date filtering per fact table (e.g., "claims in January vs. investments in March"), create role-playing date dimensions or use `USERELATIONSHIP()` with inactive relationships.
- **dim_customer** is the shared conformed dimension across all fact tables, enabling cross-domain analysis (e.g., "customers with both high premiums and investment AUM").

---

## 6. Business Measures (DAX)

All measures are defined in a dedicated `_Measures` table (a disconnected table with no data rows). Measures are organized into display folders.

### 6.1 Premium Measures

```dax
// Display Folder: Premiums

Total Premium Revenue =
SUMX(
    fact_policy_premiums,
    fact_policy_premiums[premium_amount]
)

Monthly Premium Trend =
CALCULATE(
    [Total Premium Revenue],
    DATESMTD( dim_date[full_date] )
)

Premium per Customer =
DIVIDE(
    [Total Premium Revenue],
    DISTINCTCOUNT( fact_policy_premiums[customer_key] ),
    0
)

Total Coverage Amount =
SUM( fact_policy_premiums[coverage_amount] )

Regional Premium Distribution =
CALCULATE(
    [Total Premium Revenue],
    ALLEXCEPT( dim_advisor, dim_advisor[region] )
)
```

### 6.2 Claims Measures

```dax
// Display Folder: Claims

Total Claims Amount =
SUM( fact_claims[claim_amount] )

Approved Claims Amount =
CALCULATE(
    SUM( fact_claims[approved_amount] ),
    fact_claims[is_approved] = 1
)

Claims Ratio =
DIVIDE(
    [Approved Claims Amount],
    [Total Premium Revenue],
    0
)

Average Claim Processing Time =
AVERAGE( fact_claims[processing_days] )

Claim Approval Rate =
DIVIDE(
    CALCULATE( COUNTROWS( fact_claims ), fact_claims[is_approved] = 1 ),
    COUNTROWS( fact_claims ),
    0
)

Claim Denial Rate =
DIVIDE(
    CALCULATE( COUNTROWS( fact_claims ), fact_claims[is_denied] = 1 ),
    COUNTROWS( fact_claims ),
    0
)

Claims per Customer =
DIVIDE(
    COUNTROWS( fact_claims ),
    DISTINCTCOUNT( fact_claims[customer_key] ),
    0
)

Claims by Category =
CALCULATE(
    [Total Claims Amount],
    ALLEXCEPT( dim_product, dim_product[category] )
)
```

### 6.3 Investment Measures

```dax
// Display Folder: Investments

Total AUM =
SUM( fact_investments[current_value] )

Total Investment Book Value =
SUM( fact_investments[investment_amount] )

Net Investment Inflows =
CALCULATE(
    SUM( fact_transactions[amount] ),
    fact_transactions[transaction_type] IN { "Premium Payment", "Dividend Reinvestment" }
) -
CALCULATE(
    SUM( fact_transactions[amount] ),
    fact_transactions[transaction_type] IN { "Withdrawal", "Surrender" }
)

Average Return YTD =
AVERAGE( fact_investments[return_ytd_pct] )

Total Unrealized Gain Loss =
SUM( fact_investments[unrealized_gain_loss] )

Investment Performance vs Benchmark =
VAR _avgReturn = [Average Return YTD]
VAR _benchmark = 7.5  // S&P/TSX Composite benchmark assumption
RETURN
    _avgReturn - _benchmark

High Value Customer Count =
CALCULATE(
    DISTINCTCOUNT( fact_investments[customer_key] ),
    FILTER(
        SUMMARIZE(
            fact_investments,
            fact_investments[customer_key],
            "CustomerAUM", SUM( fact_investments[current_value] )
        ),
        [CustomerAUM] > 100000
    )
)

Top Advisors by AUM =
CALCULATE(
    [Total AUM],
    ALLEXCEPT( dim_advisor, dim_advisor[full_name] )
)
```

### 6.4 Customer and Policy Measures

```dax
// Display Folder: Customers & Policies

Customer Count Active =
CALCULATE(
    DISTINCTCOUNT( dim_policy[policy_key] ),
    dim_policy[status] = "Active"
)

Active Customer Count =
CALCULATE(
    DISTINCTCOUNT( fact_policy_premiums[customer_key] ),
    dim_policy[status] = "Active"
)

Policy Count by Status =
COUNTROWS( dim_policy )

Product Mix by Category =
DIVIDE(
    CALCULATE( [Total Premium Revenue] ),
    CALCULATE( [Total Premium Revenue], ALL( dim_product[category] ) ),
    0
)

Customer Retention Rate =
VAR _customersStartOfPeriod =
    CALCULATE(
        DISTINCTCOUNT( fact_policy_premiums[customer_key] ),
        DATEADD( dim_date[full_date], -1, YEAR )
    )
VAR _customersRetained =
    CALCULATE(
        DISTINCTCOUNT( fact_policy_premiums[customer_key] ),
        FILTER(
            VALUES( fact_policy_premiums[customer_key] ),
            CALCULATE(
                COUNTROWS( fact_policy_premiums ),
                DATEADD( dim_date[full_date], -1, YEAR )
            ) > 0
        )
    )
RETURN
    DIVIDE( _customersRetained, _customersStartOfPeriod, 0 )
```

### 6.5 Summary Measure Table

| # | Measure Name | Display Folder | Format | Description |
|---|---|---|---|---|
| M1 | Total Premium Revenue | Premiums | Currency ($#,##0.00) | Sum of all premium amounts billed |
| M2 | Monthly Premium Trend | Premiums | Currency | Month-to-date premium revenue |
| M3 | Premium per Customer | Premiums | Currency | Average premium per unique customer |
| M4 | Total Coverage Amount | Premiums | Currency | Sum of all coverage amounts |
| M5 | Regional Premium Distribution | Premiums | Currency | Premium revenue by advisor region |
| M6 | Total Claims Amount | Claims | Currency | Sum of all claim amounts submitted |
| M7 | Approved Claims Amount | Claims | Currency | Sum of approved claim payouts |
| M8 | Claims Ratio | Claims | Percentage (0.00%) | Claims paid as a ratio of premiums earned |
| M9 | Average Claim Processing Time | Claims | Decimal (0.0) | Average business days to process a claim |
| M10 | Claim Approval Rate | Claims | Percentage | Proportion of claims approved |
| M11 | Claim Denial Rate | Claims | Percentage | Proportion of claims denied |
| M12 | Claims per Customer | Claims | Decimal | Average number of claims per customer |
| M13 | Claims by Category | Claims | Currency | Claims amount broken down by product category |
| M14 | Total AUM | Investments | Currency | Total assets under management (current value) |
| M15 | Net Investment Inflows | Investments | Currency | Inflows minus outflows |
| M16 | Average Return YTD | Investments | Percentage | Average year-to-date return across positions |
| M17 | Investment Performance vs Benchmark | Investments | Percentage | Return vs S&P/TSX Composite |
| M18 | High Value Customer Count | Investments | Whole Number | Customers with AUM > $100K |
| M19 | Top Advisors by AUM | Investments | Currency | AUM by advisor |
| M20 | Customer Count Active | Customers & Policies | Whole Number | Count of active policies |
| M21 | Active Customer Count | Customers & Policies | Whole Number | Distinct active customers |
| M22 | Policy Count by Status | Customers & Policies | Whole Number | Policies by current status |
| M23 | Product Mix by Category | Customers & Policies | Percentage | Premium share by product category |
| M24 | Customer Retention Rate | Customers & Policies | Percentage | Year-over-year customer retention |

---

## 7. KPI Definitions

Each KPI below is intended for executive dashboards and Data Agent responses.

### KPI-01: Claims Ratio

| Attribute | Value |
|---|---|
| **Name** | Claims Ratio (Loss Ratio) |
| **Definition** | The ratio of approved claim payouts to total premiums earned, indicating underwriting profitability |
| **Formula** | `Approved Claims Amount / Total Premium Revenue` |
| **Target** | < 65% (industry benchmark for life/health insurance) |
| **Red Threshold** | > 75% |
| **Amber Threshold** | 65% -- 75% |
| **Green Threshold** | < 65% |
| **Data Source** | fact_claims, fact_policy_premiums |
| **Refresh Frequency** | Daily |
| **Owner** | Chief Underwriting Officer |

### KPI-02: Claim Approval Rate

| Attribute | Value |
|---|---|
| **Name** | Claim Approval Rate |
| **Definition** | Percentage of submitted claims that are approved |
| **Formula** | `COUNT(claims where is_approved=1) / COUNT(all claims)` |
| **Target** | 80% -- 90% |
| **Red Threshold** | < 70% (may indicate overly restrictive underwriting) |
| **Amber Threshold** | 70% -- 80% |
| **Green Threshold** | 80% -- 90% |
| **Data Source** | fact_claims |
| **Refresh Frequency** | Daily |
| **Owner** | VP Claims |

### KPI-03: Average Claim Processing Time

| Attribute | Value |
|---|---|
| **Name** | Average Claim Processing Time |
| **Definition** | Mean number of business days from claim submission to final decision |
| **Formula** | `AVERAGE(fact_claims[processing_days])` |
| **Target** | < 10 business days |
| **Red Threshold** | > 20 days |
| **Amber Threshold** | 10 -- 20 days |
| **Green Threshold** | < 10 days |
| **Data Source** | fact_claims |
| **Refresh Frequency** | Daily |
| **Owner** | VP Claims Operations |

### KPI-04: Total AUM

| Attribute | Value |
|---|---|
| **Name** | Total Assets Under Management |
| **Definition** | Aggregate current market value of all client investment positions |
| **Formula** | `SUM(fact_investments[current_value])` |
| **Target** | Growth of 10% YoY |
| **Data Source** | fact_investments |
| **Refresh Frequency** | Daily |
| **Owner** | Chief Investment Officer |

### KPI-05: Net Investment Inflows

| Attribute | Value |
|---|---|
| **Name** | Net Investment Inflows |
| **Definition** | Total new investment deposits minus withdrawals and surrenders |
| **Formula** | `SUM(inflows) - SUM(outflows)` from fact_transactions |
| **Target** | Positive net inflows each quarter |
| **Red Threshold** | Net outflows > $1M |
| **Amber Threshold** | Net inflows < $500K |
| **Green Threshold** | Net inflows > $500K |
| **Data Source** | fact_transactions |
| **Refresh Frequency** | Daily |
| **Owner** | Head of Wealth Management |

### KPI-06: Total Premium Revenue

| Attribute | Value |
|---|---|
| **Name** | Total Premium Revenue |
| **Definition** | Aggregate premium income across all active policies |
| **Formula** | `SUM(fact_policy_premiums[premium_amount])` |
| **Target** | 8% YoY growth |
| **Data Source** | fact_policy_premiums |
| **Refresh Frequency** | Daily |
| **Owner** | Chief Financial Officer |

### KPI-07: Customer Retention Rate

| Attribute | Value |
|---|---|
| **Name** | Customer Retention Rate |
| **Definition** | Proportion of customers who maintained active policies from the prior year |
| **Formula** | `Customers retained from prior year / Customers at start of prior year` |
| **Target** | > 92% |
| **Red Threshold** | < 85% |
| **Amber Threshold** | 85% -- 92% |
| **Green Threshold** | > 92% |
| **Data Source** | fact_policy_premiums, dim_policy |
| **Refresh Frequency** | Monthly |
| **Owner** | VP Customer Experience |

### KPI-08: Average Return YTD

| Attribute | Value |
|---|---|
| **Name** | Average Portfolio Return (YTD) |
| **Definition** | Mean year-to-date percentage return across all investment positions |
| **Formula** | `AVERAGE(fact_investments[return_ytd_pct])` |
| **Target** | Outperform S&P/TSX Composite by 1% |
| **Data Source** | fact_investments |
| **Refresh Frequency** | Daily |
| **Owner** | Chief Investment Officer |

### KPI-09: Premium per Customer

| Attribute | Value |
|---|---|
| **Name** | Premium per Customer |
| **Definition** | Average premium revenue per unique policyholder |
| **Formula** | `Total Premium Revenue / DISTINCTCOUNT(customer_key)` |
| **Target** | $3,500+ annually |
| **Data Source** | fact_policy_premiums |
| **Refresh Frequency** | Monthly |
| **Owner** | VP Product |

### KPI-10: High-Value Customer Count

| Attribute | Value |
|---|---|
| **Name** | High-Value Customer Count |
| **Definition** | Number of distinct customers with total AUM exceeding $100,000 |
| **Formula** | `DISTINCTCOUNT(customer_key) WHERE SUM(current_value) > 100000` |
| **Target** | 15% growth YoY |
| **Data Source** | fact_investments |
| **Refresh Frequency** | Monthly |
| **Owner** | Head of Wealth Management |

---

## 8. Hierarchies

### 8.1 Geography Hierarchy

```
Country (implicit = "Canada" for POC)
  └── Province        (dim_customer[province] or dim_advisor[region])
       └── City       (dim_customer[city])
```

**Source table:** dim_customer (for customer-centric) or dim_advisor (for advisor-centric)

### 8.2 Time Hierarchy

```
Fiscal Year     (dim_date[fiscal_year])
  └── Fiscal Quarter   (dim_date[fiscal_quarter])
       └── Month       (dim_date[month_name])
            └── Day    (dim_date[full_date])
```

**Source table:** dim_date

### 8.3 Product Hierarchy

```
Category          (dim_product[category])
  └── Product Line    (dim_product[product_line])
       └── Product    (dim_product[product_name])
```

**Source table:** dim_product

### 8.4 Organization Hierarchy

```
Region            (dim_advisor[region])
  └── Branch          (dim_advisor[branch])
       └── Advisor    (dim_advisor[full_name])
```

**Source table:** dim_advisor

### 8.5 Fund Hierarchy

```
Fund Type         (dim_fund[fund_type])
  └── Region          (dim_fund[region])
       └── Fund       (dim_fund[fund_name])
```

**Source table:** dim_fund

---

## 9. Naming Conventions

### Tables

| Convention | Rule | Example |
|---|---|---|
| Fact tables | `fact_` prefix, snake_case | fact_claims |
| Dimension tables | `dim_` prefix, snake_case | dim_customer |
| Measures table | `_Measures` (leading underscore sorts to top) | _Measures |

### Columns

| Convention | Rule | Example |
|---|---|---|
| Surrogate keys | `[entity]_key` | customer_key |
| Business identifiers | `[entity]_id` | customer_id |
| Descriptive fields | snake_case, descriptive | full_name, postal_code |
| Boolean fields | `is_` prefix | is_approved |
| Amount fields | Explicit suffix | claim_amount, premium_amount |
| Percentage fields | `_pct` suffix | return_ytd_pct |
| Date fields | `_date` suffix (or `date_key` for FK) | registration_date |

### Measures

| Convention | Rule | Example |
|---|---|---|
| Aggregations | Start with aggregation intent | Total Premium Revenue |
| Ratios/Rates | Include "Ratio" or "Rate" | Claims Ratio, Claim Approval Rate |
| Averages | Start with "Average" or "Avg" | Average Claim Processing Time |
| Counts | Include "Count" | Customer Count Active |
| Per-unit | Use "per" | Premium per Customer |
| No abbreviations | Spell out fully | Not "Tot Prem Rev" |

### Display Folders

Measures are organized into the following display folders:
- Premiums
- Claims
- Investments
- Customers & Policies

### General Rules

1. All object names use English.
2. No spaces in table or column names (use snake_case). Measure names may use spaces (Title Case).
3. No reserved words as column names.
4. Consistent casing: snake_case for tables/columns, Title Case for measures.

---

## 10. AI-Readiness Recommendations

To ensure optimal performance with the Fabric Data Agent, Copilot, and custom AI orchestration layers, the following configurations are required.

### 10.1 Linguistic Schema Annotations

Create a linguistic schema YAML file for the semantic model. This is critical for the Data Agent and Copilot to correctly interpret natural language questions.

```yaml
# linguistic-schema.yaml (simplified example)
entities:
  - name: fact_claims
    terms:
      - claims
      - insurance claims
      - claim submissions
    properties:
      claim_amount:
        terms:
          - amount claimed
          - claim value
      approved_amount:
        terms:
          - amount approved
          - payout amount
          - approved value
      processing_days:
        terms:
          - processing time
          - days to process
          - turnaround time

  - name: dim_customer
    terms:
      - customers
      - clients
      - policyholders
      - members
    properties:
      full_name:
        terms:
          - customer name
          - client name
      segment:
        terms:
          - customer segment
          - client tier
          - wealth tier
```

### 10.2 Description Fields

Every table, column, and measure MUST have a description. These descriptions are used by the Data Agent to understand what each object represents.

**Table descriptions:**

| Table | Description |
|---|---|
| fact_claims | Insurance claim submissions including amounts, approval status, and processing duration. One row per claim. |
| fact_transactions | Financial transactions against customer policies including premium payments, withdrawals, and adjustments. |
| fact_investments | Investment portfolio positions showing book value, current market value, and year-to-date returns. |
| fact_policy_premiums | Premium billing records showing amounts billed and coverage amounts per policy per billing period. |
| dim_customer | Customer master data including demographics, geographic location, segment classification, and age band. |
| dim_product | Insurance and investment product catalog with category, product line, and risk tier classifications. |
| dim_advisor | Financial advisor master data including branch assignment, region, certification, and specialization. |
| dim_date | Calendar date dimension supporting daily, monthly, quarterly, and fiscal year analysis. |
| dim_policy | Policy master data including policy type, current status, payment frequency, and risk category. |
| dim_fund | Investment fund catalog with fund type, risk rating, and geographic investment focus. |

**Measure descriptions (subset):**

| Measure | Description |
|---|---|
| Total Premium Revenue | The total amount of insurance premiums billed across all policies and time periods in the current filter context. |
| Claims Ratio | The ratio of approved claim payouts to total premium revenue. A lower ratio indicates better underwriting profitability. Industry benchmark is below 65%. |
| Total AUM | Total assets under management -- the aggregate current market value of all client investment positions. |
| Customer Retention Rate | The percentage of customers from the prior year who continue to hold active policies in the current year. |

### 10.3 Synonyms for Common Business Terms

Configure synonyms in the linguistic schema so the Data Agent recognizes alternate phrasing:

| Canonical Term | Synonyms |
|---|---|
| Premium | premium payment, insurance premium, policy premium, premium income |
| Claim | insurance claim, claim submission, loss claim |
| AUM | assets under management, total assets, portfolio value, managed assets |
| Advisor | financial advisor, agent, representative, broker, FA |
| Policy | insurance policy, contract, coverage |
| Customer | client, policyholder, member, insured |
| Province | state, region (when geographic) |
| Fund | investment fund, mutual fund, segregated fund |
| Approval Rate | acceptance rate, approval percentage |
| Processing Time | turnaround time, cycle time, SLA |
| Coverage | benefit amount, sum insured, face amount |

### 10.4 Q&A Optimization Tips

1. **Keep measure names natural.** "Total Premium Revenue" reads better in Q&A than "M_PremRev_Total".
2. **Add row labels.** Set `IsDefaultLabel` on dim_customer[full_name], dim_product[product_name], dim_advisor[full_name], dim_fund[fund_name].
3. **Set default summarization.** Mark ID columns as "Don't Summarize". Mark amount columns as "Sum".
4. **Hide foreign keys.** Hide all `_key` columns from the report view; they exist only for relationships.
5. **Set data categories.** Mark dim_customer[city] as "City", dim_customer[province] as "State or Province", dim_customer[postal_code] as "Postal Code" for map visuals.
6. **Sort by column.** Set dim_date[month_name] to sort by dim_date[month].

### 10.5 Data Agent Compatibility Requirements

The Fabric Data Agent (preview) requires the following to function correctly:

1. **Semantic model must be in a Fabric workspace** with Data Agent enabled in tenant settings.
2. **Direct Lake mode preferred.** The Data Agent works with both Import and Direct Lake, but Direct Lake avoids stale data.
3. **All measures must have descriptions.** The Data Agent uses descriptions to determine which measure to query.
4. **Relationships must be well-defined.** Ambiguous or missing relationships cause incorrect results.
5. **Limit model complexity.** For POC, keep the model under 15 tables. More tables increase ambiguity for the NL parser.
6. **Test with the "Instructions" field.** The Data Agent supports a system-level instruction field where you can add business context (e.g., "Claims Ratio should always compare approved claims to premiums, not submitted claims to premiums").
7. **Linguistic schema upload.** Upload the linguistic schema YAML through Power BI Desktop > Model view > Q&A setup > Edit linguistic schema.

---

## 11. Sample Business Questions

The following questions represent typical queries the semantic model should support. Each maps to the measures and entities required to answer it.

### Claims Domain

| # | Question | Measures/Entities Used |
|---|---|---|
| Q1 | What is our overall claims ratio this year? | Claims Ratio, dim_date |
| Q2 | How many claims were denied last quarter? | Claim Denial Rate, dim_date |
| Q3 | What is the average processing time for life insurance claims? | Average Claim Processing Time, dim_product |
| Q4 | Which province has the highest claim amounts? | Total Claims Amount, dim_customer |
| Q5 | Show me the claim approval rate trend over the past 12 months. | Claim Approval Rate, dim_date |

### Premium Domain

| # | Question | Measures/Entities Used |
|---|---|---|
| Q6 | What is our total premium revenue year-to-date? | Total Premium Revenue, dim_date |
| Q7 | Which product category generates the most premium income? | Total Premium Revenue, dim_product |
| Q8 | How does premium revenue compare across provinces? | Regional Premium Distribution, dim_customer/dim_advisor |
| Q9 | What is the average premium per customer for high net worth clients? | Premium per Customer, dim_customer |
| Q10 | Show monthly premium trend for the last 2 years. | Monthly Premium Trend, dim_date |

### Investment Domain

| # | Question | Measures/Entities Used |
|---|---|---|
| Q11 | What is our total AUM? | Total AUM |
| Q12 | Are we seeing net inflows or outflows this quarter? | Net Investment Inflows, dim_date |
| Q13 | What is the average YTD return across all funds? | Average Return YTD |
| Q14 | Which fund type has the best performance? | Average Return YTD, dim_fund |
| Q15 | How many high-value customers do we have (AUM > $100K)? | High Value Customer Count |

### Customer and Advisor Domain

| # | Question | Measures/Entities Used |
|---|---|---|
| Q16 | Who are our top 10 advisors by AUM? | Top Advisors by AUM, dim_advisor |
| Q17 | What is our customer retention rate? | Customer Retention Rate |
| Q18 | How many active policies do we have? | Customer Count Active, dim_policy |
| Q19 | What is the product mix breakdown by category? | Product Mix by Category, dim_product |
| Q20 | Which branch has the most customers? | Active Customer Count, dim_advisor |

### Cross-Domain

| # | Question | Measures/Entities Used |
|---|---|---|
| Q21 | For customers with AUM > $100K, what is their average claims ratio? | Claims Ratio, High Value Customer Count, fact_investments, fact_claims |
| Q22 | Which advisors have clients with the highest claim denial rates? | Claim Denial Rate, dim_advisor |
| Q23 | Compare premium revenue vs claims payout by product line. | Total Premium Revenue, Approved Claims Amount, dim_product |
| Q24 | What percentage of our revenue comes from segregated funds vs term life? | Product Mix by Category, dim_product |
| Q25 | Show me the relationship between customer age and claims frequency. | Claims per Customer, dim_customer[age_band] |

---

## Appendix

### A. Data Volume Estimates (POC)

| Table | Estimated Row Count | Notes |
|---|---|---|
| fact_claims | 5,000 -- 10,000 | 2 years of synthetic data |
| fact_transactions | 50,000 -- 100,000 | Multiple transactions per policy |
| fact_investments | 10,000 -- 20,000 | Quarterly snapshots |
| fact_policy_premiums | 20,000 -- 50,000 | Monthly billing records |
| dim_customer | 2,000 -- 5,000 | Synthetic Canadian customers |
| dim_product | 20 -- 50 | Product catalog |
| dim_advisor | 50 -- 100 | Advisor roster |
| dim_date | ~2,922 | 8 years of dates |
| dim_policy | 5,000 -- 10,000 | One row per policy |
| dim_fund | 20 -- 40 | Fund catalog |

### B. Refresh Strategy

| Mode | Refresh Approach | Frequency |
|---|---|---|
| Direct Lake | Automatic (reads from Delta tables) | Near real-time after notebook runs |
| Import (fallback) | Scheduled refresh via Fabric pipeline | Every 6 hours or on-demand |

### C. Security (Future)

For production, implement Row-Level Security (RLS):
- Advisors see only their own clients
- Branch managers see their branch
- Regional VPs see their region
- Executives see all data

RLS is out of scope for the POC but should be planned for Phase 2.

---

*End of Semantic Model Specification*
