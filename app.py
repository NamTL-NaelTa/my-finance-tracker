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
dashboard_data = conn.read(worksheet="Dashboard", ttl=0) 
st.dataframe(dashboard_data, hide_index=True, use_container_width=True)

st.divider()

# --- ĐỌC SHEET DANH MỤC (MASTER DATA) ---
try:
    df_danhmuc = conn.read(worksheet="Danh_muc", ttl=0).dropna(how="all")
    # Lấy danh sách category duy nhất
    list_categories = df_danhmuc['category'].dropna().unique().tolist()
except Exception as e:
    st.error("⚠️ Hệ thống chưa tìm thấy sheet 'Danh_muc' hoặc dữ liệu trống. Vui lòng tạo sheet 'Danh_muc' với 3 cột: category, type, prefix.")
    st.stop()

# --- PHẦN 2: LUỒNG NHẬP LIỆU THÔNG MINH (WRITE) ---
st.subheader("📝 Nhập giao dịch mới")

col1, col2 = st.columns(2)

with col1:
    ngay = st.date_input("Ngày giao dịch")
    so_tien = st.number_input("Số tiền (Nhập số ÂM nếu chi tiền)", value=0, step=1000)

with col2:
    # 1. Chọn Category
    phan_loai = st.selectbox("Nhóm chi tiêu (Category)", list_categories)
    
    # 2. Lọc Type theo Category đã chọn và thêm tùy chọn "Khác..."
    filtered_types = df_danhmuc[df_danhmuc['category'] == phan_loai]['type'].dropna().tolist()
    filtered_types.append("Khác...")
    
    chon_loai = st.selectbox("Khoản chi tiết (Type)", filtered_types)

# 3. Kịch bản chọn "Khác..." để sinh mã ID mới
if chon_loai == "Khác...":
    col3, col4 = st.columns(2)
    with col3:
        noi_dung = st.text_input("Nhập nội dung mới (VD: Khám răng)")
    with col4:
        prefix = st.text_input("Nhập mã quy ước ngắn (VD: kr)")
else:
    noi_dung = chon_loai
    # Lấy prefix tự động từ sheet Danh_muc
    prefix_df = df_danhmuc[(df_danhmuc['category'] == phan_loai) & (df_danhmuc['type'] == chon_loai)]
    prefix = str(prefix_df['prefix'].values[0]).strip() if not prefix_df.empty else "xx"

# NÚT LƯU DỮ LIỆU
submit = st.button("Lưu Giao Dịch", type="primary", use_container_width=True)

if submit:
    if so_tien == 0:
        st.warning("⚠️ Vui lòng nhập số tiền khác 0!")
    elif chon_loai == "Khác..." and (not noi_dung or not prefix):
        st.warning("⚠️️ Vui lòng nhập đầy đủ Nội dung mới và Mã quy ước!")
    else:
        with st.spinner("Đang xử lý thuật toán ID và lưu dữ liệu..."):
            # Tải dữ liệu hiện tại của sheet Transactions
            df_trans = conn.read(worksheet="Transactions", ttl=0)
            
            # Định dạng ngày để so sánh đếm số thứ tự
            date_str = ngay.strftime("%m/%d/%Y") 
            yymmdd = ngay.strftime("%y%m%d")
            
            # Đếm số lượng giao dịch diễn ra TRONG CÙNG NGÀY để tạo STT
            if "transaction_date" in df_trans.columns:
                same_day_trans = df_trans[df_trans["transaction_date"] == date_str]
                stt = len(same_day_trans) + 1
            else:
                stt = 1
                
            # Ráp công thức ID: tx + [prefix] + [YYMMDD] + [STT]
            new_id = f"tx_{prefix}_{yymmdd}_{stt:02d}"
            
            # Tạo dòng dữ liệu mới
            new_row = pd.DataFrame({
                "id": [new_id],
                "transaction_date": [date_str],
                "type": [noi_dung],
                "category": [phan_loai],
                "amount": [so_tien],
                "note": [""]
            })
            
            # Đẩy lên Sheets
            updated_df = pd.concat([df_trans, new_row], ignore_index=True)
            conn.update(worksheet="Transactions", data=updated_df)
            
            st.toast(f"✅ Đã lưu thành công ID: {new_id}", icon="🎉")
            st.rerun() # Tải lại trang để cập nhật Bảng điều khiển
