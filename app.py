import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")
st.title("💰 Quản Lý Dòng Tiền")

# Kết nối Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- PHẦN 1: BẢNG ĐIỀU KHIỂN (READ) ---
st.subheader("📊 Trạng thái hiện tại")
# Lấy dữ liệu Dashboard (Xóa cache để luôn cập nhật số mới nhất)
dashboard_data = conn.read(worksheet="Dashboard", ttl=0) 
st.dataframe(dashboard_data, hide_index=True, use_container_width=True)

st.divider()

# --- PHẦN 2: FORM NHẬP LIỆU (WRITE) ---
st.subheader("📝 Nhập giao dịch mới")
with st.form("transaction_form", clear_on_submit=True):
    col1, col2 = st.columns(2)
    
    with col1:
        ngay = st.date_input("Ngày giao dịch")
        so_tien = st.number_input("Số tiền (Nhập số ÂM nếu chi tiền)", value=0, step=1000)
        
    with col2:
        phan_loai = st.selectbox("Phân loại", ["Ăn uống", "Đi lại", "Mua sắm", "Gia đình", "Thu lặt vặt"])
        noi_dung = st.text_input("Nội dung (VD: Trà sữa, Đổ xăng)")
        
    submit = st.form_submit_button("Lưu Giao Dịch", type="primary", use_container_width=True)

    if submit:
        if so_tien == 0:
            st.warning("⚠️ Vui lòng nhập số tiền khác 0!")
        elif noi_dung == "":
            st.warning("⚠️️ Vui lòng nhập nội dung giao dịch!")
        else:
            with st.spinner("Đang lưu vào Google Sheets..."):
                # 1. Tải dữ liệu hiện tại của sheet Transactions
                df_trans = conn.read(worksheet="Transactions", ttl=0)
                
                # 2. Tạo mã ID mới
                new_id = f"txn_{len(df_trans) + 1}"
                
                # 3. Tạo dòng dữ liệu mới khớp với các cột trong file Sheet
                new_row = pd.DataFrame({
                    "id": [new_id],
                    "date": [ngay.strftime("%d/%m/%Y")],
                    "description": [noi_dung],
                    "category": [phan_loai],
                    "amount": [so_tien]
                })
                
                # 4. Nối dòng mới vào bảng cũ và đẩy lên Sheets
                updated_df = pd.concat([df_trans, new_row], ignore_index=True)
                conn.update(worksheet="Transactions", data=updated_df)
                
                st.success(f"✅ Đã lưu thành công: {noi_dung}")
                st.rerun() # Tải lại trang để bảng Dashboard cập nhật số tiền mới
