import json
import os
from typing import Optional
import pandas as pd
import google.auth
from google.adk.agents import Agent
from vertexai.generative_models import Part # Part is included for future image handling

# --- Configuration ---
try:
    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
except google.auth.exceptions.DefaultCredentialsError:
    print("WARNING: Google Cloud credentials not found. Run 'gcloud auth application-default login' for local development.")
    project_id = "your-gcp-project-id" # Fallback, replace if needed

os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "us-central1")
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

# --- Load and Prepare Market Data from CSV ---
try:
    CSV_PATH = "market_data.csv"
    MARKET_DATA_DF = pd.read_csv(CSV_PATH)
    
    # Clean up column names (e.g., 'Min_x0020_Price' -> 'Min Price')
    # This leaves 'Arrival_Date' as is, which is correct.
    MARKET_DATA_DF.columns = [col.replace('_x0020_', ' ') for col in MARKET_DATA_DF.columns]
    
    # Convert 'Arrival_Date' column to datetime objects for sorting and analysis
    # This uses the correct column name from the CSV.
    MARKET_DATA_DF['Arrival_Date'] = pd.to_datetime(MARKET_DATA_DF['Arrival_Date'], format='%d/%m/%Y')
    
    print(f"Successfully loaded and processed market data from {CSV_PATH}")
    print("Available columns:", MARKET_DATA_DF.columns.tolist())

except FileNotFoundError:
    print(f"ERROR: '{CSV_PATH}' not found. Please create the CSV file and place it in the 'app' directory.")
    MARKET_DATA_DF = pd.DataFrame()

# =========================================================================
# === TOOLS (Functions the AI can use) ===
# =========================================================================

async def get_market_analysis(
    commodity: str,
    state: Optional[str] = None,
    district: Optional[str] = None,
    market: Optional[str] = None,
) -> str:
    """
    Searches a local database for market price data for a given agricultural commodity.
    It can be filtered by state, district, or a specific market.

    Args:
        commodity (str): The English name of the crop (e.g., 'Tomato', 'Potato').
        state (Optional[str]): The English name of the state (e.g., 'West Bengal').
        district (Optional[str]): The English name of the district (e.g., 'Agra').
        market (Optional[str]): The specific English market name (e.g., 'Achnera').
    """
    print(f"Tool called: Searching for Commodity='{commodity}', State='{state}', District='{district}', Market='{market}'")
    
    if MARKET_DATA_DF.empty:
        return json.dumps({"error": "Market data file is not loaded or is empty."})
        
    filtered_df = MARKET_DATA_DF.copy()

    # Apply filters one by one. The matching is case-insensitive and partial.
    if commodity:
        filtered_df = filtered_df[filtered_df['Commodity'].str.contains(commodity, case=False, na=False)]
    if state:
        filtered_df = filtered_df[filtered_df['State'].str.contains(state, case=False, na=False)]
    if district:
        filtered_df = filtered_df[filtered_df['District'].str.contains(district, case=False, na=False)]
    if market:
        filtered_df = filtered_df[filtered_df['Market'].str.contains(market, case=False, na=False)]

    if filtered_df.empty:
        return json.dumps({"error": f"Sorry, I couldn't find any price data for '{commodity}' with the specified location filters."})

    # Convert the date back to string format for JSON serialization
    filtered_df['Arrival_Date'] = filtered_df['Arrival_Date'].dt.strftime('%d/%m/%Y')

    result_json = filtered_df.to_json(orient="records")
    print(f"Found {len(filtered_df)} records. Returning JSON to agent.")
    return result_json

# =========================================================================
# === AGENT DEFINITION ===
# =========================================================================
root_agent = Agent(
    name="root_agent",
    model="gemini-2.0-flash",
    instruction="""You are 'KisanSathi-expert', an expert agricultural market advisor for Indian farmers. 
    Your primary goal is to provide clear, actionable advice in the user's language and native script.

    **YOUR TASK:**
    1.  Understand the user's request for crop price information.
    2.  Use the `get_market_analysis` tool to fetch the necessary data.
    3.  Analyze the JSON data returned by the tool.
    4.  Format your final answer to the user STRICTLY according to the 'RESPONSE FORMAT' section below.

    ---
    **TOOL BEHAVIOR:**
    - The `get_market_analysis` tool returns raw JSON data. The data includes fields like 'State', 'District', 'Market', 'Commodity', 'Variety', 'Min Price', 'Max Price', 'Modal Price', and 'Arrival_Date'.
    - The current year is 2024. Data from previous years is historical.

    ---
    **RESPONSE FORMAT:**
    You MUST structure your response using the following markdown format. Do not add any extra sentences or conversational text unless it's in the specified sections.

    **Market Analysis for [Commodity] in [Location]**

    **Price Trend:**
    - [Describe the trend based on the data. e.g., "The price has been steadily increasing," "The price has been stable," or "The price is fluctuating."].
    - On [Oldest Date], the price was ₹[Price].
    - On [Most Recent Date], the price is ₹[Price].

    **Data Summary:**
    - **Market:** [Market Name], [District], [State]
    - **Most Recent Price:** ₹[Modal Price] per quintal
    - **Price Range (Recent):** ₹[Min Price] - ₹[Max Price] per quintal

    **Recommendation:**
    - [Provide a clear, one-sentence recommendation based on the trend. Use one of the following formats]:
        - "Based on the rising trend, this appears to be a good time to sell."
        - "Based on the falling trend, you might consider waiting for prices to improve if you can."
        - "Since the price is stable, selling now is a reasonable option."


    *Would you like to check prices in other nearby markets?*
    ---
    
    **SPECIAL CASES:**
    - **General Query (No Market):** If the user asks for prices without a specific market, provide a brief summary of the price range across multiple markets and then ask them to specify a market for a detailed analysis.
    - **Location Mismatch:** If the user asks for a location (e.g., 'Uttarakhand') but the data is for a different one (e.g., 'Uttar Pradesh'), state this clearly at the beginning of your response.
    - **No Data Error:** If the tool returns an error, simply state: "Sorry, I could not find any price data for your request."
    """,
    tools=[
        get_market_analysis,
    ],
)