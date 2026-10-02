import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
from datetime import datetime, date
import gspread
import time
import plotly.graph_objects as go
import calendar

# Cấu hình giao diện web
st.set_page_config(page_title="Quản Lý Dòng Tiền", page_icon="💰", layout="centered")

# ==========================================
# BẢO MẬT: MÀN HÌNH ĐĂNG NHẬP
# ==========================================
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

if not st.session_state.authenticated:
    st.title("🔒 Xác thực bảo mật")
    st.markdown("Vui lòng nhập mật khẩu để truy cập ứng dụng quản lý tài chính cá nhân.")
    
    password_input = st.text_input("Mật khẩu truy cập", type="password")
    if st.button("Đăng nhập", type="primary", use_container_width=True):
        correct_password = st.secrets.get("passwords", {}).get("app_password", "123456")
        if password_input == correct_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("⚠️ Mật khẩu không chính xác. Vui lòng thử lại!")
    st.stop()

# ==========================================
# THANH CÔNG CỤ & PRIVACY MODE
# ==========================================
with st.sidebar:
    st.markdown("### ⚙️ Cài đặt hệ thống")
    privacy_mode = st.toggle("👁️ Chế độ riêng tư (Ẩn số tiền)", value=False)
    if st.button("Đăng xuất", type="secondary"):
        st.session_state.authenticated = False
        st.rerun()

def mask_money(amount):
    if privacy_mode:
        return "🔒 *** ₫"
    try:
        return f"{int(amount):,} ₫"
    except:
        return f"{amount:,} ₫" if isinstance(amount, (int, float)) else str(amount)

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
# HÀM PYTHON TÍNH TOÁN CỐ ĐỊNH CHUẨN XÁC
# ==========================================
def calculate_fixed_expenses(df_fixed, df_adj, report_date):
    if df_fixed is None or df_fixed.empty:
        return df_fixed
    
    rep_dt = pd.to_datetime(report_date)
    rep_year = rep_dt.year
    rep_month = rep_dt.month
    rep_day = rep_dt.day
    report_mm_yyyy = rep_dt.strftime("%m/%Y")

    thuc_tra_list = []
    trang_thai_list = []

    for idx, row in df_fixed.iterrows():
        base_amt = pd.to_numeric(row.get("base_amount", 0), errors="coerce")
        if pd.isna(base_amt): base_amt = 0

        ngay_thanh_t = row.get("ngay_thanh_toan")
        start_date = pd.to_datetime(row.get("start_date"), errors="coerce")
        end_date = pd.to_datetime(row.get("end_date"), errors="coerce")
        chu_ky = str(row.get("chu_ky", "")).strip()
        thang_thu_ti = pd.to_numeric(row.get("thang_thu_tien"), errors="coerce")
        item_id = str(row.get("id", "")).strip()

        today_dt = pd.to_datetime(date.today())
        if pd.isna(end_date) or end_date >= today_dt:
            trang_thai = "Đang hoạt động"
        else:
            trang_thai = "Đã kết thúc"
        trang_thai_list.append(trang_thai)

        try:
            j_val = int(ngay_thanh_t) if not pd.isna(ngay_thanh_t) else None
        except:
            j_val = None

        condition_met = False
        if j_val is not None:
            last_day_of_month = calendar.monthrange(rep_year, rep_month)[1]
            actual_pay_day = min(j_val, last_day_of_month)
            
            if rep_day >= actual_pay_day:
                try:
                    pay_date = datetime(rep_year, rep_month, actual_pay_day)
                    pay_pd = pd.to_datetime(pay_date)
                    
                    start_ok = pd.isna(start_date) or (pay_pd >= start_date)
                    end_ok = pd.isna(end_date) or (pay_pd <= end_date)
                    
                    if chu_ky == "Hằng tháng":
                        cycle_ok = True
                    elif chu_ky == "Hằng năm":
                        cycle_ok = (not pd.isna(thang_thu_ti)) and (int(thang_thu_ti) == rep_month)
                    else:
                        cycle_ok = True

                    if start_ok and end_ok and cycle_ok:
                        condition_met = True
                except:
                    pass

        final_amount = 0
        if condition_met:
            final_amount = base_amt
            if df_adj is not None and not df_adj.empty:
                for _, adj_row in df_adj.iterrows():
                    adj_id = str(adj_row.get("id", "")).strip()
                    adj_date = str(adj_row.get("date", "")).strip()
                    adj_amt = pd.to_numeric(adj_row.get("amount", 0), errors="coerce")
                    if pd.isna(adj_amt): adj_amt = 0

                    if adj_id == item_id and adj_date == report_mm_yyyy:
                        final_amount += adj_amt

        thuc_tra_list.append(final_amount)

    df_fixed["thuc_tra_hien_tai"] = thuc_tra_list
    df_fixed["trang_thai"] = trang_thai_list
    return df_fixed


# ==========================================
# GIAO DIỆN CHỌN NGÀY & NÚT CẬP NHẬT
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
    with st.spinner("Đang tính toán lại và đồng bộ toàn bộ dữ liệu lên Google Sheets..."):
        try:
            # 1. Cập nhật ngày chốt sổ vào ô B1 của Dashboard
            gc = gspread.service_account_from_dict(st.secrets["connections"]["gsheets"])
            sh = gc.open_by_url(st.secrets["connections"]["gsheets"]["spreadsheet"])
            worksheet = sh.worksheet("Dashboard")
            worksheet.update("B1", [[ngay_bao_cao.strftime("%Y-%m-%d")]], value_input_option='USER_ENTERED')
            
            # 2. Tự động tính toán lại Chi phí cố định và ĐỒNG BỘ NGƯỢC về Google Sheets
            df_fixed_temp = conn.read(worksheet="Fixed_Expenses_Base", ttl=0)
            df_adj_temp = conn.read(worksheet="Expense_Adjustments", ttl=0)
            
            if df_fixed_temp is not None and not df_fixed_temp.empty:
                df_fixed_updated = calculate_fixed_expenses(df_fixed_temp.copy(), df_adj_temp, ngay_bao_cao)
                df_fixed_updated = df_fixed_updated.dropna(how="all")
                conn.update(worksheet="Fixed_Expenses_Base", data=df_fixed_updated)
                
        except Exception as e:
            st.error(f"⚠️ Có lỗi khi đồng bộ lên Sheets: {e}")
            
        st.cache_data.clear()
        st.rerun()

# ==========================================
# TRÁI TIM ỨNG DỤNG (DATA ENGINE HYBRID)
# ==========================================
with st.spinner("Đang kết nối cơ sở dữ liệu..."):
    dashboard_raw = safe_read_sheet("Dashboard", ttl=600)
    df_trans_raw = safe_read_sheet("Transactions", ttl=600)
    df_inc_raw = safe_read_sheet("Incomes", ttl=600)
    df_fixed_raw = safe_read_sheet("Fixed_Expenses_Base", ttl=600)
    df_adj_raw = safe_read_sheet("Expense_Adjustments", ttl=600)
    df_danhmuc_raw = safe_read_sheet("Danh_muc", ttl=600)

if dashboard_raw is not None and df_trans_raw is not None and df_fixed_raw is not None:
    
    # 1. TÍNH TOÁN CHI PHÍ CỐ ĐỊNH CHÍNH XÁC BẰNG PYTHON
    df_fixed_computed = calculate_fixed_expenses(df_fixed_raw.copy(), df_adj_raw, ngay_bao_cao)
    chi_co_dinh = df_fixed_computed["thuc_tra_hien_tai"].sum() if not df_fixed_computed.empty else 0

    # 2. XỬ LÝ DASHBOARD HYBRID (KẾT HỢP GOOGLE SHEETS + PYTHON)
    if not dashboard_raw.empty and len(dashboard_raw.columns) > 1:
        col_name = dashboard_raw.columns[1]
        
        # Chuyển đổi dữ liệu chuỗi có dấu phẩy thành số thực để tính toán
        for idx, row in dashboard_raw.iterrows():
            try:
                val_str = str(row[col_name]).replace(',', '').strip()
                if val_str:
                    dashboard_raw.at[idx, col_name] = float(val_str)
            except:
                pass
        
        # Tiêm số chi cố định chuẩn của Python vào Bảng
        idx_fixed = dashboard_raw[dashboard_raw.iloc[:, 0].astype(str).str.contains("TỔNG CHI CỐ ĐỊNH", na=False, case=False)].index
        if not idx_fixed.empty:
            dashboard_raw.loc[idx_fixed[0], col_name] = chi_co_dinh
            
        # Lấy giá trị Thu Nhập và Đã Tiêu (giữ nguyên công thức từ Google Sheets của bạn)
        try:
            tong_thu = float(dashboard_raw.loc[dashboard_raw.iloc[:, 0].astype(str).str.contains("TỔNG THU NHẬP", na=False, case=False), col_name].values[0])
        except:
            tong_thu = 0
            
        try:
            tong_tieu = float(dashboard_raw.loc[dashboard_raw.iloc[:, 0].astype(str).str.contains("TỔNG ĐÃ TIÊU", na=False, case=False), col_name].values[0])
        except:
            tong_tieu = 0
            
        # Tính toán lại Khoản Dư Hiện Tại
        khoan_du = tong_thu - chi_co_dinh - abs(tong_tieu)
        idx_du = dashboard_raw[dashboard_raw.iloc[:, 0].astype(str).str.contains("KHOẢN DƯ HIỆN TẠI", na=False, case=False)].index
        if not idx_du.empty:
            dashboard_raw.loc[idx_du[0], col_name] = khoan_du

        # Hiển thị bảng Dashboard
        if privacy_mode:
            display_dash = dashboard_raw.copy()
            display_dash[col_name] = "🔒 ***"
            st.dataframe(display_dash, hide_index=True, use_container_width=True)
        else:
            st.dataframe(
                dashboard_raw, 
                hide_index=True, 
                use_container_width=True,
                column_config={
                    col_name: st.column_config.NumberColumn(format="%,.0f")
                }
            )

    # 3. LỌC GIAO DỊCH VÀ THU NHẬP (Dành riêng cho Phân tích Radar)
    report_dt = pd.to_datetime(ngay_bao_cao)
    current_month_str = report_dt.strftime('%m/%Y')
    
    df_trans_ana = df_trans_raw.copy()
    df_inc_ana = df_inc_raw.copy()

    tong_chi_thang = 0
    tong_thu_thang_hien_tai = 0
    trans_current_month = pd.DataFrame()

    if not df_trans_ana.empty:
        # Bỏ format chặt chẽ để Pandas tự nội suy ngày tháng, chống lỗi dữ liệu nhập tay
        df_trans_ana['date'] = pd.to_datetime(df_trans_ana['transaction_date'], errors='coerce')
        df_trans_ana['Tháng'] = df_trans_ana['date'].dt.strftime('%m/%Y')
        df_trans_ana['amount'] = pd.to_numeric(df_trans_ana['amount'], errors='coerce').fillna(0)
        trans_current_month = df_trans_ana[df_trans_ana['Tháng'] == current_month_str].copy()
        tong_chi_thang = abs(trans_current_month['amount'].sum())

    if not df_inc_ana.empty:
        df_inc_ana['date'] = pd.to_datetime(df_inc_ana['received_date'], errors='coerce')
        df_inc_ana['Tháng'] = df_inc_ana['date'].dt.strftime('%m/%Y')
        df_inc_ana['amount'] = pd.to_numeric(df_inc_ana['amount'], errors='coerce').fillna(0)
        inc_current_month = df_inc_ana[df_inc_ana['Tháng'] == current_month_str].copy()
        tong_thu_thang_hien_tai = inc_current_month['amount'].sum()

    # ==========================================
    # KHU VỰC PHÂN TÍCH & DỰ BÁO DÒNG TIỀN
    # ==========================================
    st.divider()
    st.subheader("📈 Phân tích Dữ liệu & Dự báo Dòng tiền")

    tab_overview, tab_detail, tab_action = st.tabs([
        "🌊 Toàn cảnh (Sankey & 50/30/20)", 
        "🔍 Chi tiết & Lịch sử", 
        "⚠️ Cảnh báo & Dự báo"
    ])

    with tab_overview:
        st.markdown(f"**Dòng chảy tài chính & Cơ cấu chi tiêu (Tháng {current_month_str})**")
        col_sankey, col_ratio = st.columns([3, 2])
        
        with col_sankey:
            cat_sums = trans_current_month.groupby('category')['amount'].sum().abs().reset_index()
            
            if tong_thu_thang_hien_tai > 0 and not cat_sums.empty:
                labels = ["Tổng Thu"] + cat_sums['category'].tolist() + ["Chi Cố Định", "Tiết Kiệm/Dư"]
                sources = [0] * (len(cat_sums) + 2)
                targets = list(range(1, len(labels)))
                
                tiet_kiem = tong_thu_thang_hien_tai - tong_chi_thang - chi_co_dinh
                values = cat_sums['amount'].tolist() + [chi_co_dinh, max(0, tiet_kiem)]
                
                fig = go.Figure(data=[go.Sankey(
                    node = dict(pad = 15, thickness = 20, line = dict(color = "black", width = 0.5), label = labels),
                    link = dict(source = sources, target = targets, value = values)
                )])
                fig.update_layout(height=400, margin=dict(l=0, r=0, t=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Chưa đủ dữ liệu Thu/Chi trong tháng này để vẽ biểu đồ dòng chảy.")

        with col_ratio:
            st.markdown("**Định chuẩn sức khỏe tài chính**")
            def classify_need(cat):
                needs_keywords = ['ăn', 'uống', 'đi lại', 'xăng', 'nhà', 'điện', 'nước', 'sức khỏe', 'y tế', 'bảo hiểm']
                return "Thiết yếu (Target: 50%)" if any(k in str(cat).lower() for k in needs_keywords) else "Linh hoạt/Mong muốn (Target: 30%)"
            
            if not trans_current_month.empty:
                trans_current_month['Phân_loại'] = trans_current_month['category'].apply(classify_need)
                ratio_df = trans_current_month.groupby('Phân_loại')['amount'].sum().abs().reset_index()
                
                if chi_co_dinh > 0:
                    if "Thiết yếu (Target: 50%)" in ratio_df['Phân_loại'].values:
                        ratio_df.loc[ratio_df['Phân_loại'] == "Thiết yếu (Target: 50%)", 'amount'] += chi_co_dinh
                    else:
                        ratio_df.loc[len(ratio_df)] = ["Thiết yếu (Target: 50%)", chi_co_dinh]
                
                fig_pie = go.Figure(data=[go.Pie(labels=ratio_df['Phân_loại'], values=ratio_df['amount'], hole=.4)])
                fig_pie.update_layout(height=300, margin=dict(l=0, r=0, t=10, b=10))
                st.plotly_chart(fig_pie, use_container_width=True)

    with tab_detail:
        khoang_thoi_gian = st.selectbox(
            "⏳ Chọn thời gian thống kê (tính từ ngày chốt sổ)",
            ["1 Tháng", "3 Tháng", "6 Tháng", "1 Năm", "Tất cả"]
        )

        if khoang_thoi_gian == "1 Tháng":
            start_date = report_dt - pd.DateOffset(months=1)
        elif khoang_thoi_gian == "3 Tháng":
            start_date = report_dt - pd.DateOffset(months=3)
        elif khoang_thoi_gian == "6 Tháng":
            start_date = report_dt - pd.DateOffset(months=6)
        elif khoang_thoi_gian == "1 Năm":
            start_date = report_dt - pd.DateOffset(years=1)
        else:
            start_date = None

        if start_date is not None:
            mask = (df_trans_ana['date'] >= start_date) & (df_trans_ana['date'] <= report_dt)
            df_filtered = df_trans_ana.loc[mask].copy()
        else:
            df_filtered = df_trans_ana.copy()

        if not df_filtered.empty:
            cat_stats = df_filtered.groupby('category').agg(Số_GD=('id', 'count'), Tổng_tiền=('amount', 'sum')).reset_index()
            cat_stats['Tổng_tiền_hiển_thị'] = cat_stats['Tổng_tiền'].abs()
            
            col_c1, col_c2 = st.columns([3, 2])
            col_c1.bar_chart(cat_stats.sort_values(by='Tổng_tiền_hiển_thị', ascending=False).set_index('category')['Tổng_tiền_hiển_thị'])
            col_c2.dataframe(cat_stats[['category', 'Số_GD', 'Tổng_tiền']], hide_index=True, column_config={"Tổng_tiền": st.column_config.NumberColumn(format="%,.0f")})

            st.markdown("**Ma trận chi tiêu chi tiết theo tháng**")
            pivot_df = df_filtered.pivot_table(index='category', columns='Tháng', values='amount', aggfunc='sum', fill_value=0)
            st.dataframe(pivot_df, use_container_width=True, column_config={c: st.column_config.NumberColumn(format="%,.0f") for c in pivot_df.columns})
        else:
            st.info("Không có dữ liệu trong thời gian này.")

    with tab_action:
        st.markdown("**Radar giám sát Dòng tiền & Dự báo**")
        current_day = report_dt.day
        days_in_month = calendar.monthrange(report_dt.year, report_dt.month)[1]
        
        run_rate_chi_vat = 0
        if current_day > 0:
            run_rate_chi_vat = (tong_chi_thang / current_day) * days_in_month
        
        du_bao_cuoi_thang = tong_thu_thang_hien_tai - run_rate_chi_vat - chi_co_dinh

        col_a1, col_a2 = st.columns(2)
        col_a1.metric("Tốc độ đốt tiền dự kiến (Run Rate)", mask_money(run_rate_chi_vat), delta=f"Chi vặt thực tế {current_day} ngày: {int(tong_chi_thang):,}", delta_color="off")
        col_a2.metric("Dự Báo Tiết Kiệm Cuối Tháng", mask_money(du_bao_cuoi_thang), delta=f"Nếu giữ nguyên tốc độ chi tiêu này", delta_color="normal")
        
        st.divider()
        st.markdown("🚨 **Cảnh báo rò rỉ bất thường**")
        
        past_3_months = [
            (report_dt - pd.DateOffset(months=1)).strftime('%m/%Y'),
            (report_dt - pd.DateOffset(months=2)).strftime('%m/%Y'),
            (report_dt - pd.DateOffset(months=3)).strftime('%m/%Y')
        ]
        
        df_past_3m = df_trans_ana[df_trans_ana['Tháng'].isin(past_3_months)]
        if not df_past_3m.empty and not trans_current_month.empty:
            avg_past_3m = df_past_3m.groupby('category')['amount'].sum().abs() / 3
            curr_month_spent = trans_current_month.groupby('category')['amount'].sum().abs()
            
            anomaly_found = False
            for cat, spent in curr_month_spent.items():
                if cat in avg_past_3m and avg_past_3m[cat] > 0:
                    avg_spent = avg_past_3m[cat]
                    if spent > avg_spent * 1.4 and (spent - avg_spent) > 500000:
                        percent_increase = ((spent - avg_spent) / avg_spent) * 100
                        st.warning(f"⚠️ **{cat}**: Tháng này tiêu {mask_money(spent)} (Tăng **{int(percent_increase)}%** so với trung bình 3 tháng trước).")
                        anomaly_found = True
            
            if not anomaly_found:
                st.success("✅ Tuyệt vời! Chưa phát hiện khoản chi vặt nào tăng đột biến so với 3 tháng qua.")
        else:
            st.info("Hệ thống cần tích lũy thêm dữ liệu các tháng trước để kích hoạt radar phát hiện bất thường.")

    # ==========================================
    # PHẦN 2: KHU VỰC LÀM VIỆC CHUYÊN SÂU
    # ==========================================
    st.divider()

    tab_trans, tab_income, tab_fixed, tab_category = st.tabs([
        "🛒 Giao dịch", 
        "💰 Thu nhập", 
        "🔒 Chi phí cố định",
        "📑 Danh mục"
    ])

    # -----------------------------------
    # TAB 1: GIAO DỊCH HÀNG NGÀY
    # -----------------------------------
    with tab_trans:
        st.subheader("📝 Nhập giao dịch mới")
        df_danhmuc = df_danhmuc_raw.copy() if df_danhmuc_raw is not None else pd.DataFrame()
        
        if not df_danhmuc.empty:
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
                        date_str = ngay.strftime("%m/%d/%Y") 
                        yymmdd = ngay.strftime("%y%m%d")
                        
                        if "transaction_date" in df_trans_raw.columns:
                            same_day_trans = df_trans_raw[df_trans_raw["transaction_date"] == date_str]
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
                        
                        updated_df = pd.concat([df_trans_raw, new_row], ignore_index=True)
                        conn.update(worksheet="Transactions", data=updated_df)
                        
                        st.session_state.form_reset_key += 1
                        st.toast(f"✅ Đã lưu thành công ID: {new_id}", icon="🎉")
                        st.cache_data.clear()
                        st.rerun()
            
            st.divider()
            st.write("🕒 **5 Giao dịch gần nhất**")
            if not df_trans_raw.empty:
                last_5_trans = df_trans_raw.tail(5).iloc[::-1]
                if privacy_mode:
                    display_trans = last_5_trans.copy()
                    display_trans["amount"] = "🔒 ***"
                    st.dataframe(display_trans, hide_index=True, use_container_width=True)
                else:
                    st.dataframe(
                        last_5_trans, 
                        hide_index=True, 
                        use_container_width=True,
                        column_config={"amount": st.column_config.NumberColumn("Số tiền", format="%,.0f")}
                    )
                
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
        
        df_inc_read = df_inc_raw.copy() if df_inc_raw is not None else pd.DataFrame(columns=["id", "income_source", "category", "amount", "received_date"])
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
            if privacy_mode:
                display_inc = last_5_inc.copy()
                display_inc["amount"] = "🔒 ***"
                st.dataframe(display_inc, hide_index=True, use_container_width=True)
            else:
                st.dataframe(
                    last_5_inc, 
                    hide_index=True, 
                    use_container_width=True,
                    column_config={"amount": st.column_config.NumberColumn("Số tiền", format="%,.0f")}
                )

    # -----------------------------------
    # TAB 3: CHI PHÍ CỐ ĐỊNH
    # -----------------------------------
    with tab_fixed:
        st.subheader("🏢 Quản lý Chi phí cố định (Base)")
        st.markdown("💡 **Mẹo:** Giao diện hiển thị đầy đủ toàn bộ các cột tham số và tự động tính toán bằng Python.")
        
        st.metric(
            label="TỔNG THỰC TRẢ THEO NGÀY BÁO CÁO", 
            value=mask_money(chi_co_dinh)
        )
        st.divider() 
        
        editable_cols = [
            "id", "name", "base_amount", "start_date", "end_date", 
            "chu_ky", "thang_thu_tien", "ngay_thanh_toan", 
            "thuc_tra_hien_tai", "trang_thai"
        ]
        existing_cols = [col for col in editable_cols if col in df_fixed_computed.columns]
        
        edited_df_fixed = st.data_editor(
            df_fixed_computed[existing_cols],
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key="editor_fixed",
            column_config={
                "base_amount": st.column_config.NumberColumn("base_amount", format="%,.0f"),
                "thuc_tra_hien_tai": st.column_config.NumberColumn("thuc_tra_hien_tai", format="%,.0f"),
            }
        )
        
        submit_fixed = st.button("💾 Lưu Bảng Chi Phí Cố Định", type="primary", use_container_width=True)
        
        if submit_fixed:
            with st.spinner("Đang đồng bộ dữ liệu lên Google Sheets..."):
                try:
                    cols_to_update = ["id", "name", "base_amount", "start_date", "end_date", "chu_ky", "thang_thu_tien", "ngay_thanh_toan"]
                    df_to_save = edited_df_fixed[cols_to_update].copy()
                    
                    df_final_push = calculate_fixed_expenses(df_to_save, df_adj_raw, ngay_bao_cao)
                    df_final_push = df_final_push.dropna(how="all")
                    
                    conn.update(worksheet="Fixed_Expenses_Base", data=df_final_push)
                    
                    st.toast("✅ Đã cập nhật đầy đủ cột và đồng bộ lên Google Sheets!", icon="🎉")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e:
                    st.error(f"⚠️ Lỗi: {e}")
                    
        with st.expander("🛠️️ Điều chỉnh ngân sách cố định (Phụ thu / Giảm trừ)"):
            st.markdown("Bảng ghi nhận các khoản tăng/giảm đột xuất cho các gói cước cố định.")
            if df_adj_raw is not None:
                edited_df_adj = st.data_editor(
                    df_adj_raw,
                    num_rows="dynamic",
                    use_container_width=True,
                    hide_index=True,
                    key="editor_adj",
                    column_config={"amount": st.column_config.NumberColumn(format="%,.0f")}
                )
                
                submit_adj = st.button("💾 Lưu Bảng Điều Chỉnh", type="secondary", use_container_width=True)
                
                if submit_adj:
                    with st.spinner("Đang cập nhật phụ phí..."):
                        try:
                            conn.update(worksheet="Expense_Adjustments", data=edited_df_adj)
                            st.toast("✅ Đã lưu khoản điều chỉnh!", icon="🎉")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as e:
                            st.error(f"⚠️ Lỗi: {e}")

    # -----------------------------------
    # TAB 4: QUẢN LÝ DANH MỤC
    # -----------------------------------
    with tab_category:
        st.subheader("📑 Quản lý Danh mục (Categories & Types)")
        st.markdown("Thêm, sửa, hoặc xóa các nhóm chi tiêu, khoản chi tiết và mã quy ước trực tiếp tại đây.")
        
        df_danhmuc_edit = df_danhmuc_raw.copy() if df_danhmuc_raw is not None else pd.DataFrame()
        
        if not df_danhmuc_edit.empty:
            edited_danhmuc = st.data_editor(
                df_danhmuc_edit,
                num_rows="dynamic",
                use_container_width=True,
                hide_index=True,
                key="editor_danhmuc"
            )
            
            submit_danhmuc = st.button("💾 Lưu Danh Mục", type="primary", use_container_width=True)
            
            if submit_danhmuc:
                with st.spinner("Đang đồng bộ dữ liệu lên Google Sheets..."):
                    try:
                        edited_danhmuc = edited_danhmuc.dropna(how="all")
                        conn.update(worksheet="Danh_muc", data=edited_danhmuc)
                        
                        st.toast("✅ Đã cập nhật Danh mục thành công!", icon="🎉")
                        st.cache_data.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"⚠️ Lỗi cập nhật: {e}")
else:
    st.info("⏳ Đang tải kết nối dữ liệu từ Google Sheets. Vui lòng chờ...")
