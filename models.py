from datetime import datetime

from sqlmodel import Field, SQLModel


class Invoice(SQLModel, table=True):
    id: str = Field(primary_key=True, alias="root.id")
    total_amount: float = Field(alias="root.total_amount")
    latitude: float = Field(alias="root.geo.latitude")
    longitude: float = Field(alias="root.geo.longitude")


class InvoiceItem(SQLModel, table=True):
    invoice_id: str = Field(foreign_key="invoice.id", alias="root.id")
    id: str = Field(primary_key=True, alias="root.invoice_items[*].id")
    sku: str = Field(alias="root.invoice_items[*].sku")
    description: str = Field(alias="root.invoice_items[*].description")
    quantity: int = Field(alias="root.invoice_items[*].quantity")
    unit_price: float = Field(alias="root.invoice_items[*].unit_price")


class InvoiceItemTransaction(SQLModel, table=True):
    tx_id: str = Field(
        primary_key=True, alias="root.invoice_items[*].transactions[*].tx_id"
    )
    invoice_item_id: str = Field(
        foreign_key="invoiceitem.id", alias="root.invoice_items[*].id"
    )
    invoice_id: str = Field(foreign_key="invoice.id", alias="root.id")
    amount: float = Field(alias="root.invoice_items[*].transactions[*].amount")
    payment_method: str = Field(
        alias="root.invoice_items[*].transactions[*].payment_method"
    )
    timestamp: datetime = Field(alias="root.invoice_items[*].transactions[*].timestamp")
