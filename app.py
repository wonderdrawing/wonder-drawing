import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import re
import time
import json

# 1. 원더드로잉 핵심 설정 [cite: 2025-12-31]
SENDER_PHONE = "010-8306-5526" 
SHEET_NAME = "원더드로잉_수강생관리"
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
    
    # [기능] 대기명단 시트 연결
    try: wait_sheet = spreadsheet.worksheet("대기명단")
    except: wait_sheet = None
except Exception as e:
    st.error(f"시트 연결 실패: {e}")
    st.stop()

# --- 유틸리티 함수 ---
def get_kst_now():
    return datetime.now(timezone(timedelta(hours=9)))

def load_data():
    data = sheet.get_all_records()
    return pd.DataFrame(data)

def clean_int(value):
    if not value or str(value).strip() in ["-", ""]: return 0
    nums = re.findall(r'\d+', str(value))
    return sum(map(int, nums)) if nums else 0

def process_attendance(student_name, current_df, row_sheet):
    student_row = current_df[current_df['이름'] == student_name].iloc[0]
    idx_in_sheet = current_df[current_df['이름'] == student_name].index[0] + 2
    new_rem = clean_int(student_row.get('수강권 잔여 횟수', 0)) - 1
    new_total = clean_int(student_row.get('누적 수업 횟수', 0)) + 1
    
    if new_rem <= 1:
        st.warning(f"⚠️ {student_name}님 잔여 {new_rem}회! 재등록 안내 필요")
    
    row_sheet.update_cell(idx_in_sheet, 12, new_rem)
    row_sheet.update_cell(idx_in_sheet, 13, new_total)
    row_sheet.update_cell(idx_in_sheet, 14, get_kst_now().strftime("%Y-%m-%d"))
    return True

# --- 화면 구성 ---
st.set_page_config(page_title="원더드로잉 관리 시스템 2026", layout="wide")
if 'logged_in' not in st.session_state: st.session_state.logged_in = False

df = load_data()
st.sidebar.title("🔐 보안 접속 센터")
mode = st.sidebar.radio("모드 선택", ["🙋 수강생 페이지", "🔐 관리자 모드"])

if mode == "🙋 수강생 페이지":
    st.title("🙋 원더드로잉 수강생 센터")
    if not st.session_state.logged_in:
        c1, c2 = st.columns(2)
        s_name = c1.text_input("성함")
        s_pw = c2.text_input("비밀번호 (초기: 연락처 뒷4자리)", type="password")
        if st.button("🔓 로그인"):
            student = df[df['이름'] == s_name]
            if not student.empty:
                s_data = student.iloc[0]
                valid_pw = str(s_data.get('비밀번호', '')) if s_data.get('비밀번호') else str(s_data['연락처'])[-4:]
                if s_pw == valid_pw:
                    st.session_state.logged_in, st.session_state.current_user = True, s_name
                    st.rerun()
    else:
        user_name = st.session_state.current_user
        s_info = df[df['이름'] == user_name].iloc[0]
        row_num = df[df['이름'] == user_name].index[0] + 2
        st.header(f"✨ {user_name}님 반갑습니다!")
        rem = clean_int(s_info.get('수강권 잔여 횟수', 0))
        st.metric("남은 횟수", f"{rem}회")
        if st.button("🔒 로그아웃"): st.session_state.logged_in = False; st.rerun()

elif mode == "🔐 관리자 모드":
    admin_pw = st.sidebar.text_input("관리자 인증키", type="password")
    if admin_pw == ADMIN_PASSWORD:
        tab1, tab2 = st.tabs(["👥 회원 관리", "➕ 신규 등록"])
        with tab1:
            st.dataframe(df[df['상태'] == '수강중'], use_container_width=True)
            sel_name = st.selectbox("회원 선택", ["선택"] + df['이름'].tolist())
            if sel_name != "선택" and st.button("✅ 출석 처리"):
                if process_attendance(sel_name, df, sheet): st.success("완료!"); st.rerun()
        with tab2:
            with st.form("new_reg"):
                n_name, n_phone = st.text_input("성함"), st.text_input("연락처")
                if st.form_submit_button("➕ 등록"):
                    # [중요] 리스트 괄호 ] 를 정확히 닫았습니다.
                    new_row = ["수강중", n_name, n_phone, "미술", "월 4회", "", "", "-", get_kst_now().strftime("%Y-%m-%d"), "", "", 4, 0, "-", "-", "", "", "", "", ""]
                    sheet.append_row(new_row); st.rerun()

