import os
import pandas as pd

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
TABLES = ["suppliers", "bom", "inventory", "orders"]


def load_data(data_dir=DATA_DIR):
    """Read every CSV into a dict of DataFrames."""
    return {t: pd.read_csv(os.path.join(data_dir, f"{t}.csv")) for t in TABLES}
