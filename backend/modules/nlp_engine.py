"""
Local NLP Engine for Text-to-SQL
Provides tokenization, semantic schema linking, slot extraction,
intent recognition, and AST-based SQL generation completely offline without external APIs.
"""

import re
from typing import List, Dict, Any, Optional, Tuple, Set
from pydantic import BaseModel, Field
import rapidfuzz.fuzz as fuzz

from backend.database.schema_extractor import DatabaseSchema, TableMeta, ColumnMeta


class ExtractedSlot(BaseModel):
    slot_type: str  # "table", "column", "aggregation", "filter", "sort", "limit", "formula"
    value: Any
    confidence: float = 1.0
    raw_text: str = ""


class QuerySlots(BaseModel):
    tables: List[str] = Field(default_factory=list)
    projections: List[Tuple[str, Optional[str]]] = Field(default_factory=list)  # (column_or_expr, alias)
    aggregations: List[Dict[str, str]] = Field(default_factory=list)  # {"func": "SUM", "column": "revenue", "alias": "..."}
    filters: List[Dict[str, Any]] = Field(default_factory=list)  # {"column": "score", "op": ">=", "value": 40} or {"raw": "score > 80"}
    group_by: List[str] = Field(default_factory=list)
    order_by: Optional[Dict[str, str]] = Field(default=None)  # {"column": "revenue", "direction": "DESC"}
    limit: Optional[int] = Field(default=None)
    intent: str = "SELECT"
    is_formula: bool = False
    formula_expression: Optional[str] = None
    is_context_followup: bool = False
    context_notes: Optional[str] = None
    matched_columns: List[Dict[str, Any]] = Field(default_factory=list)
    table_scores: Dict[str, int] = Field(default_factory=dict)
    wants_figures: bool = False


class LocalNLPEngine:
    """
    Independent NLP and Schema-Linking Engine.
    Parses natural language queries into structured SQL components.
    """

    # Domain synonyms dictionary
    SYNONYMS = {
        "marks": "score",
        "mark": "score",
        "scores": "score",
        "result": "score",
        "results": "score",
        "turnover": "revenue",
        "sales": "revenue",
        "earning": "revenue",
        "earnings": "revenue",
        "units": "units_sold",
        "volume": "units_sold",
        "quantity": "units_sold",
        "qty": "units_sold",
        "attendance": "attendance_percentage",
        "presence": "attendance_percentage",
        "dept": "departments",
        "department": "departments",
        "departments": "departments",
        "courses": "courses",
        "subjects": "courses",
        "classes": "courses",
        "pupil": "students",
        "pupils": "students",
        "learners": "students",
        "candidates": "students",
        # Business, Sales & Geo Column Synonyms
        "countries": "country",
        "country": "country",
        "categories": "category",
        "category": "category",
        "cities": "city",
        "regions": "region",
        "region": "region",
        "states": "state_province",
        "state": "state_province",
        "price": "unit_price",
        "prices": "unit_price",
        "cost": "unit_cost",
        "costs": "total_cost",
        "profit": "net_profit",
        "profits": "net_profit",
        "margin": "profit_margin_pct",
        "inventory": "inventory_count",
        "stock": "inventory_count",
        "discount": "discount_amount",
        "rating": "customer_rating",
        "ratings": "customer_rating",
        "status": "order_status",
        # Cricket & Sports Domain
        "wicket": "best_bowling",
        "wickets": "best_bowling",
        "bowler": "best_bowling",
        "bowlers": "best_bowling",
        "bowling": "best_bowling",
        "scorer": "top_scorer",
        "scorers": "top_scorer",
        "batsman": "top_scorer",
        "batsmen": "top_scorer",
        "batting": "top_scorer",
        "motm": "player_of_the_match",
        "mvp": "player_of_the_match",
        "award": "player_of_the_match",
        "awards": "player_of_the_match",
        "toss": "toss_winner",
        "winner": "match_winner",
        "stadium": "venue",
        "match": "ipl",
        "matches": "ipl",
        "game": "ipl",
        "games": "ipl",
        "cricket": "ipl",
    }

    AGG_PATTERNS = {
        "SUM": re.compile(r"\b(total|sum\b|sum\s+of)\b", re.I),
        "AVG": re.compile(r"\b(average\b|avg\b|mean\b|average\s+of)\b", re.I),
        "COUNT": re.compile(r"\b(how\s+many|count\b|number\s+of|total\s+number)\b", re.I),
        "MAX": re.compile(r"\b(highest|maximum|max\b|top\s+score|best\s+score|peak)\b", re.I),
        "MIN": re.compile(r"\b(lowest|minimum|min\b|least)\b", re.I),
    }

    SORT_PATTERNS = {
        "DESC": re.compile(r"\b(desc|descending|highest\s+first|most|top|best|maximum|decreasing)\b", re.I),
        "ASC": re.compile(r"\b(asc|ascending|lowest\s+first|least|bottom|worst|increasing)\b", re.I),
    }

    STOPWORDS = {
        "in", "on", "at", "to", "for", "with", "by", "of", "from", "the", "a", "an", "and",
        "or", "is", "are", "was", "were", "be", "all", "any", "some", "them", "his", "her",
        "their", "our", "its", "it", "me", "my", "we", "us", "who", "which", "what", "where",
        "when", "why", "how", "show", "list", "give", "get", "find", "tell", "calculate",
        "compute", "select", "many", "much", "total", "count", "average", "avg", "sum", "number",
        "each", "figures", "figure", "data", "following", "columns", "column", "retrieve", "dataset"
    }

    FORMULA_PATTERNS = [
        ("compound_interest", re.compile(r"\b(compound\s+interest|future\s+value)\b", re.I)),
        ("simple_interest", re.compile(r"\b(simple\s+interest)\b", re.I)),
        ("bmi", re.compile(r"\b(bmi|body\s+mass\s+index)\b", re.I)),
        ("kinetic_energy", re.compile(r"\b(kinetic\s+energy)\b", re.I)),
        ("temp_c2f", re.compile(r"\b(convert\s+(\d+(?:\.\d+)?)\s*(?:celsius|c)\s+to\s+fahrenheit)\b", re.I)),
        ("temp_f2c", re.compile(r"\b(convert\s+(\d+(?:\.\d+)?)\s*(?:fahrenheit|f)\s+to\s+celsius)\b", re.I)),
    ]

    def tokenize(self, text: str) -> List[str]:
        """Cleans and extracts meaningful linguistic tokens."""
        text = text.lower().strip()
        tokens = re.findall(r"\b[a-zA-Z0-9_\.]+\b", text)
        return tokens

    def parse_formula(self, query: str) -> Optional[str]:
        """
        Detects if query is a worldwide mathematical formula, conversion, or arithmetic calculation
        and generates standalone PostgreSQL/SQLite-compatible SQL across all STEM, statistical,
        physics, finance, business, sports, entertainment, and geographical domains.
        """
        # 1. Universal Formula Engine across all domains
        try:
            from backend.modules.formula_engine import formula_engine
            univ_sql = formula_engine.compile(query)
            if univ_sql:
                return univ_sql
        except Exception:
            pass

        q_lower = query.lower().strip()

        # Helper to extract all numeric literals from string (supports numbers with units like 70kg, 1.75m)
        def extract_numbers(s: str) -> List[float]:
            return [float(x) for x in re.findall(r"\d+(?:\.\d+)?", s)]

        # =========================================================================
        # 1. FINANCIAL & BUSINESS FORMULAS
        # =========================================================================
        # Loan EMI: e.g. "Calculate loan EMI for 500000 at 8.5% interest for 5 years" or "... for 60 months"
        if re.search(r"\b(emi|loan\s+emi|monthly\s+installment|mortgage\s+payment)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                principal = nums[0]
                annual_rate = nums[1]
                tenure = nums[2]
                n_months = int(tenure) if ("month" in q_lower or tenure > 35) else int(tenure * 12)
                r_m = (annual_rate / 100.0) / 12.0
                return (
                    f"SELECT ROUND({principal} * (({r_m:.8f} * POWER(1.0 + {r_m:.8f}, {n_months})) / "
                    f"(POWER(1.0 + {r_m:.8f}, {n_months}) - 1.0)), 2) AS monthly_emi, "
                    f"ROUND(({principal} * (({r_m:.8f} * POWER(1.0 + {r_m:.8f}, {n_months})) / "
                    f"(POWER(1.0 + {r_m:.8f}, {n_months}) - 1.0))) * {n_months}, 2) AS total_payment, "
                    f"ROUND((({principal} * (({r_m:.8f} * POWER(1.0 + {r_m:.8f}, {n_months})) / "
                    f"(POWER(1.0 + {r_m:.8f}, {n_months}) - 1.0))) * {n_months}) - {principal}, 2) AS total_interest;"
                )

        # CAGR: e.g. "Calculate CAGR from 100000 to 250000 over 5 years"
        if re.search(r"\b(cagr|compound\s+annual\s+growth|annualized\s+growth)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                v_init, v_final, years = nums[0], nums[1], nums[2]
                return f"SELECT ROUND((POWER({v_final} * 1.0 / NULLIF({v_init}, 0), 1.0 / {years}) - 1.0) * 100.0, 2) AS cagr_percentage;"

        # Compound Interest / Future Value: e.g. "Calculate compound interest on 10000 at 5% for 3 years"
        if "compound interest" in q_lower or "future value" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 3:
                p, r, t = nums[0], nums[1], nums[2]
                return f"SELECT ROUND({p} * POWER(1.0 + ({r} / 100.0), {t}), 2) AS future_value, ROUND({p} * POWER(1.0 + ({r} / 100.0), {t}) - {p}, 2) AS compound_interest;"

        # Simple Interest: e.g. "Calculate simple interest on 5000 at 4% for 2 years"
        if "simple interest" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 3:
                p, r, t = nums[0], nums[1], nums[2]
                return f"SELECT ROUND(({p} * {r} * {t}) / 100.0, 2) AS simple_interest, ROUND({p} + (({p} * {r} * {t}) / 100.0), 2) AS total_amount;"

        # ROI (Return on Investment): e.g. "ROI for investment of 50000 with return of 75000"
        if re.search(r"\b(roi|return\s+on\s+investment)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                cost, gain = (nums[0], nums[1]) if nums[1] >= nums[0] else (nums[1], nums[0])
                return f"SELECT ROUND((({gain} - {cost}) * 1.0 / NULLIF({cost}, 0)) * 100.0, 2) AS roi_percentage, ROUND({gain} - {cost}, 2) AS net_profit;"

        # Profit Margin & Markup: e.g. "Profit margin for cost 80 and selling price 120"
        if re.search(r"\b(profit\s+margin|markup)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                cost, sp = (nums[0], nums[1]) if nums[1] >= nums[0] else (nums[1], nums[0])
                return f"SELECT ROUND((({sp} - {cost}) * 1.0 / NULLIF({sp}, 0)) * 100.0, 2) AS profit_margin_percentage, ROUND((({sp} - {cost}) * 1.0 / NULLIF({cost}, 0)) * 100.0, 2) AS markup_percentage;"

        # Rule of 72: e.g. "Rule of 72 for 6% interest"
        if "rule of 72" in q_lower or "doubling time" in q_lower:
            nums = extract_numbers(query)
            if nums:
                rate = nums[0]
                return f"SELECT ROUND(72.0 / NULLIF({rate}, 0), 2) AS years_to_double;"

        # Discount & Sales Tax: e.g. "Price of 1500 with 20% discount and 5% tax"
        if ("discount" in q_lower or "tax" in q_lower) and any(w in q_lower for w in ["price", "cost", "total", "on", "amount"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                base_price = max(nums)
                other_nums = [n for n in nums if n != base_price]
                disc = other_nums[0] if other_nums else 0.0
                tax = other_nums[1] if len(other_nums) > 1 else 0.0
                return (
                    f"SELECT ROUND({base_price} * (1.0 - ({disc} / 100.0)), 2) AS discounted_price, "
                    f"ROUND(({base_price} * (1.0 - ({disc} / 100.0))) * (1.0 + ({tax} / 100.0)), 2) AS final_price_with_tax;"
                )

        # =========================================================================
        # 2. SPORTS & BIOMETRICS FORMULAS
        # =========================================================================
        # Cricket Net Run Rate (NRR): e.g. "Calculate net run rate with 180 runs in 20 overs scored and 150 runs in 20 overs conceded"
        if re.search(r"\b(net\s+run\s+rate|nrr)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 4:
                rs, os, rc, oc = nums[0], nums[1], nums[2], nums[3]
                return f"SELECT ROUND(({rs} * 1.0 / NULLIF({os}, 0)) - ({rc} * 1.0 / NULLIF({oc}, 0)), 3) AS net_run_rate;"

        # Cricket Batting Strike Rate: e.g. "batting strike rate for 75 runs in 42 balls"
        if re.search(r"\b(batting\s+strike\s+rate|strike\s+rate)\b", q_lower) and any(w in q_lower for w in ["ball", "balls", "runs", "off"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                runs, balls = nums[0], nums[1]
                return f"SELECT ROUND(({runs} * 1.0 / NULLIF({balls}, 0)) * 100.0, 2) AS batting_strike_rate;"

        # Cricket Bowling Economy Rate: e.g. "bowling economy rate for 24 runs in 4 overs"
        if re.search(r"\b(bowling\s+economy|economy\s+rate)\b", q_lower) and any(w in q_lower for w in ["over", "overs", "runs", "conceded"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                runs, overs = nums[0], nums[1]
                return f"SELECT ROUND({runs} * 1.0 / NULLIF({overs}, 0), 2) AS bowling_economy_rate;"

        # Cricket Required Run Rate (RRR): e.g. "required run rate for 60 runs in 5 overs"
        if re.search(r"\b(required\s+run\s+rate|rrr)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                runs_needed, overs_left = nums[0], nums[1]
                return f"SELECT ROUND({runs_needed} * 1.0 / NULLIF({overs_left}, 0), 2) AS required_run_rate;"

        # BMI: e.g. "BMI for 70kg and 1.75m"
        if "bmi" in q_lower or "body mass index" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                w, h = (nums[0], nums[1]) if nums[1] < 3.0 else (nums[1], nums[0])
                return (
                    f"SELECT ROUND({w} * 1.0 / POWER({h}, 2), 2) AS bmi, "
                    f"CASE "
                    f"WHEN ({w} * 1.0 / POWER({h}, 2)) < 18.5 THEN 'Underweight' "
                    f"WHEN ({w} * 1.0 / POWER({h}, 2)) < 25.0 THEN 'Normal weight' "
                    f"WHEN ({w} * 1.0 / POWER({h}, 2)) < 30.0 THEN 'Overweight' "
                    f"ELSE 'Obese' END AS bmi_category;"
                )

        # BMR (Basal Metabolic Rate - Mifflin-St Jeor): e.g. "BMR for 70 kg, 175 cm, 25 years male/female"
        if re.search(r"\b(bmr|basal\s+metabolic\s+rate)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                w, h, age = nums[0], nums[1], nums[2]
                is_female = "female" in q_lower or "woman" in q_lower
                offset = -161 if is_female else 5
                gender = "female" if is_female else "male"
                return f"SELECT ROUND((10.0 * {w}) + (6.25 * {h}) - (5.0 * {age}) + {offset}, 1) AS bmr_calories_day, '{gender}' AS gender;"

        # Target Heart Rate / Max Heart Rate: e.g. "Target heart rate for age 30"
        if re.search(r"\b(heart\s+rate|target\s+hr|max\s+hr|karvonen)\b", q_lower):
            nums = extract_numbers(query)
            if nums:
                age = nums[0]
                return (
                    f"SELECT (220 - {int(age)}) AS max_heart_rate_bpm, "
                    f"ROUND((220 - {int(age)}) * 0.70, 0) AS moderate_target_bpm, "
                    f"ROUND((220 - {int(age)}) * 0.85, 0) AS vigorous_target_bpm;"
                )

        # =========================================================================
        # 3. PHYSICS & ENGINEERING FORMULAS
        # =========================================================================
        # Kinetic Energy: e.g. "Kinetic energy of 1200 kg car moving at 25 m/s"
        if "kinetic energy" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                m, v = nums[0], nums[1]
                return f"SELECT ROUND(0.5 * {m} * POWER({v}, 2), 2) AS kinetic_energy_joules;"

        # Gravitational Potential Energy: e.g. "Potential energy of 50 kg mass at height 10 meters"
        if "potential energy" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                m, h = nums[0], nums[1]
                return f"SELECT ROUND({m} * 9.80665 * {h}, 2) AS potential_energy_joules;"

        # Ohm's Law: V = I * R, P = V * I
        if "ohm" in q_lower or ("voltage" in q_lower and ("current" in q_lower or "resistance" in q_lower or "amps" in q_lower or "ohms" in q_lower)):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                if "resistance" in q_lower and "voltage" in q_lower and "current" not in q_lower:
                    v, i = max(nums), min(nums)
                    return f"SELECT ROUND({v} * 1.0 / NULLIF({i}, 0), 2) AS resistance_ohms;"
                else:
                    i, r = nums[0], nums[1]
                    return f"SELECT ROUND({i} * {r}, 2) AS voltage_volts, ROUND(POWER({i}, 2) * {r}, 2) AS power_watts;"

        # Newton's Second Law (Force): e.g. "Force for mass 15 kg and acceleration 3 m/s2"
        if re.search(r"\b(force|newton'?s?\s+second\s+law|f\s*=\s*ma)\b", q_lower) and any(w in q_lower for w in ["mass", "acceleration", "kg", "m/s"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                m, a = nums[0], nums[1]
                return f"SELECT ROUND({m} * {a}, 2) AS force_newtons;"

        # Speed, Distance, Time: e.g. "Speed for 150 km in 2 hours"
        if ("speed" in q_lower or "velocity" in q_lower) and ("distance" in q_lower or "km" in q_lower or "miles" in q_lower or "meter" in q_lower) and ("hour" in q_lower or "time" in q_lower or "sec" in q_lower or "minute" in q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                dist, time = nums[0], nums[1]
                return f"SELECT ROUND({dist} * 1.0 / NULLIF({time}, 0), 2) AS speed;"

        # Density: e.g. "Density for mass 500 and volume 50"
        if "density" in q_lower and any(w in q_lower for w in ["mass", "volume", "weight"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                m, v = nums[0], nums[1]
                return f"SELECT ROUND({m} * 1.0 / NULLIF({v}, 0), 3) AS density;"

        # Pressure: e.g. "Pressure for force 200 and area 0.5"
        if "pressure" in q_lower and any(w in q_lower for w in ["force", "area", "pascal"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                f, a = nums[0], nums[1]
                return f"SELECT ROUND({f} * 1.0 / NULLIF({a}, 0), 2) AS pressure_pascals;"

        # Work & Power: e.g. "Work done for force 100 and distance 15"
        if "work done" in q_lower or ("work" in q_lower and ("force" in q_lower or "distance" in q_lower)):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                f, d = nums[0], nums[1]
                return f"SELECT ROUND({f} * {d}, 2) AS work_joules;"

        # Mass-Energy Equivalence: e.g. "mass energy equivalence for 0.005 kg" or "e = mc^2"
        if "e=mc" in q_lower.replace(" ", "") or "mass energy" in q_lower:
            nums = extract_numbers(query)
            if nums:
                m = nums[0]
                return f"SELECT ({m} * 299792458.0 * 299792458.0) AS energy_joules;"

        # =========================================================================
        # 4. GEOMETRY & TRIGONOMETRY FORMULAS
        # =========================================================================
        # Circle: Area and Circumference
        if "circle" in q_lower and ("radius" in q_lower or "area" in q_lower or "circumference" in q_lower or "diameter" in q_lower):
            nums = extract_numbers(query)
            if nums:
                r = nums[0] if "diameter" not in q_lower else nums[0] / 2.0
                return f"SELECT ROUND(3.141592653589793 * POWER({r}, 2), 2) AS circle_area, ROUND(2.0 * 3.141592653589793 * {r}, 2) AS circle_circumference;"

        # Sphere: Volume and Surface Area
        if "sphere" in q_lower and ("radius" in q_lower or "volume" in q_lower or "surface area" in q_lower):
            nums = extract_numbers(query)
            if nums:
                r = nums[0]
                return f"SELECT ROUND((4.0 / 3.0) * 3.141592653589793 * POWER({r}, 3), 2) AS sphere_volume, ROUND(4.0 * 3.141592653589793 * POWER({r}, 2), 2) AS sphere_surface_area;"

        # Cylinder: Volume and Surface Area
        if "cylinder" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                r, h = nums[0], nums[1]
                return f"SELECT ROUND(3.141592653589793 * POWER({r}, 2) * {h}, 2) AS cylinder_volume, ROUND(2.0 * 3.141592653589793 * {r} * ({r} + {h}), 2) AS cylinder_surface_area;"

        # Cone: Volume
        if "cone" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                r, h = nums[0], nums[1]
                return f"SELECT ROUND((1.0 / 3.0) * 3.141592653589793 * POWER({r}, 2) * {h}, 2) AS cone_volume;"

        # Triangle Area & Pythagorean Theorem
        if "hypotenuse" in q_lower or "pythagor" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                a, b = nums[0], nums[1]
                return f"SELECT ROUND(SQRT(POWER({a}, 2) + POWER({b}, 2)), 2) AS hypotenuse;"

        if "triangle" in q_lower and ("area" in q_lower or "base" in q_lower or "height" in q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                b, h = nums[0], nums[1]
                return f"SELECT ROUND(0.5 * {b} * {h}, 2) AS triangle_area;"

        # Rectangle Area & Perimeter
        if "rectangle" in q_lower and ("area" in q_lower or "perimeter" in q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                l, w = nums[0], nums[1]
                return f"SELECT ROUND({l} * {w}, 2) AS rectangle_area, ROUND(2.0 * ({l} + {w}), 2) AS rectangle_perimeter;"

        # =========================================================================
        # 5. WORLDWIDE UNIT CONVERSIONS
        # =========================================================================
        # Temperature:
        m_c2f = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:celsius|c)\s+to\s+(?:fahrenheit|f)", q_lower)
        if m_c2f:
            deg = float(m_c2f.group(1))
            return f"SELECT ROUND(({deg} * 9.0 / 5.0) + 32.0, 2) AS fahrenheit;"

        m_f2c = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:fahrenheit|f)\s+to\s+(?:celsius|c)", q_lower)
        if m_f2c:
            deg = float(m_f2c.group(1))
            return f"SELECT ROUND(({deg} - 32.0) * 5.0 / 9.0, 2) AS celsius;"

        m_c2k = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:celsius|c)\s+to\s+(?:kelvin|k)", q_lower)
        if m_c2k:
            deg = float(m_c2k.group(1))
            return f"SELECT ROUND({deg} + 273.15, 2) AS kelvin;"

        m_k2c = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:kelvin|k)\s+to\s+(?:celsius|c)", q_lower)
        if m_k2c:
            deg = float(m_k2c.group(1))
            return f"SELECT ROUND({deg} - 273.15, 2) AS celsius;"

        # Length / Distance:
        m_km2m = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:km|kilometers?)\s+to\s+(?:miles?|mi)", q_lower)
        if m_km2m:
            val = float(m_km2m.group(1))
            return f"SELECT ROUND({val} * 0.621371, 2) AS miles;"

        m_m2km = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:miles?|mi)\s+to\s+(?:km|kilometers?)", q_lower)
        if m_m2km:
            val = float(m_m2km.group(1))
            return f"SELECT ROUND({val} * 1.60934, 2) AS kilometers;"

        m_m2ft = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:meters?|m)\s+to\s+(?:feet|ft)", q_lower)
        if m_m2ft:
            val = float(m_m2ft.group(1))
            return f"SELECT ROUND({val} * 3.28084, 2) AS feet;"

        m_ft2m = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:feet|ft)\s+to\s+(?:meters?|m)", q_lower)
        if m_ft2m:
            val = float(m_ft2m.group(1))
            return f"SELECT ROUND({val} * 0.3048, 2) AS meters;"

        m_in2cm = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:inches?|in)\s+to\s+(?:cm|centimeters?)", q_lower)
        if m_in2cm:
            val = float(m_in2cm.group(1))
            return f"SELECT ROUND({val} * 2.54, 2) AS centimeters;"

        m_cm2in = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:cm|centimeters?)\s+to\s+(?:inches?|in)", q_lower)
        if m_cm2in:
            val = float(m_cm2in.group(1))
            return f"SELECT ROUND({val} / 2.54, 2) AS inches;"

        # Weight / Mass:
        m_kg2lb = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\s+to\s+(?:lbs?|pounds?)", q_lower)
        if m_kg2lb:
            val = float(m_kg2lb.group(1))
            return f"SELECT ROUND({val} * 2.20462, 2) AS pounds;"

        m_lb2kg = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:lbs?|pounds?)\s+to\s+(?:kg|kilograms?)", q_lower)
        if m_lb2kg:
            val = float(m_lb2kg.group(1))
            return f"SELECT ROUND({val} * 0.453592, 2) AS kilograms;"

        m_g2oz = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:grams?|g)\s+to\s+(?:ounces?|oz)", q_lower)
        if m_g2oz:
            val = float(m_g2oz.group(1))
            return f"SELECT ROUND({val} * 0.035274, 2) AS ounces;"

        # Volume:
        m_l2gal = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:liters?|l)\s+to\s+(?:gallons?|gal)", q_lower)
        if m_l2gal:
            val = float(m_l2gal.group(1))
            return f"SELECT ROUND({val} * 0.264172, 2) AS gallons;"

        m_gal2l = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:gallons?|gal)\s+to\s+(?:liters?|l)", q_lower)
        if m_gal2l:
            val = float(m_gal2l.group(1))
            return f"SELECT ROUND({val} * 3.78541, 2) AS liters;"

        # Speed:
        m_kmh2mph = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:kmh|km/h|kph)\s+to\s+(?:mph|miles\s+per\s+hour)", q_lower)
        if m_kmh2mph:
            val = float(m_kmh2mph.group(1))
            return f"SELECT ROUND({val} * 0.621371, 2) AS mph;"

        m_mph2kmh = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:mph|miles\s+per\s+hour)\s+to\s+(?:kmh|km/h|kph)", q_lower)
        if m_mph2kmh:
            val = float(m_mph2kmh.group(1))
            return f"SELECT ROUND({val} * 1.60934, 2) AS kmh;"

        # =========================================================================
        # 6. PERCENTAGES & GENERAL MATHEMATICAL EXPRESSIONS
        # =========================================================================
        # "X % of Y" or "X percent of Y"
        m_pct_of = re.search(r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s*(?:of)\s*(\d+(?:\.\d+)?)", q_lower)
        if m_pct_of:
            pct = float(m_pct_of.group(1))
            tot = float(m_pct_of.group(2))
            return f"SELECT ROUND(({pct} * {tot}) / 100.0, 2) AS percentage_value;"

        # "X is what percent of Y"
        m_what_pct = re.search(r"(\d+(?:\.\d+)?)\s+is\s+what\s+percent(?:age)?\s+of\s+(\d+(?:\.\d+)?)", q_lower)
        if m_what_pct:
            part = float(m_what_pct.group(1))
            tot = float(m_what_pct.group(2))
            return f"SELECT ROUND(({part} * 1.0 / NULLIF({tot}, 0)) * 100.0, 2) AS percentage;"

        # "percentage change / increase / decrease from X to Y"
        m_pct_chg = re.search(r"percent(?:age)?\s+(?:change|increase|decrease|growth)\s+from\s+(\d+(?:\.\d+)?)\s+to\s+(\d+(?:\.\d+)?)", q_lower)
        if m_pct_chg:
            v1 = float(m_pct_chg.group(1))
            v2 = float(m_pct_chg.group(2))
            return f"SELECT ROUND((({v2} - {v1}) * 1.0 / NULLIF({v1}, 0)) * 100.0, 2) AS percentage_change;"

        # Direct arithmetic expression: e.g. "calculate 25 * 4 + sqrt(144) - power(2, 3)"
        m_calc = re.search(r"^(?:calculate|compute|evaluate|what\s+is)\s+([\d\.\+\-\*\/\^\(\)\s%a-zA-Z_,]+)$", q_lower)
        if m_calc:
            expr_str = m_calc.group(1).strip()
            safe_tokens = re.findall(r"[a-zA-Z_]+", expr_str)
            allowed_math_funcs = {"sqrt", "power", "abs", "round", "ceil", "floor", "exp", "ln", "log", "mod", "sin", "cos", "tan", "pi"}
            if all(tok in allowed_math_funcs for tok in safe_tokens):
                expr_norm = expr_str
                expr_norm = re.sub(r"\bpi\(\)", "3.141592653589793", expr_norm, flags=re.I)
                expr_norm = re.sub(r"\bpi\b", "3.141592653589793", expr_norm, flags=re.I)
                return f"SELECT ROUND({expr_norm}, 4) AS result;"

        return None

    @staticmethod
    def _singularize(word: str) -> str:
        w = word.lower().strip()
        if w.endswith("ies") and len(w) > 4:
            return w[:-3] + "y"
        if w.endswith(("ches", "shes", "xes", "zes", "ses")) and len(w) > 4:
            return w[:-2]
        if w.endswith("s") and not w.endswith("ss") and w != "sales" and len(w) > 3:
            return w[:-1]
        return w

    @staticmethod
    def _is_numeric_type(data_type: str) -> bool:
        dt = (data_type or "").upper()
        return any(ty in dt for ty in ("INT", "NUMERIC", "FLOAT", "REAL", "DECIMAL", "DOUBLE", "SERIAL"))

    @staticmethod
    def _is_metric_col_name(col_name: str) -> bool:
        c = col_name.lower()
        if c == "id" or c.endswith("_id") or c in ("postal_code", "zip", "zipcode"):
            return False
        return True

    def _match_columns_and_tables(
        self,
        q_lower: str,
        tokens: List[str],
        schema: DatabaseSchema,
        stopwords: Set[str]
    ) -> Tuple[List[Dict[str, Any]], Dict[str, int], Set[str]]:
        """
        Performs multi-word phrase, singular/plural stem, synonym, and fuzzy column matching
        across all tables, returning ordered matched columns and weighted table relevance scores.
        """
        matched_columns_map: Dict[Tuple[str, str], Dict[str, Any]] = {}
        table_scores: Dict[str, int] = {t: 0 for t in schema.tables.keys()}
        candidate_tables: Set[str] = set()

        # Table-level matching
        for tbl_name in schema.tables.keys():
            t_low = tbl_name.lower()
            t_space = t_low.replace("_", " ")
            t_sing = self._singularize(t_low)

            # Explicit preposition + table name (e.g. "from sales", "in global_enterprise")
            m_explicit_tbl = re.search(rf"\b(?:from|in|of|on|table|dataset)\s+(?:{re.escape(t_low)}|{re.escape(t_space)})\b", q_lower)
            if m_explicit_tbl:
                table_scores[tbl_name] += 28
                candidate_tables.add(tbl_name)
                continue

            # Standalone table mention (avoid penalizing when "sales" appears solely inside "net sales" / "gross sales")
            q_for_tbl = q_lower
            if t_low == "sales":
                q_for_tbl = re.sub(r"\b(?:net|gross)\s+sales\b", " ", q_for_tbl)

            if re.search(rf"\b(?:{re.escape(t_low)}|{re.escape(t_space)})\b", q_for_tbl):
                table_scores[tbl_name] += 15
                candidate_tables.add(tbl_name)
                continue

            for tok in tokens:
                if tok in stopwords or len(tok) < 3:
                    continue
                if t_low == "sales" and tok == "sales" and not re.search(r"\bsales\b", q_for_tbl):
                    continue
                tok_sing = self._singularize(tok)
                syn = self.SYNONYMS.get(tok, tok)
                if tok_sing == t_sing or syn == t_low or fuzz.ratio(tok_sing, t_sing) >= 85:
                    table_scores[tbl_name] += 10
                    candidate_tables.add(tbl_name)
                elif len(tok) >= 4 and (tok in t_low or t_low in tok):
                    table_scores[tbl_name] += 5
                    candidate_tables.add(tbl_name)

        # Build semantic phrase aliases for columns
        phrase_to_col_candidates = [
            (r"\bnet\s+sales?\b", ["net_sales", "revenue"], 98),
            (r"\bgross\s+sales?\b", ["gross_sales", "revenue"], 98),
            (r"\btotal\s+revenue\b|\brevenue\b", ["revenue", "total_revenue", "gross_sales", "net_sales"], 92),
            (r"\bnet\s+profit\b|\bprofit\b|\bprofits\b", ["net_profit", "gross_profit", "profit"], 92),
            (r"\bgross\s+profit\b", ["gross_profit", "net_profit"], 96),
            (r"\bprofit\s+margin\b|\bmargin\b", ["profit_margin_pct", "margin"], 92),
            (r"\bunit\s+price\b|\bprices?\b", ["unit_price", "price"], 92),
            (r"\bunit\s+cost\b|\btotal\s+cost\b|\bcosts?\b", ["total_cost", "unit_cost", "cost"], 90),
            (r"\bproducts?\b|\bproduct\s+name\b", ["product_name", "product", "item_name"], 88),
            (r"\bcountr(?:y|ies)\b", ["country"], 95),
            (r"\bcit(?:y|ies)\b", ["city", "store_city", "customer_city"], 90),
            (r"\bstore\s+cit(?:y|ies)\b", ["store_city", "city"], 96),
            (r"\bcustomer\s+cit(?:y|ies)\b", ["customer_city", "city"], 96),
            (r"\bunits?\s+sold\b|\bquantit(?:y|ies)\b", ["units_sold", "quantity"], 92),
            (r"\binventory\b|\bstock\b", ["inventory_count", "inventory", "stock"], 92),
            (r"\bscores?\b|\bmarks?\b", ["score"], 95),
            (r"\battendance\b", ["attendance_percentage"], 95),
        ]

        def record_match(tbl_n: str, col_obj: ColumnMeta, score: int, pos: int):
            key = (tbl_n, col_obj.name)
            prev = matched_columns_map.get(key)
            if not prev or score > prev["score"]:
                matched_columns_map[key] = {
                    "table": tbl_n,
                    "column": col_obj.name,
                    "data_type": col_obj.data_type,
                    "score": score,
                    "pos": pos if not prev else min(prev["pos"], pos)
                }

        # Column-level matching
        for tbl_name, tbl_meta in schema.tables.items():
            cols_by_low = {c.name.lower(): c for c in tbl_meta.columns}
            matched_col_names_in_tbl: Set[str] = set()

            for col in tbl_meta.columns:
                c_low = col.name.lower()
                c_space = c_low.replace("_", " ")

                # 1. Exact column or space-separated column phrase in prompt
                m_exact = re.search(rf"\b(?:{re.escape(c_low)}|{re.escape(c_space)})\b", q_lower)
                if m_exact:
                    record_match(tbl_name, col, 100, m_exact.start())
                    matched_col_names_in_tbl.add(c_low)
                    candidate_tables.add(tbl_name)
                    continue

                # 2. Direct single-token / plural / synonym match (excluding generic numeric words on unrelated PKs)
                for idx_t, tok in enumerate(tokens):
                    if tok in stopwords or len(tok) < 3:
                        continue
                    tok_sing = self._singularize(tok)
                    mapped = self.SYNONYMS.get(tok, self.SYNONYMS.get(tok_sing, tok_sing))
                    if mapped == c_low or tok_sing == c_low:
                        pos_m = q_lower.find(tok)
                        record_match(tbl_name, col, 90, pos_m if pos_m >= 0 else idx_t * 5)
                        matched_col_names_in_tbl.add(c_low)
                        candidate_tables.add(tbl_name)
                    elif len(tok) >= 4 and len(c_low) >= 4 and fuzz.ratio(mapped, c_low) >= 88:
                        pos_m = q_lower.find(tok)
                        record_match(tbl_name, col, 76, pos_m if pos_m >= 0 else idx_t * 5)
                        matched_col_names_in_tbl.add(c_low)
                        candidate_tables.add(tbl_name)

            # 3. Domain phrase matching (net sales, total revenue, countries, unit price, etc.)
            for pat, target_cols, sc in phrase_to_col_candidates:
                m_ph = re.search(pat, q_lower)
                if m_ph:
                    # Prefer highest priority alias that exists on this table
                    for tc in target_cols:
                        if tc in cols_by_low:
                            record_match(tbl_name, cols_by_low[tc], sc, m_ph.start())
                            matched_col_names_in_tbl.add(tc)
                            candidate_tables.add(tbl_name)
                            break

            # Award weighted table relevance points per distinct column matched
            for c_low in matched_col_names_in_tbl:
                sc_val = matched_columns_map[(tbl_name, cols_by_low[c_low].name)]["score"]
                table_scores[tbl_name] += 16 if sc_val >= 95 else (12 if sc_val >= 85 else 6)

        matched_list = sorted(matched_columns_map.values(), key=lambda x: (x["pos"], -x["score"]))
        return matched_list, table_scores, candidate_tables

    def _resolve_col_phrase(self, phrase: str, schema: DatabaseSchema, preferred_tables: List[str]) -> Optional[Tuple[str, str]]:
        """Resolves a 1-2 word user phrase (e.g. 'countries', 'net sales', 'unit price', 'revenue') to (table, column)."""
        p_clean = re.sub(r"[^a-zA-Z0-9_ ]", "", phrase.strip().lower())
        p_snake = p_clean.replace(" ", "_")
        p_sing = self._singularize(p_clean)
        syn = self.SYNONYMS.get(p_clean, self.SYNONYMS.get(p_sing, p_snake))

        # Phrase-level fallback aliases ordered by preference
        alias_sets = {
            "revenue": ["revenue", "total_revenue", "gross_sales", "net_sales"],
            "sales": ["net_sales", "gross_sales", "revenue", "sales"],
            "profit": ["net_profit", "gross_profit", "profit"],
            "price": ["unit_price", "price"],
            "cost": ["total_cost", "unit_cost", "cost"],
            "country": ["country"],
            "city": ["city", "store_city", "customer_city"],
        }
        extra_candidates = alias_sets.get(syn, []) or alias_sets.get(p_sing, [])
        exact_targets = [p_snake, p_clean, p_sing, syn]

        search_order = [t for t in preferred_tables if t in schema.tables] + [
            t for t in schema.tables.keys() if t not in preferred_tables
        ]
        # Pass 1: Look in preferred_tables first (exact then semantic alias) before falling back to unrelated tables
        for t_name in search_order:
            cols_by_low = {c.name.lower(): c.name for c in schema.tables[t_name].columns}
            for tgt in exact_targets:
                if tgt in cols_by_low:
                    return t_name, cols_by_low[tgt]
            for alias_tgt in extra_candidates:
                if alias_tgt in cols_by_low:
                    return t_name, cols_by_low[alias_tgt]

        # Fuzzy fallback
        best_score = 0
        best_hit = None
        for t_name in search_order:
            for col in schema.tables[t_name].columns:
                cl = col.name.lower()
                r = fuzz.ratio(syn, cl)
                if r >= 82 and r > best_score:
                    best_score = r
                    best_hit = (t_name, col.name)
        return best_hit

    def extract_slots(
        self, 
        query: str, 
        schema: Optional[DatabaseSchema],
        history: Optional[List[Dict[str, Any]]] = None
    ) -> QuerySlots:
        """Extracts SQL structural slots from natural language query using schema metadata."""
        slots = QuerySlots()
        q_lower = query.lower()

        # Check for pure standalone formula
        formula_sql = self.parse_formula(query)
        if formula_sql:
            slots.is_formula = True
            slots.formula_expression = formula_sql
            slots.intent = "FORMULA_COMPUTE"
            return slots

        if not schema or not schema.tables:
            return slots

        tokens = self.tokenize(query)

        # 1. Check for domain-specific entity ranking & team analytics in cricket / IPL
        if "ipl" in schema.tables:
            ipl_cols = [c.name.lower() for c in schema.tables["ipl"].columns]

            # Detect all IPL teams mentioned
            team_aliases = {
                "chennai super kings": "Chennai Super Kings",
                "csk": "Chennai Super Kings",
                "mumbai indians": "Mumbai Indians",
                "mi": "Mumbai Indians",
                "royal challengers bangalore": "Royal Challengers Bangalore",
                "royal challengers bengaluru": "Royal Challengers Bangalore",
                "rcb": "Royal Challengers Bangalore",
                "kolkata knight riders": "Kolkata Knight Riders",
                "kkr": "Kolkata Knight Riders",
                "rajasthan royals": "Rajasthan Royals",
                "rr": "Rajasthan Royals",
                "gujarat titans": "Gujarat Titans",
                "gt": "Gujarat Titans",
                "lucknow super giants": "Lucknow Super Giants",
                "lsg": "Lucknow Super Giants",
                "delhi capitals": "Delhi Capitals",
                "dc": "Delhi Capitals",
                "sunrisers hyderabad": "Sunrisers Hyderabad",
                "srh": "Sunrisers Hyderabad",
                "punjab kings": "Punjab Kings",
                "pbks": "Punjab Kings",
                "kings xi punjab": "Punjab Kings",
                "kxip": "Punjab Kings"
            }
            detected_teams = []
            for alias, full_name in team_aliases.items():
                if re.search(r"\b" + re.escape(alias) + r"\b", q_lower):
                    if full_name not in detected_teams:
                        detected_teams.append(full_name)
            detected_team = detected_teams[0] if detected_teams else None

            # A. Multi-team head-to-head match filter (e.g. CSK vs MI)
            if len(detected_teams) >= 2 and any(w in q_lower for w in ["vs", "against", "between", "matches", "head to head", "played"]):
                t1, t2 = detected_teams[0], detected_teams[1]
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "FILTER_SELECT"
                slots.formula_expression = (
                    f"SELECT season, team1, team2, match_winner, venue, toss_winner, player_of_the_match "
                    f"FROM ipl "
                    f"WHERE ((team1 = '{t1}' AND team2 = '{t2}') OR (team1 = '{t2}' AND team2 = '{t1}'));"
                )
                return slots

            # B. Toss statistics
            if "toss" in q_lower:
                slots.tables = ["ipl"]
                slots.is_formula = True
                if detected_team:
                    slots.intent = "FILTER_SELECT"
                    slots.formula_expression = (
                        f"SELECT '{detected_team}' AS team, "
                        f"COUNT(*) AS total_matches_played, "
                        f"SUM(CASE WHEN toss_winner = '{detected_team}' THEN 1 ELSE 0 END) AS toss_wins, "
                        f"ROUND(SUM(CASE WHEN toss_winner = '{detected_team}' THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0) * 100.0, 2) AS toss_win_percentage "
                        f"FROM ipl "
                        f"WHERE (team1 = '{detected_team}' OR team2 = '{detected_team}');"
                    )
                else:
                    slots.intent = "TOP_N_RANK"
                    slots.formula_expression = (
                        f"SELECT toss_winner, COUNT(*) AS toss_wins "
                        f"FROM ipl "
                        f"GROUP BY toss_winner "
                        f"ORDER BY toss_wins DESC LIMIT 1;"
                    )
                return slots

            # C. Venue / Stadium analytics
            if re.search(r"\b(venue|stadium|ground)\b", q_lower):
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "TOP_N_RANK"
                slots.formula_expression = (
                    f"SELECT venue, COUNT(*) AS matches_hosted, "
                    f"ROUND(AVG(highscore), 2) AS average_highscore, "
                    f"MAX(highscore) AS peak_highscore "
                    f"FROM ipl "
                    f"GROUP BY venue "
                    f"ORDER BY matches_hosted DESC LIMIT 1;"
                )
                return slots

            # D. Team-specific Bowling Strike Rate
            if detected_team and re.search(r"\b(bowling\s+strike|strike\s+of|bowling\s+average|bowling\s+stats|bowling\s+performance|bowling\s+rate)\b", q_lower):
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "FORMULA_COMPUTE"
                slots.formula_expression = (
                    f"SELECT '{detected_team}' AS team, "
                    f"COUNT(*) AS matches_played, "
                    f"COUNT(*) * 120 AS total_balls_bowled, "
                    f"SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)) AS wickets_taken, "
                    f"ROUND(CAST(COUNT(*) * 120 AS FLOAT) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2) AS average_bowling_strike_rate, "
                    f"SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) AS runs_conceded, "
                    f"ROUND(SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2) AS bowling_average "
                    f"FROM ipl "
                    f"WHERE (team1 = '{detected_team}' OR team2 = '{detected_team}') "
                    f"AND best_bowling_figure LIKE '%--%';"
                )
                return slots

            # E. Team-specific Bowling Economy
            if detected_team and re.search(r"\b(economy|economy\s+rate|bowling\s+economy|team\s+economy)\b", q_lower):
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "FORMULA_COMPUTE"
                slots.formula_expression = (
                    f"SELECT '{detected_team}' AS team, "
                    f"COUNT(*) AS matches_played, "
                    f"COUNT(*) * 20 AS total_overs_bowled, "
                    f"SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) AS approx_runs_conceded, "
                    f"ROUND(SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) / NULLIF(COUNT(*) * 20.0, 0), 2) AS estimated_economy_rate "
                    f"FROM ipl "
                    f"WHERE (team1 = '{detected_team}' OR team2 = '{detected_team}') "
                    f"AND best_bowling_figure LIKE '%--%';"
                )
                return slots

            # F. Team-specific Batting Performance / Strike Rate
            if detected_team and re.search(r"\b(batting\s+strike|batting\s+performance|runs\s+scored|average\s+score|batting\s+average)\b", q_lower):
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "FORMULA_COMPUTE"
                slots.formula_expression = (
                    f"SELECT '{detected_team}' AS team, "
                    f"COUNT(*) AS matches_played, "
                    f"SUM(highscore) AS total_runs_scored, "
                    f"ROUND(AVG(highscore), 2) AS average_score, "
                    f"MAX(highscore) AS highest_score "
                    f"FROM ipl "
                    f"WHERE (team1 = '{detected_team}' OR team2 = '{detected_team}');"
                )
                return slots

            # G. Team Match Wins / Win Percentage
            if detected_team and re.search(r"\b(matches\s+won|won\s+by|wins\s+by|win\s+percentage|total\s+wins)\b", q_lower):
                slots.tables = ["ipl"]
                slots.is_formula = True
                slots.intent = "FORMULA_COMPUTE"
                slots.formula_expression = (
                    f"SELECT '{detected_team}' AS team, "
                    f"COUNT(*) AS total_matches_played, "
                    f"SUM(CASE WHEN match_winner = '{detected_team}' THEN 1 ELSE 0 END) AS matches_won, "
                    f"ROUND(SUM(CASE WHEN match_winner = '{detected_team}' THEN 1.0 ELSE 0.0 END) / NULLIF(COUNT(*), 0) * 100.0, 2) AS win_percentage "
                    f"FROM ipl "
                    f"WHERE (team1 = '{detected_team}' OR team2 = '{detected_team}');"
                )
                return slots

            # H. Individual Bowler Strike Rate / Bowling Average
            m_bowler = re.search(r"\b(?:bowling\s+strike(?:\s+rate)?|strike\s+rate|bowling\s+average|bowling\s+economy|wickets)\s+(?:of|for)?\s*([a-zA-Z\s]+?)(?:\s+in\s+ipl|\s+this\s+season|\s+throughout|$)", q_lower)
            if m_bowler:
                cand_bowler = m_bowler.group(1).strip()
                if cand_bowler and not any(cand_bowler == a or a in cand_bowler for a in team_aliases.keys()):
                    bowler_name = cand_bowler.title()
                    slots.tables = ["ipl"]
                    slots.is_formula = True
                    slots.intent = "FORMULA_COMPUTE"
                    slots.formula_expression = (
                        f"SELECT best_bowling AS bowler, "
                        f"COUNT(*) AS matches_as_top_bowler, "
                        f"COUNT(*) * 24 AS approx_balls_bowled, "
                        f"SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)) AS wickets_taken, "
                        f"ROUND(CAST(COUNT(*) * 24 AS FLOAT) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2) AS bowling_strike_rate, "
                        f"SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) AS runs_conceded, "
                        f"ROUND(SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2) AS bowling_average "
                        f"FROM ipl "
                        f"WHERE best_bowling LIKE '%{bowler_name}%' AND best_bowling_figure LIKE '%--%' "
                        f"GROUP BY best_bowling;"
                    )
                    return slots

            # I. Top N Wicket Takers Ranking (Dynamic limit N)
            m_top_wickets = re.search(r"\b(?:top|first|leading)?\s*(\d+)?\s*(?:wicket\s+takers?|bowlers?|most\s+wickets|leading\s+wicket|best\s+bowler)\b", q_lower)
            if m_top_wickets and not detected_team and any(w in q_lower for w in ["wicket", "wickets", "bowler", "bowlers"]):
                lim_str = m_top_wickets.group(1)
                limit_val = int(lim_str) if lim_str else (1 if any(w in q_lower for w in ["highest", "best", "most", "leading"]) else 5)
                slots.tables = ["ipl"]
                slots.limit = limit_val
                slots.intent = "TOP_N_RANK"
                if "best_bowling" in ipl_cols:
                    slots.group_by = ["best_bowling"]
                    if "best_bowling_figure" in ipl_cols:
                        slots.projections = [
                            ("best_bowling", "bowler"),
                            ("COUNT(*)", "best_bowler_matches"),
                            ("SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER))", "total_wickets"),
                            ("SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC))", "runs_conceded"),
                            ("ROUND(SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2)", "bowling_average"),
                            ("ROUND(CAST(COUNT(*) * 24 AS FLOAT) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2)", "bowling_strike_rate")
                        ]
                        slots.filters.append({
                            "column": "best_bowling_figure",
                            "op": "LIKE",
                            "value": "%--%"
                        })
                        slots.order_by = {"column": "total_wickets", "direction": "DESC"}
                    else:
                        slots.projections = [("best_bowling", "bowler"), ("COUNT(*)", "times_top_bowler")]
                        slots.order_by = {"column": "times_top_bowler", "direction": "DESC"}
                    return slots

            # J. Top N Run Scorers Ranking (Dynamic limit N)
            m_top_runs = re.search(r"\b(?:top|first|leading)?\s*(\d+)?\s*(?:run\s+scorers?|scorers?|batsmen|batsman|most\s+runs|orange\s+cap)\b", q_lower)
            if m_top_runs and not detected_team and any(w in q_lower for w in ["scorer", "scorers", "batsman", "batsmen", "runs"]):
                lim_str = m_top_runs.group(1)
                limit_val = int(lim_str) if lim_str else (1 if any(w in q_lower for w in ["highest", "best", "most", "leading"]) else 5)
                slots.tables = ["ipl"]
                slots.limit = limit_val
                slots.intent = "TOP_N_RANK"
                if "top_scorer" in ipl_cols:
                    slots.group_by = ["top_scorer"]
                    if "highscore" in ipl_cols:
                        slots.projections = [
                            ("top_scorer", "batsman"),
                            ("SUM(highscore)", "total_runs"),
                            ("COUNT(*)", "matches"),
                            ("MAX(highscore)", "highest_match_score")
                        ]
                        slots.order_by = {"column": "total_runs", "direction": "DESC"}
                    else:
                        slots.projections = [("top_scorer", "batsman"), ("COUNT(*)", "matches")]
                        slots.order_by = {"column": "matches", "direction": "DESC"}
                    return slots

            # K. Player of the match awards
            if re.search(r"\b(player\s+of\s+the\s+match|motm|mvp|most\s+awards)\b", q_lower):
                m_lim = re.search(r"\b(?:top|first)\s+(\d+)\b", q_lower)
                slots.tables = ["ipl"]
                slots.limit = int(m_lim.group(1)) if m_lim else 1
                slots.intent = "TOP_N_RANK"
                if "player_of_the_match" in ipl_cols:
                    slots.group_by = ["player_of_the_match"]
                    slots.projections = [("player_of_the_match", "player"), ("COUNT(*)", "awards_count")]
                    slots.order_by = {"column": "awards_count", "direction": "DESC"}
                    return slots

        # 2. Identify Candidate Tables & Columns via Multi-Word Phrase, Synonym & Table Scoring
        matched_cols_info, table_scores, candidate_tables = self._match_columns_and_tables(
            q_lower=q_lower, tokens=tokens, schema=schema, stopwords=self.STOPWORDS
        )
        slots.matched_columns = matched_cols_info
        slots.table_scores = table_scores
        slots.wants_figures = bool(re.search(
            r"\b(figures?|numbers?|values?|amounts?|metrics?|stats?|statistics?|details?|breakdown|each|summary|sample\s+rows?|all\s+columns?)\b",
            q_lower
        ))

        # Check if query asks "who" or mentions students/people
        if re.search(r"\b(who|which\s+student|which\s+pupil|learners?)\b", q_lower) and "students" in schema.tables:
            candidate_tables.add("students")
            table_scores["students"] = table_scores.get("students", 0) + 12

        # Context continuation: inspect history for active tables, previous filters, and pronouns
        context_table = None
        context_filters = []
        is_followup = False

        followup_tokens = {"his", "her", "their", "them", "those", "ones", "which", "now", "also", "who", "whom"}
        if history and (set(tokens) & followup_tokens or any(p in q_lower for p in ["now show", "now only", "also", "what about", "how about", "sort them", "what was his"])):
            is_followup = True
            for h in reversed(history):
                h_sql = str(h.get("sql", ""))
                h_content = str(h.get("content", ""))
                
                # Check table from prior SQL
                m_from = re.search(r"\bFROM\s+([a-zA-Z0-9_]+)", h_sql, re.I)
                if m_from and m_from.group(1).lower() in schema.tables:
                    context_table = m_from.group(1).lower()
                elif not context_table:
                    for tbl_name in schema.tables.keys():
                        if tbl_name.lower() in (h_sql + " " + h_content).lower():
                            context_table = tbl_name
                            break

                # Extract WHERE clause from prior SQL
                if h_sql:
                    m_where = re.search(r"\bWHERE\s+(.*?)(?:\s+GROUP\s+BY|\s+ORDER\s+BY|\s+LIMIT|;|$)", h_sql, re.I)
                    if m_where:
                        where_str = m_where.group(1).strip()
                        raw_conds = [c.strip() for c in re.split(r"\s+AND\s+", where_str, flags=re.I)]
                        for cond in raw_conds:
                            if cond and cond not in context_filters:
                                context_filters.append(cond)
                if context_table:
                    break

        if not candidate_tables and context_table:
            candidate_tables.add(context_table)
            table_scores[context_table] = table_scores.get(context_table, 0) + 10

        # Order candidate tables by relevance score descending
        ranked_tables = sorted(candidate_tables, key=lambda t: table_scores.get(t, 0), reverse=True)
        matched_columns: List[Tuple[str, str]] = [(m["table"], m["column"]) for m in matched_cols_info]

        # 4. Identify Limit / Top N
        m_limit = re.search(r"\b(top|first|limit)\s+(\d+)\b", q_lower)
        if m_limit:
            slots.limit = int(m_limit.group(2))

        # Check for "who" / "which <entity>" with superlative (e.g. "who has highest score", "which student has highest attendance")
        is_who_which = bool(re.search(r"\b(who|which\s+(?:student|player|bowler|batsman|team|course|product|customer|department|venue|stadium))\b", q_lower))
        has_superlative = bool(re.search(r"\b(highest|top|best|maximum|most|lowest|bottom|worst|minimum|least)\b", q_lower))
        if is_who_which and has_superlative and not slots.limit:
            slots.limit = 1

        # 5. Extract Explicit Per-Metric Aggregations & General Aggregation
        metric_agg_specs: List[Dict[str, str]] = []
        agg_phrase_patterns = [
            ("MAX", r"\b(?:highest|maximum|max|peak|largest|biggest)\s+(?:of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)"),
            ("MIN", r"\b(?:lowest|minimum|min|least|smallest)\s+(?:of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)"),
            ("SUM", r"\b(?:total|sum\s+of|sum)\s+(?:of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)"),
            ("AVG", r"\b(?:average|avg|mean)\s+(?:of\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)"),
        ]
        seen_metric_keys: Set[Tuple[str, str]] = set()
        for func_name, pat_str in agg_phrase_patterns:
            for m_agg in re.finditer(pat_str, q_lower):
                phrase = m_agg.group(1).strip()
                resolved = self._resolve_col_phrase(phrase, schema, ranked_tables)
                if not resolved:
                    # Try single-word tail if 2-word captured extra preposition/word
                    first_w = phrase.split()[0]
                    resolved = self._resolve_col_phrase(first_w, schema, ranked_tables)
                if resolved:
                    r_tbl, r_col = resolved
                    # Ensure target column is actually numeric
                    t_meta_r = schema.tables.get(r_tbl)
                    is_num = any(
                        c.name == r_col and self._is_numeric_type(c.data_type)
                        for c in (t_meta_r.columns if t_meta_r else [])
                    )
                    if is_num and (func_name, r_col) not in seen_metric_keys:
                        seen_metric_keys.add((func_name, r_col))
                        prefix = "highest" if func_name == "MAX" else ("lowest" if func_name == "MIN" else ("total" if func_name == "SUM" else "avg"))
                        metric_agg_specs.append({
                            "func": func_name,
                            "column": r_col,
                            "table": r_tbl,
                            "alias": f"{prefix}_{r_col}"
                        })

        active_agg = None
        if not slots.limit and not (is_who_which and has_superlative):
            if re.search(r"\b(how\s+many|count\b|total\s+number|number\s+of|total\s+count)\b", q_lower):
                active_agg = "COUNT"
            elif re.search(r"\b(total|sum\b|sum\s+of)\b", q_lower):
                # If query says "total students", "total courses", "total matches", "total products" (entity counting)
                if any(re.search(r"\btotal\s+" + re.escape(tbl) + r"\b", q_lower) for tbl in schema.tables.keys()) or \
                   re.search(r"\btotal\s+(students?|courses?|departments?|matches?|products?|orders?|items?|records?)\b", q_lower):
                    active_agg = "COUNT"
                else:
                    active_agg = "SUM"
            elif re.search(r"\b(average\b|avg\b|mean\b|average\s+of)\b", q_lower):
                active_agg = "AVG"
            elif re.search(r"\b(highest|maximum|max\b|top\s+score|best\s+score|peak)\b", q_lower):
                active_agg = "MAX"
            elif re.search(r"\b(lowest|minimum|min\b|least)\b", q_lower):
                active_agg = "MIN"

        # 6. Identify Order By & Direction (handles 'sorted by countries', 'order by net sales', etc.)
        sort_dir = "ASC" if re.search(r"\b(asc|ascending|lowest\s+first|least|bottom|worst|minimum)\b", q_lower) else "DESC"

        m_sort = re.search(
            r"\b(?:sort|sorted|order|ordered|arrange|arranged)\s+(?:them\s+|all\s+|results?\s+)?(?:by\s+)?([a-zA-Z_]+(?:\s+[a-zA-Z_]+)?)\b",
            q_lower
        )
        if m_sort:
            raw_phrase = m_sort.group(1).strip()
            raw_tokens = raw_phrase.split()
            # Drop trailing sort direction / filler words if captured as 2nd token
            while len(raw_tokens) > 1 and raw_tokens[-1] in ("asc", "desc", "ascending", "descending", "give", "with", "and"):
                raw_tokens.pop()
            clean_phrase = " ".join(raw_tokens)
            if clean_phrase and clean_phrase not in ("asc", "desc", "ascending", "descending"):
                resolved_sort = self._resolve_col_phrase(clean_phrase, schema, ranked_tables)
                if resolved_sort:
                    s_tbl, s_col = resolved_sort
                    # If sorting by a text dimension without explicit asc/desc direction, default A-Z
                    col_is_num = any(
                        c.name == s_col and self._is_numeric_type(c.data_type)
                        for c in schema.tables[s_tbl].columns
                    )
                    explicit_dir = bool(re.search(r"\b(asc|ascending|desc|descending)\b", q_lower))
                    effective_dir = sort_dir if (col_is_num or explicit_dir) else "ASC"
                    slots.order_by = {"column": s_col, "direction": effective_dir}
                else:
                    mapped_col = self.SYNONYMS.get(clean_phrase, self._singularize(clean_phrase))
                    slots.order_by = {"column": mapped_col, "direction": sort_dir}
        elif is_who_which and has_superlative:
            sort_col = None
            if any(w in q_lower for w in ["score", "mark", "marks"]):
                sort_col = "score"
            elif "attendance" in q_lower:
                sort_col = "attendance_percentage"
            elif any(w in q_lower for w in ["revenue", "sales", "spending"]):
                sort_col = "revenue"
            elif any(w in q_lower for w in ["highscore", "run", "runs"]):
                sort_col = "highscore"
            elif "credit" in q_lower:
                sort_col = "credits"
            elif "price" in q_lower:
                sort_col = "price"
            if sort_col:
                slots.order_by = {"column": sort_col, "direction": sort_dir}

        # 7. Extract Filters
        # Look for numeric comparisons: e.g. "score > 80", "attendance >= 90"
        m_filters = re.findall(
            r"\b([a-zA-Z_]+)\s*([><]=?|!=|=|\babove\b|\bover\b|\bgreater\s+than\b|\bless\s+than\b|\bbelow\b)\s*(\d+(?:\.\d+)?)\b",
            q_lower
        )
        for f_col, f_op, f_val in m_filters:
            op_norm = f_op.strip()
            if op_norm in ("above", "over", "greater than"):
                op_norm = ">"
            elif op_norm in ("less than", "below"):
                op_norm = "<"
            
            # Map column name to schema
            mapped_col = self.SYNONYMS.get(f_col, f_col)
            slots.filters.append({
                "column": mapped_col,
                "op": op_norm,
                "value": float(f_val) if "." in f_val else int(f_val)
            })

        # Look for string/category filters: e.g. "category = 'Electronics'" or "in Electronics"
        # Cricket Teams: CSK, MI, RCB, KKR, GT, DC, LSG, SRH, RR, PK/PBKS
        team_map = {
            "csk": "Chennai Super Kings",
            "chennai super kings": "Chennai Super Kings",
            "mi": "Mumbai Indians",
            "mumbai indians": "Mumbai Indians",
            "rcb": "Royal Challengers Bangalore",
            "royal challengers bengaluru": "Royal Challengers Bangalore",
            "rcb": "Royal Challengers Bangalore",
            "kkr": "Kolkata Knight Riders",
            "kolkata knight riders": "Kolkata Knight Riders",
            "gt": "Gujarat Titans",
            "gujarat titans": "Gujarat Titans",
            "dc": "Delhi Capitals",
            "delhi capitals": "Delhi Capitals",
            "lsg": "Lucknow Super Giants",
            "lucknow super giants": "Lucknow Super Giants",
            "srh": "Sunrisers Hyderabad",
            "sunrisers hyderabad": "Sunrisers Hyderabad",
            "rr": "Rajasthan Royals",
            "rajasthan royals": "Rajasthan Royals"
        }
        ipl_teams_detected = []
        for team_key, team_full in team_map.items():
            if re.search(rf"\b{re.escape(team_key)}\b", q_lower):
                if team_full not in ipl_teams_detected:
                    ipl_teams_detected.append(team_full)

        if ipl_teams_detected and "ipl" in schema.tables:
            candidate_tables.add("ipl")
            if len(ipl_teams_detected) >= 2:
                t1, t2 = ipl_teams_detected[0], ipl_teams_detected[1]
                slots.filters.append({
                    "raw": f"((team1 = '{t1}' AND team2 = '{t2}') OR (team1 = '{t2}' AND team2 = '{t1}'))"
                })
            else:
                team_full = ipl_teams_detected[0]
                if "toss" in q_lower and any(w in q_lower for w in ["won", "win", "wins", "winner"]):
                    slots.filters.append({
                        "column": "toss_winner",
                        "op": "=",
                        "value": team_full
                    })
                elif any(w in q_lower for w in ["won", "win", "wins", "winner"]):
                    slots.filters.append({
                        "column": "match_winner",
                        "op": "=",
                        "value": team_full
                    })
                else:
                    slots.filters.append({
                        "raw": f"(team1 = '{team_full}' OR team2 = '{team_full}')"
                    })

        # E-Commerce Product Categories
        for cat in ["Laptops", "Smartphones", "Audio", "Monitors", "Accessories", "Electronics"]:
            if cat.lower() in q_lower and "sarah_products" in schema.tables:
                candidate_tables.add("sarah_products")
                slots.filters.append({
                    "column": "category",
                    "op": "=",
                    "value": cat
                })
                break

        # Academic Departments
        for dept in ["Computer Science", "Data Science", "Mechanical Engineering"]:
            if dept.lower() in q_lower:
                candidate_tables.add("departments")
                if "departments" in schema.tables:
                    slots.filters.append({
                        "column": "name" if "name" in [c.name for c in schema.tables["departments"].columns] else "departments.name",
                        "op": "=",
                        "value": dept
                    })
                break

        # Academic Courses / Subjects
        course_subjects = [
            ("Mathematics", "Math"), ("Physics", "Physics"), ("Chemistry", "Chemistry"),
            ("Computer Science", "CS"), ("Algorithms", "Algorithms"), ("Data Structures", "Data Structures"),
            ("Statistics", "Statistics")
        ]
        for subj_name, subj_kw in course_subjects:
            if re.search(r"\b" + re.escape(subj_kw.lower()) + r"\b", q_lower) or re.search(r"\b" + re.escape(subj_name.lower()) + r"\b", q_lower):
                if "courses" in schema.tables:
                    candidate_tables.add("courses")
                    slots.filters.append({
                        "column": "courses.title" if len(candidate_tables) > 1 else "title",
                        "op": "LIKE",
                        "value": f"%{subj_kw}%"
                    })
                break

        # Match cities: Mumbai, Delhi, Pune, Bangalore, Ahmedabad, Chennai, Kolkata, Lucknow
        for city in ["Mumbai", "Delhi", "Pune", "Bangalore", "Ahmedabad", "Chennai", "Kolkata", "Lucknow"]:
            if city.lower() in q_lower:
                slots.filters.append({
                    "column": "city",
                    "op": "=",
                    "value": city
                })

        # Identify Group By from "by <term>" or "per <term>" (ignoring "sort/order by <term>")
        m_group = re.search(r"\b(?<!sort\s)(?<!sorted\s)(?<!order\s)(?<!ordered\s)(?:by|per|group\s+by|grouped\s+by)\s+([a-zA-Z_]+)\b", q_lower)
        if m_group:
            raw_group = m_group.group(1).lower()
            mapped_group = self.SYNONYMS.get(raw_group, self._singularize(raw_group))
            found_group_col = None
            for tbl_name in ranked_tables + [t for t in schema.tables.keys() if t not in ranked_tables]:
                tbl_meta = schema.tables[tbl_name]
                if raw_group == tbl_name or raw_group == tbl_name.rstrip("s") or mapped_group == tbl_name:
                    candidate_tables.add(tbl_name)
                    for c in tbl_meta.columns:
                        if c.name in ("name", "title", "code"):
                            found_group_col = f"{tbl_name}.{c.name}"
                            break
                    if not found_group_col and tbl_meta.columns:
                        found_group_col = f"{tbl_name}.{tbl_meta.columns[0].name}"
                    break
                for c in tbl_meta.columns:
                    c_clean = c.name.lower()
                    if raw_group == c_clean or mapped_group == c_clean:
                        candidate_tables.add(tbl_name)
                        found_group_col = f"{tbl_name}.{c.name}" if len(candidate_tables) > 1 else c.name
                        break
                if found_group_col:
                    break
            if found_group_col and found_group_col not in slots.group_by:
                slots.group_by.append(found_group_col)

        # Retain prior context filters if this turn is a follow-up
        if is_followup and context_filters:
            slots.is_context_followup = True
            slots.context_notes = f"Continued context from {context_table}"
            existing_cols = {f.get("column", "").lower() for f in slots.filters if "column" in f}
            for cond in context_filters:
                cond_cols = re.findall(r"\b([a-zA-Z_]+)\b", cond)
                # Only inherit prior condition if user hasn't explicitly re-filtered that column in this turn
                if not any(c.lower() in existing_cols for c in cond_cols):
                    slots.filters.append({"raw": cond})

        # Order candidate tables by relevance score descending
        slots.tables = sorted(candidate_tables, key=lambda t: table_scores.get(t, 0), reverse=True)

        primary_cand = slots.tables[0] if slots.tables else None
        primary_cand_cols = {c.name.lower() for c in schema.tables[primary_cand].columns} if (primary_cand and primary_cand in schema.tables) else set()

        # Check explicit dimension columns matched in query for primary candidate
        matched_dims_on_primary = [
            m["column"] for m in matched_cols_info
            if m["table"] == primary_cand and not self._is_numeric_type(m["data_type"]) and self._is_metric_col_name(m["column"])
        ]
        # Filter metric_agg_specs that actually belong to primary_cand (or reachable joined table)
        valid_metric_aggs = [
            a for a in metric_agg_specs
            if a["column"].lower() in primary_cand_cols or (primary_cand and self.resolve_join_path([primary_cand, a["table"]], schema))
        ]

        if active_agg:
            # Prefer multiple matched metric aggregations if explicitly requested (e.g. "total revenue and highest profit")
            if len(valid_metric_aggs) >= 2 and active_agg != "COUNT":
                slots.aggregations.extend([
                    {"func": a["func"], "column": a["column"], "alias": a["alias"]}
                    for a in valid_metric_aggs
                ])
            else:
                target_metric_col = "*"
                if active_agg != "COUNT" and matched_columns:
                    # Prefer numeric columns on highest-scoring candidate tables
                    group_col_names = {g.split(".")[-1].lower() for g in slots.group_by}
                    ordered_matches = sorted(
                        matched_cols_info,
                        key=lambda m: (0 if m["table"] == primary_cand else 1, -m["score"], m["pos"])
                    )
                    candidate_metric_cols = [
                        (m["table"], m["column"]) for m in ordered_matches
                        if m["column"].lower() not in group_col_names and self._is_numeric_type(m["data_type"]) and self._is_metric_col_name(m["column"])
                    ]
                    if not candidate_metric_cols:
                        candidate_metric_cols = [
                            (m["table"], m["column"]) for m in ordered_matches
                            if m["column"].lower() not in group_col_names
                        ]
                    if candidate_metric_cols:
                        target_metric_col = candidate_metric_cols[0][1]
                slots.aggregations.append({"func": active_agg, "column": target_metric_col})
        elif slots.limit and valid_metric_aggs and (slots.group_by or (matched_dims_on_primary and len(valid_metric_aggs) >= 2) or (matched_dims_on_primary and any(a["func"] in ("SUM", "AVG") for a in valid_metric_aggs))):
            # Grouped Top-N analytical query (e.g. "Top 3 products with highest net sales, total revenue")
            for dim_c in matched_dims_on_primary:
                if dim_c not in slots.group_by and not any(g.endswith(f".{dim_c}") for g in slots.group_by):
                    slots.group_by.append(dim_c)
            if slots.order_by and not any(
                c.name == slots.order_by["column"] and self._is_numeric_type(c.data_type)
                for t in slots.tables if t in schema.tables
                for c in schema.tables[t].columns
            ):
                s_col = slots.order_by["column"]
                if s_col in primary_cand_cols and s_col not in slots.group_by:
                    slots.group_by.append(s_col)
            slots.aggregations.extend([
                {"func": a["func"], "column": a["column"], "alias": a["alias"]}
                for a in valid_metric_aggs
            ])

        return slots

    def resolve_join_path(self, tables: List[str], schema: DatabaseSchema) -> List[str]:
        """
        Resolves SQL JOIN clauses between multiple tables using BFS on foreign key relationships.
        Handles direct and multi-hop relationships (e.g. departments <-> marks via students).
        """
        if len(tables) <= 1:
            return []

        rels = schema.get_all_relationships()
        from collections import deque

        # Build undirected graph of table relationships
        adj = {}
        for r in rels:
            s = r["source_table"].lower()
            t = r["target_table"].lower()
            cond = r["join_condition"]
            adj.setdefault(s, []).append((t, cond))
            adj.setdefault(t, []).append((s, cond))

        primary = tables[0].lower()
        visited = {primary}
        join_clauses = []

        for target in tables[1:]:
            t_low = target.lower()
            if t_low in visited:
                continue

            # BFS from any currently visited table to t_low
            queue = deque([(v_tbl, [v_tbl]) for v_tbl in list(visited)])
            seen_nodes = set(visited)
            found_path = None
            path_conds = {}

            while queue:
                curr, path = queue.popleft()
                if curr == t_low:
                    found_path = path
                    break
                for nxt, cond in adj.get(curr, []):
                    if nxt not in seen_nodes:
                        seen_nodes.add(nxt)
                        path_conds[(curr, nxt)] = cond
                        path_conds[(nxt, curr)] = cond
                        queue.append((nxt, path + [nxt]))

            if found_path and len(found_path) > 1:
                for i in range(len(found_path) - 1):
                    node_a = found_path[i]
                    node_b = found_path[i + 1]
                    if node_b not in visited:
                        cond = path_conds.get((node_a, node_b)) or path_conds.get((node_b, node_a))
                        if cond:
                            join_clauses.append(f"JOIN {node_b} ON {cond}")
                            visited.add(node_b)

        return join_clauses

    def generate_sql(
        self, 
        query: str, 
        schema: Optional[DatabaseSchema],
        history: Optional[List[Dict[str, Any]]] = None
    ) -> Tuple[str, str]:
        """Generates a complete PostgreSQL SQL query and analytical explanation locally."""
        # 1. Pure Formula Check
        formula_sql = self.parse_formula(query)
        if formula_sql:
            return formula_sql, "Evaluated standalone mathematical/domain formula directly."

        if not schema or not schema.tables:
            return "SELECT 1;", "No active schema available."

        slots = self.extract_slots(query, schema, history=history)
        if slots.is_formula and slots.formula_expression:
            return slots.formula_expression, "Computed domain analytics and formula directly."
        q_lower = query.lower()

        # Check if an aggregation was requested on a column not in candidate tables
        if slots.aggregations and slots.aggregations[0]["column"] != "*":
            target_metric_col = slots.aggregations[0]["column"].lower()
            # If not in any current slot table, find which table in schema owns it
            owns_target = any(
                target_metric_col in [c.name.lower() for c in schema.tables[t].columns]
                for t in slots.tables if t in schema.tables
            )
            if not owns_target:
                for s_tbl, s_meta in schema.tables.items():
                    if target_metric_col in [c.name.lower() for c in s_meta.columns]:
                        slots.tables.append(s_tbl)
                        break

        # Primary Table
        if not slots.tables:
            # Check history first
            hist_tbl = None
            if history:
                for h in reversed(history):
                    content = str(h.get("content", "")) + " " + str(h.get("sql", ""))
                    for t in schema.tables.keys():
                        if t.lower() in content.lower():
                            hist_tbl = t
                            break
                    if hist_tbl:
                        break

            if hist_tbl:
                primary_table = hist_tbl
            elif any(k in q_lower for k in ["sale", "revenue", "store", "units"]):
                primary_table = "sales" if "sales" in schema.tables else list(schema.tables.keys())[0]
            elif any(k in q_lower for k in ["course", "subject", "credit"]):
                primary_table = "courses" if "courses" in schema.tables else list(schema.tables.keys())[0]
            elif any(k in q_lower for k in ["dept", "department"]):
                primary_table = "departments" if "departments" in schema.tables else list(schema.tables.keys())[0]
            elif any(k in q_lower for k in ["mark", "score", "grade"]):
                primary_table = "marks" if "marks" in schema.tables else list(schema.tables.keys())[0]
            elif any(k in q_lower for k in ["match", "cricket", "ipl", "wicket", "bowler", "scorer", "runs", "toss", "venue"]):
                primary_table = "ipl" if "ipl" in schema.tables else list(schema.tables.keys())[0]
            elif any(k in q_lower for k in ["product", "products", "item", "inventory"]):
                primary_table = "sarah_products" if "sarah_products" in schema.tables else list(schema.tables.keys())[0]
            else:
                primary_table = "students" if "students" in schema.tables else list(schema.tables.keys())[0]
            slots.tables = [primary_table]
        else:
            primary_table = slots.tables[0]

        # Prioritize table that matches best by table_scores and owns requested metrics
        best_score = slots.table_scores.get(primary_table, 0)
        if slots.aggregations and slots.aggregations[0]["column"] != "*":
            target_metric = slots.aggregations[0]["column"].lower()
            cur_has_metric = primary_table in schema.tables and target_metric in [c.name.lower() for c in schema.tables[primary_table].columns]
            if not cur_has_metric:
                for t in list(slots.tables):
                    if t in schema.tables:
                        col_names_in_t = [c.name.lower() for c in schema.tables[t].columns]
                        if target_metric in col_names_in_t:
                            primary_table = t
                            slots.tables = [t] + [x for x in slots.tables if x != t]
                            break
        elif best_score < 15:
            if any(k in q_lower for k in ["sale", "revenue", "store", "units"]) and "sales" in schema.tables:
                if slots.table_scores.get("sales", 0) >= best_score:
                    primary_table = "sales"
                    slots.tables = ["sales"] + [x for x in slots.tables if x != "sales"]
            elif any(k in q_lower for k in ["product", "item", "inventory"]) and "sarah_products" in schema.tables:
                if slots.table_scores.get("sarah_products", 0) >= best_score:
                    primary_table = "sarah_products"
                    slots.tables = ["sarah_products"] + [x for x in slots.tables if x != "sarah_products"]
            elif any(k in q_lower for k in ["match", "cricket", "ipl", "wicket", "bowler", "scorer"]) and "ipl" in schema.tables:
                if slots.table_scores.get("ipl", 0) >= best_score:
                    primary_table = "ipl"
                    slots.tables = ["ipl"] + [x for x in slots.tables if x != "ipl"]

        # Ensure any tables referenced in group_by are included
        for g_expr in slots.group_by:
            if "." in g_expr:
                g_tbl = g_expr.split(".")[0].strip()
                if g_tbl in schema.tables and g_tbl not in slots.tables:
                    slots.tables.append(g_tbl)

        # Prune tables that have no foreign key path to primary_table
        if len(slots.tables) > 1:
            reachable = [primary_table]
            for cand in slots.tables[1:]:
                path = self.resolve_join_path([primary_table, cand], schema)
                if path:
                    reachable.append(cand)
            slots.tables = reachable

        tbl_meta = schema.tables.get(primary_table)
        col_names = [c.name for c in tbl_meta.columns] if tbl_meta else []
        col_types_by_tbl = {
            t: {c.name.lower(): c for c in schema.tables[t].columns}
            for t in slots.tables if t in schema.tables
        }

        def qualify_col(tbl_n: str, col_n: str) -> str:
            return f"{tbl_n}.{col_n}" if len(slots.tables) > 1 else col_n

        def find_col_in_active_tables(col_raw: str) -> Optional[Tuple[str, ColumnMeta]]:
            c_low = col_raw.split(".")[-1].lower()
            for t in slots.tables:
                if t in col_types_by_tbl and c_low in col_types_by_tbl[t]:
                    return t, col_types_by_tbl[t][c_low]
            return None

        # Projections
        projections: List[str] = []
        explanation_parts: List[str] = []
        agg_aliases: List[str] = []

        if slots.projections:
            for expr, alias in slots.projections:
                projections.append(f"{expr} AS {alias}" if alias else expr)
            explanation_parts.append(f"Ranked metrics for `{primary_table}`")
        elif slots.aggregations:
            seen_agg_exprs: Set[str] = set()
            for agg in slots.aggregations:
                func = agg["func"]
                target_col = agg["column"]

                found_pair = find_col_in_active_tables(target_col) if target_col != "*" else None
                if not found_pair and target_col != "*":
                    # Check remaining schema tables for the metric column
                    for t, s_meta in schema.tables.items():
                        c_map = {c.name.lower(): c for c in s_meta.columns}
                        if target_col.lower() in c_map:
                            if t not in slots.tables and self.resolve_join_path([primary_table, t], schema):
                                slots.tables.append(t)
                                col_types_by_tbl[t] = c_map
                                found_pair = (t, c_map[target_col.lower()])
                                break

                if target_col == "*" or not found_pair:
                    if func == "COUNT":
                        if "COUNT(*) AS total_count" not in projections:
                            projections.append("COUNT(*) AS total_count")
                            agg_aliases.append("total_count")
                            explanation_parts.append(f"Count of records in `{primary_table}`")
                    else:
                        numeric_cols = [
                            c.name for c in (tbl_meta.columns if tbl_meta else [])
                            if self._is_numeric_type(c.data_type) and self._is_metric_col_name(c.name)
                        ]
                        fallback_c = numeric_cols[0] if numeric_cols else "*"
                        if fallback_c != "*":
                            q_c = qualify_col(primary_table, fallback_c)
                            alias = agg.get("alias") or f"{func.lower()}_{fallback_c}"
                            expr = f"ROUND({func}({q_c}), 2) AS {alias}" if func == "AVG" else f"{func}({q_c}) AS {alias}"
                            if expr not in seen_agg_exprs:
                                seen_agg_exprs.add(expr)
                                projections.append(expr)
                                agg_aliases.append(alias)
                                explanation_parts.append(f"Computed {func} of `{q_c}`")
                        elif "COUNT(*) AS total_count" not in projections:
                            projections.append("COUNT(*) AS total_count")
                            agg_aliases.append("total_count")
                else:
                    f_tbl, f_col = found_pair
                    qualified_target_col = qualify_col(f_tbl, f_col.name)
                    alias = agg.get("alias") or f"{func.lower()}_{f_col.name}"
                    expr = f"ROUND({func}({qualified_target_col}), 2) AS {alias}" if func == "AVG" else f"{func}({qualified_target_col}) AS {alias}"
                    if expr not in seen_agg_exprs:
                        seen_agg_exprs.add(expr)
                        projections.append(expr)
                        agg_aliases.append(alias)
                        explanation_parts.append(f"Computed {func} of `{qualified_target_col}`")

            if slots.group_by:
                clean_group_cols = []
                for g_col in slots.group_by:
                    if len(slots.tables) == 1 and "." in g_col and g_col.split(".")[0].lower() == primary_table.lower():
                        g_col_clean = g_col.split(".", 1)[1]
                        clean_group_cols.append(g_col_clean)
                    elif "." in g_col:
                        clean_group_cols.append(f"{g_col} AS {g_col.replace('.', '_')}")
                    else:
                        clean_group_cols.append(g_col)
                projections = clean_group_cols + projections
        else:
            # 1. Include ALL explicitly prompted columns from active tables in mention order
            selected_col_keys: Set[Tuple[str, str]] = set()
            has_numeric_proj = False

            for m in slots.matched_columns:
                mt, mc = m["table"], m["column"]
                if mt not in slots.tables:
                    continue
                if (mt, mc) in selected_col_keys:
                    continue
                selected_col_keys.add((mt, mc))
                projections.append(qualify_col(mt, mc))
                if self._is_numeric_type(m["data_type"]) and self._is_metric_col_name(mc):
                    has_numeric_proj = True

            # 2. Check if order_by resolves cleanly to a valid active column & include it
            if slots.order_by and slots.order_by.get("column") not in (None, "*"):
                hit_sort = find_col_in_active_tables(slots.order_by["column"])
                if hit_sort:
                    st, sc_meta = hit_sort
                    if (st, sc_meta.name) not in selected_col_keys:
                        selected_col_keys.add((st, sc_meta.name))
                        projections.append(qualify_col(st, sc_meta.name))
                        if self._is_numeric_type(sc_meta.data_type) and self._is_metric_col_name(sc_meta.name):
                            has_numeric_proj = True

            # 3. If no columns matched (e.g. "Show summary and sample rows from X"), pick balanced text + figures
            if not projections:
                all_meta_cols = [c for c in (tbl_meta.columns if tbl_meta else []) if self._is_metric_col_name(c.name)]
                if not all_meta_cols and tbl_meta:
                    all_meta_cols = list(tbl_meta.columns)
                text_cols = [c for c in all_meta_cols if not self._is_numeric_type(c.data_type)]
                num_cols = [c for c in all_meta_cols if self._is_numeric_type(c.data_type)]
                balanced = text_cols[:3] + num_cols[:4]
                if not balanced:
                    balanced = all_meta_cols[:6]
                for c in balanced:
                    selected_col_keys.add((primary_table, c.name))
                    projections.append(qualify_col(primary_table, c.name))
                    if self._is_numeric_type(c.data_type):
                        has_numeric_proj = True

            # 4. Numeric Figures Guarantee: Never return ONLY text labels if user asked for figures or none matched
            if not has_numeric_proj or slots.wants_figures:
                current_num_count = sum(
                    1 for (t_k, c_k) in selected_col_keys
                    if t_k in col_types_by_tbl and c_k.lower() in col_types_by_tbl[t_k]
                    and self._is_numeric_type(col_types_by_tbl[t_k][c_k.lower()].data_type)
                    and self._is_metric_col_name(c_k)
                )
                target_num_min = 2 if slots.wants_figures else 1
                if current_num_count < target_num_min:
                    # Rank numeric columns by analytical significance
                    priority_rx = re.compile(r"(net_sales|gross_sales|revenue|net_profit|gross_profit|unit_price|price|inventory|units_sold|quantity|score|attendance|highscore|margin|amount|cost|rating)", re.I)
                    cand_nums = []
                    for t in slots.tables:
                        if t in schema.tables:
                            for c in schema.tables[t].columns:
                                if (t, c.name) not in selected_col_keys and self._is_numeric_type(c.data_type) and self._is_metric_col_name(c.name):
                                    prio = 0 if priority_rx.search(c.name) else 1
                                    cand_nums.append((prio, 0 if t == primary_table else 1, t, c))
                    cand_nums.sort(key=lambda x: (x[0], x[1]))
                    needed = max(0, (3 if slots.wants_figures else 2) - current_num_count)
                    for _, _, t_n, c_obj in cand_nums[:needed]:
                        selected_col_keys.add((t_n, c_obj.name))
                        projections.append(qualify_col(t_n, c_obj.name))

            if not projections:
                projections = ["*"]

            explanation_parts.append(f"Retrieved `{', '.join(projections)}` from `{primary_table}`")

        # Joins
        join_sql = ""
        if len(slots.tables) > 1:
            joins = self.resolve_join_path(slots.tables, schema)
            join_sql = " " + " ".join(joins)

        # Filters
        where_clauses = []
        for flt in slots.filters:
            if "raw" in flt:
                where_clauses.append(flt["raw"])
                explanation_parts.append(f"Retained filter `{flt['raw']}` from context")
                continue
            col = flt["column"]
            if col == "city" and "store_city" in col_names:
                col = "store_city"
            elif col == "city" and "city" in col_names:
                col = "city"
            elif len(slots.tables) > 1 and "." not in col:
                hit_f = find_col_in_active_tables(col)
                if hit_f:
                    col = f"{hit_f[0]}.{hit_f[1].name}"

            val = flt["value"]
            if flt.get("op") == "LIKE":
                val_str = f"'{val}'"
            else:
                val_str = f"'{val}'" if isinstance(val, str) else str(val)
            where_clauses.append(f"{col} {flt['op']} {val_str}")
            explanation_parts.append(f"Filtered where `{col}` {flt['op']} {val_str}")

        where_sql = f" WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        # Group By
        group_sql = ""
        if slots.group_by:
            clean_gb = [
                g.split(".", 1)[1] if (len(slots.tables) == 1 and "." in g and g.split(".")[0].lower() == primary_table.lower()) else g
                for g in slots.group_by
            ]
            group_sql = f" GROUP BY {', '.join(clean_gb)}"

        # Order By: Validate sort column against active tables or aliases
        order_sql = ""
        if slots.order_by:
            raw_sort = slots.order_by["column"]
            dir_str = slots.order_by.get("direction", "DESC")
            if raw_sort in agg_aliases or raw_sort == "awards_count":
                order_sql = f" ORDER BY {raw_sort} {dir_str}"
            else:
                hit_sort = find_col_in_active_tables(raw_sort)
                if hit_sort:
                    st, sc_meta = hit_sort
                    qualified_sort = qualify_col(st, sc_meta.name)
                    if slots.aggregations and slots.group_by and agg_aliases and slots.limit and not self._is_numeric_type(sc_meta.data_type):
                        # When ranking Top N with explicit metric + dimension sort, rank by primary metric first then tie-break by dimension
                        order_sql = f" ORDER BY {agg_aliases[0]} DESC, {qualified_sort} {dir_str}"
                    else:
                        order_sql = f" ORDER BY {qualified_sort} {dir_str}"
                elif agg_aliases:
                    order_sql = f" ORDER BY {agg_aliases[0]} DESC"
        elif slots.group_by:
            if agg_aliases:
                order_sql = f" ORDER BY {agg_aliases[0]} DESC"
            else:
                order_sql = " ORDER BY 2 DESC"
        elif not slots.aggregations:
            # Ensure ranking metric is both sorted AND included in SELECT projections
            if any(w in q_lower for w in ("highest", "top", "best", "lowest", "least")):
                sort_d = "ASC" if any(w in q_lower for w in ("lowest", "least")) else "DESC"
                metric_priority_rx = re.compile(r"(net_sales|gross_sales|revenue|net_profit|unit_price|price|score|attendance|highscore|inventory|units_sold|quantity)", re.I)
                num_cands = [
                    c.name for c in (tbl_meta.columns if tbl_meta else [])
                    if self._is_numeric_type(c.data_type) and self._is_metric_col_name(c.name)
                ]
                num_cands.sort(key=lambda n: 0 if metric_priority_rx.search(n) else 1)
                if num_cands:
                    rank_col = num_cands[0]
                    q_rank = qualify_col(primary_table, rank_col)
                    if q_rank not in projections and rank_col not in projections:
                        projections.append(q_rank)
                    order_sql = f" ORDER BY {q_rank} {sort_d}"

        # Limit
        limit_sql = f" LIMIT {slots.limit}" if slots.limit else ""
        if not limit_sql and not slots.aggregations and not where_clauses and not order_sql and not slots.group_by:
            limit_sql = " LIMIT 20"

        sql = f"SELECT {', '.join(projections)} FROM {primary_table}{join_sql}{where_sql}{group_sql}{order_sql}{limit_sql};"
        if slots.is_context_followup and slots.context_notes:
            explanation_parts.append(slots.context_notes)
        explanation = ". ".join(explanation_parts) + "."
        return sql, explanation


# Global singleton instance
local_nlp_engine = LocalNLPEngine()
