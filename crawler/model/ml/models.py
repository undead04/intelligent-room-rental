"""
ml/models.py
Định nghĩa các lớp và hàm lõi của mô hình định giá Homigo ML.
Được tách riêng vào module này để đảm bảo khi serialize bằng joblib/pickle
sẽ không bị lỗi module '__main__'.
"""

from __future__ import annotations
import copy
from typing import Tuple
import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.neighbors import BallTree
import xgboost as xgb

from crawler.model.ml.feature_extractor import (
    PRUNED_LOW_IMPACT_FLAGS,
    ROOM_TYPE_FILTER_RULES,
    VIETNAM_LAT_RANGE,
    VIETNAM_LNG_RANGE,
)


DROP_COLS = ["region_price_median", "district_median_price", "ward_median_price"] + PRUNED_LOW_IMPACT_FLAGS
PPM_RANGE = (30_000, 600_000)
MAX_PRICE = 25_000_000


def make_base_features(X: pd.DataFrame) -> pd.DataFrame:
    """Tạo các đặc trưng phái sinh cơ sở (đã khử đa cộng tuyến cho mô hình cây)."""
    X = X.drop(columns=[c for c in DROP_COLS if c in X.columns]).copy()
    safe_area = np.clip(X["area_m2"].to_numpy(dtype=float), 1.0, None)
    if "amenity_overall" in X.columns:
        amen_score = X["amenity_overall"].to_numpy(dtype=float)
    else:
        amen_cols = [c for c in X.columns if c.startswith("is_")]
        amen_score = X[amen_cols].mean(axis=1).to_numpy(dtype=float) * 5.0 if amen_cols else np.full(len(X), 3.0)

    X["amenity_density"] = amen_score / np.log1p(safe_area)
    X["lat_lng_sum"] = X["lat"] + X["lng"]
    X["lat_lng_diff"] = X["lat"] - X["lng"]
    return X


def attach(X: pd.DataFrame, nb: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([X.reset_index(drop=True), nb.reset_index(drop=True)], axis=1)


class SpatialTE:
    """Feature giá của k phòng gần nhất theo tọa độ (Inverse-Distance Weighting). Fit trên tập train.

    Tách biệt nhóm SLEEPBOX (room_type_id == 4, giá theo giường) khỏi nhóm phòng/căn hộ nguyên phòng
    và hỗ trợ exclude_self_match để triệt tiêu Inference Self-Leakage khi chấm điểm DB.
    """

    def __init__(self, ks=(5, 20)):
        self.ks = tuple(ks)
        self.kmax = max(ks)
        self.tree = None
        self.logy = None
        self.logppm = None
        self.fit_areas = None
        self.group_trees: dict[int, tuple[BallTree, np.ndarray]] = {}

    def fit(self, X: pd.DataFrame, y: pd.Series):
        coords = np.radians(X[["lat", "lng"]].values)
        self.tree = BallTree(coords, metric="haversine")
        y = np.asarray(y, dtype=float).ravel()
        area = np.asarray(X["area_m2"], dtype=float).ravel()
        self.logy = np.log1p(y)
        self.logppm = np.log(np.clip(y, 1, None) / np.clip(area, 1, None))
        self.fit_areas = area
        self.group_trees = {}
        if "room_type_id" in X.columns:
            rts = X["room_type_id"].fillna(1).to_numpy(dtype=int)
            for is_sb in (0, 1):
                m_idx = np.where((rts == 4) if is_sb == 1 else (rts != 4))[0]
                if len(m_idx) >= 5:
                    self.group_trees[is_sb] = (BallTree(coords[m_idx], metric="haversine"), m_idx)
        return self

    def _agg(self, dist: np.ndarray, idx: np.ndarray) -> pd.DataFrame:
        dist_km = dist * 6371.0
        weights = 1.0 / (1.0 + dist_km)
        max_avail = idx.shape[1]
        out = {}
        for k in self.ks:
            k_eff = min(k, max_avail)
            wk = weights[:, :k_eff]
            wk_norm = wk / np.clip(wk.sum(axis=1, keepdims=True), 1e-9, None)
            out[f"nb{k}_logy_mean"] = np.sum(self.logy[idx[:, :k_eff]] * wk_norm, axis=1)
            out[f"nb{k}_logppm_mean"] = np.sum(self.logppm[idx[:, :k_eff]] * wk_norm, axis=1)
            out[f"nb{k}_dist_km"] = dist_km[:, :k_eff].mean(1)
        out[f"nb{self.kmax}_logy_std"] = self.logy[idx].std(1)
        return pd.DataFrame(out)

    def _query_subset(
        self,
        coords: np.ndarray,
        areas: np.ndarray,
        tree: BallTree,
        map_idx: np.ndarray,
        is_train: bool,
        q_glob_idx: np.ndarray | None = None,
        exclude_self_match: bool = False,
    ) -> pd.DataFrame:
        n_fit = len(map_idx)
        fit_areas = getattr(self, "fit_areas", None)
        need_extra = is_train or (exclude_self_match and fit_areas is not None)
        k_q = min(self.kmax + (1 if need_extra else 0), n_fit)
        d, loc_i = tree.query(coords, k=k_q)
        glob_i = map_idx[loc_i]

        if is_train and q_glob_idx is not None:
            keep = glob_i != q_glob_idx[:, None]
            order = np.argsort(~keep, axis=1, kind="stable")
            k_take = min(self.kmax, max(1, k_q - 1))
            glob_i = np.take_along_axis(glob_i, order, 1)[:, :k_take]
            d = np.take_along_axis(d, order, 1)[:, :k_take]
        elif exclude_self_match and fit_areas is not None:
            is_self = (d < 1e-7) & (np.abs(fit_areas[glob_i] - areas[:, None]) < 1e-3)
            first_self = is_self & (np.cumsum(is_self, axis=1) == 1)
            keep = ~first_self
            order = np.argsort(~keep, axis=1, kind="stable")
            has_any_self = bool(np.any(first_self))
            k_take = min(self.kmax, max(1, k_q - (1 if (k_q > self.kmax or has_any_self) else 0)))
            glob_i = np.take_along_axis(glob_i, order, 1)[:, :k_take]
            d = np.take_along_axis(d, order, 1)[:, :k_take]
        else:
            k_take = min(self.kmax, k_q)
            glob_i = glob_i[:, :k_take]
            d = d[:, :k_take]

        if k_take < self.kmax:
            glob_i = np.hstack([glob_i, np.repeat(glob_i[:, -1:], self.kmax - k_take, axis=1)])
            d = np.hstack([d, np.repeat(d[:, -1:], self.kmax - k_take, axis=1)])
        return self._agg(d, glob_i)

    def _run(self, X: pd.DataFrame, is_train: bool = False, exclude_self_match: bool = False) -> pd.DataFrame:
        if len(X) == 0:
            return pd.DataFrame(
                columns=[
                    *(col for k in self.ks for col in (f"nb{k}_logy_mean", f"nb{k}_logppm_mean", f"nb{k}_dist_km")),
                    f"nb{self.kmax}_logy_std",
                ]
            )
        coords = np.radians(X[["lat", "lng"]].values)
        areas = np.asarray(X["area_m2"], dtype=float).ravel() if "area_m2" in X.columns else np.zeros(len(X))
        n = len(X)
        group_trees = getattr(self, "group_trees", None)
        if not group_trees or len(group_trees) < 2 or "room_type_id" not in X.columns:
            return self._query_subset(
                coords,
                areas,
                self.tree,
                np.arange(len(self.logy)),
                is_train,
                np.arange(n) if is_train else None,
                exclude_self_match,
            )

        rts = X["room_type_id"].fillna(1).to_numpy(dtype=int)
        parts = []
        for is_sb in (0, 1):
            sub_pos = np.where((rts == 4) if is_sb == 1 else (rts != 4))[0]
            if len(sub_pos) == 0:
                continue
            tree, map_idx = group_trees[is_sb]
            sub_df = self._query_subset(
                coords[sub_pos],
                areas[sub_pos],
                tree,
                map_idx,
                is_train,
                sub_pos if is_train else None,
                exclude_self_match,
            )
            sub_df.index = sub_pos
            parts.append(sub_df)
        return pd.concat(parts).sort_index().reset_index(drop=True)

    def transform_train(self, X: pd.DataFrame) -> pd.DataFrame:
        """Cho chính các dòng đã fit: loại chính nó để chống rò rỉ dữ liệu (leakage)."""
        return self._run(X, is_train=True, exclude_self_match=False)

    def transform(self, X: pd.DataFrame, exclude_self_match: bool = False) -> pd.DataFrame:
        """Cho các dòng suy luận / val / test (tùy chọn exclude_self_match chống Inference Self-Leakage)."""
        return self._run(X, is_train=False, exclude_self_match=exclude_self_match)


FINAL_PREDICT = {
    "LightGBM": lambda m, X: m.predict(X, num_iteration=m.best_iteration),
    "XGBoost": lambda m, X: m.predict(xgb.DMatrix(X, enable_categorical=True)),
}


def predict_log(res: dict, X_raw: pd.DataFrame, exclude_self_match: bool = False) -> np.ndarray:
    Xb = make_base_features(X_raw).reset_index(drop=True)
    Xf = attach(Xb, res["fe"].transform(Xb, exclude_self_match=exclude_self_match))
    return FINAL_PREDICT[res["model_name"]](res["best_estimator"], Xf)


def blend_predict(
    results: list[dict],
    X_raw: pd.DataFrame,
    smear: bool = True,
    exclude_self_match: bool = False,
) -> np.ndarray:
    logs = np.mean([predict_log(r, X_raw, exclude_self_match=exclude_self_match) for r in results], axis=0)
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

    def predict(self, X_raw: pd.DataFrame, exclude_self_match: bool = False) -> pd.DataFrame:
        Xb = make_base_features(X_raw).reset_index(drop=True)
        lo, hi = self._raw(attach(Xb, self.te.transform(Xb, exclude_self_match=exclude_self_match)))
        return pd.DataFrame({
            "low": np.expm1(lo - self.qhat),
            "high": np.expm1(hi + self.qhat),
        })


class MondrianPriceInterval(PriceInterval):
    """Mondrian Conformal Prediction: qhat & bias shift hiệu chuẩn riêng theo từng phân khúc giá."""

    def __init__(self, lgb_result, n_bins=4, min_bin=150, **kw):
        super().__init__(lgb_result, **kw)
        self.n_bins, self.min_bin = n_bins, min_bin
        self.edges = None
        self.qhats = []
        self.shifts = []

    def fit(self, X_raw: pd.DataFrame, y: pd.Series):
        super().fit(X_raw, y)
        lo, hi, yc = self._cal
        center = (lo + hi) / 2.0

        nb = int(max(1, min(self.n_bins, len(center) // self.min_bin)))
        self.edges = np.quantile(center, np.linspace(0, 1, nb + 1)[1:-1])
        b = np.searchsorted(self.edges, center, side="right")

        self.qhats = []
        self.shifts = []
        for k in range(nb):
            mask = b == k
            if not np.any(mask):
                self.shifts.append(0.0)
                self.qhats.append(self.qhat)
                continue
            shift_k = 0.5 * float(np.median(yc[mask] - center[mask]))
            lo_k = lo[mask] + shift_k
            hi_k = hi[mask] + shift_k
            s = np.maximum(lo_k - yc[mask], yc[mask] - hi_k)
            n = len(s)
            level = min(1.0, np.ceil((n + 1) * self.coverage) / n)
            self.shifts.append(shift_k)
            self.qhats.append(float(np.quantile(s, level, method="higher")))
        return self

    def predict(self, X_raw: pd.DataFrame, exclude_self_match: bool = False) -> pd.DataFrame:
        Xb = make_base_features(X_raw).reset_index(drop=True)
        lo, hi = self._raw(attach(Xb, self.te.transform(Xb, exclude_self_match=exclude_self_match)))
        center = (lo + hi) / 2.0
        b = np.searchsorted(self.edges, center, side="right")
        q = np.array([self.qhats[k] for k in b])
        shifts = getattr(self, "shifts", None)
        sh = np.array([shifts[k] for k in b]) if shifts else 0.0
        return pd.DataFrame({
            "low": np.expm1(lo + sh - q),
            "high": np.expm1(hi + sh + q),
        })


class InputGuard:
    """Bảo vệ biên dữ liệu toàn quốc và thích ứng ngưỡng theo từng phân loại phòng (room_type_id)."""

    def __init__(self, ppm_range=PPM_RANGE, max_price=MAX_PRICE, margin_deg=0.02):
        self.ppm_range = ppm_range
        self.max_price = max_price
        self.margin = margin_deg
        self.area_rng = (4.0, 300.0)
        self.lat_rng = VIETNAM_LAT_RANGE
        self.lng_rng = VIETNAM_LNG_RANGE
        self.rules = copy.deepcopy(ROOM_TYPE_FILTER_RULES)

    def fit(self, X_raw: pd.DataFrame):
        a = X_raw["area_m2"]
        m = self.margin
        self.area_rng = (
            min(4.0, float(a.quantile(0.001))),
            max(300.0, float(a.quantile(0.999))),
        )
        # Mở rộng toàn lãnh thổ Việt Nam để không chặn các tỉnh/thành hợp lệ
        self.lat_rng = (
            min(VIETNAM_LAT_RANGE[0], float(X_raw["lat"].min() - m)),
            max(VIETNAM_LAT_RANGE[1], float(X_raw["lat"].max() + m)),
        )
        self.lng_rng = (
            min(VIETNAM_LNG_RANGE[0], float(X_raw["lng"].min() - m)),
            max(VIETNAM_LNG_RANGE[1], float(X_raw["lng"].max() + m)),
        )
        self.rules = copy.deepcopy(ROOM_TYPE_FILTER_RULES)
        return self

    def check(self, X_new: pd.DataFrame, price: np.ndarray) -> pd.DataFrame:
        price = np.asarray(price, dtype=float).ravel()
        area = X_new["area_m2"].to_numpy(dtype=float)
        lat = X_new["lat"].to_numpy(dtype=float)
        lng = X_new["lng"].to_numpy(dtype=float)
        ppm = price / np.clip(area, 1e-6, None)

        if "room_type_id" in X_new.columns:
            rt_ids = X_new["room_type_id"].fillna(1).to_numpy(dtype=int)
        else:
            rt_ids = np.ones(len(X_new), dtype=int)

        rules = getattr(self, "rules", None) or ROOM_TYPE_FILTER_RULES

        area_min = np.array([rules.get(int(rt), rules[1])["area"][0] for rt in rt_ids], dtype=float)
        area_max = np.array([rules.get(int(rt), rules[1])["area"][1] for rt in rt_ids], dtype=float)
        price_min = np.array([rules.get(int(rt), rules[1])["price"][0] for rt in rt_ids], dtype=float)
        price_max = np.array([rules.get(int(rt), rules[1])["price"][1] for rt in rt_ids], dtype=float)
        ppm_min = np.array([rules.get(int(rt), rules[1])["ppm"][0] for rt in rt_ids], dtype=float)
        ppm_max = np.array([rules.get(int(rt), rules[1])["ppm"][1] for rt in rt_ids], dtype=float)

        oor = (
            (price < price_min)
            | (price > price_max)
            | (area < area_min)
            | (area > area_max)
            | (lat < self.lat_rng[0])
            | (lat > self.lat_rng[1])
            | (lng < self.lng_rng[0])
            | (lng > self.lng_rng[1])
        )
        odd = (ppm < ppm_min) | (ppm > ppm_max)

        status = np.where(oor, "oor", np.where(odd, "odd", "ok"))
        return pd.DataFrame({"status": status})
