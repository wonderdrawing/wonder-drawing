import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import re
import time

# 1. 원더드로잉 핵심 설정 [cite: 2025-12-31]
SENDER_PHONE = "010-8306-5526" 
SHEET_NAME = "원더드로잉_수강생관리"
DEFAULT_MSG = "{name}님, 안녕하세요:) 원더드로잉 취미미술화실입니다. {time} 수업 안내드립니다. 내일뵙겠습니다. 🎨"
ADMIN_PASSWORD = "dnjsejemfhdldghktlf" 

# 2. 구글 시트 연결
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)

try:
    spreadsheet = client.open(SHEET_NAME)
    sheet = spreadsheet.get_worksheet(0)
except Exception as e:
    st.error(f"시트 연결 실패: {e}")
    st.stop()

# --- 유틸리티 함수 로직 ---
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def load_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def clean_int(value):
    if not value or str(value).strip() in ["-", ""]: return 0
    nums = re.findall(r'\d+', str(value))
    return sum(map(int, nums)) if nums else 0

def add_msg_feed(name, type_msg):
    now = get_kst_now().strftime("%H:%M:%S")
    if 'feed' not in st.session_state: st.session_state.feed = []
    st.session_state.feed.insert(0, f"[{now}] {name}님께 {type_msg} 처리 완료 ✅")

def process_attendance(student_name, current_df, row_sheet):
    """출석 처리 및 횟수 자동 차감 (L, M, N열)"""
    student_row = current_df[current_df['이름'] == student_name].iloc[0]
    idx_in_sheet = current_df[current_df['이름'] == student_name].index[0] + 2
    
    new_rem = clean_int(student_row.get('수강권 잔여 횟수', 0)) - 1
    new_total = clean_int(student_row.get('누적 수업 횟수', 0)) + 1
    today_str = get_kst_now().strftime("%Y-%m-%d")
    
    row_sheet.update_cell(idx_in_sheet, 12, new_rem)
    row_sheet.update_cell(idx_in_sheet, 13, new_total)
    row_sheet.update_cell(idx_in_sheet, 14, today_str)
    
    add_msg_feed(student_name, "출석 처리 (횟수 자동 차감)")
    return True

# --- 화면 구성 ---
st.set_page_config(page_title="원더드로잉 관리 시스템", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None

df = load_data()
st.sidebar.title("🔐 보안 접속 센터")
mode = st.sidebar.radio("접속 모드 선택", ["🙋 수강생 페이지", "🔐 관리자 모드"])

# ---------------------------------------------------------
# [모드 1] 수강생 페이지: 독립적 비밀번호 로직 적용 [cite: 2025-12-31]
# ---------------------------------------------------------
if mode == "🙋 수강생 페이지":
    st.title("🙋 원더드로잉 수강생 센터")
    
    if not st.session_state.logged_in:
        with st.container(border=True):
            st.subheader("🔑 수강생 로그인")
            c1, c2 = st.columns(2)
            with c1: s_login_name = st.text_input("성함")
            with c2: s_login_pw = st.text_input("비밀번호 (초기번호: 연락처 뒷4자리)", type="password")
            
            if st.button("🔓 로그인 확인"):
                # 비밀번호 확인 로직 (S열에 값이 있으면 S열 확인, 없으면 연락처 뒷4자리 확인)
                student = df[df['이름'] == s_login_name]
                if not student.empty:
                    s_data = student.iloc[0]
                    stored_pw = str(s_data.get('비밀번호', ''))
                    phone_last4 = str(s_data['연락처']).replace("-","")[-4:]
                    
                    # 저장된 비번이 있으면 그것과 대조, 없으면 연락처 뒷자리와 대조
                    valid_pw = stored_pw if stored_pw else phone_last4
                    
                    if s_login_pw == valid_pw:
                        st.session_state.logged_in = True
                        st.session_state.current_user = s_login_name
                        st.rerun()
                    else: st.error("비밀번호가 틀렸습니다.")
                else: st.error("등록되지 않은 성함입니다.")
    else:
        user_name = st.session_state.current_user
        s_info = df[df['이름'] == user_name].iloc[0]
        row_num = df[df['이름'] == user_name].index[0] + 2
        
        st.header(f"✨ {user_name}님, 반갑습니다!")
        col1, col2, col3 = st.columns(3)
        rem = clean_int(s_info.get('수강권 잔여 횟수', 0))
        col1.metric("남은 횟수", f"{rem}회")
        col2.info(f"📅 예약 일정: {s_info.get('다음 수업 예약일', '-')}")
        col3.success(f"📖 수업 진도: {s_info.get('현재 진도', '-')}")

        # --- 수정된 비밀번호 변경 기능 (연락처와 별개) ---
        with st.expander("⚙️ 비밀번호 변경 (연락처는 유지됨)"):
            new_pw = st.text_input("새로운 비밀번호 설정", type="password")
            confirm_pw = st.text_input("비밀번호 확인", type="password")
            if st.button("💾 비밀번호 단독 저장"):
                if new_pw == confirm_pw and len(new_pw) >= 4:
                    sheet.update_cell(row_num, 19, new_pw) # S열(19번째)에 저장
                    st.success("비밀번호가 성공적으로 변경되었습니다."); time.sleep(1); st.rerun()
                else: st.error("비밀번호가 일치하지 않거나 너무 짧습니다.")

        # 예약 로직... (v26.1과 동일)
        st.divider()
        st.subheader("🗓️ 수업 예약하기 (정원 6명)")
        if rem > 0:
            kst_now = get_kst_now()
            weekdays = ['월', '화', '수', '목', '금', '토', '일']
            date_opts = [(kst_now + timedelta(days=i)).strftime("%m/%d") + f" ({weekdays[(kst_now + timedelta(days=i)).weekday()]})" for i in range(1, 15)]
            time_slots = ["10:00 (오전반)", "13:00 (오후반1)", "15:30 (오후반2)", "19:00 (저녁반)"]
            b1, b2 = st.columns(2)
            with b1: sel_date = st.selectbox("날짜 선택", date_opts)
            with b2: sel_time = st.selectbox("시간 선택", time_slots)
            booking_str = f"{sel_date} {sel_time}"
            booked_count = len(df[df['다음 수업 예약일'] == booking_str])
            if booked_count < 6:
                if st.button(f"🚀 {booking_str} 예약 확정"):
                    sheet.update_cell(row_num, 8, booking_str); st.success("예약 완료!"); time.sleep(1); st.rerun()
            else: st.error("정원이 마감되었습니다.")
        
        if st.button("🔒 로그아웃"):
            st.session_state.logged_in = False; st.rerun()

# ---------------------------------------------------------
# [모드 2] 관리자 모드: 필터링 및 예약지 상세 정보 노출 (유지)
# ---------------------------------------------------------
elif mode == "🔐 관리자 모드":
    admin_pw = st.sidebar.text_input("관리자 인증키", type="password")
    if admin_pw != ADMIN_PASSWORD:
        st.warning("비밀번호를 입력해 주세요."); st.stop()

    tab1, tab2, tab3 = st.tabs(["👥 수강생 현황/상세 수정", "➕ 신규 등록", "📅 전체 예약 현황"])

    with tab1:
        st.subheader("👥 수강생 필터링 및 모든 정보 수정")
        status_option = st.multiselect("필터링", ["수강중", "휴강중", "종료"], default=["수강중"])
        filtered_df = df[df['상태'].isin(status_option)]
        st.dataframe(filtered_df, use_container_width=True)

        selected_name = st.selectbox("🎯 회원 선택", ["선택하세요"] + filtered_df['이름'].tolist())
        if selected_name != "선택하세요":
            idx = df[df['이름'] == selected_name].index[0]; row_num = idx + 2; s = df.iloc[idx]
            c_l, c_r = st.columns([1, 2.5])
            with c_l:
                if st.button("✅ 개별 출석 처리"):
                    if process_attendance(selected_name, df, sheet): st.success("완료!"); time.sleep(1); st.rerun()
                with st.expander("🗑️ 회원 삭제"):
                    if st.button(f"❗ {selected_name} 삭제"): sheet.delete_rows(row_num); st.rerun()
            with c_r:
                with st.expander("📝 모든 상세 정보 수정 (A~R열)", expanded=True):
                    with st.form(f"full_edit_{selected_name}"):
                        f1, f2, f3 = st.columns(3)
                        with f1:
                            u_status = st.selectbox("상태 (A)", ["수강중", "휴강중", "종료"], index=["수강중", "휴강중", "종료"].index(s.get('상태', '수강중')))
                            u_name = st.text_input("이름 (B)", value=str(s.get('이름', '')))
                            u_phone = st.text_input("연락처 (C)", value=str(s.get('연락처', '')))
                        with f2:
                            u_price = st.text_input("수강금액 (F)", value=str(s.get('수강금액', '')))
                            u_next = st.text_input("예약일 (H)", value=str(s.get('다음 수업 예약일', '')))
                            u_end = st.text_input("종료일 (K)", value=str(s.get('수강 종료일', '')))
                        with f3:
                            u_rem = st.text_input("잔여 횟수 (L)", value=str(s.get('수강권 잔여 횟수', '0')))
                            u_prog = st.text_input("진도 (O)", value=str(s.get('현재 진도', '')))
                            u_car = st.text_input("차량 (R)", value=str(s.get('차량번호', '')))
                        if st.form_submit_button("💾 시트에 정보 저장"):
                            sheet.update_cell(row_num, 1, u_status); sheet.update_cell(row_num, 2, u_name)
                            sheet.update_cell(row_num, 3, u_phone); sheet.update_cell(row_num, 12, u_rem)
                            sheet.update_cell(row_num, 18, u_car); st.success("저장됨!"); st.rerun()

    with tab2:
        st.subheader("🆕 신규 등록")
        with st.form("new_reg"):
            n_name = st.text_input("성함*"); n_phone = st.text_input("연락처*")
            if st.form_submit_button("➕ 등록"):
                new_row = ["수강중", n_name, n_phone, "미술", "월 4회", "", "", "-", get_kst_now().strftime("%Y-%m-%d"), "", "", 4, 0, "-", "-", "", "", ""]
                sheet.append_row(new_row); st.rerun()

    with tab3:
        # --- 예약자 명단 (전화/차량번호 포함) 및 퀵 출결 (보전) ---
        st.subheader("📅 시간대별 예약 현황 및 즉시 출결")
        booked_times = sorted([t for t in df['다음 수업 예약일'].unique() if t not in ["-", ""]])
        if not booked_times: st.info("예약된 수업이 없습니다.")
        else:
            for t_str in booked_times:
                students_at_time = df[df['다음 수업 예약일'] == t_str]
                with st.container(border=True):
                    st.write(f"⏰ **{t_str}** (총 {len(students_at_time)}/6명)")
                    for i, row in students_at_time.iterrows():
                        c1, c2, c3 = st.columns([2, 2, 0.8])
                        c1.write(f"👤 **{row['이름']}** ({row['연락처']})")
                        c2.caption(f"잔여: {row['수강권 잔여 횟수']}회 / 🚗차량: {row.get('차량번호', '-')}")
                        if c3.button("출석", key=f"q_btn_{row['이름']}_{t_str}"):
                            if process_attendance(row['이름'], df, sheet): st.toast(f"{row['이름']}님 출석 완료!"); time.sleep(1); st.rerun()
