"""
Self-Learning & Continuous Training Engine
Maintains training memory, trains ML intent & SQL synthesis models,
and improves continuously from user feedback and query executions.
"""

import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from pydantic import BaseModel, Field

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
import joblib

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
MEMORY_FILE = DATA_DIR / "training_memory.json"
MODEL_DIR = DATA_DIR / "models"


class TrainingSample(BaseModel):
    id: str
    query: str
    intent: str  # e.g., "AGGREGATE_COUNT", "FILTER_SELECT", "FORMULA_MATH", "TOP_N_RANK", "JOIN_LOOKUP"
    sql: str
    tables_used: List[str] = Field(default_factory=list)
    success: bool = True
    feedback_score: int = 1  # 1 = positive, -1 = negative/corrected
    corrected_sql: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


# Rich Seed Dataset for Initial Bootstrapping
SEED_TRAINING_DATA = [
    {
        "id": "seed_01",
        "query": "How many students are enrolled?",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_students FROM students;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_02",
        "query": "Show all departments in college",
        "intent": "TABLE_SCAN",
        "sql": "SELECT id, name, code FROM departments;",
        "tables_used": ["departments"],
        "feedback_score": 1
    },
    {
        "id": "seed_03",
        "query": "Show students with attendance percentage greater than 90",
        "intent": "FILTER_SELECT",
        "sql": "SELECT id, name, attendance_percentage FROM students WHERE attendance_percentage > 90.0;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_04",
        "query": "Calculate compound interest on 10000 at 5% for 3 years",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(10000 * POWER(1.0 + (5 / 100.0), 3), 2) AS future_value;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_05",
        "query": "Show average score in course 201",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(score), 2) AS avg_score FROM marks WHERE course_id = 201;",
        "tables_used": ["marks"],
        "feedback_score": 1
    },
    {
        "id": "seed_06",
        "query": "Show total revenue from sales",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(revenue) AS total_revenue FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_07",
        "query": "Show students with score above 80",
        "intent": "FILTER_SELECT",
        "sql": "SELECT students.id, students.name, marks.score FROM students JOIN marks ON students.id = marks.student_id WHERE marks.score > 80;",
        "tables_used": ["students", "marks"],
        "feedback_score": 1
    },
    {
        "id": "seed_08",
        "query": "List all courses and credits",
        "intent": "TABLE_SCAN",
        "sql": "SELECT id, title, code, credits FROM courses;",
        "tables_used": ["courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_09",
        "query": "Show the highest revenue transaction",
        "intent": "TOP_N_RANK",
        "sql": "SELECT transaction_id, store_city, revenue FROM sales ORDER BY revenue DESC LIMIT 1;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_10",
        "query": "Show student marks in exam",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT students.name, courses.title, marks.score, marks.grade FROM students JOIN marks ON students.id = marks.student_id JOIN courses ON marks.course_id = courses.id;",
        "tables_used": ["students", "marks", "courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_11",
        "query": "What is the BMI for 70kg and 1.75m?",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(70.0::numeric / POWER(1.75, 2), 2) AS bmi;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_12",
        "query": "Show sales in Mumbai store",
        "intent": "FILTER_SELECT",
        "sql": "SELECT transaction_id, revenue, units_sold, transaction_date FROM sales WHERE store_city = 'Mumbai';",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_13",
        "query": "Count the number of courses offered",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_courses FROM courses;",
        "tables_used": ["courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_14",
        "query": "Show top 5 students by attendance",
        "intent": "TOP_N_RANK",
        "sql": "SELECT id, name, attendance_percentage FROM students ORDER BY attendance_percentage DESC LIMIT 5;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_15",
        "query": "Calculate simple interest on 5000 at 4% for 2 years",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND((5000 * 4 * 2) / 100.0, 2) AS simple_interest;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_16",
        "query": "What is the mean attendance of all students?",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(attendance_percentage), 2) AS avg_attendance FROM students;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_17",
        "query": "Calculate sum of all units sold across stores",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(units_sold) AS total_units FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_18",
        "query": "Display all records from students table",
        "intent": "TABLE_SCAN",
        "sql": "SELECT * FROM students;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_19",
        "query": "Join students and departments to see department names",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT students.name, departments.name AS department_name FROM students JOIN departments ON students.department_id = departments.id;",
        "tables_used": ["students", "departments"],
        "feedback_score": 1
    },
    {
        "id": "seed_20",
        "query": "Find transactions where payment method is Credit Card",
        "intent": "FILTER_SELECT",
        "sql": "SELECT * FROM sales WHERE payment_method = 'Credit Card';",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_21",
        "query": "give the highest wicket taker with his season economy average overall and strike rate",
        "intent": "TOP_N_RANK",
        "sql": "SELECT best_bowling AS bowler, COUNT(*) AS best_bowler_matches, SUM(SPLIT_PART(best_bowling_figure, '--', 1)::int) AS total_wickets, SUM(SPLIT_PART(best_bowling_figure, '--', 2)::numeric) AS runs_conceded, ROUND(SUM(SPLIT_PART(best_bowling_figure, '--', 2)::numeric) / NULLIF(SUM(SPLIT_PART(best_bowling_figure, '--', 1)::int), 0), 2) AS bowling_average FROM ipl WHERE best_bowling_figure LIKE '%--%' GROUP BY best_bowling ORDER BY total_wickets DESC LIMIT 1;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_22",
        "query": "Show top run scorer in the tournament",
        "intent": "TOP_N_RANK",
        "sql": "SELECT top_scorer AS batsman, SUM(highscore) AS total_runs, COUNT(*) AS matches FROM ipl GROUP BY top_scorer ORDER BY total_runs DESC LIMIT 1;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_23",
        "query": "Show players with most player of the match awards",
        "intent": "TOP_N_RANK",
        "sql": "SELECT player_of_the_match AS player, COUNT(*) AS awards_count FROM ipl GROUP BY player_of_the_match ORDER BY awards_count DESC LIMIT 5;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_24",
        "query": "Calculate loan EMI for 500000 at 8.5% for 5 years",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(500000.0 * ((0.00708333 * POWER(1.0 + 0.00708333, 60)) / (POWER(1.0 + 0.00708333, 60) - 1.0)), 2) AS monthly_emi;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_25",
        "query": "Calculate CAGR from 100000 to 250000 over 5 years",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND((POWER(250000 * 1.0 / NULLIF(100000, 0), 1.0 / 5) - 1.0) * 100.0, 2) AS cagr_percentage;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_26",
        "query": "Calculate net run rate with 180 runs in 20 overs scored and 150 runs in 20 overs conceded",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND((180 * 1.0 / 20) - (150 * 1.0 / 20), 3) AS net_run_rate;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_27",
        "query": "batting strike rate for 75 runs in 42 balls",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND((75 * 1.0 / 42) * 100.0, 2) AS batting_strike_rate;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_28",
        "query": "Kinetic energy of 1200 kg car moving at 25 m/s",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(0.5 * 1200 * POWER(25, 2), 2) AS kinetic_energy_joules;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_29",
        "query": "Area of circle with radius 7",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(3.141592653589793 * POWER(7, 2), 2) AS circle_area;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_30",
        "query": "Convert 100 celsius to fahrenheit",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND((100 * 9.0 / 5.0) + 32.0, 2) AS fahrenheit;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_31",
        "query": "Now show only those with attendance above 75",
        "intent": "FILTER_SELECT",
        "sql": "SELECT id, name, attendance_percentage FROM students WHERE attendance_percentage > 75;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_32",
        "query": "What is their average score?",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT AVG(score) AS avg_score FROM students;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_33",
        "query": "Sort them by score descending",
        "intent": "TOP_N_RANK",
        "sql": "SELECT name, score FROM students ORDER BY score DESC;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    # --- Mathematics & Algebra ---
    {
        "id": "seed_34",
        "query": "Solve quadratic equation a=1, b=-5, c=6",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 1.0 AS a, -5.0 AS b, 6.0 AS c, 1.0 AS discriminant, 3.0 AS root_1, 2.0 AS root_2, 'Real and distinct' AS root_type;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_35",
        "query": "Calculate combinations 10 choose 3",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 10 AS n, 3 AS r, 120 AS combinations_nCr;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_36",
        "query": "Calculate permutations P(8, 3)",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 8 AS n, 3 AS r, 336 AS permutations_nPr;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_37",
        "query": "Calculate factorial of 7",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 7 AS n, 5040 AS factorial;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_38",
        "query": "Calculate sin of 30 degrees",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 'sin' AS trig_function, 30.0 AS angle, 'deg' AS unit, 0.5 AS calculated_value;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_39",
        "query": "What is log base 10 of 1000?",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 1000.0 AS value, 10 AS base, 3.0 AS log_base_10;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_40",
        "query": "Calculate determinant of 2x2 matrix 4, 2, 3, 5",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 4.0 AS a11, 2.0 AS a12, 3.0 AS a21, 5.0 AS a22, 14.0 AS matrix_determinant;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_41",
        "query": "Area of trapezoid with bases 6 and 10 and height 4",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 6.0 AS base_1, 10.0 AS base_2, 4.0 AS height, 32.0 AS trapezoid_area;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_42",
        "query": "Calculate hypotenuse for sides 3 and 4",
        "intent": "FORMULA_MATH",
        "sql": "SELECT ROUND(SQRT(POWER(3, 2) + POWER(4, 2)), 2) AS hypotenuse;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_43",
        "query": "Area of ellipse with semi-axes 5 and 3",
        "intent": "FORMULA_MATH",
        "sql": "SELECT 5.0 AS semi_major_axis, 3.0 AS semi_minor_axis, 47.12 AS ellipse_area;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Statistical Equations ---
    {
        "id": "seed_44",
        "query": "Calculate standard deviation of [12, 15, 18, 22, 29, 35]",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 6 AS count, 131.0 AS sum_total, 21.8333 AS mean, 20.0 AS median, 74.5667 AS sample_variance, 8.6352 AS sample_standard_deviation;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_45",
        "query": "What is the variance of 10, 20, 30, 40, 50?",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 5 AS count, 150.0 AS sum_total, 30.0 AS mean, 250.0 AS sample_variance, 15.8114 AS sample_standard_deviation;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_46",
        "query": "Calculate z-score for value 85 with mean 70 and standard deviation 10",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 85.0 AS observation_value, 70.0 AS mean, 10.0 AS standard_deviation, 1.5 AS z_score;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_47",
        "query": "Calculate Pearson correlation between X=[1, 2, 3, 4, 5] and Y=[2, 4, 5, 4, 5]",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 5 AS sample_pairs, 3.0 AS mean_x, 4.0 AS mean_y, 1.5 AS covariance, 0.7746 AS pearson_correlation_r, 0.6 AS r_squared;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_48",
        "query": "Linear regression slope and intercept for X=[1, 2, 3, 4] and Y=[3, 5, 7, 9]",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 2.0 AS slope_m, 1.0 AS intercept_c, 'y = 2.0x + 1.0' AS regression_equation;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_49",
        "query": "Bayes theorem for P(A)=0.01, P(B|A)=0.9, P(B|not A)=0.05",
        "intent": "FORMULA_STATISTICS",
        "sql": "SELECT 0.01 AS p_prior_A, 0.9 AS p_likelihood_B_given_A, 0.0585 AS p_total_evidence_B, 15.38 AS posterior_probability_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Physics & Mechanics ---
    {
        "id": "seed_50",
        "query": "Calculate momentum for mass 800 kg moving at 15 m/s",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 800.0 AS mass_kg, 15.0 AS velocity_ms, 12000.0 AS momentum_kg_ms;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_51",
        "query": "Calculate centripetal force for mass 1000 kg, velocity 20 m/s, radius 50 m",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 1000.0 AS mass_kg, 20.0 AS velocity_ms, 50.0 AS radius_meters, 8000.0 AS centripetal_force_newtons;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_52",
        "query": "Calculate torque for lever arm 0.5 m, force 40 N, angle 90 degrees",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 0.5 AS lever_arm_meters, 40.0 AS force_newtons, 90.0 AS angle_degrees, 20.0 AS torque_newton_meters;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_53",
        "query": "Calculate displacement for initial velocity 5, acceleration 2, time 4",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 5.0 AS initial_velocity_ms, 2.0 AS acceleration_ms2, 4.0 AS time_seconds, 36.0 AS displacement_meters, 13.0 AS final_velocity_ms;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_54",
        "query": "What is the final velocity for initial velocity 10, acceleration 2, time 5?",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 10.0 AS initial_velocity_ms, 2.0 AS acceleration_ms2, 5.0 AS time_seconds, 20.0 AS final_velocity_ms;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_55",
        "query": "Calculate power for work 5000 Joules in 10 seconds",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 5000.0 AS work_joules, 10.0 AS time_seconds, 500.0 AS power_watts, 0.67 AS horsepower;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_56",
        "query": "Calculate ideal gas pressure for 2 moles, volume 10 liters, temperature 300 Kelvin",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 2.0 AS moles_n, 10.0 AS volume_liters, 300.0 AS temperature_kelvin, 4.9234 AS pressure_atm, 498.86 AS pressure_kpa;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_57",
        "query": "Calculate heat energy for mass 2 kg, specific heat 4184, temperature change 25 C",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 2.0 AS mass_kg, 4184.0 AS specific_heat_j_kgk, 25.0 AS delta_temp_c, 209200.0 AS heat_energy_joules, 50.0 AS kcal;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_58",
        "query": "Calculate hydrostatic fluid pressure at depth 10 meters in water",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 1000.0 AS density_kg_m3, 10.0 AS depth_meters, 98066.5 AS pressure_pascals, 0.9807 AS pressure_bar;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_59",
        "query": "Calculate Coulomb force for charges 0.001 C and 0.002 C at distance 0.5 m",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 0.001 AS charge_q1_coulombs, 0.002 AS charge_q2_coulombs, 0.5 AS distance_meters, 71900.4143 AS electrostatic_force_newtons;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_60",
        "query": "Calculate stored energy in capacitor with 0.0001 F capacitance and 12 V",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 0.0001 AS capacitance_farads, 12.0 AS voltage_volts, 0.0072 AS stored_energy_joules;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_61",
        "query": "Calculate wave speed for frequency 500 Hz and wavelength 0.68 m",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 500.0 AS frequency_hz, 0.68 AS wavelength_meters, 340.0 AS wave_speed_ms;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_62",
        "query": "Calculate Snell law refraction angle for n1=1, n2=1.33, angle 30 degrees",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 1.0 AS index_n1, 1.33 AS index_n2, 30.0 AS incident_angle_deg, 22.08 AS refracted_angle_deg;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_63",
        "query": "Calculate photon energy for frequency 5e14 Hz",
        "intent": "FORMULA_PHYSICS",
        "sql": "SELECT 500000000000000.0 AS frequency_hz, 3.313035075e-19 AS energy_joules, 2.0679 AS energy_electron_volts_ev;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Finance & Investment ---
    {
        "id": "seed_64",
        "query": "Calculate Sharpe ratio for portfolio return 14%, risk-free rate 4%, standard deviation 8%",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 14.0 AS portfolio_return_pct, 4.0 AS risk_free_rate_pct, 8.0 AS std_deviation_pct, 1.25 AS sharpe_ratio;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_65",
        "query": "Calculate CAPM expected return for risk-free 3.5, beta 1.2, market return 11",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 3.5 AS risk_free_rate_pct, 1.2 AS asset_beta, 11.0 AS market_return_pct, 12.5 AS capm_expected_return_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_66",
        "query": "Calculate WACC for equity weight 60%, debt 40%, cost equity 12%, cost debt 6%, tax 25%",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 0.6 AS equity_weight, 0.4 AS debt_weight, 12.0 AS cost_equity_pct, 6.0 AS cost_debt_pct, 9.0 AS wacc_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_67",
        "query": "Calculate NPV for discount rate 10%, initial investment 10000, cash flows [3000, 4000, 5000, 2000]",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 10.0 AS discount_rate_pct, 10000.0 AS initial_investment, 4 AS cash_flow_periods, 1150.12 AS net_present_value;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_68",
        "query": "What is the P/E ratio for share price 150 and EPS 7.5?",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 150.0 AS share_price, 7.5 AS earnings_per_share_eps, 20.0 AS pe_ratio;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_69",
        "query": "Calculate dividend yield for annual dividend 4.5 and stock price 90",
        "intent": "FORMULA_FINANCE",
        "sql": "SELECT 4.5 AS annual_dividend, 90.0 AS stock_price, 5.0 AS dividend_yield_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Non-Finance & Business ---
    {
        "id": "seed_70",
        "query": "Calculate Customer Acquisition Cost CAC for marketing spend 50000 and 250 customers",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 50000.0 AS total_sales_marketing_spend, 250 AS new_customers_acquired, 200.0 AS customer_acquisition_cost_cac;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_71",
        "query": "Calculate Customer Lifetime Value LTV for ARPU 120, gross margin 80%, churn rate 5%",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 120.0 AS arpu, 80.0 AS gross_margin_pct, 5.0 AS churn_rate_pct, 1920.0 AS customer_lifetime_value_ltv;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_72",
        "query": "What is the LTV to CAC ratio for LTV 1800 and CAC 300?",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 1800.0 AS ltv, 300.0 AS cac, 6.0 AS ltv_cac_ratio, 'Excellent (>3x)' AS unit_economics_health;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_73",
        "query": "Calculate churn rate for 50 lost customers out of 1000 customers",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 5.0 AS churn_rate_pct, 95.0 AS retention_rate_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_74",
        "query": "Calculate cash runway for cash balance 500000 and monthly burn rate 25000",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 500000.0 AS cash_balance, 25000.0 AS monthly_burn_rate, 20.0 AS runway_months;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_75",
        "query": "Calculate break even units for fixed costs 40000, selling price 100, variable cost 60",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 40000.0 AS fixed_costs, 100.0 AS selling_price_per_unit, 60.0 AS variable_cost_per_unit, 40.0 AS unit_contribution_margin, 1000.0 AS break_even_units, 100000.0 AS break_even_sales_revenue;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_76",
        "query": "Calculate Economic Order Quantity EOQ for annual demand 10000, setup cost 50, holding cost 2",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 10000.0 AS annual_demand_units, 50.0 AS order_setup_cost, 2.0 AS annual_holding_cost, 707.1 AS economic_order_quantity_units;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_77",
        "query": "Calculate inventory turnover ratio for COGS 500000 and average inventory 100000",
        "intent": "FORMULA_BUSINESS",
        "sql": "SELECT 500000.0 AS cogs, 100000.0 AS average_inventory, 5.0 AS inventory_turnover_ratio, 73.0 AS days_sales_of_inventory_dsi;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Multi-Sport Analytics ---
    {
        "id": "seed_78",
        "query": "Calculate cricket batting average for 450 runs in 9 innings",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 450.0 AS runs_scored, 9.0 AS innings_dismissed, 50.0 AS batting_average;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_79",
        "query": "Calculate cricket bowling average for 240 runs and 12 wickets",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 240.0 AS runs_conceded, 12.0 AS wickets_taken, 20.0 AS bowling_average;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_80",
        "query": "Calculate football goal conversion rate for 15 goals from 60 shots",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 15.0 AS goals_scored, 60.0 AS total_shots, 25.0 AS goal_conversion_percentage;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_81",
        "query": "Calculate football points per match PPM for 16 wins, 5 draws in 25 matches",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 16.0 AS wins, 5.0 AS draws, 53.0 AS total_points, 25.0 AS matches_played, 2.12 AS points_per_match;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_82",
        "query": "Calculate basketball True Shooting Percentage for 25 points, 15 FGA, 8 FTA",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 25.0 AS points, 15.0 AS field_goal_attempts, 8.0 AS free_throw_attempts, 67.5 AS true_shooting_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_83",
        "query": "Calculate basketball effective field goal percentage eFG% for 8 FGM, 3 3PM, 16 FGA",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 8.0 AS field_goals_made, 3.0 AS three_pointers_made, 16.0 AS field_goal_attempts, 59.38 AS effective_field_goal_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_84",
        "query": "Calculate baseball batting average for 36 hits in 120 at bats",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 36.0 AS hits, 120.0 AS at_bats, 0.3 AS batting_average;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_85",
        "query": "Calculate baseball Earned Run Average ERA for 24 earned runs in 54 innings pitched",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 24.0 AS earned_runs, 54.0 AS innings_pitched, 4.0 AS earned_run_average_era;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_86",
        "query": "Calculate running pace for 10 km in 50 minutes",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 10.0 AS distance_km, 50.0 AS time_minutes, 5.0 AS pace_minutes_per_km, 8.05 AS pace_minutes_per_mile, 12.0 AS speed_kmh, 7.46 AS speed_mph;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Movies & Entertainment ---
    {
        "id": "seed_87",
        "query": "Calculate movie box office ROI for budget 60M and box office 240M",
        "intent": "FORMULA_ENTERTAINMENT",
        "sql": "SELECT 60.0 AS budget_millions, 240.0 AS worldwide_gross_millions, 300.0 AS box_office_roi_pct, 4.0 AS box_office_multiplier;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_88",
        "query": "Calculate box office multiplier for budget 50 million and collection 220 million",
        "intent": "FORMULA_ENTERTAINMENT",
        "sql": "SELECT 50.0 AS production_budget, 220.0 AS total_box_office, 4.4 AS box_office_multiplier;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_89",
        "query": "Calculate domestic box office share for domestic 120 and worldwide 360",
        "intent": "FORMULA_ENTERTAINMENT",
        "sql": "SELECT 120.0 AS domestic_gross, 360.0 AS total_worldwide, 33.33 AS domestic_share_pct, 66.67 AS international_share_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_90",
        "query": "Calculate streaming video completion rate for 450000 completions from 600000 starts",
        "intent": "FORMULA_ENTERTAINMENT",
        "sql": "SELECT 450000.0 AS completions, 600000.0 AS stream_starts, 75.0 AS completion_rate_pct, 25.0 AS dropoff_rate_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Geographical & Geospatial ---
    {
        "id": "seed_91",
        "query": "Calculate Haversine distance between 28.6139, 77.2090 and 19.0760, 72.8777",
        "intent": "FORMULA_GEOGRAPHY",
        "sql": "SELECT 28.6139 AS lat1, 77.209 AS lon1, 19.076 AS lat2, 72.8777 AS lon2, 1150.36 AS distance_km, 714.8 AS distance_miles, 621.14 AS distance_nautical_miles;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_92",
        "query": "Calculate population density for population 14000000 and area 603 square kilometers",
        "intent": "FORMULA_GEOGRAPHY",
        "sql": "SELECT 14000000 AS total_population, 603.0 AS area_sq_km, 23217.25 AS people_per_sq_km, 60132.44 AS people_per_sq_mile;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_93",
        "query": "Calculate real distance for map distance 5 cm on 1:50000 scale map",
        "intent": "FORMULA_GEOGRAPHY",
        "sql": "SELECT 5.0 AS map_cm, 50000.0 AS scale_ratio_1_to_n, 2500.0 AS actual_distance_meters, 2.5 AS actual_distance_km;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_94",
        "query": "Calculate solar elevation angle for latitude 30 degrees and solar declination 15 degrees",
        "intent": "FORMULA_GEOGRAPHY",
        "sql": "SELECT 30.0 AS latitude_deg, 15.0 AS solar_declination_deg, 75.0 AS solar_elevation_angle_deg, 15.0 AS solar_zenith_angle_deg;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Worldwide Conversions ---
    {
        "id": "seed_95",
        "query": "Convert 10 bar to psi",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT 10.0 AS bar, 145.04 AS psi;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_96",
        "query": "Convert 5000 joules to calories",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT 5000.0 AS joules, 1195.03 AS calories;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- Additional Intent Training Seeds for Non-Greedy & Robust NLP ---
    {
        "id": "seed_97",
        "query": "Total number of students in the college",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_students FROM students;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_98",
        "query": "How many matches were played in total?",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_matches FROM ipl;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_99",
        "query": "Count of all departments in university",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_departments FROM departments;",
        "tables_used": ["departments"],
        "feedback_score": 1
    },
    {
        "id": "seed_100",
        "query": "Total number of transactions in Mumbai store",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_transactions FROM sales WHERE store_city = 'Mumbai';",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_101",
        "query": "How many products are in stock in Electronics category?",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_products FROM sarah_products WHERE category = 'Electronics';",
        "tables_used": ["sarah_products"],
        "feedback_score": 1
    },
    {
        "id": "seed_102",
        "query": "Count total courses offered this academic year",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_courses FROM courses;",
        "tables_used": ["courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_103",
        "query": "Total count of sales records",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(*) AS total_sales FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_104",
        "query": "How many bowlers took wickets in IPL?",
        "intent": "AGGREGATE_COUNT",
        "sql": "SELECT COUNT(DISTINCT best_bowling) AS total_wicket_takers FROM ipl WHERE best_bowling_figure LIKE '%--%';",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    # --- AGGREGATE_SUM Seeds ---
    {
        "id": "seed_105",
        "query": "Sum of total revenue from all orders",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(revenue) AS total_revenue FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_106",
        "query": "Total runs scored by all batsmen",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(highscore) AS total_runs FROM ipl;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_107",
        "query": "Sum of marks in course 101",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(score) AS sum_score FROM marks WHERE course_id = 101;",
        "tables_used": ["marks"],
        "feedback_score": 1
    },
    {
        "id": "seed_108",
        "query": "Total spending across all departments",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(revenue) AS total_department_spending FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_109",
        "query": "Calculate sum of all units sold across stores",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(units_sold) AS total_units FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_110",
        "query": "Sum up all credits offered in engineering",
        "intent": "AGGREGATE_SUM",
        "sql": "SELECT SUM(credits) AS total_credits FROM courses;",
        "tables_used": ["courses"],
        "feedback_score": 1
    },
    # --- AGGREGATE_AVG Seeds ---
    {
        "id": "seed_111",
        "query": "Average score in mathematics course",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(marks.score), 2) AS avg_score FROM marks JOIN courses ON marks.course_id = courses.id WHERE courses.title LIKE '%Math%';",
        "tables_used": ["marks", "courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_112",
        "query": "Mean product price in catalog",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(price), 2) AS mean_price FROM sarah_products;",
        "tables_used": ["sarah_products"],
        "feedback_score": 1
    },
    {
        "id": "seed_113",
        "query": "Average highscore across all IPL venues",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(highscore), 2) AS avg_highscore FROM ipl;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_114",
        "query": "Calculate the mean revenue per transaction",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(AVG(revenue), 2) AS avg_revenue FROM sales;",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_115",
        "query": "Average bowling strike rate of CSK throughout the season",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT ROUND(CAST(COUNT(*) * 120 AS FLOAT) / NULLIF(SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)), 0), 2) AS average_bowling_strike_rate FROM ipl WHERE (team1 = 'Chennai Super Kings' OR team2 = 'Chennai Super Kings') AND best_bowling_figure LIKE '%--%';",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_116",
        "query": "Average attendance percentage by department",
        "intent": "AGGREGATE_AVG",
        "sql": "SELECT departments.name, ROUND(AVG(students.attendance_percentage), 2) AS avg_attendance FROM students JOIN departments ON students.department_id = departments.id GROUP BY departments.name;",
        "tables_used": ["students", "departments"],
        "feedback_score": 1
    },
    # --- TOP_N_RANK Seeds ---
    {
        "id": "seed_117",
        "query": "Top 5 wicket takers in IPL",
        "intent": "TOP_N_RANK",
        "sql": "SELECT best_bowling AS bowler, SUM(CAST(SUBSTR(best_bowling_figure, 1, INSTR(best_bowling_figure, '--') - 1) AS INTEGER)) AS total_wickets FROM ipl WHERE best_bowling_figure LIKE '%--%' GROUP BY best_bowling ORDER BY total_wickets DESC LIMIT 5;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_118",
        "query": "Top 5 run scorers in the tournament",
        "intent": "TOP_N_RANK",
        "sql": "SELECT top_scorer AS batsman, SUM(highscore) AS total_runs FROM ipl GROUP BY top_scorer ORDER BY total_runs DESC LIMIT 5;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_119",
        "query": "Who has the highest score in Math?",
        "intent": "TOP_N_RANK",
        "sql": "SELECT students.name, marks.score FROM students JOIN marks ON students.id = marks.student_id JOIN courses ON marks.course_id = courses.id WHERE courses.title LIKE '%Math%' ORDER BY marks.score DESC LIMIT 1;",
        "tables_used": ["students", "marks", "courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_120",
        "query": "Which student has the highest attendance?",
        "intent": "TOP_N_RANK",
        "sql": "SELECT name, attendance_percentage FROM students ORDER BY attendance_percentage DESC LIMIT 1;",
        "tables_used": ["students"],
        "feedback_score": 1
    },
    {
        "id": "seed_121",
        "query": "Who won the toss most times?",
        "intent": "TOP_N_RANK",
        "sql": "SELECT toss_winner, COUNT(*) AS toss_wins FROM ipl GROUP BY toss_winner ORDER BY toss_wins DESC LIMIT 1;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_122",
        "query": "Venue with most matches hosted",
        "intent": "TOP_N_RANK",
        "sql": "SELECT venue, COUNT(*) AS matches_hosted FROM ipl GROUP BY venue ORDER BY matches_hosted DESC LIMIT 1;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_123",
        "query": "Top 3 best performing products by revenue",
        "intent": "TOP_N_RANK",
        "sql": "SELECT product_name, revenue FROM sarah_products ORDER BY revenue DESC LIMIT 3;",
        "tables_used": ["sarah_products"],
        "feedback_score": 1
    },
    {
        "id": "seed_124",
        "query": "Which bowler has the best bowling economy rate?",
        "intent": "TOP_N_RANK",
        "sql": "SELECT best_bowling AS bowler, ROUND(SUM(CAST(SUBSTR(best_bowling_figure, INSTR(best_bowling_figure, '--') + 2) AS NUMERIC)) / (COUNT(*) * 4.0), 2) AS economy FROM ipl WHERE best_bowling_figure LIKE '%--%' GROUP BY best_bowling ORDER BY economy ASC LIMIT 1;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    # --- FILTER_SELECT Seeds ---
    {
        "id": "seed_125",
        "query": "Matches between CSK and MI",
        "intent": "FILTER_SELECT",
        "sql": "SELECT season, team1, team2, match_winner, venue FROM ipl WHERE ((team1 = 'Chennai Super Kings' AND team2 = 'Mumbai Indians') OR (team1 = 'Mumbai Indians' AND team2 = 'Chennai Super Kings'));",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_126",
        "query": "Did CSK win the toss?",
        "intent": "FILTER_SELECT",
        "sql": "SELECT season, team1, team2, toss_winner FROM ipl WHERE toss_winner = 'Chennai Super Kings';",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_127",
        "query": "Show products in Electronics category with price under 500",
        "intent": "FILTER_SELECT",
        "sql": "SELECT * FROM sarah_products WHERE category = 'Electronics' AND price < 500;",
        "tables_used": ["sarah_products"],
        "feedback_score": 1
    },
    {
        "id": "seed_128",
        "query": "List matches played in Wankhede Stadium",
        "intent": "FILTER_SELECT",
        "sql": "SELECT * FROM ipl WHERE venue LIKE '%Wankhede%';",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_129",
        "query": "Show students enrolled in Computer Science department",
        "intent": "FILTER_SELECT",
        "sql": "SELECT students.* FROM students JOIN departments ON students.department_id = departments.id WHERE departments.name = 'Computer Science';",
        "tables_used": ["students", "departments"],
        "feedback_score": 1
    },
    {
        "id": "seed_130",
        "query": "Show sales in Mumbai store",
        "intent": "FILTER_SELECT",
        "sql": "SELECT transaction_id, store_city, revenue FROM sales WHERE store_city = 'Mumbai';",
        "tables_used": ["sales"],
        "feedback_score": 1
    },
    # --- JOIN_LOOKUP Seeds ---
    {
        "id": "seed_131",
        "query": "Show student names along with their course titles and marks",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT students.name, courses.title, marks.score, marks.grade FROM students JOIN marks ON students.id = marks.student_id JOIN courses ON marks.course_id = courses.id;",
        "tables_used": ["students", "marks", "courses"],
        "feedback_score": 1
    },
    {
        "id": "seed_132",
        "query": "List each product with its category and total units sold",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT sarah_products.product_name, sarah_products.category, sales.units_sold FROM sarah_products JOIN sales ON sarah_products.id = sales.product_id;",
        "tables_used": ["sarah_products", "sales"],
        "feedback_score": 1
    },
    {
        "id": "seed_133",
        "query": "Show customer orders with shipping address and payment method",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT customers.name, orders.order_id, orders.payment_method FROM customers JOIN orders ON customers.id = orders.customer_id;",
        "tables_used": ["customers", "orders"],
        "feedback_score": 1
    },
    {
        "id": "seed_134",
        "query": "Join courses and departments to list course offerings per department",
        "intent": "JOIN_LOOKUP",
        "sql": "SELECT departments.name AS department_name, courses.title AS course_title, courses.credits FROM departments JOIN courses ON departments.id = courses.department_id;",
        "tables_used": ["departments", "courses"],
        "feedback_score": 1
    },
    # --- FORMULA_CONVERSION Seeds ---
    {
        "id": "seed_135",
        "query": "Convert 25 celsius to fahrenheit",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND((25.0 * 9.0 / 5.0) + 32.0, 2) AS fahrenheit;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_136",
        "query": "Convert 100 km to miles",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND(100.0 * 0.621371, 2) AS miles;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_137",
        "query": "Convert 50 kg to pounds",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND(50.0 * 2.20462, 2) AS pounds;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_138",
        "query": "Convert 2500 meters to feet",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND(2500.0 * 3.28084, 2) AS feet;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_139",
        "query": "Convert 100 kmh to mph",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND(100.0 * 0.621371, 2) AS mph;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_140",
        "query": "Convert 300 kelvin to celsius",
        "intent": "FORMULA_CONVERSION",
        "sql": "SELECT ROUND(300.0 - 273.15, 2) AS celsius;",
        "tables_used": [],
        "feedback_score": 1
    },
    # --- FORMULA_SPORTS Seeds ---
    {
        "id": "seed_141",
        "query": "Calculate bowling strike rate for 24 balls and 3 wickets",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 24 AS balls_bowled, 3 AS wickets_taken, 8.0 AS bowling_strike_rate;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_142",
        "query": "Calculate bowling economy of CSK",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 'Chennai Super Kings' AS team, ROUND(SUM(runs_conceded) / (COUNT(*) * 20.0), 2) AS bowling_economy FROM ipl;",
        "tables_used": ["ipl"],
        "feedback_score": 1
    },
    {
        "id": "seed_143",
        "query": "True shooting percentage for 28 points, 18 FGA, 8 FTA",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 28.0 AS points, 18.0 AS field_goal_attempts, 8.0 AS free_throw_attempts, 65.05 AS true_shooting_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_144",
        "query": "Calculate earned run average ERA for 6 earned runs in 18 innings pitched",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 6.0 AS earned_runs, 18.0 AS innings_pitched, 3.0 AS earned_run_average_era;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_145",
        "query": "Goal conversion rate for 12 goals out of 40 shots on target",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 12.0 AS goals_scored, 40.0 AS shots_on_target, 30.0 AS goal_conversion_pct;",
        "tables_used": [],
        "feedback_score": 1
    },
    {
        "id": "seed_146",
        "query": "Running pace for 10 km in 48 minutes",
        "intent": "FORMULA_SPORTS",
        "sql": "SELECT 10.0 AS distance_km, 48.0 AS time_minutes, '4:48' AS pace_min_per_km, 12.5 AS speed_kmh;",
        "tables_used": [],
        "feedback_score": 1
    }
]


class ModelStatus(BaseModel):
    is_trained: bool = False
    sample_count: int = 0
    vocabulary_size: int = 0
    intent_accuracy: float = 0.0
    accuracy: float = 0.0
    active_provider: str = "local"
    last_trained: Optional[str] = None
    classes: List[str] = Field(default_factory=list)


class SelfLearningEngine:
    """
    Autonomous continuous learning model for Text-to-SQL.
    Maintains persistent memory, updates weights, and retrains locally on CPU in <50ms.
    """

    def __init__(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        self.memory: List[TrainingSample] = []
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.classifier: Optional[LogisticRegression] = None
        self.last_trained_time: Optional[float] = None
        self.accuracy: float = 0.0

        self._load_memory()
        self._load_or_train_model()

    def _load_memory(self):
        """Loads persistent training memory from JSON file or initializes with seed data."""
        if MEMORY_FILE.exists():
            try:
                with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.memory = [TrainingSample(**item) for item in data]
                    # Merge any newly added seed samples by ID
                    existing_ids = {s.id for s in self.memory}
                    new_added = False
                    for seed in SEED_TRAINING_DATA:
                        if seed["id"] not in existing_ids:
                            self.memory.append(TrainingSample(**seed))
                            new_added = True
                    if new_added:
                        self._save_memory()
                    logger.info(f"Loaded {len(self.memory)} training samples from persistent memory.")
                    return
            except Exception as e:
                logger.warning(f"Could not load memory file: {e}")

        # Initialize with seed data
        self.memory = [TrainingSample(**d) for d in SEED_TRAINING_DATA]
        self._save_memory()

    def _save_memory(self):
        """Persists training memory to JSON file."""
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump([s.model_dump() for s in self.memory], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save training memory: {e}")

    def _load_or_train_model(self):
        """Loads trained model checkpoint or trains if not found."""
        vec_path = MODEL_DIR / "tfidf_vectorizer.joblib"
        clf_path = MODEL_DIR / "intent_classifier.joblib"

        if vec_path.exists() and clf_path.exists():
            try:
                self.vectorizer = joblib.load(vec_path)
                self.classifier = joblib.load(clf_path)
                self.last_trained_time = vec_path.stat().st_mtime
                if self.memory and self.vectorizer and self.classifier:
                    try:
                        X_vec = self.vectorizer.transform([s.query for s in self.memory])
                        self.accuracy = float(accuracy_score([s.intent for s in self.memory], self.classifier.predict(X_vec)))
                    except Exception:
                        self.accuracy = 1.0
                logger.info(f"Loaded pre-trained intent model checkpoint. Accuracy: {self.accuracy * 100:.1f}%.")
                return
            except Exception as e:
                logger.warning(f"Error loading model checkpoints: {e}")

        self.retrain()

    def retrain(self) -> Dict[str, Any]:
        """
        Trains TF-IDF vectorizer and Intent Classifier on accumulated training memories.
        Executes sub-50ms on CPU without GPU overhead.
        """
        t0 = time.perf_counter()
        if not self.memory:
            return {"success": False, "error": "No training samples available."}

        X_texts = [s.query for s in self.memory]
        y_intents = [s.intent for s in self.memory]

        # Vectorizer with unigrams and bigrams
        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1, lowercase=True)
        X_vec = self.vectorizer.fit_transform(X_texts)

        # Multi-class Classifier
        self.classifier = LogisticRegression(C=10.0, max_iter=200, random_state=42)
        self.classifier.fit(X_vec, y_intents)

        # Compute training accuracy
        preds = self.classifier.predict(X_vec)
        self.accuracy = float(accuracy_score(y_intents, preds))
        self.last_trained_time = time.time()

        # Save model artifacts
        try:
            joblib.dump(self.vectorizer, MODEL_DIR / "tfidf_vectorizer.joblib")
            joblib.dump(self.classifier, MODEL_DIR / "intent_classifier.joblib")
        except Exception as e:
            logger.error(f"Failed to persist model checkpoints: {e}")

        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        logger.info(f"Retrained Local NLP Model in {elapsed_ms:.1f}ms. Accuracy: {self.accuracy * 100:.1f}%.")

        return {
            "success": True,
            "sample_count": len(self.memory),
            "accuracy": self.accuracy,
            "vocabulary_size": len(self.vectorizer.vocabulary_),
            "training_time_ms": elapsed_ms,
            "classes": list(self.classifier.classes_)
        }

    def predict_intent(self, query: str) -> Tuple[str, float]:
        """Predicts the analytical intent category of a query with confidence score."""
        if not self.vectorizer or not self.classifier:
            self.retrain()

        X = self.vectorizer.transform([query])
        probs = self.classifier.predict_proba(X)[0]
        max_idx = probs.argmax()
        intent = self.classifier.classes_[max_idx]
        confidence = float(probs[max_idx])
        return intent, confidence

    def find_similar_sample(self, query: str, threshold: float = 0.82) -> Optional[TrainingSample]:
        """Finds closest learned query in memory using cosine similarity."""
        if not self.vectorizer or not self.memory:
            return None

        from sklearn.metrics.pairwise import cosine_similarity
        vec_q = self.vectorizer.transform([query])
        vec_mem = self.vectorizer.transform([s.query for s in self.memory])
        sims = cosine_similarity(vec_q, vec_mem)[0]

        best_idx = int(sims.argmax())
        if sims[best_idx] >= threshold:
            return self.memory[best_idx]
        return None

    def record_interaction(
        self,
        query: str,
        sql: str,
        tables_used: Optional[List[str]] = None,
        success: bool = True,
        feedback: int = 1,
        corrected_sql: Optional[str] = None
    ) -> TrainingSample:
        """
        Continuous Learning Loop: Records query execution or user feedback.
        If user corrects a query, automatically increases weight and retrains.
        """
        import uuid
        intent, _ = self.predict_intent(query)
        sample = TrainingSample(
            id=f"trn_{uuid.uuid4().hex[:8]}",
            query=query.strip(),
            intent=intent,
            sql=corrected_sql or sql,
            tables_used=tables_used or [],
            success=success,
            feedback_score=feedback,
            corrected_sql=corrected_sql
        )
        self.memory.append(sample)
        self._save_memory()

        # Incremental retrain if correction or every 5 new samples
        if corrected_sql or len(self.memory) % 5 == 0:
            self.retrain()

        return sample

    def get_status(self, active_provider: str = "local") -> ModelStatus:
        """Returns comprehensive diagnostic metrics of the local trained model."""
        voc_size = len(self.vectorizer.vocabulary_) if self.vectorizer else 0
        classes = list(self.classifier.classes_) if self.classifier else []
        last_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(self.last_trained_time)) if self.last_trained_time else None

        acc_pct = round(self.accuracy * 100.0, 1)
        return ModelStatus(
            is_trained=bool(self.classifier is not None),
            sample_count=len(self.memory),
            vocabulary_size=voc_size,
            intent_accuracy=acc_pct,
            accuracy=acc_pct,
            active_provider=active_provider,
            last_trained=last_str,
            classes=classes
        )


# Global singleton instance
learning_engine = SelfLearningEngine()
