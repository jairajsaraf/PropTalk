"""Single source of truth for table metadata.

Both query engines — SQLite and pandas — run over the same synthetic CSVs,
so TABLE_REGISTRY only lists tables that actually have data behind them.
"""

from dataclasses import dataclass, field


@dataclass
class TableConfig:
    display_name: str
    csv_filename: str          # synthetic CSV in sample_data/
    sqlite_table: str          # bare table name used in generated SQL
    description: str           # for LLM context
    example_questions: list[str] = field(default_factory=list)


TABLE_REGISTRY: list[TableConfig] = [
    TableConfig(
        display_name="Deed Transactions",
        csv_filename="deed_transactions_sample.csv",
        sqlite_table="deed_transactions",
        description="Single-family property deed transfers in Texas with sale amounts, investor classification, buyer types, and occupancy codes.",
        example_questions=[
            "Show me the top 10 cities by transaction volume",
            "What are the average sale prices by investor classification?",
            "Show cash purchases over $500K in Houston in 2024",
            "Monthly transaction trend for Harris County",
        ],
    ),
    TableConfig(
        display_name="MLS Listings",
        csv_filename="mls_listings_sample.csv",
        sqlite_table="mls_listings",
        description="Regional MLS listings with list/close prices, property details, and days on market.",
        example_questions=[
            "Average days on market by city",
            "Show closed listings above $1M in The Woodlands",
            "Price distribution by property type",
            "Monthly listing volume trend for 2024",
        ],
    ),
]


def get_example_questions(display_name: str) -> list[str]:
    """Return example questions for a table by display name."""
    for table in TABLE_REGISTRY:
        if table.display_name == display_name:
            return table.example_questions
    return []


def get_sqlite_tables() -> list[dict]:
    """Return table configs formatted for SqliteBackend initialization."""
    return [
        {
            "display_name": t.display_name,
            "table_id": t.display_name,
            "csv_filename": t.csv_filename,
            "sqlite_table": t.sqlite_table,
        }
        for t in TABLE_REGISTRY
    ]


def get_csv_tables() -> list[dict]:
    """Return table configs formatted for CsvBackend initialization."""
    return [
        {
            "display_name": t.display_name,
            "table_id": t.display_name,
            "csv_filename": t.csv_filename,
        }
        for t in TABLE_REGISTRY
    ]
