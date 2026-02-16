from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime


class SearchRequest(BaseModel):
    query: str
    data_type: Optional[str] = "all"
    from_field: str = "any"
    to_field: str = "any"


class ScanRequest(BaseModel):
    directory_path: str
    recursive: bool = True
