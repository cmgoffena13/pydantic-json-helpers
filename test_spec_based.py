"""Test the final_rendition JSONParser"""

from final_rendition import JSONParser
from json_examples.nestedjson import NESTED_JSON
from models import Invoice, InvoiceItem, InvoiceItemTransaction

# Define data models
data_models = [Invoice, InvoiceItem, InvoiceItemTransaction]

# Create parser instance
parser = JSONParser(data_models)

# Print inferred specs for debugging
print("Inferred Model Specs:")
for model_name, spec in parser.model_specs.items():
    print(f"  {model_name}: {spec.json_path_pattern}")
print()

# Extract data
try:
    results = parser.parse(NESTED_JSON)

    # Display results
    print("=" * 60)
    print("EXTRACTED TABLES")
    print("=" * 60)

    for model_name, items in results.items():
        print(f"\n{model_name} ({len(items)} records):")
        for item in items:
            print(f"  {item}")

    # Show errors
    if parser.errors:
        print(f"\n⚠️  Validation Errors ({len(parser.errors)}):")
        for error in parser.errors:
            print(f"  - Path: {error['path']}, Model: {error['model']}")
            for err_detail in error["errors"]:
                print(
                    f"    • {err_detail.get('type', 'unknown')}: {err_detail.get('msg', 'N/A')}"
                )
    else:
        print("\n✅ No validation errors!")

except ValueError as e:
    print(f"\n❌ Validation Error: {e}")
    if parser.errors:
        for error in parser.errors:
            print(f"  - Path: {error['path']}, Model: {error['model']}")
            for err_detail in error["errors"]:
                print(
                    f"    • {err_detail.get('type', 'unknown')}: {err_detail.get('msg', 'N/A')}"
                )
