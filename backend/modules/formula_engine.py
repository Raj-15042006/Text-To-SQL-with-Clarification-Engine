"""
Universal Formula & Calculation Engine
Comprehensive parsing and analytical SQL generation across:
- Mathematics (Quadratic, Trigonometry, Combinatorics, Geometry, Logarithms)
- Statistical Equations (Descriptive Stats, Z-Score, Pearson Correlation, Linear Regression, Bayes' Theorem)
- Physics (Kinematics, Mechanics, Thermodynamics, Fluids, Electromagnetism, Optics, Waves)
- Finance (Loan EMI, CAGR, Compound & Simple Interest, Rule of 72, ROI, Sharpe Ratio, CAPM, WACC, NPV)
- Non-Finance & Business Metrics (CAC, LTV, LTV:CAC, Churn, Runway, Burn Rate, EOQ, Break-Even)
- Multi-Sport Analytics (Cricket, Football/Soccer, Basketball, Baseball, Running & Athletics)
- Movies & Entertainment (Box Office ROI, Multiplier, Domestic/International Split, Streaming Completion)
- Geographical & Geospatial (Haversine Great-Circle Distance, Population Density, Map Scale Distance)
- Worldwide Unit Conversions & Percentages
"""

import math
import re
from typing import Optional, List, Dict, Any, Tuple


def extract_numbers(text: str) -> List[float]:
    """Extracts all floating point and integer numbers from text string."""
    raw = re.findall(r"[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?", text)
    nums = []
    for r in raw:
        try:
            nums.append(float(r))
        except ValueError:
            pass
    return nums


def extract_number_lists(text: str) -> List[List[float]]:
    """Extracts bracketed lists of numbers like [1, 2, 3] or (1, 2, 3) from text."""
    matches = re.findall(r"\[([\d\s,\.\-+eE]+)\]", text)
    if not matches:
        matches = re.findall(r"\(([\d\s,\.\-+eE]+)\)", text)
    res = []
    for m in matches:
        ns = extract_numbers(m)
        if ns:
            res.append(ns)
    return res


class UniversalFormulaEngine:
    """
    Independent, high-precision mathematical and analytical formula engine.
    Produces portable, highly optimized SQL expressions that execute in any standard SQL database.
    """

    @classmethod
    def compile(cls, query: str) -> Optional[str]:
        q = query.strip()
        q_lower = q.lower()

        # =========================================================================
        # 1. MATHEMATICS & ADVANCED ALGEBRA
        # =========================================================================
        # Quadratic Equation: e.g. "Solve quadratic equation a=1, b=-5, c=6" or "roots of quadratic a=2, b=4, c=-6"
        if re.search(r"\b(quadratic|roots\s+of\s+equation|quadratic\s+formula)\b", q_lower):
            m_a = re.search(r"\ba\s*=\s*([-+]?\d*\.?\d+)", q_lower)
            m_b = re.search(r"\bb\s*=\s*([-+]?\d*\.?\d+)", q_lower)
            m_c = re.search(r"\bc\s*=\s*([-+]?\d*\.?\d+)", q_lower)
            if m_a and m_b and m_c:
                a, b, c = float(m_a.group(1)), float(m_b.group(1)), float(m_c.group(1))
            else:
                nums = extract_numbers(query)
                if len(nums) >= 3:
                    a, b, c = nums[0], nums[1], nums[2]
                else:
                    a = b = c = None
            if a is not None and a != 0:
                disc = (b ** 2) - (4 * a * c)
                if disc >= 0:
                    r1 = (-b + math.sqrt(disc)) / (2 * a)
                    r2 = (-b - math.sqrt(disc)) / (2 * a)
                    return (
                        f"SELECT {round(a, 4)} AS a, {round(b, 4)} AS b, {round(c, 4)} AS c, "
                        f"{round(disc, 4)} AS discriminant, {round(r1, 4)} AS root_1, {round(r2, 4)} AS root_2, "
                        f"'Real and distinct' AS root_type;"
                    )
                else:
                    real_part = round(-b / (2 * a), 4)
                    imag_part = round(math.sqrt(-disc) / (2 * a), 4)
                    return (
                        f"SELECT {round(a, 4)} AS a, {round(b, 4)} AS b, {round(c, 4)} AS c, "
                        f"{round(disc, 4)} AS discriminant, '{real_part} + {imag_part}i' AS root_1, "
                        f"'{real_part} - {imag_part}i' AS root_2, 'Complex conjugate' AS root_type;"
                    )

        # Combinations nCr / n choose r: e.g. "Calculate combinations 10 choose 3" or "nCr for n=10, r=3"
        if re.search(r"\b(combinations?|ncr|choose)\b", q_lower) and not re.search(r"\b(color|option|menu)\b", q_lower):
            m_choose = re.search(r"(\d+)\s+choose\s+(\d+)", q_lower)
            if m_choose:
                n, r = int(m_choose.group(1)), int(m_choose.group(2))
            else:
                nums = [int(x) for x in extract_numbers(query)]
                n, r = (nums[0], nums[1]) if len(nums) >= 2 else (None, None)
            if n is not None and r is not None and 0 <= r <= n <= 100:
                ans = math.comb(n, r)
                return f"SELECT {n} AS n, {r} AS r, {ans} AS combinations_ncr;"

        # Permutations nPr / P(n, r): e.g. "Calculate permutations P(8, 3)" or "nPr for n=8, r=3"
        if re.search(r"\b(permutations?|npr)\b", q_lower):
            nums = [int(x) for x in extract_numbers(query)]
            if len(nums) >= 2:
                n, r = nums[0], nums[1]
                if 0 <= r <= n <= 50:
                    ans = math.perm(n, r)
                    return f"SELECT {n} AS n, {r} AS r, {ans} AS permutations_npr;"

        # Factorial: e.g. "Calculate factorial of 6" or "6!"
        if "factorial" in q_lower or re.search(r"\b(\d+)\s*!", q_lower):
            nums = [int(x) for x in extract_numbers(query)]
            if nums and 0 <= nums[0] <= 50:
                n = nums[0]
                ans = math.factorial(n)
                return f"SELECT {n} AS n, {ans} AS factorial;"

        # Trigonometry (sin, cos, tan with degrees or radians)
        m_trig = re.search(r"\b(sin(?:e)?|cos(?:ine)?|tan(?:gent)?)\s*(?:of)?\s*([-+]?\d*\.?\d+)\s*(degrees?|deg|radians?|rad)?", q_lower)
        if m_trig:
            func = m_trig.group(1)[:3]
            angle_val = float(m_trig.group(2))
            unit = m_trig.group(3) or "deg"
            rad = math.radians(angle_val) if "rad" not in unit else angle_val
            if func == "sin":
                res = math.sin(rad)
            elif func == "cos":
                res = math.cos(rad)
            else:
                res = math.tan(rad) if abs(math.cos(rad)) > 1e-9 else float('inf')
            return f"SELECT '{func}' AS trig_function, {angle_val} AS angle, '{unit}' AS unit, {round(res, 6)} AS calculated_value;"

        # Logarithms: e.g. "log base 10 of 1000", "natural log of 20", "log base 2 of 256"
        if re.search(r"\b(log(?:arithm)?|ln)\b", q_lower):
            m_log10 = re.search(r"log\s*(?:base\s*10)?\s*(?:of)?\s*(\d*\.?\d+)", q_lower)
            m_ln = re.search(r"(?:natural\s*log|ln)\s*(?:of)?\s*(\d*\.?\d+)", q_lower)
            m_log2 = re.search(r"log\s*(?:base\s*2)\s*(?:of)?\s*(\d*\.?\d+)", q_lower)
            if m_ln:
                val = float(m_ln.group(1))
                if val > 0:
                    return f"SELECT {val} AS value, {round(math.log(val), 6)} AS natural_log_ln;"
            elif m_log2:
                val = float(m_log2.group(1))
                if val > 0:
                    return f"SELECT {val} AS value, 2 AS base, {round(math.log2(val), 6)} AS log_base_2;"
            elif m_log10:
                val = float(m_log10.group(1))
                if val > 0:
                    return f"SELECT {val} AS value, 10 AS base, {round(math.log10(val), 6)} AS log_base_10;"

        # 2x2 Matrix Determinant: e.g. "Determinant of 2x2 matrix 4, 2, 3, 5" or "[[4, 2], [3, 5]]"
        if re.search(r"\b(determinant|det)\b", q_lower) and "matrix" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 4:
                a, b, c, d = nums[0], nums[1], nums[2], nums[3]
                det = (a * d) - (b * c)
                return f"SELECT {a} AS a11, {b} AS a12, {c} AS a21, {d} AS a22, {round(det, 4)} AS matrix_determinant;"

        # Geometry: Trapezoid Area
        if "trapezoid" in q_lower and ("area" in q_lower or "bases" in q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                b1, b2, h = nums[0], nums[1], nums[2]
                area = 0.5 * (b1 + b2) * h
                return f"SELECT {b1} AS base_1, {b2} AS base_2, {h} AS height, {round(area, 2)} AS trapezoid_area;"

        # Geometry: Ellipse Area
        if "ellipse" in q_lower and "area" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 2:
                a, b = nums[0], nums[1]
                area = math.pi * a * b
                return f"SELECT {a} AS semi_major_axis, {b} AS semi_minor_axis, {round(area, 2)} AS ellipse_area;"

        # =========================================================================
        # 2. STATISTICAL EQUATIONS
        # =========================================================================
        # Descriptive Statistics on series: e.g. "standard deviation of [12, 15, 18, 22, 29, 35]" or "variance of 10, 20, 30, 40, 50"
        if (
            re.search(r"\b(standard\s+deviation|std\s+dev|variance|dataset\s+stats|mean\s+and\s+std|skewness)\b", q_lower) 
            and any(c in query for c in [",", "[", "("])
            and not re.search(r"\b(sharpe|z[-_ ]?score|portfolio)\b", q_lower)
        ):
            lists = extract_number_lists(query)
            nums = lists[0] if lists else extract_numbers(query)
            if len(nums) >= 3:
                n = len(nums)
                total = sum(nums)
                mean = total / n
                sorted_nums = sorted(nums)
                median = sorted_nums[n // 2] if n % 2 != 0 else (sorted_nums[n // 2 - 1] + sorted_nums[n // 2]) / 2.0
                sample_var = sum((x - mean) ** 2 for x in nums) / (n - 1)
                sample_std = math.sqrt(sample_var)
                pop_var = sum((x - mean) ** 2 for x in nums) / n
                pop_std = math.sqrt(pop_var)
                min_v, max_v = min(nums), max(nums)
                return (
                    f"SELECT {n} AS count, {round(total, 2)} AS sum_total, {round(mean, 4)} AS mean, "
                    f"{round(median, 4)} AS median, {round(sample_var, 4)} AS sample_variance, "
                    f"{round(sample_std, 4)} AS sample_standard_deviation, {round(pop_std, 4)} AS population_standard_deviation, "
                    f"{min_v} AS min_value, {max_v} AS max_value, {round(max_v - min_v, 4)} AS value_range;"
                )

        # Z-Score: e.g. "Calculate z-score for value 85 with mean 70 and standard deviation 10"
        if re.search(r"\b(z\s*[-_]?score|standard\s+score)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                x, mu, sigma = nums[0], nums[1], nums[2]
                if sigma > 0:
                    z = (x - mu) / sigma
                    return f"SELECT {x} AS observation_value, {mu} AS mean, {sigma} AS standard_deviation, {round(z, 4)} AS z_score;"

        # Pearson Correlation Coefficient & Covariance: e.g. "correlation between X=[1, 2, 3, 4, 5] and Y=[2, 4, 5, 4, 5]"
        if re.search(r"\b(correlation|pearson|covariance)\b", q_lower) and ("[" in query or "x=" in q_lower or "y=" in q_lower):
            lists = extract_number_lists(query)
            if len(lists) >= 2 and len(lists[0]) == len(lists[1]) and len(lists[0]) >= 2:
                xs, ys = lists[0], lists[1]
                n = len(xs)
                mean_x, mean_y = sum(xs) / n, sum(ys) / n
                cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / (n - 1)
                std_x = math.sqrt(sum((x - mean_x) ** 2 for x in xs) / (n - 1))
                std_y = math.sqrt(sum((y - mean_y) ** 2 for y in ys) / (n - 1))
                r = (cov / (std_x * std_y)) if (std_x * std_y) != 0 else 0.0
                r2 = r ** 2
                return (
                    f"SELECT {n} AS sample_pairs, {round(mean_x, 4)} AS mean_x, {round(mean_y, 4)} AS mean_y, "
                    f"{round(cov, 4)} AS covariance, {round(r, 4)} AS pearson_correlation_r, {round(r2, 4)} AS r_squared;"
                )

        # Simple Linear Regression (y = mx + c): e.g. "Linear regression for X=[1, 2, 3, 4] and Y=[3, 5, 7, 9]"
        if re.search(r"\b(linear\s+regression|slope\s+and\s+intercept|best\s+fit\s+line)\b", q_lower):
            lists = extract_number_lists(query)
            if len(lists) >= 2 and len(lists[0]) == len(lists[1]) and len(lists[0]) >= 2:
                xs, ys = lists[0], lists[1]
                n = len(xs)
                mean_x, mean_y = sum(xs) / n, sum(ys) / n
                num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
                den = sum((x - mean_x) ** 2 for x in xs)
                m = num / den if den != 0 else 0.0
                c = mean_y - (m * mean_x)
                return (
                    f"SELECT {round(m, 4)} AS slope_m, {round(c, 4)} AS intercept_c, "
                    f"'y = {round(m, 4)}x + {round(c, 4)}' AS regression_equation;"
                )

        # Bayes' Theorem: e.g. "Bayes theorem for P(A)=0.01, P(B|A)=0.9, P(B|not A)=0.05"
        if re.search(r"\b(bayes'?\s+theorem|posterior\s+probability|conditional\s+probability)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                p_a, p_b_given_a, p_b_given_not_a = nums[0], nums[1], nums[2]
                if p_a > 1.0: p_a /= 100.0
                if p_b_given_a > 1.0: p_b_given_a /= 100.0
                if p_b_given_not_a > 1.0: p_b_given_not_a /= 100.0
                p_not_a = 1.0 - p_a
                p_b = (p_b_given_a * p_a) + (p_b_given_not_a * p_not_a)
                p_a_given_b = (p_b_given_a * p_a) / p_b if p_b > 0 else 0.0
                return (
                    f"SELECT {round(p_a, 4)} AS p_prior_A, {round(p_b_given_a, 4)} AS p_likelihood_B_given_A, "
                    f"{round(p_b, 4)} AS p_total_evidence_B, {round(p_a_given_b * 100, 2)} AS posterior_probability_pct;"
                )

        # =========================================================================
        # 3. PHYSICS & MECHANICS FORMULAS
        # =========================================================================
        # Momentum: p = m * v
        if re.search(r"\b(momentum|linear\s+momentum)\b", q_lower) and any(w in q_lower for w in ["mass", "kg", "velocity", "m/s", "speed"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                m, v = nums[0], nums[1]
                p = m * v
                return f"SELECT {m} AS mass_kg, {v} AS velocity_ms, {round(p, 2)} AS momentum_kg_ms;"

        # Centripetal Force: Fc = m * v^2 / r
        if re.search(r"\b(centripetal\s+force|circular\s+motion)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                m, v, r = nums[0], nums[1], nums[2]
                if r > 0:
                    fc = (m * (v ** 2)) / r
                    return f"SELECT {m} AS mass_kg, {v} AS velocity_ms, {r} AS radius_meters, {round(fc, 2)} AS centripetal_force_newtons;"

        # Torque: tau = r * F * sin(theta)
        if re.search(r"\b(torque|rotational\s+force)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                r, f = nums[0], nums[1]
                angle_deg = nums[2] if len(nums) >= 3 else 90.0
                tau = r * f * math.sin(math.radians(angle_deg))
                return f"SELECT {r} AS lever_arm_meters, {f} AS force_newtons, {angle_deg} AS angle_degrees, {round(tau, 2)} AS torque_newton_meters;"

        # Kinematics: Equation of Motion s = ut + 0.5 * a * t^2
        if re.search(r"\b(displacement|distance\s+traveled|equations?\s+of\s+motion|kinematics)\b", q_lower) and any(w in q_lower for w in ["acceleration", "initial velocity", "initial_velocity", "time"]):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                u, a, t = nums[0], nums[1], nums[2]
                s = (u * t) + (0.5 * a * (t ** 2))
                v_final = u + (a * t)
                return f"SELECT {u} AS initial_velocity_ms, {a} AS acceleration_ms2, {t} AS time_seconds, {round(s, 2)} AS displacement_meters, {round(v_final, 2)} AS final_velocity_ms;"

        # Final Velocity: v = u + at
        if re.search(r"\b(final\s+velocity|final\s+speed)\b", q_lower) and "acceleration" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 3:
                u, a, t = nums[0], nums[1], nums[2]
                v = u + (a * t)
                return f"SELECT {u} AS initial_velocity_ms, {a} AS acceleration_ms2, {t} AS time_seconds, {round(v, 2)} AS final_velocity_ms;"

        # Power: P = W / t
        if re.search(r"\b(mechanical\s+power|power\s+output)\b", q_lower) and any(w in q_lower for w in ["work", "joule", "second", "time"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                w, t = nums[0], nums[1]
                if t > 0:
                    p = w / t
                    return f"SELECT {w} AS work_joules, {t} AS time_seconds, {round(p, 2)} AS power_watts, {round(p / 745.7, 2)} AS horsepower;"

        # Ideal Gas Law: P = nRT / V
        if re.search(r"\b(ideal\s+gas|gas\s+law|pv\s*=\s*nrt)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                n, v, t = nums[0], nums[1], nums[2]
                r_gas = 0.082057  # L*atm/(mol*K)
                if v > 0:
                    p_atm = (n * r_gas * t) / v
                    p_kpa = p_atm * 101.325
                    return f"SELECT {n} AS moles_n, {v} AS volume_liters, {t} AS temperature_kelvin, {round(p_atm, 4)} AS pressure_atm, {round(p_kpa, 2)} AS pressure_kpa;"

        # Specific Heat Transfer: Q = m * c * delta_T
        if re.search(r"\b(heat\s+energy|heat\s+transfer|thermal\s+energy|calorimetry)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                m, c, dt = nums[0], nums[1], nums[2]
                q_joules = m * c * dt
                return f"SELECT {m} AS mass_kg, {c} AS specific_heat_j_kgk, {dt} AS delta_temp_c, {round(q_joules, 2)} AS heat_energy_joules, {round(q_joules / 4184.0, 2)} AS kcal;"

        # Fluid Hydrostatic Pressure: P = rho * g * h
        if re.search(r"\b(hydrostatic\s+pressure|fluid\s+pressure|pressure\s+at\s+depth)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                rho = nums[0] if nums[0] > 10 else 1000.0  # density kg/m3
                h = nums[1] if nums[0] > 10 else nums[0]   # depth meters
                g = 9.80665
                p = rho * g * h
                return f"SELECT {rho} AS density_kg_m3, {h} AS depth_meters, {round(p, 2)} AS pressure_pascals, {round(p / 100000.0, 4)} AS pressure_bar;"

        # Coulomb's Law: F = k * q1 * q2 / r^2
        if re.search(r"\b(coulomb'?s?\s*(?:law|force)?|electrostatic\s+force)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                q1, q2, r = nums[0], nums[1], nums[2]
                k = 8.9875517923e9
                if r > 0:
                    f = k * abs(q1 * q2) / (r ** 2)
                    return f"SELECT {q1} AS charge_q1_coulombs, {q2} AS charge_q2_coulombs, {r} AS distance_meters, {round(f, 4)} AS electrostatic_force_newtons;"

        # Capacitor Stored Energy: E = 0.5 * C * V^2
        if re.search(r"\b(capacitor|capacitance)\b", q_lower) and any(w in q_lower for w in ["energy", "stored", "voltage", "volts"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                c, v = nums[0], nums[1]
                e = 0.5 * c * (v ** 2)
                return f"SELECT {c} AS capacitance_farads, {v} AS voltage_volts, {round(e, 6)} AS stored_energy_joules;"

        # Wave Equation: v = f * lambda
        if re.search(r"\b(wave\s+speed|wave\s+velocity|wavelength|wave\s+frequency)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                freq, wlen = nums[0], nums[1]
                v = freq * wlen
                return f"SELECT {freq} AS frequency_hz, {wlen} AS wavelength_meters, {round(v, 2)} AS wave_speed_ms;"

        # Snell's Law: n1 * sin(theta1) = n2 * sin(theta2)
        if re.search(r"\b(snell'?s?\s*(?:law)?|refraction\s+angle|refractive\s+index)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                n1, n2, theta1_deg = nums[0], nums[1], nums[2]
                sin_theta2 = (n1 * math.sin(math.radians(theta1_deg))) / n2 if n2 > 0 else 0
                if abs(sin_theta2) <= 1.0:
                    theta2_deg = math.degrees(math.asin(sin_theta2))
                    return f"SELECT {n1} AS index_n1, {n2} AS index_n2, {theta1_deg} AS incident_angle_deg, {round(theta2_deg, 2)} AS refracted_angle_deg;"
                else:
                    return f"SELECT {n1} AS index_n1, {n2} AS index_n2, 'Total Internal Reflection' AS status;"

        # Photon Energy: E = h * f
        if re.search(r"\b(photon\s+energy|planck'?s?\s+equation)\b", q_lower):
            nums = extract_numbers(query)
            if nums:
                f = nums[0]
                h = 6.62607015e-34  # J*s
                e_joules = h * f
                e_ev = e_joules / 1.602176634e-19
                return f"SELECT {f} AS frequency_hz, {e_joules} AS energy_joules, {round(e_ev, 4)} AS energy_electron_volts_ev;"

        # =========================================================================
        # 4. ADVANCED FINANCE & INVESTMENT FORMULAS
        # =========================================================================
        # Sharpe Ratio: S = (Rp - Rf) / sigma_p
        if re.search(r"\b(sharpe\s+ratio|risk[- ]adjusted\s+return)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                rp, rf, sigma = nums[0], nums[1], nums[2]
                if sigma > 0:
                    sharpe = (rp - rf) / sigma
                    return f"SELECT {rp} AS portfolio_return_pct, {rf} AS risk_free_rate_pct, {sigma} AS std_deviation_pct, {round(sharpe, 3)} AS sharpe_ratio;"

        # CAPM Expected Return: E(R) = Rf + beta * (Rm - Rf)
        if re.search(r"\b(capm|capital\s+asset\s+pricing|expected\s+return)\b", q_lower) and "beta" in q_lower:
            nums = extract_numbers(query)
            if len(nums) >= 3:
                rf, beta, rm = nums[0], nums[1], nums[2]
                exp_ret = rf + beta * (rm - rf)
                return f"SELECT {rf} AS risk_free_rate_pct, {beta} AS asset_beta, {rm} AS market_return_pct, {round(exp_ret, 2)} AS capm_expected_return_pct;"

        # WACC (Weighted Average Cost of Capital)
        if re.search(r"\b(wacc|cost\s+of\s+capital)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 5:
                we, wd, re_cost, rd_cost, tax = nums[0], nums[1], nums[2], nums[3], nums[4]
                # Normalize percentages to decimals if needed
                if we > 1.0 and we + wd <= 105:
                    we /= 100.0
                    wd /= 100.0
                if tax > 1.0: tax /= 100.0
                wacc = (we * re_cost) + (wd * rd_cost * (1.0 - tax))
                return f"SELECT {round(we, 2)} AS equity_weight, {round(wd, 2)} AS debt_weight, {re_cost} AS cost_equity_pct, {rd_cost} AS cost_debt_pct, {round(wacc, 2)} AS wacc_pct;"

        # Net Present Value (NPV): e.g. "Calculate NPV for discount rate 10%, initial investment 10000, cash flows [3000, 4000, 5000, 2000]"
        if re.search(r"\b(npv|net\s+present\s+value)\b", q_lower):
            lists = extract_number_lists(query)
            nums = extract_numbers(query)
            rate = nums[0] / 100.0 if nums and nums[0] > 1.0 else (nums[0] if nums else 0.1)
            c0 = nums[1] if len(nums) > 1 and not lists else (nums[1] if len(nums) > 1 else 10000.0)
            cfs = lists[0] if lists else nums[2:]
            if cfs:
                npv = -c0 + sum(cf / ((1.0 + rate) ** (t + 1)) for t, cf in enumerate(cfs))
                return f"SELECT {round(rate * 100, 2)} AS discount_rate_pct, {c0} AS initial_investment, {len(cfs)} AS cash_flow_periods, {round(npv, 2)} AS net_present_value;"

        # Price-to-Earnings (P/E) & EPS: e.g. "P/E ratio for share price 150 and EPS 7.5"
        if re.search(r"\b(p/e|pe\s+ratio|price\s+to\s+earnings)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                price, eps = nums[0], nums[1]
                if eps > 0:
                    pe = price / eps
                    return f"SELECT {price} AS share_price, {eps} AS earnings_per_share_eps, {round(pe, 2)} AS pe_ratio;"

        # Dividend Yield: e.g. "Dividend yield for annual dividend 4.5 and stock price 90"
        if re.search(r"\b(dividend\s+yield)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                div, price = nums[0], nums[1]
                if price > 0:
                    dy = (div / price) * 100.0
                    return f"SELECT {div} AS annual_dividend, {price} AS stock_price, {round(dy, 2)} AS dividend_yield_pct;"

        # =========================================================================
        # 5. NON-FINANCE & BUSINESS / SAAS METRICS
        # =========================================================================
        # LTV to CAC Ratio: e.g. "LTV to CAC ratio for LTV 1800 and CAC 300"
        if re.search(r"\b(ltv\s*:\s*cac|ltv\s+to\s+cac|ratio\s+of\s+ltv)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                ltv, cac = nums[0], nums[1]
                if cac > 0:
                    ratio = ltv / cac
                    health = "Excellent (>3x)" if ratio >= 3.0 else ("Moderate (1-3x)" if ratio >= 1.0 else "Critical (<1x)")
                    return f"SELECT {ltv} AS ltv, {cac} AS cac, {round(ratio, 2)} AS ltv_cac_ratio, '{health}' AS unit_economics_health;"

        # Customer Acquisition Cost (CAC): e.g. "Calculate CAC for marketing spend 50000 and 250 customers"
        if re.search(r"\b(cac|customer\s+acquisition\s+cost)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                spend, custs = nums[0], nums[1]
                if custs > 0:
                    cac = spend / custs
                    return f"SELECT {spend} AS total_sales_marketing_spend, {int(custs)} AS new_customers_acquired, {round(cac, 2)} AS customer_acquisition_cost_cac;"

        # Customer Lifetime Value (LTV): e.g. "Calculate LTV for ARPU 120, gross margin 80%, churn rate 5%"
        if re.search(r"\b(ltv|clv|customer\s+lifetime\s+value)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                arpu = nums[0]
                margin = nums[1] / 100.0 if len(nums) >= 3 and nums[1] > 1.0 else (nums[1] if len(nums) >= 3 else 0.8)
                churn = (nums[2] / 100.0 if nums[2] > 1.0 else nums[2]) if len(nums) >= 3 else (nums[1] / 100.0 if nums[1] > 1.0 else nums[1])
                if churn > 0:
                    ltv = (arpu * margin) / churn
                    return f"SELECT {arpu} AS arpu, {round(margin * 100, 1)} AS gross_margin_pct, {round(churn * 100, 2)} AS churn_rate_pct, {round(ltv, 2)} AS customer_lifetime_value_ltv;"

        # Churn Rate & Retention Rate: e.g. "Churn rate for 50 lost customers out of 1000 start customers"
        if re.search(r"\b(churn\s+rate|retention\s+rate)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                lost_or_retained, total_start = nums[0], nums[1]
                if total_start > 0:
                    pct = (lost_or_retained / total_start) * 100.0
                    churn_pct = pct if "churn" in q_lower else (100.0 - pct)
                    ret_pct = (100.0 - pct) if "churn" in q_lower else pct
                    return f"SELECT {round(churn_pct, 2)} AS churn_rate_pct, {round(ret_pct, 2)} AS retention_rate_pct;"

        # Cash Runway & Monthly Burn Rate: e.g. "Cash runway for cash balance 500000 and monthly burn rate 25000"
        if re.search(r"\b(runway|burn\s+rate|cash\s+runway)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                balance, burn = nums[0], nums[1]
                if burn > 0:
                    runway_months = balance / burn
                    return f"SELECT {balance} AS cash_balance, {burn} AS monthly_burn_rate, {round(runway_months, 1)} AS runway_months;"

        # Break-Even Point (Units and Sales): e.g. "Break even units for fixed costs 40000, selling price 100, variable cost 60"
        if re.search(r"\b(break[- ]even|bep)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                fc, p, vc = nums[0], nums[1], nums[2]
                contrib_margin = p - vc
                if contrib_margin > 0:
                    bep_units = fc / contrib_margin
                    bep_revenue = bep_units * p
                    return (
                        f"SELECT {fc} AS fixed_costs, {p} AS selling_price_per_unit, {vc} AS variable_cost_per_unit, "
                        f"{round(contrib_margin, 2)} AS unit_contribution_margin, {round(bep_units, 1)} AS break_even_units, "
                        f"{round(bep_revenue, 2)} AS break_even_sales_revenue;"
                    )

        # Economic Order Quantity (EOQ): e.g. "Calculate EOQ for annual demand 10000, setup cost 50, holding cost 2"
        if re.search(r"\b(eoq|economic\s+order\s+quantity)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                d, s, h = nums[0], nums[1], nums[2]
                if h > 0:
                    eoq = math.sqrt((2 * d * s) / h)
                    return f"SELECT {d} AS annual_demand_units, {s} AS order_setup_cost, {h} AS annual_holding_cost, {round(eoq, 1)} AS economic_order_quantity_units;"

        # Inventory Turnover Ratio: e.g. "Inventory turnover for COGS 500000 and average inventory 100000"
        if re.search(r"\b(inventory\s+turnover|stock\s+turnover)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                cogs, avg_inv = nums[0], nums[1]
                if avg_inv > 0:
                    ito = cogs / avg_inv
                    days = 365.0 / ito
                    return f"SELECT {cogs} AS cogs, {avg_inv} AS average_inventory, {round(ito, 2)} AS inventory_turnover_ratio, {round(days, 1)} AS days_sales_of_inventory_dsi;"

        # =========================================================================
        # 6. MULTI-SPORT ANALYTICS
        # =========================================================================
        # Cricket: Batting Average
        if re.search(r"\b(batting\s+average)\b", q_lower) and any(w in q_lower for w in ["runs", "innings", "dismissals", "out"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                runs, innings = nums[0], nums[1]
                if innings > 0:
                    avg = runs / innings
                    return f"SELECT {runs} AS runs_scored, {innings} AS innings_dismissed, {round(avg, 2)} AS batting_average;"

        # Cricket: Bowling Average
        if re.search(r"\b(bowling\s+average)\b", q_lower) and any(w in q_lower for w in ["runs", "wickets", "conceded"]):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                runs, wkts = nums[0], nums[1]
                if wkts > 0:
                    b_avg = runs / wkts
                    return f"SELECT {runs} AS runs_conceded, {wkts} AS wickets_taken, {round(b_avg, 2)} AS bowling_average;"

        # Football / Soccer: Goal Conversion Rate
        if re.search(r"\b(goal\s+conversion|shot\s+conversion)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                goals, shots = nums[0], nums[1]
                if shots > 0:
                    conv = (goals / shots) * 100.0
                    return f"SELECT {goals} AS goals_scored, {shots} AS total_shots, {round(conv, 2)} AS goal_conversion_percentage;"

        # Football / Soccer: Points Per Match (PPM)
        if re.search(r"\b(points\s+per\s+match|ppm)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                w, d, matches = nums[0], nums[1], nums[2]
                pts = (w * 3) + d
                if matches > 0:
                    ppm = pts / matches
                    return f"SELECT {w} AS wins, {d} AS draws, {pts} AS total_points, {matches} AS matches_played, {round(ppm, 2)} AS points_per_match;"

        # Basketball: True Shooting Percentage (TS%)
        if re.search(r"\b(true\s+shooting|ts%)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                pts, fga, fta = nums[0], nums[1], nums[2]
                den = 2 * (fga + 0.44 * fta)
                if den > 0:
                    ts_pct = (pts / den) * 100.0
                    return f"SELECT {pts} AS points, {fga} AS field_goal_attempts, {fta} AS free_throw_attempts, {round(ts_pct, 2)} AS true_shooting_pct;"

        # Basketball: Effective Field Goal Percentage (eFG%)
        if re.search(r"\b(effective\s+field\s+goal|efg%)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 3:
                fgm, p3m, fga = nums[0], nums[1], nums[2]
                if fga > 0:
                    efg = ((fgm + 0.5 * p3m) / fga) * 100.0
                    return f"SELECT {fgm} AS field_goals_made, {p3m} AS three_pointers_made, {fga} AS field_goal_attempts, {round(efg, 2)} AS effective_field_goal_pct;"

        # Baseball: Batting Average (BA)
        if re.search(r"\b(baseball\s+batting\s+average|batting\s+avg)\b", q_lower) and ("at bat" in q_lower or "hits" in q_lower or "ab" in q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                hits, ab = nums[0], nums[1]
                if ab > 0:
                    ba = hits / ab
                    return f"SELECT {hits} AS hits, {ab} AS at_bats, {round(ba, 3)} AS batting_average;"

        # Baseball: Earned Run Average (ERA)
        if re.search(r"\b(era|earned\s+run\s+average)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                er, ip = nums[0], nums[1]
                if ip > 0:
                    era = (9.0 * er) / ip
                    return f"SELECT {er} AS earned_runs, {ip} AS innings_pitched, {round(era, 2)} AS earned_run_average_era;"

        # Running & Athletics: Pace and Speed
        if re.search(r"\b(running\s+pace|running\s+speed|marathon\s+pace|pace\s+calculator)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                dist_km, time_min = nums[0], nums[1]
                if dist_km > 0 and time_min > 0:
                    pace_min_km = time_min / dist_km
                    speed_kmh = (dist_km / time_min) * 60.0
                    pace_min_mile = pace_min_km * 1.60934
                    speed_mph = speed_kmh * 0.621371
                    return (
                        f"SELECT {dist_km} AS distance_km, {time_min} AS time_minutes, "
                        f"{round(pace_min_km, 2)} AS pace_minutes_per_km, {round(pace_min_mile, 2)} AS pace_minutes_per_mile, "
                        f"{round(speed_kmh, 2)} AS speed_kmh, {round(speed_mph, 2)} AS speed_mph;"
                    )

        # =========================================================================
        # 7. MOVIES & ENTERTAINMENT ANALYTICS
        # =========================================================================
        # Box Office ROI: e.g. "Movie box office ROI for budget 60M and box office 240M"
        if re.search(r"\b(box\s+office\s+roi|movie\s+roi|film\s+roi)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                budget, gross = nums[0], nums[1]
                if budget > 0:
                    roi = ((gross - budget) / budget) * 100.0
                    mult = gross / budget
                    return f"SELECT {budget} AS budget_millions, {gross} AS worldwide_gross_millions, {round(roi, 2)} AS box_office_roi_pct, {round(mult, 2)} AS box_office_multiplier;"

        # Box Office Multiplier: e.g. "Box office multiplier for budget 50 million and collection 220 million"
        if re.search(r"\b(box\s+office\s+multiplier|theatrical\s+multiplier)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                budget, gross = nums[0], nums[1]
                if budget > 0:
                    mult = gross / budget
                    return f"SELECT {budget} AS production_budget, {gross} AS total_box_office, {round(mult, 2)} AS box_office_multiplier;"

        # Domestic vs International Box Office Share %
        if re.search(r"\b(domestic\s+share|international\s+share|box\s+office\s+split)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                dom, total = nums[0], nums[1]
                if total > 0:
                    dom_pct = (dom / total) * 100.0
                    intl_pct = 100.0 - dom_pct
                    return f"SELECT {dom} AS domestic_gross, {total} AS total_worldwide, {round(dom_pct, 2)} AS domestic_share_pct, {round(intl_pct, 2)} AS international_share_pct;"

        # Streaming Video Completion Rate: e.g. "Streaming completion rate for 450000 completions from 600000 starts"
        if re.search(r"\b(completion\s+rate|stream\s+retention|audience\s+drop[- ]?off)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                comp, starts = nums[0], nums[1]
                if starts > 0:
                    comp_rate = (comp / starts) * 100.0
                    drop_rate = 100.0 - comp_rate
                    return f"SELECT {comp} AS completions, {starts} AS stream_starts, {round(comp_rate, 2)} AS completion_rate_pct, {round(drop_rate, 2)} AS dropoff_rate_pct;"

        # =========================================================================
        # 8. GEOGRAPHICAL & GEOSPATIAL FORMULAS
        # =========================================================================
        # Haversine Great-Circle Distance between (lat1, lon1) and (lat2, lon2)
        if re.search(r"\b(haversine|great[- ]circle\s+distance|distance\s+between\s+coordinates|lat(?:itude)?\s+and\s+long(?:itude)?)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 4:
                lat1, lon1, lat2, lon2 = nums[0], nums[1], nums[2], nums[3]
                phi1, phi2 = math.radians(lat1), math.radians(lat2)
                dphi = math.radians(lat2 - lat1)
                dlambda = math.radians(lon2 - lon1)
                a = (math.sin(dphi / 2.0) ** 2) + math.cos(phi1) * math.cos(phi2) * (math.sin(dlambda / 2.0) ** 2)
                c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
                r_km = 6371.0088
                dist_km = r_km * c
                dist_miles = dist_km * 0.621371
                dist_nm = dist_km * 0.539957
                return (
                    f"SELECT {lat1} AS lat1, {lon1} AS lon1, {lat2} AS lat2, {lon2} AS lon2, "
                    f"{round(dist_km, 2)} AS distance_km, {round(dist_miles, 2)} AS distance_miles, "
                    f"{round(dist_nm, 2)} AS distance_nautical_miles;"
                )

        # Population Density: e.g. "Population density for population 14000000 and area 603 square kilometers"
        if re.search(r"\b(population\s+density|density\s+of\s+population)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                pop, area = nums[0], nums[1]
                if area > 0:
                    density_km2 = pop / area
                    density_mi2 = density_km2 * 2.58999
                    return (
                        f"SELECT {int(pop)} AS total_population, {area} AS area_sq_km, "
                        f"{round(density_km2, 2)} AS people_per_sq_km, {round(density_mi2, 2)} AS people_per_sq_mile;"
                    )

        # Map Scale Distance: e.g. "Real distance for map distance 5 cm on 1:50000 scale map"
        if re.search(r"\b(map\s+scale|scale\s+ratio|cartograph|scale\s+map)\b", q_lower):
            m_scale = re.search(r"1\s*:\s*(\d+)", q_lower)
            scale_denom = float(m_scale.group(1)) if m_scale else None
            nums = extract_numbers(query)
            map_cm = nums[0] if nums else 1.0
            if scale_denom is None and len(nums) >= 2:
                scale_denom = max(nums)
            if scale_denom:
                real_cm = map_cm * scale_denom
                real_m = real_cm / 100.0
                real_km = real_m / 1000.0
                return f"SELECT {map_cm} AS map_cm, {scale_denom} AS scale_ratio_1_to_n, {round(real_m, 2)} AS actual_distance_meters, {round(real_km, 3)} AS actual_distance_km;"

        # Solar Elevation Angle Approximation: alpha = 90 - |lat - declination|
        if re.search(r"\b(solar\s+elevation|sun\s+angle|zenith\s+angle)\b", q_lower):
            nums = extract_numbers(query)
            if len(nums) >= 2:
                lat, decl = nums[0], nums[1]
                zenith = abs(lat - decl)
                elev = max(0.0, 90.0 - zenith)
                return f"SELECT {lat} AS latitude_deg, {decl} AS solar_declination_deg, {round(elev, 2)} AS solar_elevation_angle_deg, {round(zenith, 2)} AS solar_zenith_angle_deg;"

        # =========================================================================
        # 9. WORLDWIDE UNIT CONVERSIONS (Expanded)
        # =========================================================================
        # Pressure conversions (bar <-> psi <-> pascal <-> atm)
        m_bar2psi = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*bar\s+to\s+psi", q_lower)
        if m_bar2psi:
            b = float(m_bar2psi.group(1))
            return f"SELECT {b} AS bar, {round(b * 14.5038, 2)} AS psi;"

        m_psi2bar = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*psi\s+to\s+bar", q_lower)
        if m_psi2bar:
            p = float(m_psi2bar.group(1))
            return f"SELECT {p} AS psi, {round(p * 0.0689476, 4)} AS bar;"

        m_atm2kpa = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*atm\s+to\s+kpa", q_lower)
        if m_atm2kpa:
            a = float(m_atm2kpa.group(1))
            return f"SELECT {a} AS atm, {round(a * 101.325, 2)} AS kpa;"

        # Energy conversions (joules <-> calories <-> kwh)
        m_j2cal = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*(?:joules?|j)\s+to\s*(?:calories?|cal)", q_lower)
        if m_j2cal:
            j = float(m_j2cal.group(1))
            return f"SELECT {j} AS joules, {round(j / 4.184, 2)} AS calories;"

        m_kwh2j = re.search(r"convert\s+(\d+(?:\.\d+)?)\s*kwh\s+to\s*(?:joules?|j)", q_lower)
        if m_kwh2j:
            k = float(m_kwh2j.group(1))
            return f"SELECT {k} AS kwh, {round(k * 3600000.0, 0)} AS joules;"

        return None


formula_engine = UniversalFormulaEngine()
