import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import re
import time

# Plotly 예외 처리
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# 1. 설정 정보 [cite: 2025-12-31]
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
    # 대기명단 시트 (없으면 자동 생성 권장)
    try: wait_sheet = spreadsheet.worksheet("대기명단")
    except: wait_sheet = None
except Exception as e:
    st.error(f"시트 연결 실패: {e}")
    st.stop()

# --- 유틸리티 함수 로직 ---
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def load_data():
    return pd.DataFrame(sheet.get_all_records())

def clean_int(value):
    """'28+1' 등 텍스트 포함 숫자 정제"""
    if not value or str(value).strip() in ["-", ""]: return 0
    nums = re.findall(r'\d+', str(value))
    return sum(map(int, nums)) if nums else 0

def add_msg_feed(name, type_msg):
    now = get_kst_now().strftime("%H:%M:%S")
    if 'feed' not in st.session_state: st.session_state.feed = []
    st.session_state.feed.insert(0, f"[{now}] {name}님께 {type_msg} 처리 완료 ✅")

def process_attendance(student_name, current_df, row_sheet):
    """출석 처리 (L, M, N열 자동 갱신 및 만료 알림)"""
    student_row = current_df[current_df['이름'] == student_name].iloc[0]
    idx_in_sheet = current_df[current_df['이름'] == student_name].index[0] + 2
    
    new_rem = clean_int(student_row.get('수강권 잔여 횟수', 0)) - 1
    new_total = clean_int(student_row.get('누적 수업 횟수', 0)) + 1
    
    # [기능 1] 수강권 만료 사전 알림 [cite: 2025-12-31]
    if new_rem <= 1:
        st.warning(f"🔔 {student_name}님 잔여 {new_rem}회! 재등록 안내 시점입니다.")
    
    row_sheet.update_cell(idx_in_sheet, 12, new_rem)
    row_sheet.update_cell(idx_in_sheet, 13, new_total)
    row_sheet.update_cell(idx_in_sheet, 14, get_kst_now().strftime("%Y-%m-%d"))
    add_msg_feed(student_name, "출석(횟수 차감)")
    return True

# --- 화면 구성 ---
st.set_page_config(page_title="원더드로잉 통합 관리", layout="wide")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None

df = load_data()
st.sidebar.title("🔐 보안 접속 센터")
mode = st.sidebar.radio("모드 선택", ["🙋 수강생 페이지", "🔐 관리자 모드"])

# ---------------------------------------------------------
# [모드 1] 수강생 페이지 (포트폴리오 & 예약 & 대기신청)
# ---------------------------------------------------------
if mode == "🙋 수강생 페이지":
    st.title("🙋 원더드로잉 수강생 센터")
    if not st.session_state.logged_in:
        with st.container(border=True):
            st.subheader("🔑 로그인")
            c1, c2 = st.columns(2)
            s_name = c1.text_input("성함")
            s_pw = c2.text_input("비밀번호 (초기: 연락처 뒷4자리)", type="password")
            if st.button("🔓 로그인 확인"):
                student = df[df['이름'] == s_name]
                if not student.empty:
                    s_data = student.iloc[0]
                    valid_pw = str(s_data.get('비밀번호', '')) if s_data.get('비밀번호') else str(s_data['연락처'])[-4:]
                    if s_pw == valid_pw:
                        st.session_state.logged_in, st.session_state.current_user = True, s_name
                        st.rerun()
                else: st.error("정보가 일치하지 않습니다.")
    else:
        user_name = st.session_state.current_user
        s_info = df[df['이름'] == user_name].iloc[0]
        row_num = df[df['이름'] == user_name].index[0] + 2
        
        # [기능 2] 포트폴리오 (T열 URL 활용) [cite: 2025-12-31]
        st.subheader(f"🎨 {user_name}님의 작품 갤러리")
        urls = str(s_info.get('작품URL', '')).split(',')
        if urls[0]:
            cols = st.columns(4)
            for i, u in enumerate(urls): cols[i%4].image(u.strip(), use_container_width=True)
        else: st.info("등록된 작품 사진이 없습니다.")

        st.divider()
        col1, col2, col3 = st.columns(3)
        rem = clean_int(s_info.get('수강권 잔여 횟수', 0))
        col1.metric("남은 횟수", f"{rem}회")
        col2.info(f"📅 예약: {s_info.get('다음 수업 예약일', '-')}")
        col3.success(f"📖 진도: {s_info.get('현재 진도', '-')}")

        # 예약 및 [기능 3] 대기 신청
        st.subheader("🗓️ 수업 예약 및 대기")
        kst_now = get_kst_now()
        date_opts = [(kst_now + timedelta(days=i)).strftime("%m/%d") for i in range(1, 15)]
        time_slots = ["10:00 (오전반)", "13:00 (오후반1)", "15:30 (오후반2)", "19:00 (저녁반)"]
        b1, b2 = st.columns(2)
        sel_date, sel_time = b1.selectbox("날짜", date_opts), b2.selectbox("시간", time_slots)
        booking_str = f"{sel_date} {sel_time}"
        booked_count = len(df[df['다음 수업 예약일'] == booking_str])

        if booked_count < 6:
            if st.button("🚀 예약 확정"):
                sheet.update_cell(row_num, 8, booking_str); st.success("완료!"); st.rerun()
        else:
            st.error("정원 초과")
            if st.button("📝 이 시간에 대기 신청하기"):
                if wait_sheet: wait_sheet.append_row([user_name, booking_str, get_kst_now().strftime("%Y-%m-%d %H:%M")])
                st.info("대기 명단에 등록되었습니다."); st.rerun()

        if st.button("🔒 로그아웃"): st.session_state.logged_in = False; st.rerun()

# ---------------------------------------------------------
# [모드 2] 관리자 모드 (필터링 & 상세 수정 & 대시보드)
# ---------------------------------------------------------
elif mode == "🔐 관리자 모드":
    admin_pw = st.sidebar.text_input("인증키", type="password")
    if admin_pw != ADMIN_PASSWORD: st.stop()

    tab1, tab2, tab3, tab4 = st.tabs(["👥 회원 관리", "➕ 신규 등록", "📅 예약/대기 명단", "📊 대시보드"])

    with tab1:
        # 필터 및 모든 항목 수정 로직
        status_sel = st.multiselect("필터", ["수강중", "휴강중", "종료"], default=["수강중"])
        f_df = df[df['상태'].isin(status_sel)]
        st.dataframe(f_df, use_container_width=True)

        sel_name = st.selectbox("회원 선택", ["선택"] + f_df['이름'].tolist())
        if sel_name != "선택":
            idx = df[df['이름'] == sel_name].index[0]; row_num = idx + 2; s = df.iloc[idx]
            with st.form(f"edit_{sel_name}"):
                c1, c2, c3 = st.columns(3)
                u_name = c1.text_input("이름(B)", value=str(s.get('이름', '')))
                u_price = c2.text_input("금액(F)", value=str(s.get('수강금액', '')))
                u_end = c3.text_input("종료일(K)", value=str(s.get('수강종료일', s.get('수강 종료일', '-'))))
                u_rem = c1.text_input("잔여(L)", value=str(s.get('수강권 잔여 횟수', '0')))
                u_car = c2.text_input("차량(R)", value=str(s.get('차량번호', '')))
                u_img = c3.text_area("작품URL(T)", value=str(s.get('작품URL', '')))
                if st.form_submit_button("💾 정보 저장"):
                    sheet.update_cell(row_num, 2, u_name); sheet.update_cell(row_num, 12, u_rem)
                    sheet.update_cell(row_num, 11, u_end); sheet.update_cell(row_num, 18, u_car)
                    sheet.update_cell(row_num, 20, u_img); st.rerun()

    with tab2:
        # --- [Tab 2] 신규 등록 기존 로직 복구 ---
        st.subheader("🆕 새로운 수강생 등록")
        with st.form("new_reg_form"):
            n_name = st.text_input("성함*")
            n_phone = st.text_input("연락처*")
            n_pass = st.selectbox("수강권", ["월 4회", "3달 12회", "월 무제한"])
            n_rem = st.number_input("시작 횟수", value=4)
            if st.form_submit_button("➕ 수강생 등록 완료"):
                if n_name and n_phone:
                    # A~T열(20개) 구조에 맞춰 데이터 생성
                    new_row = ["수강중", n_name, n_phone, "미술", n_pass, "", "", "-", get_kst_now().strftime("%Y-%m-%d"), "", "", n_rem, 0, "-", "-", "", "", "", "", ""]
                    sheet.append_row(new_row); st.success(f"{n_name}님 등록 성공!"); st.rerun()

    with tab3:
        # --- [Tab 3] 상세 예약 현황 및 대기 명단 ---
        st.subheader("📅 시간대별 예약 현황 및 퀵 출결")
        booked_times = sorted([t for t in df['다음 수업 예약일'].unique() if t not in ["-", ""]])
        for t_str in booked_times:
            students = df[df['다음 수업 예약일'] == t_str]
            with st.container(border=True):
                st.write(f"⏰ **{t_str}** ({len(students)}/6명)")
                for _, r in students.iterrows():
                    c1, c2, c3 = st.columns([2, 2, 0.8])
                    c1.write(f"👤 **{r['이름']}** ({r['연락처']})")
                    c2.caption(f"🚗차량: {r.get('차량번호', '-')} / 잔여: {r['수강권 잔여 횟수']}회")
                    if c3.button("출석", key=f"att_{r['이름']}_{t_str}"):
                        if process_attendance(r['이름'], df, sheet): st.rerun()
        
        st.divider()
        st.subheader("📝 예약 대기자 명단")
        if wait_sheet:
            wait_data = pd.DataFrame(wait_sheet.get_all_records())
            st.table(wait_data)

    with tab4:
        # [기능 4] 운영 대시보드 (Plotly 시각화) [cite: 2025-12-31]
        if PLOTLY_AVAILABLE:
            st.subheader("📊 화실 운영 분석")
            rev = sum([clean_int(v) for v in df['수강금액']])
            st.metric("이번 달 총 매출", f"{rev:,}원")
            col_a, col_b = st.columns(2)
            fig_p = px.pie(df, names='상태', title='회원 상태 비율')
            col_a.plotly_chart(fig_p, use_container_width=True)
            res_pref = df[df['다음 수업 예약일'] != '-']['다음 수업 예약일'].value_counts().reset_index()
            fig_b = px.bar(res_pref, x='index', y='다음 수업 예약일', title='인기 시간대')
            col_b.plotly_chart(fig_b, use_container_width=True)
