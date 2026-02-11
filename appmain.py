import streamlit as st
from streamlit.components.v1 import html
import json
import pandas as pd
import re
from io import BytesIO
from datetime import datetime

# ================================================
# LOTTIE ANIMATION PLAYER
# ================================================
def lottie_player(lottie_url_or_json: str, height: int = 250, autoplay: bool = True, loop: bool = True):
    is_json = False
    try:
        json.loads(lottie_url_or_json)
        is_json = True
    except Exception:
        is_json = False
    if is_json:
        payload = json.dumps(json.loads(lottie_url_or_json))
        inner = f"""
            <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
            <lottie-player autoplay={'true' if autoplay else 'false'} loop={'true' if loop else 'false'}
                mode="normal" style="width:100%; height:{height}px;"
                src='data:application/json;utf8,{payload}'>
            </lottie-player>
        """
    else:
        inner = f"""
            <script src="https://unpkg.com/@lottiefiles/lottie-player@latest/dist/lottie-player.js"></script>
            <lottie-player src="{lottie_url_or_json}" autoplay={'true' if autoplay else 'false'}
                loop={'true' if loop else 'false'} mode="normal"
                style="width:100%; height:{height}px;">
            </lottie-player>
        """
    html(inner, height=height + 20)

# ================================================
# APP STYLING
# ================================================
st.set_page_config(page_title="Completed Portfolio Processor", layout="wide")
st.markdown(
    """
    <style>
    body { background-color: #0d1117 !important; }
    h1, h2, h3, h4, p, label, span { color: #e5e7eb !important; }
    .card {
        padding: 25px;
        background-color: #1f2937;
        border-radius: 14px;
        border: 1px solid #374151;
        width: 70%;
        margin: 18px auto;
        transition: 0.2s;
    }
    .card:hover { transform: scale(1.01); border-color: #4b5563; }
    .stButton button {
        background-color: #2563eb !important;
        color: white !important;
        border-radius: 8px;
    }
    .stButton button:hover { transform: scale(1.03); transition: 0.2s; }
    .small-muted { color: #9ca3af; font-size: 12px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ================================================
# HEADER + LOTTIE
# ================================================
st.markdown("<h1 style='text-align:center; margin-top:6px;'>Completed Portfolio Processor</h1>", unsafe_allow_html=True)
lottie_url = "https://assets9.lottiefiles.com/packages/lf20_3rwasyjy.json"
lottie_player(lottie_url, height=320)
st.markdown("<h3 style='text-align:center;'>Upload files below and click <b>Process Files</b></h3>", unsafe_allow_html=True)

# ================================================
# INPUT CARD
# ================================================
with st.container():
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    min_users = st.number_input(
        "Minimum unique UserIDs required per portfolio",
        min_value=1, max_value=50, value=1,
        help="Portfolios with fewer unique users will be excluded."
    )
    gridlog_file = st.file_uploader("Upload GridLog (CSV/XLSX)", type=["csv", "xlsx"])
    summary_file = st.file_uploader("Upload SUMMARY Excel (XLSX)", type=["xlsx"])
    run = st.button("Process Files", type="primary")
    st.markdown("</div>", unsafe_allow_html=True)

# ================================================
# HELPER FUNCTIONS
# ================================================
def read_gridlog(uploaded):
    if uploaded is None:
        return None
    try:
        if uploaded.name.lower().endswith(".csv"):
            return pd.read_csv(uploaded)
        else:
            return pd.read_excel(uploaded)
    except Exception as e:
        st.error(f"Failed to read GridLog: {e}")
        return None

def read_summary_excel(uploaded):
    if uploaded is None:
        return None
    try:
        return pd.ExcelFile(uploaded)
    except Exception as e:
        st.error(f"Failed to read Summary Excel: {e}")
        return None

def normalize_time(t):
    if pd.isna(t) or not t:
        return None
    t = str(t).strip()
    parts = t.split(':')
    if len(parts) == 4:  # Handles cases like 14:30:45:123 → 14:30:45.123
        t = ':'.join(parts[:3]) + '.' + parts[3]
    return t

def parse_time_for_sort(t):
    if not t:
        return datetime.min.time()
    try:
        return datetime.strptime(t, '%H:%M:%S.%f').time()
    except:
        try:
            return datetime.strptime(t, '%H:%M:%S').time()
        except:
            return datetime.min.time()

# ================================================
# PROCESSING LOGIC
# ================================================
if run:
    if not gridlog_file or not summary_file:
        st.error("⚠ Please upload both GridLog and SUMMARY files.")
        st.stop()

    with st.spinner("Processing files..."):
        # Load files
        df_grid = read_gridlog(gridlog_file)
        xl = read_summary_excel(summary_file)
        if df_grid is None or xl is None:
            st.stop()

        df_grid.columns = df_grid.columns.str.strip()

        # Normalize timestamps in GridLog
        if 'Timestamp' in df_grid.columns:
            df_grid['Normalized_Timestamp'] = df_grid['Timestamp'].apply(normalize_time)
        else:
            st.error("GridLog must have 'Timestamp' column.")
            st.stop()

        # Filter portfolios by minimum unique UserIDs
        min_users_int = int(min_users)
        if 'UserID' in df_grid.columns:
            st.info(f"Filtering portfolios with ≥ {min_users_int} unique UserIDs...")
            user_count_df = (
                df_grid.dropna(subset=['Option Portfolio', 'UserID'])
                      .groupby('Option Portfolio')['UserID']
                      .nunique()
                      .reset_index(name='UniqueUserCount')
            )
            valid_portfolios = user_count_df[user_count_df['UniqueUserCount'] >= min_users_int]['Option Portfolio'].unique()
            df_grid = df_grid[df_grid['Option Portfolio'].isin(valid_portfolios)]
        else:
            st.warning("⚠ 'UserID' column not found. Skipping user count filtering.")

        # Extract Combined SL / Trail Target messages
        mask = df_grid['Message'].astype(str).str.contains(r'Combined SL:|Combined trail target:', case=False, na=False)
        filtered_grid = df_grid.loc[mask, ['Message', 'Option Portfolio', 'Timestamp', 'Normalized_Timestamp']].dropna(subset=['Option Portfolio'])

        if not filtered_grid.empty:
            filtered_grid['MessageType'] = filtered_grid['Message'].str.extract(r'(Combined SL|Combined trail target)', flags=re.IGNORECASE)
            duplicate_mask = filtered_grid.duplicated(subset=['Option Portfolio', 'MessageType'], keep=False)
            filtered_grid = filtered_grid[duplicate_mask]

            summary_grid = (
                filtered_grid.groupby('Option Portfolio').agg({
                    'Message': lambda x: ', '.join(x.unique()),
                    'Timestamp': 'max'
                }).reset_index()
                .rename(columns={'Message': 'Reason', 'Timestamp': 'Time'})
            )
        else:
            summary_grid = pd.DataFrame(columns=['Option Portfolio', 'Reason', 'Time'])

        # Process OnSqOffTime from SUMMARY
        summary_list = []
        for sheet_name in xl.sheet_names:
            if "legs" in sheet_name.lower():
                df_leg = xl.parse(sheet_name)
                df_leg.columns = df_leg.columns.str.strip()
                required = {'Exit Type', 'Portfolio Name', 'Exit Time'}
                if required.issubset(df_leg.columns):
                    onsqoff_df = df_leg[df_leg['Exit Type'].astype(str).str.strip() == 'OnSqOffTime']
                    if not onsqoff_df.empty:
                        grouped = onsqoff_df.groupby('Portfolio Name')['Exit Time'].max().reset_index()
                        for _, row in grouped.iterrows():
                            summary_list.append({
                                'Option Portfolio': row['Portfolio Name'],
                                'Reason': 'OnSqOffTime',
                                'Time': row['Exit Time']
                            })
        onsqoff_df_final = pd.DataFrame(summary_list)

        # Identify fully completed portfolios (all legs: completed or rejected)
        grid_portfolios = set(df_grid['Option Portfolio'].dropna().unique())
        fully_completed_portfolios = set()
        completed_legs = {}  # portfolio → list of {'exit_time': str, 'exit_type': str}

        for sheet_name in xl.sheet_names:
            if "legs" in sheet_name.lower():
                df_leg = xl.parse(sheet_name)
                df_leg.columns = df_leg.columns.str.strip()
                required_cols = {'Portfolio Name', 'Status'}
                if required_cols.issubset(df_leg.columns):
                    df_leg['Status'] = df_leg['Status'].astype(str).str.strip().str.lower()
                    for portfolio, group in df_leg.groupby('Portfolio Name'):
                        if portfolio not in grid_portfolios:
                            continue
                        unique_statuses = group['Status'].replace(['nan', 'none'], None).dropna().unique()
                        if len(unique_statuses) > 0 and all(s in {'completed', 'rejected'} for s in unique_statuses):
                            fully_completed_portfolios.add(portfolio)
                            # Collect completed legs with exit info
                            comp_group = group[group['Status'] == 'completed']
                            leg_list = []
                            for _, leg in comp_group.iterrows():
                                etime = normalize_time(leg.get('Exit Time'))
                                etype = str(leg.get('Exit Type', '')).strip()
                                if etime and etype and etype.lower() != 'nan':
                                    leg_list.append({'exit_time': etime, 'exit_type': etype})
                            if leg_list:
                                completed_legs[portfolio] = leg_list

        # Build final entries
        final_entries = []

        # 1. Add OnSqOffTime
        for entry in summary_list:
            final_entries.append(entry)

        # 2. Add AllLegsCompleted (time may be updated later)
        for portfolio in fully_completed_portfolios:
            final_entries.append({
                'Option Portfolio': portfolio,
                'Reason': 'AllLegsCompleted',
                'Time': None
            })

        # 3. Add Combined SL/Trail ONLY if portfolio is fully completed
        for _, row in summary_grid.iterrows():
            portfolio = row['Option Portfolio']
            if portfolio in fully_completed_portfolios:
                existing = next((e for e in final_entries if e['Option Portfolio'] == portfolio), None)
                new_reason = row['Reason']
                new_time = row['Time']
                if existing:
                    existing['Reason'] += ', ' + new_reason
                    if new_time:
                        existing['Time'] = new_time
                else:
                    final_entries.append({
                        'Option Portfolio': portfolio,
                        'Reason': new_reason,
                        'Time': new_time
                    })

        # Create DataFrame and deduplicate
        if final_entries:
            final_df = pd.DataFrame(final_entries)
            final_df = (
                final_df.groupby('Option Portfolio').agg({
                    'Reason': lambda x: ', '.join(sorted(set(str(r) for r in x if r))),
                    'Time': 'last'
                }).reset_index()
            )
        else:
            final_df = pd.DataFrame(columns=['Option Portfolio', 'Reason', 'Time'])

        # Clean Reason text
        def clean_reason(text):
            if pd.isna(text):
                return ''
            text = str(text)
            match = re.search(r'(Combined SL: [^ ]+ hit|Combined trail target: [^ ]+ hit)', text, re.IGNORECASE)
            if match:
                return match.group(1)
            text = text.replace('AllLegsCompleted,', '').replace(',AllLegsCompleted', '').replace('AllLegsCompleted', '').strip(', ')
            return text.strip() or 'AllLegsCompleted'

        final_df['Reason'] = final_df['Reason'].apply(clean_reason)

        # Update pure AllLegsCompleted with actual Exit Type + Time if match found in GridLog
        for idx, row in final_df.iterrows():
            if row['Reason'] == 'AllLegsCompleted':
                portfolio = row['Option Portfolio']
                if portfolio in completed_legs:
                    portfolio_timestamps = set(
                        df_grid[df_grid['Option Portfolio'] == portfolio]['Normalized_Timestamp'].dropna()
                    )
                    matching_legs = [
                        leg for leg in completed_legs[portfolio]
                        if leg['exit_time'] in portfolio_timestamps
                    ]
                    if matching_legs:
                        best_leg = max(matching_legs, key=lambda x: parse_time_for_sort(x['exit_time']))
                        final_df.at[idx, 'Reason'] = best_leg['exit_type']
                        final_df.at[idx, 'Time'] = best_leg['exit_time']

        # Final cleanup
        if 'Time' in final_df.columns:
            final_df['Time'] = final_df['Time'].astype(str).replace('nan', '').replace('None', '')

        # Output filename from GridLog name
        grid_filename = gridlog_file.name
        match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', grid_filename)
        if match:
            raw_date = match.group(1)
            parts = raw_date.split()
            formatted_date = f"{parts[0]} {parts[1].lower()}"
        else:
            formatted_date = "unknown_date"
        output_filename = f"completed portfolio of {formatted_date}.csv"

        # Display results
        st.success("✅ Processing completed successfully!")
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        st.write("**Final Completed Portfolios:**")
        if final_df.empty:
            st.info("No portfolios met the completion criteria.")
        else:
            st.dataframe(final_df, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

        # Download
        csv_data = final_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📥 Download Results as CSV",
            data=csv_data,
            file_name=output_filename,
            mime="text/csv"
        )

        # Summary stats
        st.markdown("---")
        st.write("**Processing Summary**")
        st.write(f"- GridLog rows processed: {len(df_grid):,}")
        st.write(f"- Portfolios after UserID filter: {df_grid['Option Portfolio'].nunique() if 'Option Portfolio' in df_grid.columns else 0:,}")
        st.write(f"- Fully completed portfolios detected: {len(fully_completed_portfolios):,}")

        st.write(f"- Final results: {len(final_df):,}")
