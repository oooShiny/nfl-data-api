"""Fit the pre-1999 win probability model (pipeline/gold/win_probability.py)
on 1999+ nflverse plays and write pipeline/mappings/wp_model.json.

Run against a full gold database (data/nfl.duckdb):

    uv run python scripts/fit_wp_model.py            # fit, check, write
    uv run python scripts/fit_wp_model.py --check    # just print the checks for the saved model

Prints the checks: held-out seasons against nflverse's wp/vegas_wp, and
calibration on pre-1999 PFR plays against how the games actually ended.
"""
import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.config import GOLD_DB, SILVER_DIR  # noqa: E402
from pipeline.gold import win_probability as wpm  # noqa: E402

TEST_FROM = 2019  # held-out seasons for the check fit
# Seasons for the fixed expected points of kickoffs and extra points: before
# the 2015 move of the extra point back to the 15, closer to the PFR era.
KICK_EP_SEASONS = (1999, 2014)


def irls(X: np.ndarray, y: np.ndarray, iters: int = 30) -> np.ndarray:
    b = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-np.clip(X @ b, -30, 30)))
        hess = (X * (p * (1 - p))[:, None]).T @ X + 1e-6 * np.eye(len(b))
        step = np.linalg.solve(hess, X.T @ (p - y) + 1e-6 * b)
        b -= step
        if np.max(np.abs(step)) < 1e-9:
            break
    return b


def log_loss(p, y):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def calibration(p, y, bins=10):
    idx = np.minimum((p * bins).astype(int), bins - 1)
    return [(f"{i / bins:.1f}-{(i + 1) / bins:.1f}", int((idx == i).sum()),
             round(float(y[idx == i].mean()), 3) if (idx == i).any() else None) for i in range(bins)]


def training_data(con, model_stub: dict, parts: dict) -> dict:
    """Feature matrices per model part, plus outcome and comparison columns."""
    feats = {part: wpm.feature_sql(model_stub, spread) for part, spread in parts.items()}
    cols = ",\n".join(f"{expr} AS {part}__{name}" for part, f in feats.items() for name, expr in f.items())
    rows = con.execute(f"""
        SELECT m.season, m.secs, m.true_secs, m.quarter,
               s.spread_line IS NOT NULL AS has_line, s.qh IS NOT NULL AS has_elo,
               CASE WHEN s.result = 0 THEN 0.5 WHEN (s.result > 0) = (m.posteam = m.home_team) THEN 1.0 ELSE 0.0 END AS y,
               v.wp::DOUBLE AS nfl_wp, v.vegas_wp::DOUBLE AS nfl_vegas_wp,
               {cols}
        FROM {wpm.nflverse_inputs_sql()} m
        JOIN {wpm.game_spreads_sql(model_stub)} s USING (game_id)
        LEFT JOIN read_parquet('{SILVER_DIR / "pbp" / "*.parquet"}') v ON v.game_id = m.game_id AND v.play_id = m.seq
        WHERE s.result IS NOT NULL AND m.season >= 1999
    """).fetchnumpy()
    d = {k: np.ma.filled(v.astype(float) if v.dtype != object else v, np.nan) if np.ma.isMaskedArray(v) else v
         for k, v in rows.items()}
    d["X"] = {part: np.column_stack([np.asarray(d[f"{part}__{n}"], dtype=float) for n in wpm.FEATURES])
              for part in parts}
    return d


def fit_elo_spread(con) -> dict:
    s = con.execute(f"""SELECT spread_line, qh, CASE WHEN neutral THEN 0 ELSE 1 END AS home
                        FROM {wpm.game_spreads_sql(None)}
                        WHERE season >= 1999 AND spread_line IS NOT NULL AND qh IS NOT NULL""").fetchnumpy()
    X = np.column_stack([np.ones(len(s["qh"])), s["qh"], s["home"]])
    b, *_ = np.linalg.lstsq(X, s["spread_line"], rcond=None)
    resid = s["spread_line"] - X @ b
    return {"const": round(float(b[0]), 5), "qbelo_diff": round(float(b[1]), 6), "home": round(float(b[2]), 5),
            "games": int(len(resid)), "resid_sd": round(float(resid.std()), 2)}


def pfr_check(con, model: dict) -> dict:
    """Calibration of the model on pre-1999 PFR plays, against the games' results."""
    wp = f"1 / (1 + exp(-{wpm.logit_sql(model, 'wp', '0')}))"
    line = f"1 / (1 + exp(-{wpm.logit_sql(model, 'vegas_wp', wpm.posteam_spread('spread_line'))}))"
    elo = f"1 / (1 + exp(-{wpm.logit_sql(model, 'elo_wp', wpm.posteam_spread('elo_spread'))}))"
    d = con.execute(f"""
        SELECT {wp} AS wp, CASE WHEN s.spread_line IS NOT NULL THEN {line} END AS line_wp, {elo} AS elo_wp,
               CASE WHEN s.result = 0 THEN 0.5 WHEN (s.result > 0) = (m.posteam = m.home_team) THEN 1.0 ELSE 0.0 END AS y
        FROM {wpm.pfr_inputs_sql()} m JOIN {wpm.game_spreads_sql(model)} s USING (game_id)
        WHERE s.result IS NOT NULL
    """).fetchnumpy()
    y = np.asarray(d["y"], dtype=float)
    out = {"plays": int(len(y))}
    for col in ("wp", "line_wp", "elo_wp"):
        p = np.ma.filled(d[col].astype(float), np.nan) if np.ma.isMaskedArray(d[col]) else np.asarray(d[col], float)
        ok = ~np.isnan(p)
        out[col] = {"plays": int(ok.sum()), "log_loss": round(log_loss(p[ok], y[ok]), 4),
                    "brier": round(float(np.mean((p[ok] - y[ok]) ** 2)), 4), "calibration": calibration(p[ok], y[ok])}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="only print the checks for the saved model")
    args = ap.parse_args()
    con = duckdb.connect(str(GOLD_DB), read_only=True)

    if args.check:
        model = wpm.load_model()
        print(json.dumps(pfr_check(con, model), indent=1))
        return

    kick = con.execute(f"""
        SELECT avg(ep) FILTER (WHERE play_type = 'kickoff'), avg(ep) FILTER (WHERE play_type = 'extra_point')
        FROM fact_plays WHERE season BETWEEN {KICK_EP_SEASONS[0]} AND {KICK_EP_SEASONS[1]}""").fetchone()
    model = {"kickoff_ep": round(kick[0], 3), "extra_point_ep": round(kick[1], 3),
             "elo_spread": fit_elo_spread(con)}
    print("elo spread:", model["elo_spread"])
    parts = {"wp": "0", "vegas_wp": wpm.posteam_spread("spread_line"), "elo_wp": wpm.posteam_spread("elo_spread")}
    d = training_data(con, model, parts)
    y, season = d["y"], d["season"]
    rows = {"wp": np.ones(len(y), bool), "vegas_wp": d["has_line"].astype(bool), "elo_wp": d["has_elo"].astype(bool)}
    test = season >= TEST_FROM
    late = test & (d["true_secs"] < 300) & (d["quarter"] == 4)
    checks = {}
    for part in parts:
        X, use = d["X"][part], rows[part]
        keep = [i for i, n in enumerate(wpm.FEATURES) if not (part == "wp" and n == "spread_t")]
        Xp = X[:, keep]
        # Held-out check: fit on the earlier seasons, score the later ones.
        b = irls(Xp[use & ~test], y[use & ~test])
        p = 1 / (1 + np.exp(-(Xp @ b)))
        ref = d["nfl_wp"] if part == "wp" else d["nfl_vegas_wp"]
        m = use & test & ~np.isnan(ref)
        ml = use & late & ~np.isnan(ref)
        checks[part] = {
            "train_seasons": f"1999-{TEST_FROM - 1}", "test_seasons": f"{TEST_FROM}+", "test_plays": int(m.sum()),
            "log_loss": round(log_loss(p[m], y[m]), 4),
            "nflverse_log_loss": round(log_loss(ref[m], y[m]), 4),
            "log_loss_last_5_min": round(log_loss(p[ml], y[ml]), 4),
            "nflverse_log_loss_last_5_min": round(log_loss(ref[ml], y[ml]), 4),
            "mean_abs_diff_vs_nflverse": round(float(np.mean(np.abs(p[m] - ref[m]))), 4),
            "calibration": calibration(p[m], y[m]),
        }
        # Final fit on every season.
        b = irls(Xp[use], y[use])
        coef = dict.fromkeys(wpm.FEATURES, 0.0)
        coef.update({wpm.FEATURES[k]: round(float(v), 6) for k, v in zip(keep, b)})
        seasons = season[use]
        model[part] = {"coef": coef, "plays": int(use.sum()),
                       "seasons": f"{int(seasons.min())}-{int(seasons.max())}"}
        print(part, json.dumps(checks[part]))
    model["checks"] = checks
    model["pfr_check"] = pfr_check(con, model)
    print("pfr:", json.dumps({k: (v if not isinstance(v, dict) else {kk: vv for kk, vv in v.items() if kk != "calibration"})
                              for k, v in model["pfr_check"].items()}))
    wpm.MODEL_PATH.write_text(json.dumps(model, indent=1) + "\n")
    print("wrote", wpm.MODEL_PATH)


if __name__ == "__main__":
    main()
