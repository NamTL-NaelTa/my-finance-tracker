import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd

st.title("💰 Ứng Dụng Quản Lý Dòng Tiền")

# Kết nối Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Hiển thị dữ liệu từ sheet Dashboard
st.subheader("Trạng thái hiện tại")
dashboard_data = conn.read(worksheet="Dashboard")
st.dataframe(dashboard_data)
