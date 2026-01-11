下面给你一套可直接用的 Python 代码骨架（以 pandas + numpy + scikit-learn 为主），包含：
	•	Leveling 主路B：target 点的局部邻域汇聚特征（kNN + 半径两套，多尺度可选）
	•	Bow 方法1：低阶形状基拟合（2D 多项式，含拟合值 + 梯度 + 曲率）
	•	Bow 方法2：距离/加权平均/十字线投影插值特征

假设：你的 xy 坐标都以 wafer 中心为原点（你已说明）。单位随你（mm/µm 都行），但邻域半径 r要用同单位。

⸻

0) 依赖

import numpy as np
import pandas as pd

from sklearn.neighbors import KDTree
from sklearn.preprocessing import PolynomialFeatures
from sklearn.linear_model import Ridge


⸻

1) Leveling：主路B（局部邻域汇聚特征）

输入：
	•	targets_df: columns = ['wafer_id','x','y']（也可带 overlay）
	•	leveling_df: columns = ['wafer_id','x','y','z']  (z=leveling量测值)

输出：
	•	给每个 target 点生成多尺度特征：均值/方差/极差/中位数/局部平面 tilt（dx,dy）/局部二次曲率（可选）

def _local_plane_fit(xy, z):
    """
    拟合 z = a*x + b*y + c
    返回 (a, b, c)
    """
    X = np.c_[xy[:,0], xy[:,1], np.ones(len(xy))]
    coef, *_ = np.linalg.lstsq(X, z, rcond=None)
    return coef  # a, b, c

def _local_quad_fit(xy, z):
    """
    拟合二次：z = ax^2 + by^2 + cxy + dx + ey + f
    返回 [a,b,c,d,e,f]
    """
    x = xy[:,0]; y = xy[:,1]
    X = np.c_[x*x, y*y, x*y, x, y, np.ones(len(x))]
    coef, *_ = np.linalg.lstsq(X, z, rcond=None)
    return coef

def build_leveling_local_features(
    targets_df: pd.DataFrame,
    leveling_df: pd.DataFrame,
    value_col: str = "z",
    knn_list=(32, 64),
    radius_list=(5000.0, 10000.0),  # 例：单位同你的坐标（比如 µm）
    add_quad_curvature: bool = True,
    min_pts_plane: int = 6,
    min_pts_quad: int = 10,
):
    """
    对每个 wafer，基于 leveling 点云，在每个 target 点计算局部邻域聚合特征。
    """
    out_rows = []

    # 按 wafer 分组，避免跨 wafer 混
    for wafer_id, tdf in targets_df.groupby("wafer_id"):
        ldf = leveling_df[leveling_df["wafer_id"] == wafer_id]
        if len(ldf) == 0:
            # 没有 leveling 数据：全 NaN
            tmp = tdf[["wafer_id","x","y"]].copy()
            out_rows.append(tmp.assign(**{}))
            continue

        L_xy = ldf[["x","y"]].to_numpy()
        L_z  = ldf[value_col].to_numpy().astype(float)

        tree = KDTree(L_xy)

        T_xy = tdf[["x","y"]].to_numpy()
        feat = tdf[["wafer_id","x","y"]].copy()

        # --- kNN 聚合 ---
        for k in knn_list:
            dists, idx = tree.query(T_xy, k=min(k, len(L_xy)))
            # idx shape: (nT, k)
            Z = L_z[idx]  # (nT,k)

            feat[f"lvl_knn{k}_mean"] = np.nanmean(Z, axis=1)
            feat[f"lvl_knn{k}_std"]  = np.nanstd(Z, axis=1)
            feat[f"lvl_knn{k}_ptp"]  = np.nanmax(Z, axis=1) - np.nanmin(Z, axis=1)
            feat[f"lvl_knn{k}_median"] = np.nanmedian(Z, axis=1)

            # 局部平面 tilt（dx,dy）
            a_list = []
            b_list = []
            c_list = []
            for i in range(len(T_xy)):
                ii = idx[i]
                xy = L_xy[ii]
                z  = L_z[ii]
                if len(ii) >= min_pts_plane:
                    a,b,c = _local_plane_fit(xy, z)
                else:
                    a=b=c=np.nan
                a_list.append(a); b_list.append(b); c_list.append(c)

            feat[f"lvl_knn{k}_tilt_x"] = a_list
            feat[f"lvl_knn{k}_tilt_y"] = b_list
            feat[f"lvl_knn{k}_plane_c"] = c_list

            # 局部二次曲率（可选）
            if add_quad_curvature:
                # 二次曲面：z = ax^2 + by^2 + cxy + dx + ey + f
                # Hessian: d2z/dx2 = 2a, d2z/dy2 = 2b, d2z/dxdy = c
                d2x2, d2y2, d2xy, lap = [], [], [], []
                for i in range(len(T_xy)):
                    ii = idx[i]
                    xy = L_xy[ii]
                    z  = L_z[ii]
                    if len(ii) >= min_pts_quad:
                        a,b,c,_,_,_ = _local_quad_fit(xy, z)
                        d2x2_i = 2*a
                        d2y2_i = 2*b
                        d2xy_i = c
                        lap_i  = d2x2_i + d2y2_i
                    else:
                        d2x2_i=d2y2_i=d2xy_i=lap_i=np.nan
                    d2x2.append(d2x2_i); d2y2.append(d2y2_i); d2xy.append(d2xy_i); lap.append(lap_i)

                feat[f"lvl_knn{k}_d2x2"] = d2x2
                feat[f"lvl_knn{k}_d2y2"] = d2y2
                feat[f"lvl_knn{k}_d2xy"] = d2xy
                feat[f"lvl_knn{k}_laplacian"] = lap

        # --- 半径邻域聚合（多尺度） ---
        for r in radius_list:
            ind = tree.query_radius(T_xy, r=r)
            # ind is array of arrays indices

            mean_list, std_list, ptp_list, med_list = [], [], [], []
            tilt_x_list, tilt_y_list = [], []
            for i, ii in enumerate(ind):
                if len(ii) == 0:
                    mean_list.append(np.nan); std_list.append(np.nan)
                    ptp_list.append(np.nan); med_list.append(np.nan)
                    tilt_x_list.append(np.nan); tilt_y_list.append(np.nan)
                    continue

                z = L_z[ii]
                mean_list.append(np.mean(z))
                std_list.append(np.std(z))
                ptp_list.append(np.max(z) - np.min(z))
                med_list.append(np.median(z))

                if len(ii) >= min_pts_plane:
                    a,b,_ = _local_plane_fit(L_xy[ii], z)
                else:
                    a=b=np.nan
                tilt_x_list.append(a); tilt_y_list.append(b)

            feat[f"lvl_rad{r}_mean"] = mean_list
            feat[f"lvl_rad{r}_std"]  = std_list
            feat[f"lvl_rad{r}_ptp"]  = ptp_list
            feat[f"lvl_rad{r}_median"] = med_list
            feat[f"lvl_rad{r}_tilt_x"] = tilt_x_list
            feat[f"lvl_rad{r}_tilt_y"] = tilt_y_list

        out_rows.append(feat)

    return pd.concat(out_rows, ignore_index=True)


⸻

2) Bow 方法1：低阶形状基拟合（2D 多项式）+ 在 target 点生成 B_hat/梯度/曲率

输入：
	•	bow_df: columns = ['wafer_id','x','y','z']（30点）
	•	targets_df: columns = ['wafer_id','x','y']

输出：
	•	每个 target 点：bow_poly_hat, bow_poly_dBdx, bow_poly_dBdy, bow_poly_d2x2, bow_poly_d2y2, bow_poly_d2xy, bow_poly_laplacian
	•	以及每片 wafer 的拟合系数（如果你要做 wafer-level 特征）

多项式阶数建议从 degree=2 或 3 起步；30点数据用太高阶容易过拟合。

def fit_bow_poly_per_wafer(bow_df, degree=2, ridge_alpha=1e-6, value_col="z"):
    """
    每片 wafer 拟合 2D 多项式：z = f(x,y)
    返回 dict: wafer_id -> (poly, model)
    """
    models = {}
    for wafer_id, df in bow_df.groupby("wafer_id"):
        X = df[["x","y"]].to_numpy()
        y = df[value_col].to_numpy().astype(float)

        poly = PolynomialFeatures(degree=degree, include_bias=True)
        Xp = poly.fit_transform(X)

        model = Ridge(alpha=ridge_alpha, fit_intercept=False)
        model.fit(Xp, y)
        models[wafer_id] = (poly, model)
    return models

def _eval_poly_and_derivatives(poly: PolynomialFeatures, coef: np.ndarray, xy: np.ndarray):
    """
    计算 f(x,y)、一阶导、二阶导。
    poly: PolynomialFeatures 已fit，coef 与 poly.get_feature_names_out 对齐
    xy: (n,2)
    """
    x = xy[:,0]; y = xy[:,1]
    powers = poly.powers_  # shape (n_terms, 2), each term is x^px * y^py
    px = powers[:,0]
    py = powers[:,1]

    # f
    # sum_j coef_j * x^px_j * y^py_j
    # 为避免巨大广播，可以 term-by-term 累加（n_terms 通常不大）
    f = np.zeros(len(x), dtype=float)
    dfdx = np.zeros(len(x), dtype=float)
    dfdy = np.zeros(len(x), dtype=float)
    d2x2 = np.zeros(len(x), dtype=float)
    d2y2 = np.zeros(len(x), dtype=float)
    d2xy = np.zeros(len(x), dtype=float)

    for j in range(len(coef)):
        c = coef[j]
        a = px[j]
        b = py[j]

        term = (x**a) * (y**b)
        f += c * term

        # d/dx: c * a * x^(a-1) * y^b  (a>=1)
        if a >= 1:
            dfdx += c * a * (x**(a-1)) * (y**b)
        # d/dy
        if b >= 1:
            dfdy += c * b * (x**a) * (y**(b-1))

        # d2/dx2: c * a*(a-1) * x^(a-2) * y^b
        if a >= 2:
            d2x2 += c * a * (a-1) * (x**(a-2)) * (y**b)
        # d2/dy2
        if b >= 2:
            d2y2 += c * b * (b-1) * (x**a) * (y**(b-2))
        # d2/dxdy: c * a*b * x^(a-1) * y^(b-1)
        if a >= 1 and b >= 1:
            d2xy += c * a * b * (x**(a-1)) * (y**(b-1))

    lap = d2x2 + d2y2
    return f, dfdx, dfdy, d2x2, d2y2, d2xy, lap

def build_bow_poly_features(
    targets_df: pd.DataFrame,
    bow_df: pd.DataFrame,
    degree=2,
    ridge_alpha=1e-6,
    value_col="z",
    add_wafer_level_coefs=True,
):
    models = fit_bow_poly_per_wafer(bow_df, degree=degree, ridge_alpha=ridge_alpha, value_col=value_col)

    out = targets_df[["wafer_id","x","y"]].copy()

    # point-level features
    hat_list, dfdx_list, dfdy_list = [], [], []
    d2x2_list, d2y2_list, d2xy_list, lap_list = [], [], [], []

    # wafer-level coefs（可选，给每个点重复一份，树模型很爱吃）
    coef_cols = None
    wafer_coef_map = {}

    for wafer_id, (poly, model) in models.items():
        coef = model.coef_
        wafer_coef_map[wafer_id] = (poly, coef)

        if add_wafer_level_coefs and coef_cols is None:
            names = poly.get_feature_names_out(["x","y"])
            coef_cols = [f"bow_polycoef_{n}" for n in names]

    for i, row in out.iterrows():
        wafer_id = row["wafer_id"]
        xy = np.array([[row["x"], row["y"]]], dtype=float)

        if wafer_id not in models:
            hat_list.append(np.nan); dfdx_list.append(np.nan); dfdy_list.append(np.nan)
            d2x2_list.append(np.nan); d2y2_list.append(np.nan); d2xy_list.append(np.nan); lap_list.append(np.nan)
            continue

        poly, model = models[wafer_id]
        coef = model.coef_

        f, dfdx, dfdy, d2x2, d2y2, d2xy, lap = _eval_poly_and_derivatives(poly, coef, xy)

        hat_list.append(f[0])
        dfdx_list.append(dfdx[0])
        dfdy_list.append(dfdy[0])
        d2x2_list.append(d2x2[0])
        d2y2_list.append(d2y2[0])
        d2xy_list.append(d2xy[0])
        lap_list.append(lap[0])

    out["bow_poly_hat"] = hat_list
    out["bow_poly_dBdx"] = dfdx_list
    out["bow_poly_dBdy"] = dfdy_list
    out["bow_poly_d2x2"] = d2x2_list
    out["bow_poly_d2y2"] = d2y2_list
    out["bow_poly_d2xy"] = d2xy_list
    out["bow_poly_laplacian"] = lap_list

    if add_wafer_level_coefs and coef_cols is not None:
        # 每个点附带 wafer 的形状系数
        coefs_matrix = []
        for _, row in out.iterrows():
            wafer_id = row["wafer_id"]
            if wafer_id not in wafer_coef_map:
                coefs_matrix.append([np.nan]*len(coef_cols))
            else:
                poly, coef = wafer_coef_map[wafer_id]
                coefs_matrix.append(list(coef))
        coefs_df = pd.DataFrame(coefs_matrix, columns=coef_cols, index=out.index)
        out = pd.concat([out, coefs_df], axis=1)

    return out


⸻

3) Bow 方法2：距离 / 最近点加权平均 / 十字线投影插值

这里默认 bow 测点大多在 x 轴和 y 轴上（十字）。我们做三类特征：
	1.	到最近 bow 点距离、到 x 轴/y 轴距离
	2.	最近 k 个 bow 点的 IDW（inverse distance weighting）加权平均 bow
	3.	投影插值：
	•	用 bow 点中“靠近 x 轴”的子集（|y| 小）按 x 做 1D 插值 -> bow_xproj
	•	用 bow 点中“靠近 y 轴”的子集（|x| 小）按 y 做 1D 插值 -> bow_yproj

def _idw(values, dists, power=2, eps=1e-12):
    w = 1.0 / np.maximum(dists, eps)**power
    return np.sum(w * values) / np.sum(w)

def build_bow_distance_features(
    targets_df: pd.DataFrame,
    bow_df: pd.DataFrame,
    value_col="z",
    knn_list=(3,5),
    idw_power=2,
    axis_tol=1e-6,   # 用来筛选“在轴上”的点，按你的数据噪声调大些
):
    out_rows = []

    for wafer_id, tdf in targets_df.groupby("wafer_id"):
        bdf = bow_df[bow_df["wafer_id"] == wafer_id]
        feat = tdf[["wafer_id","x","y"]].copy()

        if len(bdf) == 0:
            out_rows.append(feat)
            continue

        B_xy = bdf[["x","y"]].to_numpy()
        B_z  = bdf[value_col].to_numpy().astype(float)

        tree = KDTree(B_xy)
        T_xy = tdf[["x","y"]].to_numpy()

        # 到最近bow点距离
        d1, i1 = tree.query(T_xy, k=1)
        feat["bow_nearest_dist"] = d1[:,0]
        feat["bow_nearest_val"] = B_z[i1[:,0]]

        # 到 x轴/y轴距离（十字结构很常用）
        feat["bow_dist_to_xaxis"] = np.abs(tdf["y"].to_numpy())
        feat["bow_dist_to_yaxis"] = np.abs(tdf["x"].to_numpy())

        # kNN IDW
        for k in knn_list:
            dists, idx = tree.query(T_xy, k=min(k, len(B_xy)))
            idw_vals = []
            for i in range(len(T_xy)):
                zz = B_z[idx[i]]
                dd = dists[i]
                idw_vals.append(_idw(zz, dd, power=idw_power))
            feat[f"bow_idw_knn{k}"] = idw_vals
            feat[f"bow_knn{k}_mean"] = np.mean(B_z[idx], axis=1)
            feat[f"bow_knn{k}_std"]  = np.std(B_z[idx], axis=1)

        # -------- 投影插值（1D）--------
        # x轴点：|y| <= axis_tol
        bx = bdf[np.abs(bdf["y"]) <= axis_tol].copy()
        by = bdf[np.abs(bdf["x"]) <= axis_tol].copy()

        # 如果你的点并非严格在轴上，把 axis_tol 调大些，比如 50µm/100µm
        # 也可以用“取最小|y|的一半点”来代替

        def interp_1d(xq, xp, fp):
            # np.interp 要求 xp 升序
            order = np.argsort(xp)
            xp2 = xp[order]
            fp2 = fp[order]
            # 超出范围时做端点外推（np.interp 是端点常值），够用；你也可改成线性外推
            return np.interp(xq, xp2, fp2)

        # xproj：沿x轴用 x 插值
        if len(bx) >= 2:
            xp = bx["x"].to_numpy()
            fp = bx[value_col].to_numpy().astype(float)
            feat["bow_xproj"] = interp_1d(tdf["x"].to_numpy(), xp, fp)
        else:
            feat["bow_xproj"] = np.nan

        # yproj：沿y轴用 y 插值
        if len(by) >= 2:
            yp = by["y"].to_numpy()
            fp = by[value_col].to_numpy().astype(float)
            feat["bow_yproj"] = interp_1d(tdf["y"].to_numpy(), yp, fp)
        else:
            feat["bow_yproj"] = np.nan

        # 也可以加一个简单融合
        feat["bow_proj_mean"] = np.nanmean(np.c_[feat["bow_xproj"].to_numpy(), feat["bow_yproj"].to_numpy()], axis=1)

        out_rows.append(feat)

    return pd.concat(out_rows, ignore_index=True)


⸻

4) 把三部分拼起来（Leveling features + Bow method1 + Bow method2 + global）

假设你还有 wafer_df：['wafer_id','cmp_lifetime']

def assemble_training_table(targets_df, leveling_df, bow_df, wafer_df=None):
    lvl_feat = build_leveling_local_features(
        targets_df=targets_df,
        leveling_df=leveling_df,
        value_col="z",
        knn_list=(32,64),
        radius_list=(5000.0,10000.0),
        add_quad_curvature=True
    )

    bow_poly_feat = build_bow_poly_features(
        targets_df=targets_df,
        bow_df=bow_df,
        degree=2,
        ridge_alpha=1e-6,
        value_col="z",
        add_wafer_level_coefs=True
    )

    bow_dist_feat = build_bow_distance_features(
        targets_df=targets_df,
        bow_df=bow_df,
        value_col="z",
        knn_list=(3,5),
        idw_power=2,
        axis_tol=1e-6
    )

    # 合并（按 wafer_id,x,y 对齐）
    df = targets_df.copy()
    for feat_df in [lvl_feat, bow_poly_feat, bow_dist_feat]:
        df = df.merge(feat_df, on=["wafer_id","x","y"], how="left")

    # 加 global
    if wafer_df is not None:
        df = df.merge(wafer_df, on="wafer_id", how="left")

    # 位置特征（建议保留）
    x = df["x"].to_numpy()
    y = df["y"].to_numpy()
    df["r"] = np.sqrt(x*x + y*y)
    df["theta"] = np.arctan2(y, x)

    return df


⸻

你拿到的结果长什么样？

最终 df 就是一张“每个 target 点一行”的训练表：
wafer_id, x, y, overlay(如果你有), cmp_lifetime, lvl_* , bow_poly_* , bow_idw_* , bow_xproj/yproj , r, theta ...

接下来你就能直接喂给 LightGBM / XGBoost / 线性模型做回归了（记得按 wafer 做 GroupKFold）。

⸻

如果你接下来一句话告诉我：
	•	你的坐标单位（mm 还是 µm）
	•	leveling 点大致网格间距/平均点距
	•	bow 十字点的“轴上容差”大概是多少（比如 y≈0 的点 y 会不会有噪声）

我可以把 radius_list 和 axis_tol 给你换成更合理的默认值，并补一段 GroupKFold + LightGBM 的完整训练脚本。






下面是一份可直接跑的 LightGBM 回归训练脚本（按 wafer_id 做 GroupKFold，输出 overall / per-wafer 指标，并带 early stopping）。

假设你已经用我前面给的 assemble_training_table(...) 得到了 df，并且目标列叫 overlay。
如果你目标是 overlay_x / overlay_y 两个通道，我在最后也给了做法。

⸻

1) 安装（如本地没装 LightGBM）

pip install lightgbm scikit-learn pandas numpy


⸻

2) 训练脚本（GroupKFold + early stopping + 评估）

import numpy as np
import pandas as pd

from sklearn.model_selection import GroupKFold
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score

import lightgbm as lgb


def train_lgbm_groupkfold(
    df: pd.DataFrame,
    target_col: str = "overlay",
    group_col: str = "wafer_id",
    drop_cols=("wafer_id",),     # 你也可以加上不想喂给模型的列
    n_splits: int = 5,
    random_state: int = 42,
):
    # --- 基本清理 ---
    assert target_col in df.columns, f"missing target_col={target_col}"
    assert group_col in df.columns, f"missing group_col={group_col}"

    # LightGBM不能直接处理全NaN列；先去掉全NaN特征
    y = df[target_col].astype(float).to_numpy()
    groups = df[group_col].to_numpy()

    # 特征列：排除 target、group、drop_cols
    drop_set = set(drop_cols) | {target_col}
    feature_cols = [c for c in df.columns if c not in drop_set]

    X = df[feature_cols]
    # 去掉全NaN列
    all_nan_cols = [c for c in feature_cols if X[c].isna().all()]
    if all_nan_cols:
        feature_cols = [c for c in feature_cols if c not in all_nan_cols]
        X = df[feature_cols]

    # 简单缺失值处理：LightGBM原生支持 NaN，不需要填充
    # 但如果有 inf，替换掉
    X = X.replace([np.inf, -np.inf], np.nan)

    # --- CV ---
    gkf = GroupKFold(n_splits=n_splits)

    oof_pred = np.full(shape=len(df), fill_value=np.nan, dtype=float)
    models = []
    fold_metrics = []

    params = {
        "objective": "regression",
        "metric": "rmse",
        "learning_rate": 0.05,
        "num_leaves": 64,
        "min_data_in_leaf": 50,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "lambda_l2": 1.0,
        "verbosity": -1,
        "seed": random_state,
    }

    for fold, (tr_idx, va_idx) in enumerate(gkf.split(X, y, groups=groups), start=1):
        X_tr, y_tr = X.iloc[tr_idx], y[tr_idx]
        X_va, y_va = X.iloc[va_idx], y[va_idx]

        dtrain = lgb.Dataset(X_tr, label=y_tr, feature_name=feature_cols, free_raw_data=False)
        dvalid = lgb.Dataset(X_va, label=y_va, feature_name=feature_cols, reference=dtrain, free_raw_data=False)

        model = lgb.train(
            params=params,
            train_set=dtrain,
            valid_sets=[dtrain, dvalid],
            valid_names=["train", "valid"],
            num_boost_round=5000,
            callbacks=[
                lgb.early_stopping(stopping_rounds=200, verbose=False),
                lgb.log_evaluation(period=200),
            ],
        )

        pred_va = model.predict(X_va, num_iteration=model.best_iteration)
        oof_pred[va_idx] = pred_va
        models.append(model)

        rmse = mean_squared_error(y_va, pred_va, squared=False)
        mae = mean_absolute_error(y_va, pred_va)
        r2 = r2_score(y_va, pred_va)

        fold_metrics.append({"fold": fold, "rmse": rmse, "mae": mae, "r2": r2, "best_iter": model.best_iteration})
        print(f"[Fold {fold}] RMSE={rmse:.6f}  MAE={mae:.6f}  R2={r2:.4f}  best_iter={model.best_iteration}")

    # --- Overall OOF metrics ---
    valid_mask = ~np.isnan(oof_pred)
    y_oof = y[valid_mask]
    p_oof = oof_pred[valid_mask]

    overall_rmse = mean_squared_error(y_oof, p_oof, squared=False)
    overall_mae = mean_absolute_error(y_oof, p_oof)
    overall_r2 = r2_score(y_oof, p_oof)

    print("\n=== OOF Overall ===")
    print(f"RMSE={overall_rmse:.6f}  MAE={overall_mae:.6f}  R2={overall_r2:.4f}")

    # --- Per-wafer metrics（很重要） ---
    per_wafer = []
    tmp = df[[group_col]].copy()
    tmp["y_true"] = y
    tmp["y_pred"] = oof_pred
    tmp = tmp.dropna(subset=["y_pred"])

    for wid, g in tmp.groupby(group_col):
        yt = g["y_true"].to_numpy()
        yp = g["y_pred"].to_numpy()
        per_wafer.append({
            group_col: wid,
            "n": len(g),
            "rmse": mean_squared_error(yt, yp, squared=False),
            "mae": mean_absolute_error(yt, yp),
            "r2": r2_score(yt, yp) if len(g) >= 3 else np.nan
        })

    per_wafer_df = pd.DataFrame(per_wafer).sort_values("rmse", ascending=False)

    # --- 特征重要性（用最后一折的模型 or 平均）---
    # 这里给平均 gain 重要性
    imp_gain = np.zeros(len(feature_cols), dtype=float)
    for m in models:
        imp_gain += m.feature_importance(importance_type="gain")
    imp_gain /= len(models)

    feat_imp_df = pd.DataFrame({
        "feature": feature_cols,
        "importance_gain_avg": imp_gain
    }).sort_values("importance_gain_avg", ascending=False)

    fold_metrics_df = pd.DataFrame(fold_metrics)

    return {
        "models": models,
        "feature_cols": feature_cols,
        "oof_pred": oof_pred,
        "fold_metrics": fold_metrics_df,
        "per_wafer_metrics": per_wafer_df,
        "feature_importance": feat_imp_df,
        "overall": {"rmse": overall_rmse, "mae": overall_mae, "r2": overall_r2},
    }


# ===== 用法示例 =====
# df = assemble_training_table(targets_df, leveling_df, bow_df, wafer_df)
# df 必须包含：wafer_id, x, y, overlay
# result = train_lgbm_groupkfold(df, target_col="overlay", group_col="wafer_id", drop_cols=("wafer_id",))
# print(result["feature_importance"].head(30))
# print(result["per_wafer_metrics"].head(20))


⸻

3) 如果你的目标是两个通道（overlay_x, overlay_y）

最简单实用的方式：训练两个独立模型（通常比硬搞 multioutput 更稳）：

res_x = train_lgbm_groupkfold(df, target_col="overlay_x", group_col="wafer_id", drop_cols=("wafer_id",))
res_y = train_lgbm_groupkfold(df, target_col="overlay_y", group_col="wafer_id", drop_cols=("wafer_id",))


⸻

4) 一点点建议（不改代码也能做）
    •   num_leaves / min_data_in_leaf 对你这种“点级样本很多、但 wafer 分组强相关”的场景很关键：
如果过拟合（训练集好、valid 差），就 增大 min_data_in_leaf（例如 100~300）。
    •   你特征里如果有一堆 *_coef_*（bow 多项式系数），树模型会很吃这些；但也可能导致“wafer-level shortcut”。按 wafer 分组验证能挡住泄漏，这点你已经做对了。

⸻

如果你愿意把你的坐标单位告诉我（mm/µm），我可以顺手把 LightGBM 参数里 min_data_in_leaf、以及你前面 leveling radius 的默认值，按你点密度给一套更贴合的推荐配置。