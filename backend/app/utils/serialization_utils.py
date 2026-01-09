"""
Serialization utilities for handling numpy and pandas types.
Ensures proper JSON serialization of DataFrames and numpy arrays.
"""
import json
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd


def numpy_json_encoder(obj: Any) -> Any:

    if isinstance(obj, (np.integer, np.int64, np.int32, np.int16, np.int8)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float64, np.float32, np.float16)):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif pd.isna(obj):
        return None
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def serialize_dataframe(
    df: pd.DataFrame, 
    max_rows: Optional[int] = None,
    orient: str = 'records'
) -> List[Dict[str, Any]]:
    if df.empty:
        return []
    
    # Limit rows if specified
    if max_rows is not None:
        df = df.head(max_rows)
    
    return df.to_dict(orient=orient)


def safe_json_dumps(obj: Any, **kwargs) -> str:
    """
    Safely serialize an object to JSON, handling numpy types.
    Uses custom encoder for numpy type conversion.
    """
    return json.dumps(obj, default=numpy_json_encoder, **kwargs)

