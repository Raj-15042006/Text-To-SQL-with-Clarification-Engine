# Power BI Executive Dashboard Blueprint & DAX Guide

This guide provides the complete data model, relationship blueprint, copy-paste DAX measures, and 4-page visual architecture for the generated **10,000-Row Global Enterprise Sales & Profit Dataset**.

---

## 1. Dataset Files & Locations

- **Multi-Sheet Relational Excel Workbook**:
  `data/power_bi_datasets/Global_Enterprise_PowerBI_Dataset.xlsx` (2.09 MB)
  - `Fact_Orders` (10,000 rows, 36 columns)
  - `Dim_Customers` (800 unique customers)
  - `Dim_Products` (33 enterprise products, 4 categories, 14 sub-categories)
  - `Dim_Managers` (3 Global Regional Directors)
  - `KPI_Targets` (432 monthly revenue & profit targets for Budget vs Actuals)
  - `Dim_Calendar` (1,096 continuous dates from 2023 to 2025 with Fiscal Year/Quarter)
- **Single Flat CSV (Optional Alternative)**:
  `data/power_bi_datasets/Global_Enterprise_Sales_10k.csv` (10,000 rows, 36 columns)

---

## 2. Power BI Data Modeling (Star Schema Relationships)

In Power BI **Model View**, establish the following **1-to-Many (`1 : *`)** single-direction relationships:

| Dimension Table (1) | Key Column | Fact Table (*) | Foreign Key Column | Relationship Type | Cross Filter |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`Dim_Customers`** | `Customer_ID` | **`Fact_Orders`** | `Customer_ID` | `1 : *` (One-to-Many) | Single |
| **`Dim_Products`** | `Product_ID` | **`Fact_Orders`** | `Product_ID` | `1 : *` (One-to-Many) | Single |
| **`Dim_Calendar`** | `Date` | **`Fact_Orders`** | `Order_Date` | `1 : *` (Active) | Single |
| **`Dim_Calendar`** | `Date` | **`Fact_Orders`** | `Ship_Date` | `1 : *` (Inactive - use `USERELATIONSHIP`) | Single |
| **`Dim_Managers`** | `Region` | **`Fact_Orders`** | `Region` | `1 : *` (One-to-Many) | Single |
| **`Dim_Calendar`** | `Month_Year` | **`KPI_Targets`** | `Month_Year` | `1 : *` (One-to-Many) | Single |

> [!TIP]
> In Power BI, right-click `Dim_Calendar` -> **Mark as Date Table** and select the `Date` column. This unlocks all native time-intelligence functions (`SAMEPERIODLASTYEAR`, `DATEADD`, `TOTALYTD`).

---

## 3. Essential DAX Measures (Copy & Paste)

Create a dedicated table named `_Measures` in Power BI:

### A. Core Volume & Financial Totals
```dax
Total Orders = 
COUNTROWS(Fact_Orders)

Total Units Sold = 
SUM(Fact_Orders[Quantity])

Gross Revenue = 
SUM(Fact_Orders[Gross_Sales])

Total Discount = 
SUM(Fact_Orders[Discount_Amount])

Net Revenue = 
SUM(Fact_Orders[Net_Sales])

Total COGS = 
SUM(Fact_Orders[Total_Cost])

Gross Profit = 
SUM(Fact_Orders[Gross_Profit])

Total Shipping Cost = 
SUM(Fact_Orders[Shipping_Cost])

Net Profit = 
SUM(Fact_Orders[Net_Profit])

Profit Margin % = 
DIVIDE([Net Profit], [Net Revenue], 0)
```

### B. Customer & Average Order Value (AOV)
```dax
Unique Customers = 
DISTINCTCOUNT(Fact_Orders[Customer_ID])

Average Order Value = 
DIVIDE([Net Revenue], [Total Orders], 0)

Average Order Quantity = 
DIVIDE([Total Units Sold], [Total Orders], 0)

Average Customer Rating = 
AVERAGE(Fact_Orders[Customer_Rating])
```

### C. Operational & Return Metrics
```dax
Total Returns = 
CALCULATE(
    COUNTROWS(Fact_Orders),
    Fact_Orders[Order_Status] = "Returned"
)

Return Rate % = 
DIVIDE([Total Returns], [Total Orders], 0)

Avg Delivery Transit Days = 
AVERAGE(Fact_Orders[Transit_Days])
```

### D. Time Intelligence & Year-over-Year (YoY) Growth
```dax
Sales Prior Year (PY) = 
CALCULATE(
    [Net Revenue],
    SAMEPERIODLASTYEAR(Dim_Calendar[Date])
)

YoY Sales Growth $ = 
[Net Revenue] - [Sales Prior Year (PY)]

YoY Sales Growth % = 
DIVIDE([YoY Sales Growth $], [Sales Prior Year (PY)], 0)

YTD Revenue = 
TOTALYTD([Net Revenue], Dim_Calendar[Date])

MTD Revenue = 
TOTALMTD([Net Revenue], Dim_Calendar[Date])
```

### E. Budget Target vs. Actuals
```dax
Target Revenue = 
SUM(KPI_Targets[Target_Sales])

Revenue Variance to Target $ = 
[Net Revenue] - [Target Revenue]

Target Achievement % = 
DIVIDE([Net Revenue], [Target Revenue], 0)
```

---

## 4. Recommended 4-Page Dashboard Architecture

### Page 1: Executive C-Suite Overview
- **Top Header Bar**: Company Logo, Title (`Global Enterprise Performance Cockpit`), Date Range Slicer (2023 - 2025), Region Slicer (`North America`, `Europe`, `Asia-Pacific`).
- **Top Row KPI Cards (4 Cards)**:
  1. `Net Revenue` (with YoY Growth % indicator)
  2. `Net Profit` & `Profit Margin %`
  3. `Total Orders` & `AOV`
  4. `Customer Satisfaction Rating` (out of 5.0)
- **Visual 1 (Area / Line Chart)**: `Monthly Revenue & Profit Trend` with YoY Comparison.
- **Visual 2 (Gauge / Bullet Chart)**: `Actual Revenue vs. Target Revenue` (using `Target Achievement %`).
- **Visual 3 (Clustered Bar Chart)**: `Revenue by Category & Sub-Category`.
- **Visual 4 (Decomposition Tree / Donut Chart)**: `Revenue by Customer Segment` (Consumer vs. Corporate vs. Home Office).

### Page 2: Product & Profitability Deep-Dive
- **Visual 1 (Scatter Plot)**: `Quantity Sold (X-axis)` vs. `Net Profit (Y-axis)` with `Bubble Size = Net Revenue`, colored by `Category`. (Instantly surfaces star products vs. margin drains).
- **Visual 2 (Waterfall Chart)**: `Gross Sales -> Discount -> Net Sales -> COGS -> Shipping -> Net Profit`.
- **Visual 3 (Matrix with Data Bars)**: `Product Name`, `Quantity`, `Net Revenue`, `Net Profit`, `Profit Margin %`, `Return Rate %`.
- **Top 5 & Bottom 5 Slicers**: Filter high-margin vs loss-making items.

### Page 3: Customer & Cohort Demographics
- **Visual 1 (Donut Chart)**: `Orders by Customer Age Group` (`18-25`, `26-35`, `36-50`, `51-65`, `65+`).
- **Visual 2 (Stacked Column Chart)**: `Segment Revenue by Payment Method` (Credit Card, PayPal, Apple Pay, etc.).
- **Visual 3 (Table / Card Visuals)**: Top 10 High-Value Customers by Lifetime Value.
- **Visual 4 (Ribbon / Area Chart)**: Customer repeat purchase frequency.

### Page 4: Geographic & Logistics Operations
- **Visual 1 (Map / Azure Map / Shape Map)**: Global revenue and profit by `Country`, `State_Province`, and `City`.
- **Visual 2 (Bar Chart)**: `Delivery Transit Days & Shipping Cost by Ship Mode`.
- **Visual 3 (Tree Map / Funnel)**: `Returned Orders by Return Reason` (Defective, Late Delivery, Wrong Item, etc.).
- **Visual 4 (Card Matrix)**: `Regional Director Performance vs Quota`.

---

## 5. Professional Color Palette (Hex Codes)

- **Primary Dark Navy**: `#1F4E78`
- **Secondary Slate Blue**: `#2F5597`
- **Success / Positive Profit**: `#107C41`
- **Accent / Alert (Returns / Loss)**: `#D83B01`
- **Neutral Light Background**: `#F8F9FA`
- **Card Background**: `#FFFFFF` with soft shadow (`rgba(0,0,0,0.06)`)

