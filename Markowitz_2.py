"""
Package Import
"""
import yfinance as yf
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import quantstats as qs
import gurobipy as gp
import warnings
import argparse

"""
Project Setup
"""
warnings.simplefilter(action="ignore", category=FutureWarning)

assets = [
    "SPY",
    "XLB",
    "XLC",
    "XLE",
    "XLF",
    "XLI",
    "XLK",
    "XLP",
    "XLRE",
    "XLU",
    "XLV",
    "XLY",
]

# Initialize Bdf and df
Bdf = pd.DataFrame()
for asset in assets:
    raw = yf.download(asset, start="2012-01-01", end="2024-04-01", auto_adjust = False)
    Bdf[asset] = raw['Adj Close']

df = Bdf.loc["2019-01-01":"2024-04-01"]

"""
Strategy Creation

Create your own strategy, you can add parameter but please remain "price" and "exclude" unchanged
"""


class MyPortfolio:
    """
    NOTE: You can modify the initialization function
    """

    def __init__(self, price, exclude, lookback=50, gamma=0):
        self.price = price
        self.returns = price.pct_change().fillna(0)
        self.exclude = exclude
        self.lookback = lookback
        self.gamma = gamma

    def calculate_weights(self):
        assets = self.price.columns[self.price.columns != self.exclude]
        # 初始化 weights
        self.portfolio_weights = pd.DataFrame(0.0, index=self.price.index, columns=self.price.columns)

        # 年化因子
        ann_factor = 252

        # 事前計算滾動平均報酬與共變異數
        mu_rol = self.returns[assets].rolling(self.lookback).mean() * ann_factor
        cov_rol = self.returns[assets].rolling(self.lookback).cov() * ann_factor

        # 逐日 re‐balance
        for t in range(self.lookback, len(self.price)):
            date = self.price.index[t]
            mu_t = mu_rol.loc[date].dropna()
            # cov_rol 是一個多層索引 DataFrame，先擷取當天的子矩陣
            cov_t = cov_rol.loc[date].unstack().loc[assets, assets]

            # 建 Gurobi 模型
            model = gp.Model()
            # 關閉 log
            model.Params.OutputFlag = 0

            # 決策變數：每個資產的權重
            w = model.addVars(assets, lb=0.0, ub=1.0)

            # 總權重 ≤ 1（不使用槓桿）
            model.addConstr(gp.quicksum(w[a] for a in assets) <= 1)

            # 目標函數：最大化 μ^T w − γ w^T Σ w
            lin_term = gp.quicksum(mu_t[a] * w[a] for a in assets)
            if self.gamma > 0:
                quad_term = gp.quicksum(cov_t.loc[i, j] * w[i] * w[j]
                                         for i in assets for j in assets)
                model.setObjective(lin_term - self.gamma * quad_term,
                                   gp.GRB.MAXIMIZE)
            else:
                model.setObjective(lin_term, gp.GRB.MAXIMIZE)

            model.optimize()

            # 取解並填入
            for a in assets:
                self.portfolio_weights.at[date, a] = w[a].X

        # 排除 exclude（如 SPY）
        self.portfolio_weights[self.exclude] = 0.0

        # 向前填補空值並將剩餘 NaN 置 0
        self.portfolio_weights.ffill(inplace=True)
        self.portfolio_weights.fillna(0.0, inplace=True)

    def calculate_portfolio_returns(self):
        # Ensure weights are calculated
        if not hasattr(self, "portfolio_weights"):
            self.calculate_weights()

        # Calculate the portfolio returns
        self.portfolio_returns = self.returns.copy()
        assets = self.price.columns[self.price.columns != self.exclude]
        self.portfolio_returns["Portfolio"] = (
            self.portfolio_returns[assets]
            .mul(self.portfolio_weights[assets])
            .sum(axis=1)
        )

    def get_results(self):
        # Ensure portfolio returns are calculated
        if not hasattr(self, "portfolio_returns"):
            self.calculate_portfolio_returns()

        return self.portfolio_weights, self.portfolio_returns


"""
Assignment Judge

The following functions will help check your solution.
"""


class AssignmentJudge:
    def __init__(self):
        self.mp = MyPortfolio(df, "SPY").get_results()
        self.Bmp = MyPortfolio(Bdf, "SPY").get_results()

    def plot_performance(self, price, strategy):
        # Plot cumulative returns
        _, ax = plt.subplots()
        returns = price.pct_change().fillna(0)
        (1 + returns["SPY"]).cumprod().plot(ax=ax, label="SPY")
        (1 + strategy[1]["Portfolio"]).cumprod().plot(ax=ax, label=f"MyPortfolio")

        ax.set_title("Cumulative Returns")
        ax.set_xlabel("Date")
        ax.set_ylabel("Cumulative Returns")
        ax.legend()
        plt.show()
        return None

    def plot_allocation(self, df_weights):
        df_weights = df_weights.fillna(0).ffill()

        # long only
        df_weights[df_weights < 0] = 0

        # Plotting
        _, ax = plt.subplots()
        df_weights.plot.area(ax=ax)
        ax.set_xlabel("Date")
        ax.set_ylabel("Allocation")
        ax.set_title("Asset Allocation Over Time")
        plt.show()
        return None

    def report_metrics(self, price, strategy, show=False):
        df_bl = pd.DataFrame()
        returns = price.pct_change().fillna(0)
        df_bl["SPY"] = returns["SPY"]
        df_bl["MP"] = pd.to_numeric(strategy[1]["Portfolio"], errors="coerce")
        sharpe_ratio = qs.stats.sharpe(df_bl)

        if show == True:
            qs.reports.metrics(df_bl, mode="full", display=show)

        return sharpe_ratio

    def cumulative_product(self, dataframe):
        (1 + dataframe.pct_change().fillna(0)).cumprod().plot()

    def check_sharp_ratio_greater_than_one(self):
        if not self.check_portfolio_position(self.mp[0]):
            return 0
        if self.report_metrics(df, self.mp)[1] > 1:
            print("Problem 4.1 Success - Get 15 points")
            return 15
        else:
            print("Problem 4.1 Fail")
        return 0

    def check_sharp_ratio_greater_than_spy(self):
        if not self.check_portfolio_position(self.mp[0]):
            return 0
        if (
            self.report_metrics(Bdf, self.Bmp)[1]
            > self.report_metrics(Bdf, self.Bmp)[0]
        ):
            print("Problem 4.2 Success - Get 15 points")
            return 15
        else:
            print("Problem 4.2 Fail")
        return 0

    def check_portfolio_position(self, portfolio_weights):
        if (portfolio_weights.sum(axis=1) <= 1.01).all():
            return True
        print("Portfolio Position Exceeds 1. No Leverage.")
        return False

    def check_all_answer(self):
        score = 0
        score += self.check_sharp_ratio_greater_than_one()
        score += self.check_sharp_ratio_greater_than_spy()
        return score


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Introduction to Fintech Assignment 3 Part 12"
    )

    parser.add_argument(
        "--score",
        action="append",
        help="Score for assignment",
    )

    parser.add_argument(
        "--allocation",
        action="append",
        help="Allocation for asset",
    )

    parser.add_argument(
        "--performance",
        action="append",
        help="Performance for portfolio",
    )

    parser.add_argument(
        "--report", action="append", help="Report for evaluation metric"
    )

    parser.add_argument(
        "--cumulative", action="append", help="Cumulative product result"
    )

    args = parser.parse_args()

    judge = AssignmentJudge()

    if args.score:
        if ("one" in args.score) or ("spy" in args.score):
            if "one" in args.score:
                judge.check_sharp_ratio_greater_than_one()
            if "spy" in args.score:
                judge.check_sharp_ratio_greater_than_spy()
        elif "all" in args.score:
            print(f"==> total Score = {judge.check_all_answer()} <==")

    if args.allocation:
        if "mp" in args.allocation:
            judge.plot_allocation(judge.mp[0])
        if "bmp" in args.allocation:
            judge.plot_allocation(judge.Bmp[0])

    if args.performance:
        if "mp" in args.performance:
            judge.plot_performance(df, judge.mp)
        if "bmp" in args.performance:
            judge.plot_performance(Bdf, judge.Bmp)

    if args.report:
        if "mp" in args.report:
            judge.report_metrics(df, judge.mp, show=True)
        if "bmp" in args.report:
            judge.report_metrics(Bdf, judge.Bmp, show=True)

    if args.cumulative:
        if "mp" in args.cumulative:
            judge.cumulative_product(df)
        if "bmp" in args.cumulative:
            judge.cumulative_product(Bdf)
