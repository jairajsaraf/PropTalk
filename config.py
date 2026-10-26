"""Single source of truth for table metadata and model configuration."""

from dataclasses import dataclass, field


@dataclass
class TableConfig:
    display_name: str
    fq_sql_name: str          # fully qualified SQL Server name
    csv_filename: str          # fallback CSV filename
    description: str           # for LLM context
    example_questions: list[str] = field(default_factory=list)


TABLE_REGISTRY: list[TableConfig] = [
    TableConfig(
        display_name="Deed Transactions",
        fq_sql_name="[demo_db].[dbo].[deed_transactions]",
        csv_filename="deed_transactions_sample.csv",
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
        fq_sql_name="[demo_db].[dbo].[mls_listings]",
        csv_filename="mls_listings_sample.csv",
        description="Regional MLS listings with list/close prices, property details, and days on market.",
        example_questions=[
            "Average days on market by city",
            "Show closed listings above $1M in The Woodlands",
            "Price distribution by property type",
            "Monthly listing volume trend for 2024",
        ],
    ),
    TableConfig(
        display_name="Code Lookups",
        fq_sql_name="[demo_db].[dbo].[code_lookups]",
        csv_filename="",
        description="Property code reference table with property indicator codes, land use codes, and other classification values.",
        example_questions=[
            "Show all distinct code types",
            "List property indicator codes and their descriptions",
            "What land use codes are available?",
            "Show the first 100 rows",
        ],
    ),
    TableConfig(
        display_name="MLS Statistics",
        fq_sql_name="[demo_db].[dbo].[mls_monthly_stats]",
        csv_filename="",
        description="Monthly MLS statistics with median prices, listing counts, and key performance indicators by area.",
        example_questions=[
            "Show monthly median price trends",
            "Compare active listings vs closed sales by month",
            "What are the top areas by total volume?",
            "Show the first 100 rows sorted by date",
        ],
    ),
    TableConfig(
        display_name="Property Tax Stats",
        fq_sql_name="[demo_db].[dbo].[property_tax_stats]",
        csv_filename="",
        description="State-level property tax statistics including tax rates, median home values, and assessment data.",
        example_questions=[
            "Average property tax rate by state",
            "Show tax statistics for Texas",
            "Compare median home values across states",
            "Show the first 100 rows",
        ],
    ),
    TableConfig(
        display_name="Investor Deed Activity",
        fq_sql_name="[demo_db].[dbo].[investor_deed_activity]",
        csv_filename="",
        description="Investor-focused deed activity for single-family properties with investor classification and purchase patterns.",
        example_questions=[
            "Top 10 counties by investor deed volume",
            "Monthly investor activity trend",
            "Compare small vs institutional investor purchases by city",
            "Show investor deed activity in Harris County",
        ],
    ),
    TableConfig(
        display_name="Data Center Properties",
        fq_sql_name="[demo_db].[dbo].[data_center_properties]",
        csv_filename="",
        description="Verified data center properties with locations, sizes, and verification status.",
        example_questions=[
            "Map all verified data center properties",
            "Show data centers by state",
            "List the largest data center properties",
            "Show the first 100 rows",
        ],
    ),
]


def get_example_questions(display_name: str) -> list[str]:
    """Return example questions for a table by display name."""
    for table in TABLE_REGISTRY:
        if table.display_name == display_name:
            return table.example_questions
    return []


def get_sql_tables() -> list[dict]:
    """Return table configs formatted for SqlBackend initialization."""
    return [
        {
            "display_name": t.display_name,
            "table_id": t.display_name,
            "fq_sql_name": t.fq_sql_name,
        }
        for t in TABLE_REGISTRY
    ]


def get_csv_tables() -> list[dict]:
    """Return table configs formatted for CsvBackend initialization (CSV-available only)."""
    return [
        {
            "display_name": t.display_name,
            "table_id": t.display_name,
            "csv_filename": t.csv_filename,
        }
        for t in TABLE_REGISTRY
        if t.csv_filename  # only tables with CSV fallbacks
    ]
