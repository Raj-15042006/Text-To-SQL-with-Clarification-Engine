import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from backend.modules.formula_engine import formula_engine
from backend.modules.nlp_engine import local_nlp_engine
from backend.modules.learning_engine import learning_engine
from backend.database.connection import db_manager


def test_mathematics_formulas():
    # 1. Quadratic equation
    sql_quad = local_nlp_engine.parse_formula("Solve quadratic equation a=1, b=-5, c=6")
    assert sql_quad is not None
    assert "root_1" in sql_quad and "root_2" in sql_quad
    res_quad = db_manager.execute_query(sql_quad)
    assert res_quad.success is True
    assert res_quad.rows[0]["root_1"] == 3.0
    assert res_quad.rows[0]["root_2"] == 2.0

    # 2. Combinations nCr
    sql_comb = local_nlp_engine.parse_formula("Calculate combinations 10 choose 3")
    assert sql_comb is not None
    assert "combinations_ncr" in sql_comb.lower()
    res_comb = db_manager.execute_query(sql_comb)
    assert res_comb.success is True
    assert res_comb.rows[0]["combinations_ncr"] == 120

    # 3. Permutations nPr
    sql_perm = local_nlp_engine.parse_formula("Calculate permutations P(8, 3)")
    assert sql_perm is not None
    res_perm = db_manager.execute_query(sql_perm)
    assert res_perm.success is True
    assert res_perm.rows[0]["permutations_npr"] == 336

    # 4. Trigonometry
    sql_trig = local_nlp_engine.parse_formula("sin of 30 degrees")
    assert sql_trig is not None
    res_trig = db_manager.execute_query(sql_trig)
    assert res_trig.success is True
    assert round(res_trig.rows[0]["calculated_value"], 2) == 0.5

    # 5. Logarithms
    sql_log = local_nlp_engine.parse_formula("log base 10 of 1000")
    assert sql_log is not None
    res_log = db_manager.execute_query(sql_log)
    assert res_log.success is True
    assert res_log.rows[0]["log_base_10"] == 3.0


def test_statistical_equations():
    # 1. Descriptive stats on dataset list
    sql_stats = local_nlp_engine.parse_formula("Calculate standard deviation of [12, 15, 18, 22, 29, 35]")
    assert sql_stats is not None
    res_stats = db_manager.execute_query(sql_stats)
    assert res_stats.success is True
    assert res_stats.rows[0]["count"] == 6
    assert "sample_standard_deviation" in res_stats.rows[0]

    # 2. Z-Score
    sql_z = local_nlp_engine.parse_formula("Calculate z-score for value 85 with mean 70 and standard deviation 10")
    assert sql_z is not None
    res_z = db_manager.execute_query(sql_z)
    assert res_z.success is True
    assert res_z.rows[0]["z_score"] == 1.5

    # 3. Pearson Correlation
    sql_corr = local_nlp_engine.parse_formula("Calculate Pearson correlation between X=[1, 2, 3, 4, 5] and Y=[2, 4, 5, 4, 5]")
    assert sql_corr is not None
    res_corr = db_manager.execute_query(sql_corr)
    assert res_corr.success is True
    assert "pearson_correlation_r" in res_corr.rows[0]

    # 4. Bayes Theorem
    sql_bayes = local_nlp_engine.parse_formula("Bayes theorem for P(A)=0.01, P(B|A)=0.9, P(B|not A)=0.05")
    assert sql_bayes is not None
    res_bayes = db_manager.execute_query(sql_bayes)
    assert res_bayes.success is True
    assert res_bayes.rows[0]["posterior_probability_pct"] == 15.38


def test_physics_formulas():
    # 1. Momentum p = mv
    sql_p = local_nlp_engine.parse_formula("Calculate momentum for mass 800 kg moving at 15 m/s")
    assert sql_p is not None
    res_p = db_manager.execute_query(sql_p)
    assert res_p.success is True
    assert res_p.rows[0]["momentum_kg_ms"] == 12000.0

    # 2. Centripetal Force Fc = mv^2 / r
    sql_fc = local_nlp_engine.parse_formula("Calculate centripetal force for mass 1000 kg, velocity 20 m/s, radius 50 m")
    assert sql_fc is not None
    res_fc = db_manager.execute_query(sql_fc)
    assert res_fc.success is True
    assert res_fc.rows[0]["centripetal_force_newtons"] == 8000.0

    # 3. Ideal Gas Law
    sql_gas = local_nlp_engine.parse_formula("Calculate ideal gas pressure for 2 moles, volume 10 liters, temperature 300 Kelvin")
    assert sql_gas is not None
    res_gas = db_manager.execute_query(sql_gas)
    assert res_gas.success is True
    assert "pressure_atm" in res_gas.rows[0]

    # 4. Wave Equation
    sql_wave = local_nlp_engine.parse_formula("Calculate wave speed for frequency 500 Hz and wavelength 0.68 m")
    assert sql_wave is not None
    res_wave = db_manager.execute_query(sql_wave)
    assert res_wave.success is True
    assert res_wave.rows[0]["wave_speed_ms"] == 340.0


def test_finance_and_business_formulas():
    # 1. Sharpe Ratio
    sql_sharpe = local_nlp_engine.parse_formula("Calculate Sharpe ratio for portfolio return 14%, risk-free rate 4%, standard deviation 8%")
    assert sql_sharpe is not None
    res_sharpe = db_manager.execute_query(sql_sharpe)
    assert res_sharpe.success is True
    assert res_sharpe.rows[0]["sharpe_ratio"] == 1.25

    # 2. CAPM Expected Return
    sql_capm = local_nlp_engine.parse_formula("Calculate CAPM expected return for risk-free 3.5, beta 1.2, market return 11")
    assert sql_capm is not None
    res_capm = db_manager.execute_query(sql_capm)
    assert res_capm.success is True
    assert res_capm.rows[0]["capm_expected_return_pct"] == 12.5

    # 3. SaaS: CAC
    sql_cac = local_nlp_engine.parse_formula("Calculate Customer Acquisition Cost CAC for marketing spend 50000 and 250 customers")
    assert sql_cac is not None
    res_cac = db_manager.execute_query(sql_cac)
    assert res_cac.success is True
    assert res_cac.rows[0]["customer_acquisition_cost_cac"] == 200.0

    # 4. SaaS: LTV to CAC
    sql_ltv_cac = local_nlp_engine.parse_formula("What is the LTV to CAC ratio for LTV 1800 and CAC 300?")
    assert sql_ltv_cac is not None
    res_ltv_cac = db_manager.execute_query(sql_ltv_cac)
    assert res_ltv_cac.success is True
    assert res_ltv_cac.rows[0]["ltv_cac_ratio"] == 6.0

    # 5. Break-Even Units
    sql_bep = local_nlp_engine.parse_formula("Calculate break even units for fixed costs 40000, selling price 100, variable cost 60")
    assert sql_bep is not None
    res_bep = db_manager.execute_query(sql_bep)
    assert res_bep.success is True
    assert res_bep.rows[0]["break_even_units"] == 1000.0


def test_multi_sport_and_entertainment():
    # 1. Football: Goal Conversion
    sql_conv = local_nlp_engine.parse_formula("Calculate football goal conversion rate for 15 goals from 60 shots")
    assert sql_conv is not None
    res_conv = db_manager.execute_query(sql_conv)
    assert res_conv.success is True
    assert res_conv.rows[0]["goal_conversion_percentage"] == 25.0

    # 2. Basketball: True Shooting %
    sql_ts = local_nlp_engine.parse_formula("Calculate basketball True Shooting Percentage for 25 points, 15 FGA, 8 FTA")
    assert sql_ts is not None
    res_ts = db_manager.execute_query(sql_ts)
    assert res_ts.success is True
    assert round(res_ts.rows[0]["true_shooting_pct"], 1) == 67.5

    # 3. Movie Box Office ROI
    sql_box = local_nlp_engine.parse_formula("Calculate movie box office ROI for budget 60M and box office 240M")
    assert sql_box is not None
    res_box = db_manager.execute_query(sql_box)
    assert res_box.success is True
    assert res_box.rows[0]["box_office_roi_pct"] == 300.0


def test_geographical_formulas():
    # 1. Haversine distance
    sql_hav = local_nlp_engine.parse_formula("Calculate Haversine distance between 28.6139, 77.2090 and 19.0760, 72.8777")
    assert sql_hav is not None
    res_hav = db_manager.execute_query(sql_hav)
    assert res_hav.success is True
    assert res_hav.rows[0]["distance_km"] > 1100.0
    assert res_hav.rows[0]["distance_miles"] > 700.0

    # 2. Population Density
    sql_pop = local_nlp_engine.parse_formula("Calculate population density for population 14000000 and area 603 square kilometers")
    assert sql_pop is not None
    res_pop = db_manager.execute_query(sql_pop)
    assert res_pop.success is True
    assert res_pop.rows[0]["people_per_sq_km"] == 23217.25


def test_trained_model_intent_predictions():
    # Verify the trained model classifies intents across the expanded domains
    intents = [
        ("Solve quadratic equation a=1, b=-5, c=6", "FORMULA_MATH"),
        ("Calculate standard deviation of [12, 15, 18, 22, 29, 35]", "FORMULA_STATISTICS"),
        ("Calculate momentum for mass 800 kg moving at 15 m/s", "FORMULA_PHYSICS"),
        ("Calculate Sharpe ratio for portfolio return 14%, risk-free rate 4%, standard deviation 8%", "FORMULA_FINANCE"),
        ("Calculate Customer Acquisition Cost CAC for marketing spend 50000 and 250 customers", "FORMULA_BUSINESS"),
        ("Calculate football goal conversion rate for 15 goals from 60 shots", "FORMULA_SPORTS"),
        ("Calculate movie box office ROI for budget 60M and box office 240M", "FORMULA_ENTERTAINMENT"),
        ("Calculate Haversine distance between 28.6139, 77.2090 and 19.0760, 72.8777", "FORMULA_GEOGRAPHY"),
    ]
    for q, expected in intents:
        pred, conf = learning_engine.predict_intent(q)
        assert pred == expected, f"Expected {expected} for '{q}', got {pred} (conf: {conf:.2f})"
