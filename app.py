import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime
import gspread
import time

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")
st.title("💰 Quản Lý Dòng Tiền")

if "form_reset_key" not in st.session_state:
    st.session_state.form_reset_key = 0

conn = st.connection("gsheets", type=GSheetsConnection)

def safe_read_sheet(worksheet_name, ttl=600):
    try:
        return conn.read(worksheet=worksheet_name, ttl=ttl)
    except Exception as e:
        return None

# ==========================================
# PHẦN 1: BẢNG ĐIỀU KHIỂN
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
    with st.spinner("Đang đồng bộ mốc thời gian và tính toán lại dữ liệu..."):
        try:
            gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
            sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
            worksheet = sh.worksheet("Dashboard")
            worksheet.update("B1", [[ngay_bao_cao.strftime("%Y-%m-%d")]], value_input_option='USER_ENTERED')
            st.cache_data.clear()
            st.rerun() 
        except Exception as e:
            st.error(f"⚠️ Lỗi cập nhật ô B1: {e}")

dashboard_data = safe_read_sheet("Dashboard", ttl=600) 

if dashboard_data is not None:
    # Áp dụng column_config để định dạng quốc tế cột số 2 của Dashboard
    if len(dashboard_data.columns) > 1:
        col_name = dashboard_data.columns[1]
        st.dataframe(
            dashboard_data, 
            hide_index=True, 
            use_container_width=True,
            column_config={
                col_name: st.column_config.NumberColumn(format="%,.0f")
            }
        )
    else:
        st.dataframe(dashboard_data, hide_index=True, use_container_width=True)
else:
    st.warning("⏳ Hệ thống đang quá tải yêu cầu từ Google. Vui lòng nhấn F5 tải lại trang sau 1 phút.")

# ==========================================
# PHẦN 2: KHU VỰC LÀM VIỆC CHUYÊN SÂU
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
        
        st.divider()
        st.write("🕒 **5 Giao dịch gần nhất**")
        df_trans_history = safe_read_sheet("Transactions", ttl=600)
        if df_trans_history is not None and not df_trans_history.empty:
            last_5_trans = df_trans_history.tail(5).iloc[::-1]
            st.dataframe(
                last_5_trans, 
                hide_index=True, 
                use_container_width=True,
                column_config={"amount": st.column_config.NumberColumn("Số tiền", format="%,.0f")}
            )
        else:
            st.info("Chưa có dữ liệu hoặc đang tải...")
            
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
                    
    st.divider()
    st.write("🕒 **5 Khoản thu gần nhất**")
    if not df_inc_read.empty:
        last_5_inc = df_inc_read.tail(5).iloc[::-1]
        st.dataframe(
            last_5_inc, 
            hide_index=True, 
            use_container_width=True,
            column_config={"amount": st.column_config.NumberColumn("Số tiền", format="%,.0f")}
        )
    else:
        st.info("Chưa có dữ liệu hoặc đang tải...")

# -----------------------------------
# TAB 3: CHI PHÍ CỐ ĐỊNH
# -----------------------------------
with tab_fixed:
    st.subheader("🏢 Quản lý Chi phí cố định (Base)")
    st.markdown("💡 **Mẹo:** Các cột `thuc_tra_hien_tai` và `trang_thai` được **tính toán tự động 100% bằng công thức trên Google Sheets** dựa vào mốc Ngày chọn báo cáo. Bạn có thể chỉnh sửa các tham số gốc trực tiếp tại đây.")
    
    df_fixed = safe_read_sheet("Fixed_Expenses_Base", ttl=600)
    
    if df_fixed is not None:
        tong_chi_phi = 0
        
        if not df_fixed.empty and "thuc_tra_hien_tai" in df_fixed.columns:
            df_fixed["thuc_tra_hien_tai"] = pd.to_numeric(df_fixed["thuc_tra_hien_tai"], errors="coerce").fillna(0)
            tong_chi_phi = df_fixed["thuc_tra_hien_tai"].sum()
            
        st.metric(
            label="TỔNG THỰC TRẢ THEO NGÀY BÁO CÁO (Đồng bộ từ Google Sheets)", 
            value=f"{int(tong_chi_phi):,} VND"
        )
        st.divider() 
        
        editable_cols = ["id", "name", "base_amount", "start_date", "end_date", "chu_ky", "thang_thu_ti", "ngay_thanh_t"]
        existing_cols = [col for col in editable_cols if col in df_fixed.columns]
        df_editable = df_fixed[existing_cols]
        
        edited_df_fixed = st.data_editor(
            df_editable,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="editor_fixed",
            column_config={
                "base_amount": st.column_config.NumberColumn("base_amount", format="%,.0f")
            }
        )
        
        submit_fixed = st.button("💾 Lưu Bảng Chi Phí Cố Định", type="primary", use_container_width=True)
        
        if submit_fixed:
            with st.spinner("Đang đồng bộ dữ liệu lên Google Sheets..."):
                try:
                    for col in existing_cols:
                        if len(edited_df_fixed) > len(df_fixed):
                            diff = len(edited_df_fixed) - len(df_fixed)
                            empty_rows = pd.DataFrame([{c: "" for c in df_fixed.columns}] * diff)
                            df_fixed = pd.concat([df_fixed, empty_rows], ignore_index=True)
                        elif len(edited_df_fixed) < len(df_fixed):
                            df_fixed = df_fixed.iloc[:len(edited_df_fixed)]
                            
                        df_fixed[col] = edited_df_fixed[col].values
                    
                    cols_to_update = [c for c in df_fixed.columns if c not in ["thuc_tra_hien_tai", "trang_thai", "amount"]]
                    df_to_push = df_fixed[cols_to_update]
                    
                    conn.update(worksheet="Fixed_Expenses_Base", data=df_to_push)
                    
                    st.toast("✅ Đã cập nhật tham số gốc lên Sheets!", icon="🎉")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"⚠️ Lỗi: {e}")
    else:
        st.info("⏳ Đang đợi kết nối từ Google Sheets...")

# -----------------------------------
# TAB 4: ĐIỀU CHỈNH
# -----------------------------------
with tab_adj:
    st.subheader("⚖️️ Lịch sử điều chỉnh ngân sách")
    st.info("Bảng ghi nhận các khoản phụ thu/giảm trừ vào ngân sách cố định hàng tháng.")
    df_adj = safe_read_sheet("Expense_Adjustments", ttl=600)
    
    if df_adj is not None:
        st.dataframe(
            df_adj, 
            hide_index=True, 
            use_container_width=True,
            column_config={"amount": st.column_config.NumberColumn(format="%,.0f")}
        )
    else:
        st.info("⏳ Đang đợi kết nối từ Google Sheets...")
