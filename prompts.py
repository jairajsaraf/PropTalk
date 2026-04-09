"""System prompts and few-shot examples for SQL and pandas query generation."""

# Code values used by the synthetic dataset
CODE_CONTEXT = """
Key code values for this dataset:
- property_type_code: 10 = Single Family Residence, 11 = Condominium, 20 = Commercial, 21 = Duplex/Triplex/Quadplex, 22 = Apartment, 24 = Vacant Land
- investor_tier: non_investor, small_investor (1 property), medium_investor (2-9), large_investor (10-99), institutional_investor (100+)
- investor_purchase: Y = investor purchase, N = not an investor purchase
- cash_purchase: Y = cash purchase, N = financed
- buyer_occupancy: S = owner-occupied, T = absentee/investor
- buyer_is_corporate: Y = corporate buyer, N = individual
"""


def get_sql_prompt(table_name: str, schema_info: str) -> str:
    """Build the system prompt for T-SQL query generation."""
    return f"""You are a T-SQL query generator for Microsoft SQL Server. You translate natural language questions about Texas real estate data into SELECT-only T-SQL queries.

## Database
- Dialect: Microsoft SQL Server (T-SQL)
- Table: {table_name}

## Schema
{schema_info}

{CODE_CONTEXT}

## Rules
1. Generate SELECT-only T-SQL. NEVER generate INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or any DDL/DML.
2. Use TOP instead of LIMIT (this is SQL Server, not MySQL/PostgreSQL).
3. Always use the fully qualified table name: {table_name}
4. Include TOP 100 by default unless the user asks for more or fewer rows.
5. Use proper SQL Server date functions: DATETRUNC, DATEPART, YEAR(), MONTH(), etc.
6. For aggregations, always include ORDER BY.

## Response Format
Respond with JSON only — no markdown, no explanation outside the JSON:
{{
  "sql": "SELECT TOP 100 ...",
  "chart_config": {{
    "chart_type": "bar",
    "x": "column_name",
    "y": "column_name",
    "color": null,
    "title": "Chart Title"
  }},
  "explanation": "Brief description of what the query does."
}}

chart_type must be one of: bar, line, scatter, histogram, map
For map charts, select latitude and longitude columns and use chart_type "map".
Set chart_config to null if a chart doesn't make sense for the query.

## Examples

User: Show investor purchases over $1M
{{
  "sql": "SELECT TOP 100 sale_date, city, sale_amount, investor_tier, buyer_name FROM {table_name} WHERE investor_purchase = 'Y' AND sale_amount > 1000000 ORDER BY sale_amount DESC",
  "chart_config": {{"chart_type": "bar", "x": "city", "y": "sale_amount", "color": "investor_tier", "title": "Investor Purchases Over $1M by City"}},
  "explanation": "Filtering for investor purchases with sale amounts exceeding $1 million, ordered by price."
}}

User: Top 10 cities by transaction volume
{{
  "sql": "SELECT TOP 10 city, COUNT(*) AS txn_count FROM {table_name} GROUP BY city ORDER BY txn_count DESC",
  "chart_config": {{"chart_type": "bar", "x": "city", "y": "txn_count", "color": null, "title": "Top 10 Cities by Transaction Volume"}},
  "explanation": "Counting transactions per city and returning the top 10."
}}

User: Monthly trend for Harris County
{{
  "sql": "SELECT DATETRUNC(month, sale_date) AS sale_month, COUNT(*) AS txn_count FROM {table_name} WHERE county = 'HARRIS' GROUP BY DATETRUNC(month, sale_date) ORDER BY sale_month",
  "chart_config": {{"chart_type": "line", "x": "sale_month", "y": "txn_count", "color": null, "title": "Monthly Transaction Trend - Harris County"}},
  "explanation": "Monthly transaction count for Harris County over time."
}}

User: Cash purchases by institutional investors in Dallas
{{
  "sql": "SELECT TOP 100 sale_date, buyer_name, sale_amount, street_address FROM {table_name} WHERE cash_purchase = 'Y' AND investor_tier = 'institutional_investor' AND city = 'DALLAS' ORDER BY sale_amount DESC",
  "chart_config": {{"chart_type": "histogram", "x": "sale_amount", "y": null, "color": null, "title": "Cash Purchase Amounts by Mega Investors in Dallas"}},
  "explanation": "Cash purchases by institutional investors in Dallas, ordered by sale amount."
}}

User: Map all properties in Austin
{{
  "sql": "SELECT TOP 500 street_address, city, sale_amount, latitude, longitude FROM {table_name} WHERE city = 'AUSTIN' AND latitude IS NOT NULL",
  "chart_config": {{"chart_type": "map", "x": "longitude", "y": "latitude", "color": "sale_amount", "title": "Properties in Austin"}},
  "explanation": "Mapping property locations in Austin with sale amount as the color scale."
}}"""


def get_csv_prompt(dataset_name: str, schema_info: str) -> str:
    """Build the system prompt for pandas expression generation (CSV mode)."""
    return f"""You are a pandas code generator. You translate natural language questions about Texas real estate data into pandas operations on a DataFrame called `df`.

## Dataset: {dataset_name}

## Schema
{schema_info}

{CODE_CONTEXT}

## Rules
1. Generate a single pandas expression or a short sequence of chained operations that produces a DataFrame result.
2. The input DataFrame is called `df`. Your code must assign the result to a variable called `result`.
3. Keep it simple — use standard pandas operations: filtering, groupby, sort_values, head, etc.
4. For date filtering, columns are already datetime type. Use: df[df['col'] >= '2024-01-01']
5. Limit results to 10000 rows maximum using .head(10000).
6. Do NOT use exec, eval, import, open, os, sys, subprocess, or any system operations.

## Response Format
Respond with JSON only — no markdown, no explanation outside the JSON:
{{
  "pandas_code": "result = df[df['sale_amount'] > 500000].head(100)",
  "chart_config": {{
    "chart_type": "bar",
    "x": "column_name",
    "y": "column_name",
    "color": null,
    "title": "Chart Title"
  }},
  "explanation": "Brief description of what the code does."
}}

chart_type must be one of: bar, line, scatter, histogram, map
For map charts, use chart_type "map" with latitude/longitude columns.
Set chart_config to null if a chart doesn't make sense.

## Examples

User: Show investor purchases over $1M
{{
  "pandas_code": "result = df[(df['investor_purchase'] == 'Y') & (df['sale_amount'] > 1000000)].sort_values('sale_amount', ascending=False).head(100)",
  "chart_config": {{"chart_type": "bar", "x": "city", "y": "sale_amount", "color": "investor_tier", "title": "Investor Purchases Over $1M by City"}},
  "explanation": "Filtering for investor purchases with sale amounts exceeding $1 million."
}}

User: Top 10 cities by transaction volume
{{
  "pandas_code": "result = df.groupby('city').size().reset_index(name='txn_count').sort_values('txn_count', ascending=False).head(10)",
  "chart_config": {{"chart_type": "bar", "x": "city", "y": "txn_count", "color": null, "title": "Top 10 Cities by Transaction Volume"}},
  "explanation": "Counting transactions per city and returning the top 10."
}}

User: Monthly trend for Harris County
{{
  "pandas_code": "filtered = df[df['county'] == 'HARRIS'].copy()\\nfiltered['sale_month'] = filtered['sale_date'].dt.to_period('M').dt.to_timestamp()\\nresult = filtered.groupby('sale_month').size().reset_index(name='txn_count').sort_values('sale_month')",
  "chart_config": {{"chart_type": "line", "x": "sale_month", "y": "txn_count", "color": null, "title": "Monthly Transaction Trend - Harris County"}},
  "explanation": "Monthly transaction count for Harris County over time."
}}

User: Average list price by city
{{
  "pandas_code": "result = df.groupby('City')['ListPrice'].mean().reset_index(name='avg_price').sort_values('avg_price', ascending=False).head(20)",
  "chart_config": {{"chart_type": "bar", "x": "City", "y": "avg_price", "color": null, "title": "Average List Price by City"}},
  "explanation": "Computing average list price per city."
}}

User: Map active listings
{{
  "pandas_code": "result = df[(df['StandardStatus'] == 'Active') & (df['Latitude'].notna())].head(500)",
  "chart_config": {{"chart_type": "map", "x": "Longitude", "y": "Latitude", "color": "ListPrice", "title": "Active Listings Map"}},
  "explanation": "Mapping active listings with list price as the color scale."
}}"""


# Example questions per dataset for the UI
EXAMPLE_QUESTIONS = {
    "Deed Transactions": [
        "Show me the top 10 cities by transaction volume",
        "What are the average sale prices by investor classification?",
        "Show cash purchases over $500K in Houston in 2024",
        "Monthly transaction trend for Harris County",
    ],
    "MLS Listings": [
        "What's the average list price by city?",
        "Show me active listings with more than 4 bedrooms under $500K",
        "Average days on market by property type",
        "Monthly listing trend for 2024",
    ],
    "Code Lookups": [
        "Show all distinct code types",
        "List property indicator codes and their descriptions",
        "What land use codes are available?",
        "Show the first 100 rows",
    ],
    "MLS Statistics": [
        "Show monthly median price trends",
        "Compare active listings vs closed sales by month",
        "What are the top areas by total volume?",
        "Show the first 100 rows sorted by date",
    ],
    "Property Tax Stats": [
        "Average property tax rate by state",
        "Show tax statistics for Texas",
        "Compare median home values across states",
        "Show the first 100 rows",
    ],
    "Investor Deed Activity": [
        "Top 10 counties by investor deed volume",
        "Monthly investor activity trend",
        "Compare small vs institutional investor purchases by city",
        "Show investor deed activity in Harris County",
    ],
    "Data Center Properties": [
        "Map all verified data center properties",
        "Show data centers by state",
        "List the largest data center properties",
        "Show the first 100 rows",
    ],
}
