import streamlit as st
from streamlit.components.v1 import html
import json
import pandas as pd
import re
import os
from io import BytesIO

# ================================================
# LOTTIE ANIMATION PLAYER
# ================================================
def lottie_player(lottie_url_or_json: str, height: int = 250, autoplay: bool = True, loop: bool = True):
    """Embed a Lottie animation (URL or raw JSON)."""
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
# APP STYLING (dark + card)
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
# INPUT CARD (centered)
# ================================================
with st.container():
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    min_users = st.number_input(
        "Minimum unique UserIDs required",
        min_value=1, max_value=50, value=3,
        help="Portfolios with fewer unique UserIDs will be dropped."
    )

    gridlog_file = st.file_uploader("Upload GridLog CSV/XLSX", type=["csv", "xlsx"])
    summary_file = st.file_uploader("Upload SUMMARY Excel (XLSX)", type=["xlsx"])

    run = st.button("Process Files")

    st.markdown("</div>", unsafe_allow_html=True)


# ================================================
# PROCESSING: your original logic adapted for uploads
# ================================================
def read_gridlog(uploaded):
    if uploaded is None:
        return None
    name = uploaded.name.lower()
    try:
        if name.endswith(".csv"):
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


if run:
    # basic checks
    if gridlog_file is None or summary_file is None:
        st.error("⚠ Please upload BOTH GridLog and SUMMARY files.")
        st.stop()

    # Step 1: Load GridLog
    df_grid = read_gridlog(gridlog_file)
    xl = read_summary_excel(summary_file)

    if df_grid is None or xl is None:
        st.stop()

    # preserve original behavior: strip column names
    df_grid.columns = df_grid.columns.str.strip()

    # Step 2: Keep only portfolios with N or more unique UserIDs
    if 'UserID' in df_grid.columns:
        try:
            min_users_int = int(min_users)
        except Exception:
            min_users_int = 3

        st.info(f"Filtering portfolios with at least {min_users_int} unique UserIDs...")

        user_count_df = (
            df_grid.dropna(subset=['Option Portfolio', 'UserID'])
                  .groupby('Option Portfolio')['UserID']
                  .nunique()
                  .reset_index(name='UniqueUserCount')
        )

        valid_portfolios = user_count_df[
            user_count_df['UniqueUserCount'] >= min_users_int
        ]['Option Portfolio'].unique()

        df_grid = df_grid[df_grid['Option Portfolio'].isin(valid_portfolios)]

    else:
        st.warning("⚠ 'UserID' column not found. Skipping unique-user filtering.")

    # Step 3: Filter for Combined SL / Trail Target messages
    if 'Message' not in df_grid.columns or 'Option Portfolio' not in df_grid.columns:
        st.error("GridLog must contain 'Message' and 'Option Portfolio' columns.")
        st.stop()

    mask = df_grid['Message'].astype(str).str.contains(r'Combined SL:|Combined trail target:', case=False, na=False)
    filtered_grid = df_grid.loc[mask, ['Message', 'Option Portfolio', 'Timestamp']].dropna(subset=['Option Portfolio'])

    # Identify message type
    filtered_grid['MessageType'] = filtered_grid['Message'].astype(str).str.extract(
        r'(Combined SL|Combined trail target)', flags=re.IGNORECASE
    )

    # Keep only duplicates of same message type per portfolio
    duplicate_mask = filtered_grid.duplicated(subset=['Option Portfolio', 'MessageType'], keep=False)
    filtered_grid = filtered_grid[duplicate_mask]

    # Group GridLog results
    if not filtered_grid.empty:
        summary_grid = (
            filtered_grid.groupby('Option Portfolio').agg({
                'Message': lambda x: ', '.join(x.unique()),
                'Timestamp': 'max'
            }).reset_index()
            .rename(columns={'Message': 'Reason', 'Timestamp': 'Time'})
        )
    else:
        summary_grid = pd.DataFrame(columns=['Option Portfolio', 'Reason', 'Time'])

    # Step 4: Process Summary Excel File
    summary_list = []
    try:
        for sheet_name in xl.sheet_names:
            if "legs" in sheet_name.lower():
                df_leg = xl.parse(sheet_name)
                df_leg.columns = df_leg.columns.str.strip()

                if {'Exit Type', 'Portfolio Name', 'Exit Time'}.issubset(df_leg.columns):
                    onsqoff_df = df_leg[df_leg['Exit Type'].astype(str).str.strip() == 'OnSqOffTime']

                    if not onsqoff_df.empty:
                        grouped = onsqoff_df.groupby('Portfolio Name')['Exit Time'].max().reset_index()
                        for _, row in grouped.iterrows():
                            summary_list.append({
                                'Option Portfolio': row['Portfolio Name'],
                                'Reason': 'OnSqOffTime',
                                'Time': row['Exit Time']
                            })
    except Exception as e:
        st.error(f"Error processing SUMMARY sheets: {e}")

    summary_summary = pd.DataFrame(summary_list)

    # Step 5: Combine GridLog and Summary results
    if summary_grid.empty and summary_summary.empty:
        final_df = pd.DataFrame(columns=['Option Portfolio', 'Reason', 'Time'])
    else:
        final_df = pd.concat([summary_grid, summary_summary], ignore_index=True)

        final_df = (
            final_df.groupby('Option Portfolio').agg({
                'Reason': lambda x: ', '.join(sorted(set(x))),
                'Time': 'last'
            }).reset_index()
        )

    # Step 6: Add completed portfolios
    completed_list = []
    grid_portfolios = df_grid['Option Portfolio'].dropna().unique() if 'Option Portfolio' in df_grid.columns else []

    try:
        for sheet_name in xl.sheet_names:
            if "legs" in sheet_name.lower():
                df_leg = xl.parse(sheet_name)
                df_leg.columns = df_leg.columns.str.strip()

                if 'Portfolio Name' in df_leg.columns and 'Status' in df_leg.columns:
                    for portfolio, group in df_leg.groupby('Portfolio Name'):
                        if portfolio not in final_df['Option Portfolio'].values and portfolio in grid_portfolios:
                            statuses = group['Status'].astype(str).str.strip().unique()
                            if len(statuses) == 1 and statuses[0].lower() == 'completed':
                                reason_text = 'AllLegsCompleted'
                                exit_time_to_use = None

                                if 'Exit Time' in group.columns:
                                    for exit_time, exit_type in zip(group['Exit Time'], group.get('Exit Type', [])):
                                        if pd.isna(exit_time):
                                            continue
                                        normalized_exit_time = str(exit_time).replace('.', ':').strip()
                                        matching_rows = df_grid[
                                            (df_grid['Option Portfolio'] == portfolio) &
                                            (df_grid['Timestamp'].astype(str).str.contains(normalized_exit_time))
                                        ]
                                        if not matching_rows.empty:
                                            # guard exit_type
                                            try:
                                                reason_text += f", {exit_type.strip()}"
                                            except Exception:
                                                reason_text += f", {str(exit_type)}"
                                            exit_time_to_use = exit_time
                                            break

                                completed_list.append({
                                    'Option Portfolio': portfolio,
                                    'Reason': reason_text,
                                    'Time': exit_time_to_use
                                })
    except Exception as e:
        st.warning(f"Issue while building completed portfolios: {e}")

    if completed_list:
        completed_df = pd.DataFrame(completed_list)
        if final_df.empty:
            final_df = completed_df
        else:
            final_df = pd.concat([final_df, completed_df], ignore_index=True)

    # Step 7: Clean Reason Texts
    def clean_reason(text):
        if pd.isna(text):
            return text
        text = str(text)

        match = re.search(r'(Combined SL: [^ ]+ hit|Combined Trail Target: [^ ]+ hit)', text, re.IGNORECASE)
        if match:
            return match.group(1)

        if 'AllLegsCompleted' in text:
            text = text.replace('AllLegsCompleted,', '').strip()
            text = text.replace('AllLegsCompleted', '').strip()

        return text.strip()

    if 'Reason' in final_df.columns:
        final_df['Reason'] = final_df['Reason'].apply(clean_reason)

    # Step 8: Build dynamic output file name (best-effort from uploaded filename)
    grid_filename = getattr(gridlog_file, "name", "gridlog")
    match = re.search(r'(\d{1,2}\s+[A-Za-z]{3}\s+\d{4})', grid_filename)
    if match:
        raw_date = match.group(1)
        parts = raw_date.split()
        formatted_date = f"{parts[0]} {parts[1].lower()}"
    else:
        formatted_date = "unknown_date"

    output_filename = f"completed portfolio of {formatted_date}.csv"

    # Step 9: Save final result to bytes (for download)
    if 'Time' in final_df.columns:
        final_df['Time'] = final_df['Time'].astype(str).str.strip().replace('nan', '')

    # Display results
    st.success("✅ Processing completed!")
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.write("**Final portfolios:**")
    st.dataframe(final_df, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Download button
    csv_bytes = final_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Completed Portfolio CSV",
        data=csv_bytes,
        file_name=output_filename,
        mime="text/csv"
    )

    # small summary
    st.markdown("---")
    st.write("**Summary**")
    st.write(f"- Grid rows processed: {len(df_grid):,}")
    st.write(f"- Portfolios found in final result: {len(final_df):,}")

