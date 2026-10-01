import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import gspread

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")
st.title("💰 Quản Lý Dòng Tiền")

# Khởi tạo bộ đếm để reset form mượt mà
if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

# Kết nối Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# ==========================================
# PHẦN 1: BẢNG ĐIỀU KHIỂN (LUÔN HIỂN THỊ)
# ==========================================
st.subheader("📊 Trạng thái hiện tại")

col_date, col_btn = st.columns([3, 1])
with col_date:
    ngay_bao_cao = st.date_input("📅 Chọn Tháng Báo Cáo (Ngày chốt sổ)", format="DD/MM/YYYY")
with col_btn:
    st.write("") 
    st.write("")
    cap_nhat_btn = st.button("Cập nhật số liệu", type="secondary", use_container_width=True)

if cap_nhat_btn:
    with st.spinner("Đang tính toán lại dữ liệu..."):
        gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
        sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = sh.worksheet("Dashboard")
        worksheet.update_acell("B1", ngay_bao_cao.strftime("%m/%d/%Y"))
        st.rerun() 

dashboard_data = conn.read(worksheet="Dashboard", ttl=0) 

def format_currency_intl(val):
    try:
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return val

if len(dashboard_data.columns) > 1:
    col_name = dashboard_data.columns[1]
    dashboard_data[col_name] = dashboard_data[col_name].apply(format_currency_intl)

st.dataframe(dashboard_data, hide_index=True, use_container_width=True)

# ==========================================
# PHẦN 2: KHU VỰC LÀM VIỆC CHUYÊN SÂU (TABS)
# ==========================================
st.divider()

# Khởi tạo 4 thẻ điều hướng
tab_trans, tab_income, tab_fixed, tab_adj = st.tabs([
    "🛒 Giao dịch", 
    "💰 Thu nhập", 
    "🔒 Chi phí cố định", 
    "⚙ Điều chỉnh"
])

# -----------------------------------
# TAB 1: GIAO DỊCH HÀNG NGÀY
# -----------------------------------
with tab_trans:
    st.subheader("📝 Nhập giao dịch mới")
    
    try:
        df_danhmuc = conn.read(worksheet="Danh_muc", ttl=0).dropna(how="all")
        list_categories = df_danhmuc['category'].dropna().unique().tolist()
    except Exception as e:
        st.error("⚠ Lỗi: Không tìm thấy sheet 'Danh_muc' hoặc dữ liệu trống.")
        st.stop()

    col1, col2 = st.columns(2)

    with col1:
        ngay = st.date_input("Ngày giao dịch")
        so_tien = st.number_input("Số tiền (Nhập số ÂM nếu chi tiền)", value=0, step=1000, key=f"amount_{st.session_state.form_reset_key}")

    with col2:
        phan_loai = st.selectbox("Nhóm chi tiêu (Category)", list_categories)
        filtered_types = df_danhmuc[df_danhmuc['category'] == phan_loai]['type'].dropna().tolist()
        filtered_types.append("Khác...")
        chon_loai = st.selectbox("Khoản chi tiết (Type)", filtered_types)

    if chon_loai == "Khác...":
        col3, col4 = st.columns(2)
        with col3:
            noi_dung = st.text_input("Nhập nội dung mới (VD: Khám răng)", key=f"noidung_{st.session_state.form_reset_key}")
        with col4:
            prefix = st.text_input("Nhập mã quy ước ngắn (VD: kr)", key=f"prefix_{st.session_state.form_reset_key}")
    else:
        noi_dung = chon_loai
        prefix_df = df_danhmuc[(df_danhmuc['category'] == phan_loai) & (df_danhmuc['type'] == chon_loai)]
        prefix = str(prefix_df['prefix'].values[0]).strip() if not prefix_df.empty else "xx"

    submit_trans = st.button("Lưu Giao Dịch", type="primary", use_container_width=True)

    if submit_trans:
        if so_tien == 0:
            st.warning("⚠️ Vui lòng nhập số tiền khác 0!")
        elif chon_loai == "Khác..." and (not noi_dung or not prefix):
            st.warning("⚠ Vui lòng nhập đầy đủ Nội dung mới và Mã quy ước!")
        else:
            with st.spinner("Đang lưu dữ liệu..."):
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
                
                st.session_state.form_reset_key += 1
                st.toast(f"✅ Đã lưu thành công ID: {new_id}", icon="🎉")
                st.rerun()

# -----------------------------------
# TAB 2: THU NHẬP
# -----------------------------------
with tab_income:
    st.subheader("💵 Ghi nhận thu nhập mới")
    
    # 1. TỪ ĐIỂN MẶC ĐỊNH CHO THU NHẬP
    default_incomes = {
        "Lương chính": ["Lương kỳ 1", "Lương kỳ 2"],
        "Thưởng": ["Lương tháng 13", "KPIs"],
        "Vốn mang sang": ["Tồn tiền kỳ trước"],
        "Lãi tiết kiệm": []
    }
    
    # Kéo dữ liệu từ sheet Incomes để bổ sung thêm nếu có phát sinh mới
    try:
        df_inc_read = conn.read(worksheet="Incomes", ttl=0).dropna(how="all")
    except Exception:
        df_inc_read = pd.DataFrame(columns=["id", "income_source", "category", "amount", "received_date"])
        
    # Gộp danh mục mặc định và danh mục trên sheet
    list_inc_categories = list(default_incomes.keys())
    if not df_inc_read.empty and 'category' in df_inc_read.columns:
        sheet_cats = df_inc_read['category'].dropna().unique().tolist()
        for cat in sheet_cats:
            if cat not in list_inc_categories:
                list_inc_categories.append(cat)
    
    col_inc1, col_inc2 = st.columns(2)
    with col_inc1:
        ngay_thu = st.date_input("Ngày nhận tiền", key=f"inc_date_{st.session_state.form_reset_key}")
        so_tien_thu = st.number_input("Số tiền thu (VD: 5000000)", min_value=0, value=0, step=100000, key=f"inc_amount_{st.session_state.form_reset_key}")
        
    with col_inc2:
        loai_thu_nhap = st.selectbox("Nhóm thu nhập (Category)", list_inc_categories, key=f"inc_cat_{st.session_state.form_reset_key}")
        
        # Gộp nguồn thu mặc định và nguồn thu đã có trên sheet theo Category
        filtered_sources = default_incomes.get(loai_thu_nhap, []).copy()
        if not df_inc_read.empty and 'category' in df_inc_read.columns and 'income_source' in df_inc_read.columns:
            sheet_sources = df_inc_read[df_inc_read['category'] == loai_thu_nhap]['income_source'].dropna().unique().tolist()
            for src in sheet_sources:
                if src not in filtered_sources:
                    filtered_sources.append(src)
            
        filtered_sources.append("Khác...")
        chon_nguon_thu = st.selectbox("Nguồn thu (Income Source)", filtered_sources, key=f"inc_source_sel_{st.session_state.form_reset_key}")
        
    if chon_nguon_thu == "Khác...":
        nguon_thu = st.text_input("Nhập nguồn thu mới (VD: Bán đồ cũ)", key=f"inc_source_new_{st.session_state.form_reset_key}")
    else:
        nguon_thu = chon_nguon_thu
        
    submit_inc = st.button("Lưu Thu Nhập", type="primary", use_container_width=True, key="btn_inc")
    
    if submit_inc:
        if so_tien_thu == 0:
            st.warning("⚠️ Vui lòng nhập số tiền lớn hơn 0!")
        elif not nguon_thu:
            st.warning("⚠️ Vui lòng nhập nguồn thu!")
        else:
            with st.spinner("Đang lưu dữ liệu..."):
                date_str = ngay_thu.strftime("%m/%d/%Y")
                yymmdd = ngay_thu.strftime("%y%m%d")
                
                if "received_date" in df_inc_read.columns:
                    same_day_inc = df_inc_read[df_inc_read["received_date"] == date_str]
                    stt = len(same_day_inc) + 1
                else:
                    stt = 1
                    
                new_inc_id = f"inc_{yymmdd}_{stt:02d}"
                
                new_inc_row = pd.DataFrame({
                    "id": [new_inc_id],
                    "income_source": [nguon_thu],
                    "category": [loai_thu_nhap],
                    "amount": [so_tien_thu],
                    "received_date": [date_str]
                })
                
                updated_inc_df = pd.concat([df_inc_read, new_inc_row], ignore_index=True)
                conn.update(worksheet="Incomes", data=updated_inc_df)
                
                st.session_state.form_reset_key += 1
                st.toast(f"✅ Đã lưu thành công ID: {new_inc_id}", icon="🎉")
                st.rerun()

# -----------------------------------
# TAB 3: CHI PHÍ CỐ ĐỊNH
# -----------------------------------
with tab_fixed:
    st.subheader("🏢 Quản lý Chi phí cố định (Base)")
    st.markdown("Khu vực này hoạt động như một bảng Excel thu nhỏ. Bạn có thể **click đúp vào ô bất kỳ để sửa**, chọn dòng nhấn nút `Delete` để xóa, hoặc cuộn xuống cuối bảng để thêm gói cước mới.")
    
    # Kéo dữ liệu từ sheet
    df_fixed = conn.read(worksheet="Fixed_Expenses_Base", ttl=0)
    
    # Bật tính năng Data Editor siêu việt của Streamlit
    edited_df_fixed = st.data_editor(
        df_fixed,
        num_rows="dynamic", # Chìa khóa cho phép thêm/xóa dòng tự do
        use_container_width=True,
        hide_index=True,
        key="editor_fixed"
    )
    
    # Nút lưu đồng bộ một lần
    submit_fixed = st.button("💾 Lưu Bảng Chi Phí Cố Định", type="primary", use_container_width=True)
    
    if submit_fixed:
        with st.spinner("Đang đồng bộ dữ liệu lên Google Sheets..."):
            # Ghi đè toàn bộ bảng đã chỉnh sửa lên file gốc
            conn.update(worksheet="Fixed_Expenses_Base", data=edited_df_fixed)
            st.toast("✅ Đã cập nhật thành công cấu trúc chi phí cố định!", icon="🎉")
            st.rerun()
# -----------------------------------
# TAB 4: ĐIỀU CHỈNH
# -----------------------------------
with tab_adj:
    st.subheader("⚖️ Lịch sử điều chỉnh ngân sách")
    st.info("Bảng ghi nhận các khoản phụ thu/giảm trừ vào ngân sách cố định hàng tháng.")
    df_adj = conn.read(worksheet="Expense_Adjustments", ttl=0)
    st.dataframe(df_adj, hide_index=True, use_container_width=True)
