def mock_payment(vendor: str, amount: float) -> dict:
    
    print(f"Paid {amount} to {vendor}")
    return {"status": "success"}