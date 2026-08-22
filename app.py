import streamlit as st
from streamlit_gsheets import GSheetsConnection
import google.generativeai as genai
import pandas as pd
import datetime
import requests
from bs4 import BeautifulSoup
import plotly.express as px
import json

# --- Page Configuration (Light Mode is enforced via Streamlit settings/theme) ---
st.set_page_config(page_title="Coffee Log", page_icon="☕", layout="wide")

# --- Initialize Connections & API ---
# Configure Gemini API
if "GEMINI_API_KEY" in st.secrets:
    genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
    model = genai.GenerativeModel('gemini-1.5-flash')

# Connect to Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- Helper Functions ---
def fetch_url_text(url):
    """Scrape text from a coffee roaster's URL."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        return soup.get_text(separator=' ', strip=True)
    except Exception as e:
        st.error(f"Failed to fetch URL: {e}")
        return ""

def parse_coffee_with_ai(image_bytes=None, url_text=""):
    """Use Gemini to extract coffee details from image and/or URL."""
    prompt = """
    Analyze the provided coffee bag image and/or webpage text. 
    Extract the following details and return ONLY a valid JSON object. 
    If a detail is missing, leave the value as an empty string "".
    JSON keys: roaster, coffee_name, country, producer, processing, variety, roast_level, tasting_notes.
    """
    
    contents = [prompt]
    if url_text:
        contents.append(f"Webpage Text: {url_text[:5000]}") # Limit text length
    if image_bytes:
        contents.append({"mime_type": "image/jpeg", "data": image_bytes})
        
    try:
        response = model.generate_content(contents)
        # Clean markdown formatting if Gemini returns it
        result = response.text.replace('```json', '').replace('```', '').strip()
        return json.loads(result)
    except Exception as e:
        st.error(f"AI Processing failed: {e}")
        return None

def load_data(worksheet="Recipes"):
    """Load data from GSheets and handle empty states."""
    try:
        df = conn.read(worksheet=worksheet, ttl=0)
        return df.dropna(how="all")
    except Exception:
        # Return empty DF with expected columns if sheet doesn't exist yet
        if worksheet == "Recipes":
            return pd.DataFrame(columns=[
                "Date", "Roaster", "Coffee_Name", "Country", "Producer", "Processing", 
                "Variety", "Brew_Method", "Grinder", "Grind_Size", "Coffee_In_g", 
                "Water_g", "Ratio", "Temp_C", "TDS", "Bloom", "Total_Time", 
                "Rating", "Comments"
            ])
        else:
            return pd.DataFrame(columns=["Grinder_Name"])

# --- Session State Management ---
if 'ai_dossier' not in st.session_state:
    st.session_state.ai_dossier = {}

# --- Main UI ---
st.title("☕ Coffee Log")

# Create Tabs
tab_dash, tab_add, tab_analytics, tab_settings = st.tabs([
    "📜 History", "➕ Add & Scan", "📊 Analytics", "⚙️ Settings"
])

# -----------------------------------
# TAB 1: HISTORY (Dashboard)
# -----------------------------------
with tab_dash:
    df_recipes = load_data("Recipes")
    
    if df_recipes.empty:
        st.info("No brews found. Start by adding a recipe!")
    else:
        # Filters
        col1, col2 = st.columns(2)
        with col1:
            brew_methods = ["All"] + list(df_recipes["Brew_Method"].dropna().unique())
            selected_method = st.selectbox("Filter by Brew Method", brew_methods)
        
        # Apply filter
        if selected_method != "All":
            df_display = df_recipes[df_recipes["Brew_Method"] == selected_method]
        else:
            df_display = df_recipes
            
        # Display Cards
        for _, row in df_display.iterrows():
            with st.expander(f"{row.get('Roaster', 'Unknown')} - {row.get('Coffee_Name', '')} ({row.get('Brew_Method', '')})"):
                c1, c2, c3 = st.columns(3)
                c1.write(f"**Country:** {row.get('Country', '-')}")
                c1.write(f"**Producer/Farm:** {row.get('Producer', '-')}")
                c1.write(f"**Processing:** {row.get('Processing', '-')}")
                
                c2.write(f"**Dose:** {row.get('Coffee_In_g', '-')}g")
                c2.write(f"**Yield/Water:** {row.get('Water_g', '-')}g")
                c2.write(f"**Ratio:** 1:{row.get('Ratio', '-')}")
                
                c3.write(f"**Grinder:** {row.get('Grinder', '-')} ({row.get('Grind_Size', '-')})")
                c3.write(f"**Time:** {row.get('Total_Time', '-')}")
                c3.write(f"**Rating:** {row.get('Rating', '-')} / 10")
                
                st.write(f"**Comments:** {row.get('Comments', '-')}")

# -----------------------------------
# TAB 2: ADD & SCAN
# -----------------------------------
with tab_add:
    st.subheader("AI Coffee Scanner")
    col_img, col_url = st.columns(2)
    
    with col_img:
        uploaded_file = st.file_uploader("Upload Bag Image", type=['jpg', 'jpeg', 'png'])
    with col_url:
        coffee_url = st.text_input("Or paste Roaster's Webpage URL")
        
    if st.button("Scan Details with AI"):
        with st.spinner("Analyzing coffee details..."):
            img_bytes = uploaded_file.getvalue() if uploaded_file else None
            url_data = fetch_url_text(coffee_url) if coffee_url else ""
            
            if img_bytes or url_data:
                ai_result = parse_coffee_with_ai(img_bytes, url_data)
                if ai_result:
                    st.session_state.ai_dossier = ai_result
                    st.success("Data extracted successfully!")
            else:
                st.warning("Please upload an image or provide a URL.")

    st.divider()
    st.subheader("Recipe Details")
    
    # Load Grinders for Dropdown
    df_settings = load_data("Settings")
    grinder_options = df_settings["Grinder_Name"].tolist() if not df_settings.empty else ["Default"]

    with st.form("recipe_form"):
        # Auto-fill from AI Dossier if available
        dossier = st.session_state.ai_dossier
        
        c1, c2, c3 = st.columns(3)
        roaster = c1.text_input("Roaster", value=dossier.get("roaster", ""))
        coffee_name = c2.text_input("Coffee Name", value=dossier.get("coffee_name", ""))
        country = c3.text_input("Country", value=dossier.get("country", ""))
        
        c4, c5, c6 = st.columns(3)
        producer = c4.text_input("Producer / Farm", value=dossier.get("producer", ""))
        processing = c5.text_input("Processing", value=dossier.get("processing", ""))
        variety = c6.text_input("Variety", value=dossier.get("variety", ""))
        
        st.write("---")
        
        b1, b2, b3 = st.columns(3)
        brew_method = b1.selectbox("Brew Method", ["V60", "DEEP27", "Origami", "Espresso", "AeroPress", "Chemex", "Cold Brew", "Other"])
        grinder = b2.selectbox("Grinder", grinder_options)
        grind_size = b3.text_input("Grind Size (Settings/Clicks)")
        
        d1, d2, d3, d4 = st.columns(4)
        coffee_in = d1.number_input("Coffee (g)", min_value=0.0, step=0.5, format="%.1f")
        water_out = d2.number_input("Water (g)", min_value=0.0, step=1.0, format="%.1f")
        temp = d3.number_input("Temp (°C)", min_value=0, step=1)
        tds = d4.number_input("Water TDS (ppm)", min_value=0, step=1)
        
        t1, t2, t3 = st.columns(3)
        bloom = t1.text_input("Bloom (e.g., 50g for 30s)")
        total_time = t2.text_input("Total Time (e.g., 2:45)")
        rating = t3.slider("Rating", 1, 10, 5)
        
        comments = st.text_area("Tasting Notes & Comments", value=dossier.get("tasting_notes", ""))
        
        submit = st.form_submit_button("Save Recipe")
        
        if submit:
            ratio = round(water_out / coffee_in, 1) if coffee_in > 0 else 0
            
            new_data = pd.DataFrame([{
                "Date": datetime.date.today().strftime("%Y-%m-%d"),
                "Roaster": roaster,
                "Coffee_Name": coffee_name,
                "Country": country,
                "Producer": producer,
                "Processing": processing,
                "Variety": variety,
                "Brew_Method": brew_method,
                "Grinder": grinder,
                "Grind_Size": grind_size,
                "Coffee_In_g": coffee_in,
                "Water_g": water_out,
                "Ratio": ratio,
                "Temp_C": temp,
                "TDS": tds,
                "Bloom": bloom,
                "Total_Time": total_time,
                "Rating": rating,
                "Comments": comments
            }])
            
            # Append and Save
            updated_df = pd.concat([df_recipes, new_data], ignore_index=True)
            conn.update(worksheet="Recipes", data=updated_df)
            st.session_state.ai_dossier = {} # Clear AI data after save
            st.success("Recipe saved to Google Sheets!")
            st.rerun()

# -----------------------------------
# TAB 3: ANALYTICS
# -----------------------------------
with tab_analytics:
    if not df_recipes.empty:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Top Roasters")
            roaster_counts = df_recipes['Roaster'].value_counts().reset_index()
            roaster_counts.columns = ['Roaster', 'Count']
            fig1 = px.pie(roaster_counts, names='Roaster', values='Count', hole=0.4)
            st.plotly_chart(fig1, use_container_width=True)
            
        with col2:
            st.subheader("Coffee Origins")
            origin_counts = df_recipes['Country'].value_counts().reset_index()
            origin_counts.columns = ['Country', 'Count']
            fig2 = px.bar(origin_counts, x='Country', y='Count', color='Country')
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("Not enough data to display analytics.")

# -----------------------------------
# TAB 4: SETTINGS
# -----------------------------------
with tab_settings:
    st.subheader("Manage Grinders")
    df_settings = load_data("Settings")
    
    current_grinders = df_settings["Grinder_Name"].tolist() if not df_settings.empty else []
    st.write("Current Grinders:", ", ".join(current_grinders) if current_grinders else "None")
    
    new_grinder = st.text_input("Add New Grinder")
    if st.button("Add Grinder"):
        if new_grinder and new_grinder not in current_grinders:
            new_row = pd.DataFrame([{"Grinder_Name": new_grinder}])
            updated_settings = pd.concat([df_settings, new_row], ignore_index=True)
            conn.update(worksheet="Settings", data=updated_settings)
            st.success(f"Added {new_grinder}!")
            st.rerun()
