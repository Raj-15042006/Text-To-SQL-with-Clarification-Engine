"""
High-Fidelity Power BI Dataset Generator
Generates a multi-sheet, relational enterprise dataset (10,000+ rows)
optimized for professional Power BI dashboards, DAX measures, and Star Schema modeling.
"""

import os
import random
import datetime
from pathlib import Path
import pandas as pd
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Seed for reproducible high-craft data
random.seed(42)

OUTPUT_DIR = Path(__file__).resolve().parent
XLSX_PATH = OUTPUT_DIR / "Global_Enterprise_PowerBI_Dataset.xlsx"
CSV_PATH = OUTPUT_DIR / "Global_Enterprise_Sales_10k.csv"

# ==============================================================================
# 1. MASTER METADATA & DIMENSIONS
# ==============================================================================

SEGMENTS = ["Consumer", "Corporate", "Home Office"]
SEGMENT_WEIGHTS = [0.50, 0.32, 0.18]

AGE_GROUPS = ["18-25", "26-35", "36-50", "51-65", "65+"]
AGE_WEIGHTS = [0.15, 0.40, 0.28, 0.12, 0.05]

GENDERS = ["Male", "Female"]

SHIP_MODES = ["Standard Class", "Second Class", "First Class", "Same Day"]
SHIP_WEIGHTS = [0.60, 0.20, 0.14, 0.06]

PAYMENT_METHODS = ["Credit Card", "PayPal", "Bank Transfer", "Debit Card", "Apple Pay", "UPI"]
PAYMENT_WEIGHTS = [0.45, 0.22, 0.12, 0.11, 0.06, 0.04]

RETURN_REASONS = ["Defective Item", "Late Delivery", "Wrong Item Sent", "Changed Mind", "Not as Described", "Found Better Price"]

GEO_HIERARCHY = [
    {"Country": "United States", "Region": "North America", "State": "California", "City": "Los Angeles", "Postal_Code": "90001", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "California", "City": "San Francisco", "Postal_Code": "94102", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "New York", "City": "New York City", "Postal_Code": "10001", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "Texas", "City": "Houston", "Postal_Code": "77001", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "Washington", "City": "Seattle", "Postal_Code": "98101", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "Illinois", "City": "Chicago", "Postal_Code": "60601", "Manager": "Sarah Jenkins"},
    {"Country": "United States", "Region": "North America", "State": "Florida", "City": "Miami", "Postal_Code": "33101", "Manager": "Sarah Jenkins"},
    {"Country": "Canada", "Region": "North America", "State": "Ontario", "City": "Toronto", "Postal_Code": "M5V 2T6", "Manager": "Sarah Jenkins"},
    {"Country": "Canada", "Region": "North America", "State": "British Columbia", "City": "Vancouver", "Postal_Code": "V6B 1A1", "Manager": "Sarah Jenkins"},
    {"Country": "United Kingdom", "Region": "Europe", "State": "England", "City": "London", "Postal_Code": "EC1A 1BB", "Manager": "Alexander Wright"},
    {"Country": "United Kingdom", "Region": "Europe", "State": "England", "City": "Manchester", "Postal_Code": "M1 1AE", "Manager": "Alexander Wright"},
    {"Country": "Germany", "Region": "Europe", "State": "Bavaria", "City": "Munich", "Postal_Code": "80331", "Manager": "Alexander Wright"},
    {"Country": "Germany", "Region": "Europe", "State": "Berlin", "City": "Berlin", "Postal_Code": "10115", "Manager": "Alexander Wright"},
    {"Country": "France", "Region": "Europe", "State": "Île-de-France", "City": "Paris", "Postal_Code": "75001", "Manager": "Alexander Wright"},
    {"Country": "France", "Region": "Europe", "State": "Rhône-Alpes", "City": "Lyon", "Postal_Code": "69001", "Manager": "Alexander Wright"},
    {"Country": "Australia", "Region": "Asia-Pacific", "State": "New South Wales", "City": "Sydney", "Postal_Code": "2000", "Manager": "Mei-Ling Chen"},
    {"Country": "Australia", "Region": "Asia-Pacific", "State": "Victoria", "City": "Melbourne", "Postal_Code": "3000", "Manager": "Mei-Ling Chen"},
    {"Country": "India", "Region": "Asia-Pacific", "State": "Maharashtra", "City": "Mumbai", "Postal_Code": "400001", "Manager": "Mei-Ling Chen"},
    {"Country": "India", "Region": "Asia-Pacific", "State": "Karnataka", "City": "Bangalore", "Postal_Code": "560001", "Manager": "Mei-Ling Chen"},
    {"Country": "India", "Region": "Asia-Pacific", "State": "Delhi", "City": "New Delhi", "Postal_Code": "110001", "Manager": "Mei-Ling Chen"},
    {"Country": "Singapore", "Region": "Asia-Pacific", "State": "Central", "City": "Singapore", "Postal_Code": "018989", "Manager": "Mei-Ling Chen"},
    {"Country": "Japan", "Region": "Asia-Pacific", "State": "Tokyo", "City": "Tokyo", "Postal_Code": "100-0001", "Manager": "Mei-Ling Chen"},
]

PRODUCT_CATALOG = [
    # Technology
    {"Category": "Technology", "Sub_Category": "Laptops & Desktops", "Product_Name": "ProBook 16-inch M3 Max", "Unit_Cost": 1850.00, "Base_Price": 2499.00},
    {"Category": "Technology", "Sub_Category": "Laptops & Desktops", "Product_Name": "UltraSlim 14-inch Touch Laptop", "Unit_Cost": 920.00, "Base_Price": 1299.00},
    {"Category": "Technology", "Sub_Category": "Laptops & Desktops", "Product_Name": "Enterprise Mini Workstation Pro", "Unit_Cost": 750.00, "Base_Price": 1050.00},
    {"Category": "Technology", "Sub_Category": "Smartphones", "Product_Name": "Apex Phone 15 Titanium 256GB", "Unit_Cost": 680.00, "Base_Price": 999.00},
    {"Category": "Technology", "Sub_Category": "Smartphones", "Product_Name": "Nexus Fold Smartphone Gen 5", "Unit_Cost": 1100.00, "Base_Price": 1699.00},
    {"Category": "Technology", "Sub_Category": "Monitors & Displays", "Product_Name": "34-inch Curved UltraWide 4K Monitor", "Unit_Cost": 420.00, "Base_Price": 649.00},
    {"Category": "Technology", "Sub_Category": "Monitors & Displays", "Product_Name": "27-inch ColorPrecision Designer Display", "Unit_Cost": 310.00, "Base_Price": 489.00},
    {"Category": "Technology", "Sub_Category": "Audio & Headphones", "Product_Name": "Noise-Cancelling Wireless Headphones Pro", "Unit_Cost": 160.00, "Base_Price": 349.00},
    {"Category": "Technology", "Sub_Category": "Audio & Headphones", "Product_Name": "Spatial Audio True Wireless Earbuds", "Unit_Cost": 85.00, "Base_Price": 199.00},
    {"Category": "Technology", "Sub_Category": "Computer Accessories", "Product_Name": "Ergonomic Mechanical Keyboard (RGB)", "Unit_Cost": 65.00, "Base_Price": 149.00},
    {"Category": "Technology", "Sub_Category": "Computer Accessories", "Product_Name": "Precision Wireless Laser Mouse", "Unit_Cost": 35.00, "Base_Price": 89.00},
    {"Category": "Technology", "Sub_Category": "Computer Accessories", "Product_Name": "Thunderbolt 4 Universal Docking Station", "Unit_Cost": 120.00, "Base_Price": 229.00},

    # Furniture
    {"Category": "Furniture", "Sub_Category": "Office Chairs", "Product_Name": "Executive Ergonomic Mesh Chair", "Unit_Cost": 280.00, "Base_Price": 520.00},
    {"Category": "Furniture", "Sub_Category": "Office Chairs", "Product_Name": "Task Swivel Chair with Lumbar Support", "Unit_Cost": 140.00, "Base_Price": 249.00},
    {"Category": "Furniture", "Sub_Category": "Standing Desks", "Product_Name": "Dual-Motor Electric Standing Desk 60x30", "Unit_Cost": 320.00, "Base_Price": 599.00},
    {"Category": "Furniture", "Sub_Category": "Standing Desks", "Product_Name": "Compact Pneumatic Riser Desk", "Unit_Cost": 95.00, "Base_Price": 189.00},
    {"Category": "Furniture", "Sub_Category": "Bookcases & Storage", "Product_Name": "5-Tier Modular Steel & Wood Bookcase", "Unit_Cost": 110.00, "Base_Price": 219.00},
    {"Category": "Furniture", "Sub_Category": "Bookcases & Storage", "Product_Name": "Locking Lateral Mobile Filing Cabinet", "Unit_Cost": 85.00, "Base_Price": 169.00},
    {"Category": "Furniture", "Sub_Category": "Conference Tables", "Product_Name": "8-Person Conference Boardroom Table", "Unit_Cost": 620.00, "Base_Price": 1150.00},

    # Office Supplies
    {"Category": "Office Supplies", "Sub_Category": "Paper & Stationery", "Product_Name": "Multi-Purpose High White Copy Paper (Box)", "Unit_Cost": 22.00, "Base_Price": 48.00},
    {"Category": "Office Supplies", "Sub_Category": "Paper & Stationery", "Product_Name": "Premium Executive Leather Bound Notebooks", "Unit_Cost": 9.50, "Base_Price": 24.50},
    {"Category": "Office Supplies", "Sub_Category": "Storage & Binders", "Product_Name": "Heavy Duty 3-Ring Binder Set (Pack of 6)", "Unit_Cost": 14.00, "Base_Price": 32.00},
    {"Category": "Office Supplies", "Sub_Category": "Storage & Binders", "Product_Name": "Mesh Desktop File Organizer & Trays", "Unit_Cost": 12.00, "Base_Price": 28.00},
    {"Category": "Office Supplies", "Sub_Category": "Printers & Ink", "Product_Name": "Enterprise Wireless Color Laser Printer", "Unit_Cost": 290.00, "Base_Price": 479.00},
    {"Category": "Office Supplies", "Sub_Category": "Printers & Ink", "Product_Name": "High-Yield Black Toner Cartridge Multi-Pack", "Unit_Cost": 60.00, "Base_Price": 125.00},
    {"Category": "Office Supplies", "Sub_Category": "Writing Supplies", "Product_Name": "Gel Ink Retractable Pens (Pack of 24)", "Unit_Cost": 6.50, "Base_Price": 18.50},
    {"Category": "Office Supplies", "Sub_Category": "Writing Supplies", "Product_Name": "Dry Erase Magnetic Whiteboard Marker Set", "Unit_Cost": 7.00, "Base_Price": 19.99},

    # Fitness & Smart Lifestyle
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Smart Wearables", "Product_Name": "Pro Fitness & ECG Smartwatch Titanium", "Unit_Cost": 145.00, "Base_Price": 299.00},
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Smart Wearables", "Product_Name": "Smart Sleep & Recovery Ring Gen 3", "Unit_Cost": 130.00, "Base_Price": 279.00},
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Home Gym Gear", "Product_Name": "Adjustable Quick-Select Dumbbell Pair", "Unit_Cost": 180.00, "Base_Price": 349.00},
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Home Gym Gear", "Product_Name": "Compact Foldable Under-Desk Walking Treadmill", "Unit_Cost": 210.00, "Base_Price": 399.00},
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Wellness & Accents", "Product_Name": "Insulated Smart Temperature Control Tumbler", "Unit_Cost": 35.00, "Base_Price": 85.00},
    {"Category": "Fitness & Lifestyle", "Sub_Category": "Wellness & Accents", "Product_Name": "High-Density Non-Slip Eco Yoga Mat", "Unit_Cost": 18.00, "Base_Price": 49.00},
]

# Assign Product IDs
for i, p in enumerate(PRODUCT_CATALOG, start=101):
    cat_code = p["Category"][:3].upper()
    p["Product_ID"] = f"PRD-{cat_code}-{i}"

# Generate 800 Unique Customers
FIRST_NAMES = ["Liam", "Olivia", "Noah", "Emma", "Oliver", "Charlotte", "Elijah", "Amelia", "James", "Sophia",
               "William", "Isabella", "Benjamin", "Mia", "Lucas", "Evelyn", "Henry", "Harper", "Alexander", "Camila",
               "Rohan", "Ananya", "Vikram", "Pooja", "Arjun", "Aditi", "Rahul", "Neha", "Wei", "Mei",
               "Hans", "Ingrid", "Pierre", "Chloé", "Jack", "Sienna", "Lucas", "Zoe", "Mateo", "Valentina"]

LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
              "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
              "Sharma", "Patel", "Verma", "Gupta", "Iyer", "Nair", "Chen", "Tanaka", "Müller", "Dubois"]

CUSTOMERS = []
for c_id in range(1001, 1801):
    fname = random.choice(FIRST_NAMES)
    lname = random.choice(LAST_NAMES)
    name = f"{fname} {lname}"
    seg = random.choices(SEGMENTS, weights=SEGMENT_WEIGHTS)[0]
    age_grp = random.choices(AGE_GROUPS, weights=AGE_WEIGHTS)[0]
    gender = random.choice(GENDERS)
    geo = random.choice(GEO_HIERARCHY)
    CUSTOMERS.append({
        "Customer_ID": f"CUST-{c_id}",
        "Customer_Name": name,
        "Segment": seg,
        "Age_Group": age_grp,
        "Gender": gender,
        "Default_Country": geo["Country"],
        "Default_Region": geo["Region"],
        "Default_City": geo["City"]
    })

# ==============================================================================
# 2. GENERATE 10,000 TRANSACTIONAL ORDERS (Fact_Orders)
# ==============================================================================
print("Generating 10,000 transaction orders with realistic distributions...")

START_DATE = datetime.date(2023, 1, 1)
END_DATE = datetime.date(2025, 12, 31)
TOTAL_DAYS = (END_DATE - START_DATE).days

orders_data = []

# Generate seasonal weights by month (Q4 Holiday surge: Nov/Dec 1.6x, Jan-Feb lower 0.8x)
MONTH_SEASONALITY = {
    1: 0.82, 2: 0.80, 3: 0.95, 4: 0.92, 5: 0.98, 6: 1.05,
    7: 1.08, 8: 1.10, 9: 1.15, 10: 1.25, 11: 1.65, 12: 1.85
}

TOTAL_ORDERS = 10000

for i in range(1, TOTAL_ORDERS + 1):
    order_id = f"ORD-{2023 + (i % 3)}-{10000 + i}"
    
    # Select date with seasonal probability
    while True:
        rand_days = random.randint(0, TOTAL_DAYS)
        order_date = START_DATE + datetime.timedelta(days=rand_days)
        month = order_date.month
        # Accept with probability proportional to seasonality
        if random.random() <= (MONTH_SEASONALITY[month] / 2.0):
            break

    # Shipping Date (1 to 6 days after order date)
    ship_mode = random.choices(SHIP_MODES, weights=SHIP_WEIGHTS)[0]
    if ship_mode == "Same Day":
        transit_days = 0
    elif ship_mode == "First Class":
        transit_days = random.randint(1, 2)
    elif ship_mode == "Second Class":
        transit_days = random.randint(2, 4)
    else:  # Standard Class
        transit_days = random.randint(3, 6)

    ship_date = order_date + datetime.timedelta(days=transit_days)

    # Customer & Geography
    cust = random.choice(CUSTOMERS)
    geo = random.choice(GEO_HIERARCHY)
    # 70% chance order is from customer's default region/country
    if random.random() < 0.70:
        matching_geos = [g for g in GEO_HIERARCHY if g["Country"] == cust["Default_Country"]]
        if matching_geos:
            geo = random.choice(matching_geos)

    # Product
    prod = random.choice(PRODUCT_CATALOG)
    
    # Quantity: mostly 1-4, corporate sometimes 5-10
    if cust["Segment"] == "Corporate":
        quantity = random.choices([1, 2, 3, 4, 5, 8, 10], weights=[0.2, 0.25, 0.2, 0.15, 0.1, 0.05, 0.05])[0]
    else:
        quantity = random.choices([1, 2, 3, 4, 5], weights=[0.55, 0.25, 0.12, 0.05, 0.03])[0]

    # Discounts: 0%, 5%, 10%, 15%, 20%
    # Corporate and Home Office get occasional higher discounts
    discount_pct = random.choices([0.0, 0.05, 0.10, 0.15, 0.20, 0.25], weights=[0.45, 0.20, 0.18, 0.10, 0.05, 0.02])[0]

    unit_cost = prod["Unit_Cost"]
    unit_price = prod["Base_Price"]

    gross_sales = round(unit_price * quantity, 2)
    discount_amount = round(gross_sales * discount_pct, 2)
    net_sales = round(gross_sales - discount_amount, 2)

    total_cost = round(unit_cost * quantity, 2)
    gross_profit = round(net_sales - total_cost, 2)
    profit_margin_pct = round((gross_profit / net_sales) * 100.0, 2) if net_sales > 0 else 0.0

    # Shipping Cost
    base_ship = 4.50
    if ship_mode == "Same Day":
        base_ship = 22.00
    elif ship_mode == "First Class":
        base_ship = 14.00
    elif ship_mode == "Second Class":
        base_ship = 8.50
    shipping_cost = round(base_ship + (quantity * 1.75), 2)

    net_profit = round(gross_profit - shipping_cost, 2)

    # Order Status & Returns
    # Overall ~5% return rate, higher on high discounts or wrong items
    is_returned = random.random() < 0.055
    if is_returned:
        order_status = "Returned"
        return_reason = random.choice(RETURN_REASONS)
        rating = random.choices([1, 2, 3], weights=[0.60, 0.30, 0.10])[0]
    else:
        order_status = "Delivered"
        return_reason = "Not Applicable"
        rating = random.choices([3, 4, 5], weights=[0.10, 0.35, 0.55])[0]

    payment_method = random.choices(PAYMENT_METHODS, weights=PAYMENT_WEIGHTS)[0]

    orders_data.append({
        "Order_ID": order_id,
        "Order_Date": order_date,
        "Ship_Date": ship_date,
        "Ship_Mode": ship_mode,
        "Transit_Days": transit_days,
        "Customer_ID": cust["Customer_ID"],
        "Customer_Name": cust["Customer_Name"],
        "Segment": cust["Segment"],
        "Age_Group": cust["Age_Group"],
        "Gender": cust["Gender"],
        "Country": geo["Country"],
        "Region": geo["Region"],
        "State_Province": geo["State"],
        "City": geo["City"],
        "Postal_Code": geo["Postal_Code"],
        "Regional_Manager": geo["Manager"],
        "Product_ID": prod["Product_ID"],
        "Category": prod["Category"],
        "Sub_Category": prod["Sub_Category"],
        "Product_Name": prod["Product_Name"],
        "Unit_Cost": unit_cost,
        "Unit_Price": unit_price,
        "Quantity": quantity,
        "Gross_Sales": gross_sales,
        "Discount_Pct": discount_pct,
        "Discount_Amount": discount_amount,
        "Net_Sales": net_sales,
        "Total_Cost": total_cost,
        "Gross_Profit": gross_profit,
        "Profit_Margin_Pct": profit_margin_pct,
        "Shipping_Cost": shipping_cost,
        "Net_Profit": net_profit,
        "Order_Status": order_status,
        "Return_Reason": return_reason,
        "Customer_Rating": rating,
        "Payment_Method": payment_method
    })

df_orders = pd.DataFrame(orders_data)

# Sort chronologically
df_orders.sort_values(by="Order_Date", inplace=True)
df_orders.reset_index(drop=True, inplace=True)

# Re-assign sequential Order IDs based on sorted date
for idx in range(len(df_orders)):
    yr = df_orders.at[idx, "Order_Date"].year
    df_orders.at[idx, "Order_ID"] = f"ORD-{yr}-{10001 + idx}"

print(f"Total Fact Orders Generated: {len(df_orders):,} rows.")

# ==============================================================================
# 3. CREATE DIMENSION TABLES & AGGREGATES
# ==============================================================================

# Dim_Customers
df_customers = pd.DataFrame(CUSTOMERS)

# Dim_Products
df_products = pd.DataFrame(PRODUCT_CATALOG)[[
    "Product_ID", "Category", "Sub_Category", "Product_Name", "Unit_Cost", "Base_Price"
]]

# Dim_Regional_Managers
df_managers = pd.DataFrame([
    {"Region": "North America", "Regional_Director": "Sarah Jenkins", "Target_Annual_Revenue": 4500000.00, "Territory_Headquarters": "San Francisco, USA"},
    {"Region": "Europe", "Regional_Director": "Alexander Wright", "Target_Annual_Revenue": 3200000.00, "Territory_Headquarters": "London, UK"},
    {"Region": "Asia-Pacific", "Regional_Director": "Mei-Ling Chen", "Target_Annual_Revenue": 3800000.00, "Territory_Headquarters": "Singapore"},
])

# Monthly Targets by Region & Category (for Target vs Actual Power BI Bullet & Gauge Visuals)
target_rows = []
for yr in [2023, 2024, 2025]:
    for mo in range(1, 13):
        dt = datetime.date(yr, mo, 1)
        for reg in ["North America", "Europe", "Asia-Pacific"]:
            for cat in ["Technology", "Furniture", "Office Supplies", "Fitness & Lifestyle"]:
                base = 35000 if cat == "Technology" else 22000 if cat == "Furniture" else 15000 if cat == "Office Supplies" else 18000
                mo_factor = MONTH_SEASONALITY[mo]
                yr_growth = 1.0 + ((yr - 2023) * 0.12)
                tgt_sales = round(base * mo_factor * yr_growth * random.uniform(0.95, 1.05), 2)
                tgt_profit = round(tgt_sales * (0.28 if cat == "Technology" else 0.22 if cat == "Furniture" else 0.35 if cat == "Office Supplies" else 0.30), 2)
                target_rows.append({
                    "Year": yr,
                    "Month": mo,
                    "Month_Year": dt.strftime("%b %Y"),
                    "Region": reg,
                    "Category": cat,
                    "Target_Sales": tgt_sales,
                    "Target_Profit": tgt_profit
                })

df_targets = pd.DataFrame(target_rows)

# Dim_Date / Calendar Dimension (Every single continuous day from 2023 to 2025)
calendar_dates = []
cur_dt = START_DATE
while cur_dt <= END_DATE:
    calendar_dates.append({
        "Date": cur_dt,
        "Year": cur_dt.year,
        "Quarter": f"Q{(cur_dt.month - 1) // 3 + 1}",
        "Year_Quarter": f"{cur_dt.year}-Q{(cur_dt.month - 1) // 3 + 1}",
        "Month_Number": cur_dt.month,
        "Month_Name": cur_dt.strftime("%B"),
        "Month_Short": cur_dt.strftime("%b"),
        "Month_Year": cur_dt.strftime("%b %Y"),
        "Week_Number": cur_dt.isocalendar()[1],
        "Day_Of_Month": cur_dt.day,
        "Day_Of_Week": cur_dt.strftime("%A"),
        "Day_Short": cur_dt.strftime("%a"),
        "Is_Weekend": "Yes" if cur_dt.weekday() >= 5 else "No",
        "Fiscal_Year": f"FY{cur_dt.year if cur_dt.month >= 4 else cur_dt.year - 1}",
        "Fiscal_Quarter": f"FQ{(cur_dt.month - 4) % 12 // 3 + 1}"
    })
    cur_dt += datetime.timedelta(days=1)

df_calendar = pd.DataFrame(calendar_dates)

# ==============================================================================
# 4. EXPORT TO CSV
# ==============================================================================
print(f"Exporting flat CSV to: {CSV_PATH}")
df_orders.to_csv(CSV_PATH, index=False)

# ==============================================================================
# 5. EXPORT TO MULTI-SHEET EXCEL WITH OPENPYXL FORMATTING
# ==============================================================================
print(f"Exporting multi-sheet formatted workbook to: {XLSX_PATH}...")

with pd.ExcelWriter(XLSX_PATH, engine="openpyxl") as writer:
    df_orders.to_excel(writer, sheet_name="Fact_Orders", index=False)
    df_customers.to_excel(writer, sheet_name="Dim_Customers", index=False)
    df_products.to_excel(writer, sheet_name="Dim_Products", index=False)
    df_managers.to_excel(writer, sheet_name="Dim_Managers", index=False)
    df_targets.to_excel(writer, sheet_name="KPI_Targets", index=False)
    df_calendar.to_excel(writer, sheet_name="Dim_Calendar", index=False)

# Polish styles with openpyxl (Headers, Column widths, Freeze Panes)
wb = openpyxl.load_workbook(XLSX_PATH)

header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
thin_border = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9')
)

for ws in wb.worksheets:
    ws.views.sheetView[0].showGridLines = True
    ws.freeze_panes = "A2"  # Freeze top row
    
    # Format header row
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=False)

    # Auto-adjust column widths
    for col in ws.columns:
        col_letter = get_column_letter(col[0].column)
        max_len = max(len(str(cell.value or '')) for cell in col[:100])  # sample first 100
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)

wb.save(XLSX_PATH)
print("Workbook formatted and saved successfully!")
print(f"File size: {os.path.getsize(XLSX_PATH) / (1024*1024):.2f} MB")

