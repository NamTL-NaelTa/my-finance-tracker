import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import gspread
import time

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")
st.title("💰 Quản Lý Dòng Tiền")

# Khởi tạo bộ đếm để reset form mượt mà
if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

# Kết nối Google Sheets
conn = st.connection("gsheets", type=GSheetsConnection)

# Hàm đọc dữ liệu có lớp bảo vệ chống sập (Rate Limit Protection)
def safe_read_sheet(worksheet_name, ttl=600):
    try:
        return conn.read(worksheet=worksheet_name, ttl=ttl)
    except Exception as e:
        return None

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
        try:
            gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
            sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
            worksheet = sh.worksheet("Dashboard")
            worksheet.update_acell("B1", ngay_bao_cao.strftime("%m/%d/%Y"))
            st.cache_data.clear()
            st.rerun() 
        except Exception as e:
            st.error("⚠️ Google Sheets đang xử lý quá nhiều yêu cầu. Vui lòng đợi 30 giây rồi thử lại!")

# Đọc dữ liệu Dashboard
dashboard_data = safe_read_sheet("Dashboard", ttl=600) 

def format_currency_intl(val):
    try:
        return f"{int(float(val)):,}"
    except (ValueError, TypeError):
        return val

if dashboard_data is not None:
    if len(dashboard_data.columns) > 1:
        col_name = dashboard_data.columns[1]
        dashboard_data[col_name] = dashboard_data[col_name].apply(format_currency_intl)
    st.dataframe(dashboard_data, hide_index=True, use_container_width=True)
else:
    st.warning("⏳ Hệ thống đang quá tải yêu cầu từ Google. Vui lòng nhấn F5 tải lại trang sau 1 phút.")

# ==========================================
# PHẦN 2: KHU VỰC LÀM VIỆC CHUYÊN SÂU (TABS)
# ==========================================
st.divider()

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
    
    df_danhmuc = safe_read_sheet("Danh_muc", ttl=600)
    
    if df_danhmuc is not None and not df_danhmuc.empty:
        df_danhmuc = df_danhmuc.dropna(how="all")
        list_categories = df_danhmuc['category'].dropna().unique().tolist()
        
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
                    df_trans = safe_read_sheet("Transactions", ttl=600)
                    if df_trans is not None:
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
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("⚠️ Quá tải kết nối, chưa thể lưu. Vui lòng thử lại sau 30 giây!")
    else:
        st.info("Đang tải dữ liệu danh mục hoặc hệ thống quá tải. Vui lòng F5 sau ít phút...")

# -----------------------------------
# TAB 2: THU NHẬP
# -----------------------------------
with tab_income:
    st.subheader("💵 Ghi nhận thu nhập mới")
    
    default_incomes = {
        "Lương chính": ["Lương kỳ 1", "Lương kỳ 2"],
        "Thưởng": ["Lương tháng 13", "KPIs"],
        "Vốn mang sang": ["Tồn tiền kỳ trước"],
        "Lãi tiết kiệm": []
    }
    
    df_inc_read = safe_read_sheet("Incomes", ttl=600)
    if df_inc_read is None:
        df_inc_read = pd.DataFrame(columns=["id", "income_source", "category", "amount", "received_date"])
    else:
        df_inc_read = df_inc_read.dropna(how="all")
        
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
                try:
                    conn.update(worksheet="Incomes", data=updated_inc_df)
                    st.session_state.form_reset_key += 1
                    st.toast(f"✅ Đã lưu thành công ID: {new_inc_id}", icon="🎉")
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.error("⚠️ Quá tải kết nối, chưa thể lưu. Vui lòng thử lại sau 30 giây!")

# -----------------------------------
# TAB 3: CHI PHÍ CỐ ĐỊNH
# -----------------------------------
with tab_fixed:
    st.subheader("🏢 Quản lý Chi phí cố định (Base)")
    st.markdown("💡 **Mẹo:** Cột `amount` (số tiền thực thu) và `trang_thai` được **tính toán hoàn toàn tự động** dựa trên Ngày báo cáo bạn chọn. Bạn chỉ cần điền `base_amount`, `start_date` và `end_date`.")
    
    df_fixed = safe_read_sheet("Fixed_Expenses_Base", ttl=600)
    
    if df_fixed is not None:
        tong_chi_phi = 0
        if not df_fixed.empty:
            # 1. Ép kiểu cột ngày về dạng datetime để so sánh
            df_fixed['start_date_dt'] = pd.to_datetime(df_fixed['start_date'], errors='coerce')
            df_fixed['end_date_dt'] = pd.to_datetime(df_fixed['end_date'], errors='coerce')
            report_date = pd.to_datetime(ngay_bao_cao)
            
            # 2. Xây dựng logic tự động cập nhật Trạng thái
            def check_status(row):
                if pd.notna(row['end_date_dt']) and report_date > row['end_date_dt']:
                    return "Đã kết thúc"
                elif pd.notna(row['start_date_dt']) and report_date < row['start_date_dt']:
                    return "Chưa bắt đầu"
                else:
                    return "Đang hoạt động"
            
            df_fixed['trang_thai'] = df_fixed.apply(check_status, axis=1)
            
            # 3. Tính toán số tiền thực tế (amount)
            if "base_amount" in df_fixed.columns:
                df_fixed["base_amount"] = pd.to_numeric(df_fixed["base_amount"], errors="coerce").fillna(0)
                # Nếu đang hoạt động thì tính tiền, ngược lại thì bằng 0
                df_fixed['amount'] = df_fixed.apply(lambda x: x['base_amount'] if x['trang_thai'] == 'Đang hoạt động' else 0, axis=1)
                tong_chi_phi = df_fixed['amount'].sum()
                
            # Xóa các cột datetime tạm sau khi tính xong
            df_fixed = df_fixed.drop(columns=['start_date_dt', 'end_date_dt'])
        
        # 4. Hiển thị tổng chi phí theo ngày chốt sổ
        st.metric(
            label=f"TỔNG CHI PHÍ DUY TRÌ TÍNH ĐẾN ({ngay_bao_cao.strftime('%d/%m/%Y')})", 
            value=f"{int(tong_chi_phi):,} VND"
        )
        st.divider() 
        
        # 5. Khóa 2 cột tính toán tự động không cho sửa tay
        edited_df_fixed = st.data_editor(
            df_fixed,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="editor_fixed",
            disabled=["amount", "trang_thai"] 
        )
        
        submit_fixed = st.button("💾 Lưu Bảng Chi Phí Cố Định", type="primary", use_container_width=True)
        
        if submit_fixed:
            with st.spinner("Đang đồng bộ dữ liệu lên Google Sheets..."):
                try:
                    conn.update(worksheet="Fixed_Expenses_Base", data=edited_df_fixed)
                    st.toast("✅ Đã cập nhật thành công cấu trúc chi phí cố định!", icon="🎉")
                    st.cache_data.clear()
                    st.rerun()
                except Exception:
                    st.error("⚠️ Lỗi mạng hoặc quá tải API. Vui lòng nhấn Lưu lại sau 30 giây!")
    else:
        st.info("⏳ Đang đợi kết nối từ Google Sheets...")

# -----------------------------------
# TAB 4: ĐIỀU CHỈNH
# -----------------------------------
with tab_adj:
    st.subheader("⚖️ Lịch sử điều chỉnh ngân sách")
    st.info("Bảng ghi nhận các khoản phụ thu/giảm trừ vào ngân sách cố định hàng tháng.")
    df_adj = safe_read_sheet("Expense_Adjustments", ttl=600)
    
    if df_adj is not None:
        st.dataframe(df_adj, hide_index=True, use_container_width=True)
    else:
        st.info("⏳ Đang đợi kết nối từ Google Sheets...")
