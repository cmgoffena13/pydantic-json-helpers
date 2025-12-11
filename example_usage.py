"""Example: Using parse_json_to_tables to extract normalized tables from nested JSON"""

from better import parse_json_into_tables
from json_examples.nestedjson import NESTED_JSON
from models import Invoice, InvoiceItem, InvoiceItemTransaction

# Define the table models mapping
# The keys are table names, values are the SQLModel classes
table_models = {
    "invoices": Invoice,
    "invoice_items": InvoiceItem,
    "invoice_item_transactions": InvoiceItemTransaction,
}

# Parse the JSON and extract tables
tables, errors = parse_json_into_tables(NESTED_JSON, table_models)

# Display results
print("=" * 60)
print("EXTRACTED TABLES")
print("=" * 60)

print(f"\n📄 Invoices ({len(tables['invoices'])}):")
for invoice in tables["invoices"]:
    print(
        f"  - {invoice.id}: ${invoice.total_amount:.2f} @ ({invoice.latitude}, {invoice.longitude})"
    )

print(f"\n📦 Invoice Items ({len(tables['invoice_items'])}):")
for item in tables["invoice_items"]:
    print(
        f"  - {item.id} (Invoice: {item.invoice_id}): {item.quantity}x {item.sku} @ ${item.unit_price:.2f}"
    )

print(f"\n💳 Transactions ({len(tables['invoice_item_transactions'])}):")
for tx in tables["invoice_item_transactions"]:
    print(
        f"  - {tx.tx_id} (Item: {tx.invoice_item_id}): ${tx.amount:.2f} via {tx.payment_method} @ {tx.timestamp}"
    )

# Show any validation errors
if errors:
    print(f"\n⚠️  Validation Errors ({len(errors)}):")
    # for error in errors:
    #     print(f"  - Path: {error['path']}, Model: {error['model']}")
    #     for err_detail in error["errors"]:
    #         print(f"    • {err_detail['type']}: {err_detail.get('msg', 'N/A')}")
else:
    print("\n✅ No validation errors!")
