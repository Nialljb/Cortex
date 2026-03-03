import streamlit as st
import pandas as pd
import plotly.express as px
import os

st.set_page_config(page_title="Visualize Data", page_icon="📊", layout="wide")

st.title("📊 Visualize Data")

# Check connection
if not st.session_state.get("connected", False):
    st.warning("⚠️ Not connected to HPC cluster. You can still visualize local files.")

st.write("Create interactive visualizations from your results.")

# ============================================================================
# FILE UPLOAD / SELECTION
# ============================================================================
st.header("📁 Load Data")

data_source = st.radio(
    "Data Source",
    options=["Upload Local File", "Load from HPC"],
    horizontal=True
)

df = None

if data_source == "Upload Local File":
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=["csv", "txt", "tsv", "xlsx"],
        help="Upload a data file to visualize"
    )
    
    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            elif uploaded_file.name.endswith('.tsv'):
                df = pd.read_csv(uploaded_file, sep='\t')
            elif uploaded_file.name.endswith('.xlsx'):
                df = pd.read_excel(uploaded_file)
            else:
                df = pd.read_csv(uploaded_file)
            
            st.success(f"✅ Loaded {len(df)} rows from {uploaded_file.name}")
        except Exception as e:
            st.error(f"Error loading file: {e}")

else:
    st.info("🚧 Loading from HPC feature coming soon!")
    st.write("You'll be able to browse and load data files directly from your HPC cluster.")

# ============================================================================
# DATA PREVIEW
# ============================================================================
if df is not None:
    st.divider()
    st.header("👀 Data Preview")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rows", len(df))
    with col2:
        st.metric("Columns", len(df.columns))
    with col3:
        st.metric("Memory", f"{df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")
    
    with st.expander("View Data", expanded=True):
        st.dataframe(df.head(100), use_container_width=True)
    
    with st.expander("Column Statistics"):
        st.write(df.describe())
    
    # ============================================================================
    # VISUALIZATION
    # ============================================================================
    st.divider()
    st.header("📈 Create Visualization")
    
    viz_type = st.selectbox(
        "Visualization Type",
        options=[
            "Scatter Plot",
            "Line Chart",
            "Bar Chart",
            "Histogram",
            "Box Plot",
            "Heatmap"
        ]
    )
    
    numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
    all_cols = df.columns.tolist()
    
    col1, col2 = st.columns(2)
    
    if viz_type == "Scatter Plot":
        with col1:
            x_col = st.selectbox("X-axis", options=numeric_cols)
        with col2:
            y_col = st.selectbox("Y-axis", options=numeric_cols)
        
        color_col = st.selectbox("Color by (optional)", options=["None"] + all_cols)
        
        if x_col and y_col:
            fig = px.scatter(
                df, 
                x=x_col, 
                y=y_col,
                color=None if color_col == "None" else color_col,
                title=f"{y_col} vs {x_col}"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Line Chart":
        with col1:
            x_col = st.selectbox("X-axis", options=all_cols)
        with col2:
            y_cols = st.multiselect("Y-axis", options=numeric_cols)
        
        if x_col and y_cols:
            fig = px.line(df, x=x_col, y=y_cols, title=f"Line Chart")
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Bar Chart":
        with col1:
            x_col = st.selectbox("X-axis (Category)", options=all_cols)
        with col2:
            y_col = st.selectbox("Y-axis (Value)", options=numeric_cols)
        
        if x_col and y_col:
            fig = px.bar(df, x=x_col, y=y_col, title=f"{y_col} by {x_col}")
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Histogram":
        col = st.selectbox("Column", options=numeric_cols)
        bins = st.slider("Number of bins", 10, 100, 30)
        
        if col:
            fig = px.histogram(df, x=col, nbins=bins, title=f"Distribution of {col}")
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Box Plot":
        with col1:
            y_col = st.selectbox("Value", options=numeric_cols)
        with col2:
            x_col = st.selectbox("Group by (optional)", options=["None"] + all_cols)
        
        if y_col:
            fig = px.box(
                df,
                y=y_col,
                x=None if x_col == "None" else x_col,
                title=f"Box Plot of {y_col}"
            )
            st.plotly_chart(fig, use_container_width=True)
    
    elif viz_type == "Heatmap":
        if not numeric_cols:
            st.warning("No numeric columns available for correlation heatmap.")
        else:
            corr_data = df[numeric_cols].corr()
            fig = px.imshow(
                corr_data,
                labels=dict(color="Correlation"),
                title="Correlation Heatmap",
                color_continuous_scale="RdBu_r"
            )
            st.plotly_chart(fig, use_container_width=True)

else:
    st.info("📁 Upload a data file to get started with visualizations.")
    
    # Example visualization
    st.divider()
    st.header("📊 Example Visualization")
    
    # Generate sample data
    sample_df = pd.DataFrame({
        'x': range(100),
        'y': [i**2 + i*10 for i in range(100)],
        'category': ['A' if i % 2 == 0 else 'B' for i in range(100)]
    })
    
    fig = px.scatter(sample_df, x='x', y='y', color='category', title="Sample Scatter Plot")
    st.plotly_chart(fig, use_container_width=True)