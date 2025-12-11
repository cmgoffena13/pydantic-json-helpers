NESTED_JSON = {
    "id": "INV-2025-12345",
    "total_amount": 1567.89,
    "geo": {"latitude": 40.7128, "longitude": -74.0060},
    "invoice_items": [
        {
            "id": "ITEM-001",
            "sku": "LAPTOP-001",
            "description": "Dell XPS 13",
            "quantity": 2,
            "unit_price": 999.99,
            "transactions": [
                {
                    "tx_id": "TX-001A",
                    "amount": 999.99,
                    "payment_method": "credit_card",
                    "timestamp": "2025-12-01T10:30:00Z",
                },
                {
                    "tx_id": "TX-001B",
                    "amount": -50.00,
                    "payment_method": "refund",
                    "timestamp": "2025-12-02T14:15:00Z",
                },
            ],
        },
        {
            "id": "ITEM-002",
            "sku": "MOUSE-101",
            "description": "Logitech MX Master 3",
            "quantity": 5,
            "unit_price": 79.99,
            "transactions": [
                {
                    "tx_id": "TX-002A",
                    "amount": 399.95,
                    "payment_method": "paypal",
                    "timestamp": "2025-12-01T11:45:00Z",
                }
            ],
        },
        {
            "id": "ITEM-003",
            "sku": "DOCK-202",
            "description": "USB-C Docking Station",
            "quantity": 1,
            "unit_price": 167.95,
            "transactions": [
                {
                    "tx_id": "TX-003A",
                    "amount": 167.95,
                    "payment_method": "credit_card",
                    "timestamp": "2025-12-01T12:20:00Z",
                }
            ],
        },
    ],
}
