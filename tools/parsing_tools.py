import json
from models.invoice_state import GLOBAL_INVOICE_STATE

import os

def get_validation_by_file_name(filename: str) -> str:
    # 1. Normalize the search path
    search_path = os.path.normpath(filename).lower()
    
    # 2. Access the list from your Global State
    validations = GLOBAL_INVOICE_STATE.invoice_validations
    
    for v in validations:
        # 3. Compare normalized paths
        if os.path.normpath(v.file_name).lower() == search_path:
            # 4. Use model_dump() so json.dumps can read the data
            return json.dumps(v.model_dump(), indent=2, default=str)
            
    return "[]" # Better to return an empty list string than a completely empty string