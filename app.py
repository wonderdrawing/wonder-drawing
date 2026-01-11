import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import re
import time
import json # [중요] json 라이브러리 추가

# Plotly 예외 처리 (대시보드 차트용)
try:
    import plotly.express as px
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# 1. 원더드로잉 핵심 설정
SENDER_PHONE = "010-8306-5526" 
SHEET_NAME = "원더드로잉_수강생관리"
DEFAULT_MSG = "{name}님, 안녕하세요:) 원더드로잉 취미미술화실입니다. {time} 수업 안내드립니다. 내일뵙겠습니다. 🎨"
ADMIN_PASSWORD = "dnjsejemfhdldghktlf" 

# 2. 구글 시트 연결 (Secrets 방식 적용)
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
try:
    if "creds_json" in st.secrets:
        creds_info = json.loads(st.secrets["creds_json"])
        creds = ServiceAccountCredentials.from_json_dict(creds_info, scope)
    else:
        creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
    
    client = gspread.authorize(creds)
    spreadsheet = client.open(SHEET_NAME)
    sheet = spreadsheet.get_worksheet(0)
    
    # [기능 3] 대기명단 시트 연결
    try: wait_sheet = spreadsheet.worksheet("대기명단")
    except: wait_sheet = None
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
    """출석 처리 및 [기능 1] 수강권 만료 자동 알림 통합"""
    student_row = current_df[current_df['이름'] == student_name].iloc[0]
    idx_in_sheet = current_df[current_df['이름'] == student_name].index[0] + 2
    
    new_rem = clean_int(student_row.get('수강권 잔여 횟수', 0)) - 1
    new_total = clean_int(student_row.get('누적 수업 횟수', 0)) + 1
    
    # [기능 1] 잔여 1회 이하 시 알림 알림
    if new_rem <= 1:
        st.warning(f"⚠️ {student_name}님 잔여 {new_rem}회! 재등록 안내가 필요합니다.")
    
    row_sheet.update_cell(idx_in_sheet, 12, new_rem)
    row_sheet.update_cell(idx_in_sheet, 13, new_total)
    row_sheet.update_cell(idx_in_sheet, 14, get_kst_now().strftime("%Y-%m-%d"))
    
    add_msg_feed(student_name, "출석 처리 (횟수 차감)")
    return True

# --- 화면 구성 ---
st.set_page_config(page_title="원더드로잉 관리 시스템", layout="wide")

if 'logged_in' not in st.session_state: st.session_state.logged_in = False
if 'current_user' not in st.session_state: st.session_state.current_user = None

df = load_data()
st.sidebar.title("🔐 보안 접속 센터")
mode = st.sidebar.radio("접속 모드 선택", ["🙋 수강생 페이지", "🔐 관리자 모드"])

# ---------------------------------------------------------
# [모드 1] 수강생 페이지: 포트폴리오 및 대기 신청 기능 추가
# ---------------------------------------------------------
if mode == "🙋 수강생 페이지":
    st.title("🙋 원더드로잉 수강생 센터")
    
    if not st.session_state.logged_in:
        with st.container(border=True):
            st.subheader("🔑 수강생 로그인")
            c1, c2 = st.columns(2)
            s_login_name = c1.text_input("성함")
            s_login_pw = c2.text_input("비밀번호 (초기번호: 연락처 뒷4자리)", type="password")
            
            if st.button("🔓 로그인 확인"):
                student = df[df['이름'] == s_login_name]
                if not student.empty:
                    s_data = student.iloc[0]
                    valid_pw = str(s_data.get('비밀번호', '')) if s_data.get('비밀번호') else str(s_data['연락처']).replace("-","")[-4:]
                    if s_login_pw == valid_pw:
                        st.session_state.logged_in, st.session_state.current_user = True, s_login_name
                        st.rerun()
                    else: st.error("비밀번호가 틀렸습니다.")
                else: st.error("등록되지 않은 성함입니다.")
    else:
        user_name = st.session_state.current_user
        s_info = df[df['이름'] == user_name].iloc[0]
        row_num = df[df['이름'] == user_name].index[0] + 2
        
        # [기능 2] 비주얼 포트폴리오 (T열/20번째 열 URL 사용 가정)
        st.subheader(f"🎨 {user_name}님의 작품 갤러리")
        img_urls = str(s_info.get('작품URL', '')).split(',')
        if img_urls[0]:
            cols = st.columns(4)
            for i, url in enumerate(img_urls):
                if url.strip(): cols[i%4].image(url.strip(), use_container_width=True)
        else: st.info("아직 등록된 작품 사진이 없습니다.")

        st.divider()
        st.header(f"✨ {user_name}님, 반갑습니다!")
        col1, col2, col3 = st.columns(3)
        rem = clean_int(s_info.get('수강권 잔여 횟수', 0))
        col1.metric("남은 횟수", f"{rem}회")
        col2.info(f"📅 예약 일정: {s_info.get('다음 수업 예약일', '-')}")
        col3.success(f"📖 수업 진도: {s_info.get('현재 진도', '-')}")

        with st.expander("⚙️ 비밀번호 변경"):
            new_pw = st.text_input("새로운 비밀번호 설정", type="password")
            if st.button("💾 비밀번호 단독 저장"):
                sheet.update_cell(row_num, 19, new_pw); st.success("변경 완료!"); st.rerun()

        # [기능 3] 수업 예약 및 대기 신청
        st.divider()
        st.subheader("🗓️ 수업 예약하기 (정원 6명)")
        if rem > 0:
            kst_now = get_kst_now()
            weekdays = ['월', '화', '수', '목', '금', '토', '일']
            date_opts = [(kst_now + timedelta(days=i)).strftime("%m/%d") + f" ({weekdays[(kst_now + timedelta(days=i)).weekday()]})" for i in range(1, 15)]
            time_slots = ["10:00 (오전반)", "13:00 (오후반1)", "15:30 (오후반2)", "19:00 (저녁반)"]
            b1, b2 = st.columns(2)
            sel_date, sel_time = b1.selectbox("날짜 선택", date_opts), b2.selectbox("시간 선택", time_slots)
            booking_str = f"{sel_date} {sel_time}"
            booked_count = len(df[df['다음 수업 예약일'] == booking_str])
            
            if booked_count < 6:
                if st.button(f"🚀 {booking_str} 예약 확정"):
                    sheet.update_cell(row_num, 8, booking_str); st.success("완료!"); st.rerun()
            else:
                st.error("⚠️ 정원 마감! 대기 신청이 가능합니다.")
                if st.button("📝 대기 명단 등록"):
                    if wait_sheet:
                        wait_sheet.append_row([user_name, booking_str, get_kst_now().strftime("%Y-%m-%d %H:%M")])
                        st.info("대기 등록 완료!"); st.rerun()
        
        if st.button("🔒 로그아웃"): st.session_state.logged_in = False; st.rerun()

# ---------------------------------------------------------
# [모드 2] 관리자 모드: 대시보드 및 대기명단 관리 통합
# ---------------------------------------------------------
elif mode == "🔐 관리자 모드":
    admin_pw = st.sidebar.text_input("관리자 인증키", type="password")
    if admin_pw != ADMIN_PASSWORD: st.stop()

    # [기능 4] 대시보드 탭 추가
    tab1, tab2, tab3, tab4 = st.tabs(["👥 회원 현황/상세 수정", "➕ 신규 등록", "📅 전체 예약/대기 현황", "📊 운영 대시보드"])

    with tab1:
        st.subheader("👥 수강생 필터링 및 정보 수정")
        status_option = st.multiselect("필터링", ["수강중", "휴강중", "종료"], default=["수강중"])
        filtered_df = df[df['상태'].isin(status_option)]
        st.dataframe(filtered_df, use_container_width=True)

        selected_name = st.selectbox("🎯 회원 선택", ["선택하세요"] + filtered_df['이름'].tolist())
        if selected_name != "선택하세요":
            idx = df[df['이름'] == selected_name].index[0]; row_num = idx + 2; s = df.iloc[idx]
            c_l, c_r = st.columns([1, 2.5])
            with c_l:
                if st.button("✅ 개별 출석 처리"):
                    if process_attendance(selected_name, df, sheet): st.success("완료!"); st.rerun()
            with c_r:
                with st.expander("📝 상세 정보 수정 (A~T열)", expanded=True):
                    with st.form(f"full_edit_{selected_name}"):
                        f1, f2, f3 = st.columns(3)
                        u_status = f1.selectbox("상태", ["수강중", "휴강중", "종료"], index=["수강중", "휴강중", "종료"].index(s.get('상태', '수강중')))
                        u_price = f2.text_input("수강금액 (F)", value=str(s.get('수강금액', '')))
                        # KeyError 방지 (get 활용)
                        u_end = f2.text_input("종료일 (K)", value=str(s.get('수강종료일', s.get('수강 종료일', '-'))))
                        u_rem = f3.text_input("잔여 횟수 (L)", value=str(s.get('수강권 잔여 횟수', '0')))
                        u_portfolio = st.text_area("작품 URL (쉼표로 구분)", value=str(s.get('작품URL', '')))
                        if st.form_submit_button("💾 시트에 정보 저장"):
                            sheet.update_cell(row_num, 1, u_status); sheet.update_cell(row_num, 6, u_price)
                            sheet.update_cell(row_num, 11, u_end); sheet.update_cell(row_num, 12, u_rem)
                            sheet.update_cell(row_num, 20, u_portfolio); st.success("저장됨!"); st.rerun()

    with tab2:
        st.subheader("🆕 신규 등록")
        with st.form("new_reg"):
            n_name = st.text_input("성함*"); n_phone = st.text_input("연락처*")
            if st.form_submit_button("➕ 등록"):
                new_row = ["수강중", n_name, n_phone, "미술", "월 4회", "", "", "-", get_kst_now().strftime("%Y-%m-%d"), "", "", 4, 0, "-", "-", "", "", "", "", ""]



