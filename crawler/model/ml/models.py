"""
ml/models.py
Định nghĩa các lớp và hàm lõi của mô hình định giá Homigo ML.
Được tách riêng vào module này để đảm bảo khi serialize bằng joblib/pickle
sẽ không bị lỗi module '__main__'.
"""

from __future__ import annotations
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.neighbors import BallTree
import xgboost as xgb

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DROP_COLS = ["region_price_median", "district_median_price", "ward_median_price"]
PPM_RANGE = (30_000, 600_000)
MAX_PRICE = 25_000_000


def make_base_features(X: pd.DataFrame) -> pd.DataFrame:
    """Tạo các đặc trưng phái sinh cơ sở."""
    X = X.drop(columns=[c for c in DROP_COLS if c in X.columns]).copy()
    amen = [c for c in X.columns if c.startswith("is_")]
    X["n_amenities"] = X[amen].sum(axis=1)
    X["log_area"] = np.log1p(X["area_m2"])
    X["lat_lng_sum"] = X["lat"] + X["lng"]
    X["lat_lng_diff"] = X["lat"] - X["lng"]
    return X


def attach(X: pd.DataFrame, nb: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([X.reset_index(drop=True), nb.reset_index(drop=True)], axis=1)


class SpatialTE:
    """Feature giá của k phòng gần nhất theo tọa độ. Fit trên tập train."""

    def __init__(self, ks=(5, 20)):
        self.ks = tuple(ks)
        self.kmax = max(ks)
        self.tree = None
        self.logy = None
        self.logppm = None

    def fit(self, X: pd.DataFrame, y: pd.Series):
        self.tree = BallTree(np.radians(X[["lat", "lng"]].values), metric="haversine")
        y = np.asarray(y, dtype=float).ravel()
        area = np.asarray(X["area_m2"], dtype=float).ravel()
        self.logy = np.log1p(y)
        self.logppm = np.log(np.clip(y, 1, None) / np.clip(area, 1, None))
        return self

    def _agg(self, dist: np.ndarray, idx: np.ndarray) -> pd.DataFrame:
        out = {}
        for k in self.ks:
            out[f"nb{k}_logy_mean"] = self.logy[idx[:, :k]].mean(1)
            out[f"nb{k}_logppm_mean"] = self.logppm[idx[:, :k]].mean(1)
            out[f"nb{k}_logppm_med"] = np.median(self.logppm[idx[:, :k]], axis=1)
            out[f"nb{k}_dist_km"] = dist[:, :k].mean(1) * 6371.0
        out[f"nb{self.kmax}_logy_std"] = self.logy[idx].std(1)
        return pd.DataFrame(out)

    def transform_train(self, X: pd.DataFrame) -> pd.DataFrame:
        """Cho chính các dòng đã fit: loại chính nó để chống rò rỉ dữ liệu (leakage)."""
        n = len(X)
        d, i = self.tree.query(np.radians(X[["lat", "lng"]].values), k=self.kmax + 1)
        keep = i != np.arange(n)[:, None]
        order = np.argsort(~keep, axis=1, kind="stable")
        i = np.take_along_axis(i, order, 1)[:, : self.kmax]
        d = np.take_along_axis(d, order, 1)[:, : self.kmax]
        return self._agg(d, i)

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Cho các dòng suy luận / val / test."""
        d, i = self.tree.query(np.radians(X[["lat", "lng"]].values), k=self.kmax)
        return self._agg(d, i)


FINAL_PREDICT = {
    "LightGBM": lambda m, X: m.predict(X, num_iteration=m.best_iteration),
    "XGBoost": lambda m, X: m.predict(xgb.DMatrix(X, enable_categorical=True)),
}


def predict_log(res: dict, X_raw: pd.DataFrame) -> np.ndarray:
    Xb = make_base_features(X_raw).reset_index(drop=True)
    Xf = attach(Xb, res["fe"].transform(Xb))
    return FINAL_PREDICT[res["model_name"]](res["best_estimator"], Xf)


def blend_predict(results: list[dict], X_raw: pd.DataFrame, smear: bool = True) -> np.ndarray:
    logs = np.mean([predict_log(r, X_raw) for r in results], axis=0)
    s = np.mean([r["smear"] for r in results]) if smear else 1.0
    return np.expm1(logs) * s


class PriceInterval:
    """Khoảng giá [low, high] với độ phủ danh định CQR."""

    def __init__(self, lgb_result, coverage=0.8, ks=(5, 20), cal_frac=0.2, es_frac=0.15, seed=42, winsor=(0.01, 0.99)):
        self.base = {
            k: v for k, v in lgb_result["best_params"].items()
            if k not in ("objective", "metric", "alpha")
        }
        self.coverage, self.ks, self.seed = coverage, ks, seed
        self.cal_frac, self.es_frac, self.winsor = cal_frac, es_frac, winsor
        a = (1.0 - coverage) / 2.0
        self.alphas = (a, 1.0 - a)
        self.te = None
        self.models = []
        self.qhat = 0.0
        self._cal = None

    def fit(self, X_raw: pd.DataFrame, y: pd.Series):
        y = pd.Series(np.asarray(y, dtype=float).ravel())
        X = make_base_features(X_raw).reset_index(drop=True)
        idx = np.arange(len(X))
        rest, cal = train_test_split(idx, test_size=self.cal_frac, random_state=self.seed)
        fit, es = train_test_split(rest, test_size=self.es_frac, random_state=self.seed)

        self.te = SpatialTE(self.ks).fit(X.iloc[fit], y.iloc[fit])
        Xf = attach(X.iloc[fit], self.te.transform_train(X.iloc[fit]))
        Xe = attach(X.iloc[es], self.te.transform(X.iloc[es]))
        Xc = attach(X.iloc[cal], self.te.transform(X.iloc[cal]))

        y_fit = y.iloc[fit]
        y_fit = y_fit.clip(y_fit.quantile(self.winsor[0]), y_fit.quantile(self.winsor[1]))
        yf = np.log1p(y_fit.values)
        ye, yc = np.log1p(y.iloc[es].values), np.log1p(y.iloc[cal].values)

        self.models = []
        for a in self.alphas:
            p = {**self.base, "objective": "quantile", "alpha": a, "metric": "quantile"}
            m = lgb.train(
                p,
                lgb.Dataset(Xf, yf),
                num_boost_round=1500,
                valid_sets=[lgb.Dataset(Xe, ye)],
                callbacks=[lgb.early_stopping(50, verbose=False)],
            )
            self.models.append(m)

        lo, hi = self._raw(Xc)
        self._cal = (lo, hi, yc)
        score = np.maximum(lo - yc, yc - hi)
        n = len(score)
        level = min(1.0, np.ceil((n + 1) * self.coverage) / n)
        self.qhat = float(np.quantile(score, level, method="higher"))
        return self

    def _raw(self, Xf: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        lo, hi = (m.predict(Xf, num_iteration=m.best_iteration) for m in self.models)
        return np.minimum(lo, hi), np.maximum(lo, hi)

    def predict(self, X_raw: pd.DataFrame) -> pd.DataFrame:
        Xb = make_base_features(X_raw).reset_index(drop=True)
        lo, hi = self._raw(attach(Xb, self.te.transform(Xb)))
        return pd.DataFrame({
            "low": np.expm1(lo - self.qhat),
            "high": np.expm1(hi + self.qhat),
        })


class MondrianPriceInterval(PriceInterval):
    """Mondrian Conformal Prediction: qhat hiệu chuẩn riêng theo từng phân khúc giá."""

    def __init__(self, lgb_result, n_bins=4, min_bin=150, **kw):
        super().__init__(lgb_result, **kw)
        self.n_bins, self.min_bin = n_bins, min_bin
        self.edges = None
        self.qhats = []

    def fit(self, X_raw: pd.DataFrame, y: pd.Series):
        super().fit(X_raw, y)
        lo, hi, yc = self._cal
        center = (lo + hi) / 2.0
        score = np.maximum(lo - yc, yc - hi)

        nb = int(max(1, min(self.n_bins, len(center) // self.min_bin)))
        self.edges = np.quantile(center, np.linspace(0, 1, nb + 1)[1:-1])
        b = np.searchsorted(self.edges, center, side="right")

        self.qhats = []
        for k in range(nb):
            s = score[b == k]
            if len(s) == 0:
                self.qhats.append(self.qhat)
                continue
            n = len(s)
            level = min(1.0, np.ceil((n + 1) * self.coverage) / n)
            self.qhats.append(float(np.quantile(s, level, method="higher")))
        return self

    def predict(self, X_raw: pd.DataFrame) -> pd.DataFrame:
        Xb = make_base_features(X_raw).reset_index(drop=True)
        lo, hi = self._raw(attach(Xb, self.te.transform(Xb)))
        center = (lo + hi) / 2.0
        b = np.searchsorted(self.edges, center, side="right")
        q = np.array([self.qhats[k] for k in b])
        return pd.DataFrame({
            "low": np.expm1(lo - q),
            "high": np.expm1(hi + q),
        })


class InputGuard:
    def __init__(self, ppm_range=PPM_RANGE, max_price=MAX_PRICE, margin_deg=0.02):
        self.ppm_range = ppm_range
        self.max_price = max_price
        self.margin = margin_deg
        self.area_rng = (8.0, 150.0)
        self.lat_rng = (10.3, 11.2)
        self.lng_rng = (106.3, 107.1)

    def fit(self, X_raw: pd.DataFrame):
        a = X_raw["area_m2"]
        m = self.margin
        self.area_rng = (float(a.quantile(0.005)), float(a.quantile(0.995)))
        self.lat_rng = (float(X_raw["lat"].min() - m), float(X_raw["lat"].max() + m))
        self.lng_rng = (float(X_raw["lng"].min() - m), float(X_raw["lng"].max() + m))
        return self

    def check(self, X_new: pd.DataFrame, price: np.ndarray) -> pd.DataFrame:
        price = np.asarray(price, dtype=float).ravel()
        area = X_new["area_m2"].to_numpy(dtype=float)
        lat = X_new["lat"].to_numpy(dtype=float)
        lng = X_new["lng"].to_numpy(dtype=float)
        ppm = price / np.clip(area, 1e-6, None)

        odd = (ppm < self.ppm_range[0]) | (ppm > self.ppm_range[1])
        oor = (
            (price > self.max_price)
            | (area < self.area_rng[0])
            | (area > self.area_rng[1])
            | (lat < self.lat_rng[0])
            | (lat > self.lat_rng[1])
            | (lng < self.lng_rng[0])
            | (lng > self.lng_rng[1])
        )

        status = np.where(oor, "oor", np.where(odd, "odd", "ok"))
        return pd.DataFrame({"status": status})
