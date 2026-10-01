import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")
st.title("💰 Quản Lý Dòng Tiền")

# Kết nối Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# --- PHẦN 1: BẢNG ĐIỀU KHIỂN (READ & FORMAT) ---
st.subheader("📊 Trạng thái hiện tại")
dashboard_data = conn.read(worksheet="Dashboard", ttl=0) 

# Hàm định dạng số có dấu phẩy phân cách hàng ngàn (Chuẩn quốc tế)
def format_currency_intl(val):
    try:
        # Dùng định dạng mặc định của Python: f"{...:,}" sẽ tự chèn dấu phẩy
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return val # Nếu ô trống hoặc là chữ thì giữ nguyên

# Tự động tìm cột thứ 2 (chứa số liệu) để áp dụng định dạng
if len(dashboard_data.columns) > 1:
    col_name = dashboard_data.columns[1]
    dashboard_data[col_name] = dashboard_data[col_name].apply(format_currency_intl)

st.dataframe(dashboard_data, hide_index=True, use_container_width=True)

st.divider()

# --- ĐỌC SHEET DANH MỤC (MASTER DATA) ---
try:
    df_danhmuc = conn.read(worksheet="Danh_muc", ttl=0).dropna(how="all")
    list_categories = df_danhmuc['category'].dropna().unique().tolist()
except Exception as e:
    st.error("⚠️ Lỗi: Không tìm thấy sheet 'Danh_muc' hoặc dữ liệu trống.")
    st.stop()

# --- PHẦN 2: LUỒNG NHẬP LIỆU THÔNG MINH (WRITE) ---
st.subheader("📝 Nhập giao dịch mới")

col1, col2 = st.columns(2)

with col1:
    ngay = st.date_input("Ngày giao dịch")
    # Gắn key để quản lý trạng thái reset
    so_tien = st.number_input("Số tiền (Nhập số ÂM nếu chi tiền)", value=0, step=1000, key="val_amount")

with col2:
    phan_loai = st.selectbox("Nhóm chi tiêu (Category)", list_categories)
    
    filtered_types = df_danhmuc[df_danhmuc['category'] == phan_loai]['type'].dropna().tolist()
    filtered_types.append("Khác...")
    chon_loai = st.selectbox("Khoản chi tiết (Type)", filtered_types)

if chon_loai == "Khác...":
    col3, col4 = st.columns(2)
    with col3:
        noi_dung = st.text_input("Nhập nội dung mới (VD: Khám răng)", key="val_noidung")
    with col4:
        prefix = st.text_input("Nhập mã quy ước ngắn (VD: kr)", key="val_prefix")
else:
    noi_dung = chon_loai
    prefix_df = df_danhmuc[(df_danhmuc['category'] == phan_loai) & (df_danhmuc['type'] == chon_loai)]
    prefix = str(prefix_df['prefix'].values[0]).strip() if not prefix_df.empty else "xx"

# NÚT LƯU DỮ LIỆU
submit = st.button("Lưu Giao Dịch", type="primary", use_container_width=True)

if submit:
    if so_tien == 0:
        st.warning("⚠️ Vui lòng nhập số tiền khác 0!")
    elif chon_loai == "Khác..." and (not noi_dung or not prefix):
        st.warning("⚠ Vui lòng nhập đầy đủ Nội dung mới và Mã quy ước!")
    else:
        with st.spinner("Đang xử lý thuật toán ID và lưu dữ liệu..."):
            df_trans = conn.read(worksheet="Transactions", ttl=0)
            
            date_str = ngay.strftime("%m/%d/%Y") 
            yymmdd = ngay.strftime("%y%m%d")
            
            if "transaction_date" in df_trans.columns:
                same_day_trans = df_trans[df_trans["transaction_date"] == date_str]
                stt = len(same_day_trans) + 1
            else:
                stt = 1
                
            new_id = f"tx_{prefix}_{yymmdd}_{stt:02d}"
            
            new_row = pd.DataFrame({
                "id": [new_id],
                "transaction_date": [date_str],
                "type": [noi_dung],
                "category": [phan_loai],
                "amount": [so_tien],
                "note": [""]
            })
            
            updated_df = pd.concat([df_trans, new_row], ignore_index=True)
            conn.update(worksheet="Transactions", data=updated_df)
            
            # --- CLEAR TRẠNG THÁI Ô NHẬP LIỆU ---
            st.session_state.val_amount = 0
            if "val_noidung" in st.session_state:
                st.session_state.val_noidung = ""
            if "val_prefix" in st.session_state:
                st.session_state.val_prefix = ""
                
            st.toast(f"✅ Đã lưu thành công ID: {new_id}", icon="🎉")
            st.rerun()
