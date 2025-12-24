import tkinter as tk
from tkinter import messagebox, scrolledtext
import json
import os
from datetime import datetime, timedelta, timezone
import threading
import time
import requests
import logging
import logging.handlers
import sys
import glob
from typing import Dict, List, Any
import calendar
import asyncio
import aiohttp
import re
from cryptography.fernet import Fernet
import base64
import ntplib
import uuid
from ttkbootstrap.scrolled import ScrolledFrame

# 🎨 현대적인 UI 라이브러리
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import DateEntry
# 버전 호환성을 위해 try-except 처리
try:
    from ttkbootstrap.widgets import ToastNotification
except ImportError:
    from ttkbootstrap.toast import ToastNotification

# ==============================================================================
# 1. 로깅 및 기본 설정
# ==============================================================================

DATA_DIR = "app_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE_BASENAME = os.path.join(DATA_DIR, 'app.log')
file_handler = None

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("예외 발생:", exc_info=(exc_type, exc_value, exc_traceback))

def setup_logging():
    global file_handler
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)
    
    formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%H:%M:%S')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE_BASENAME, when='midnight', interval=1, backupCount=30, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

sys.excepthook = handle_exception
setup_logging()

# 설정 및 상수
ANALYTICS_URL = "https://uppuyydtqhaulobevczk.supabase.co"
ANALYTICS_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVwcHV5eWR0cWhhdWxvYmV2Y3prIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI0ODE5NTQsImV4cCI6MjA2ODA1Nzk1NH0.yHz7U7XXV34Dlvs8PAoZ6EyD6vz1y77dAFpbh0_7noc"
APP_VERSION = "3.0 Dashboard"
SUPABASE_URL = "https://ydiivmmorbqbvrahrutd.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlkaWl2bW1vcmJxYnZyYWhydXRkIiwicm9sZSI6ImFub24iLCJpYXQiOjE2NzM3MjA4MDEsImV4cCI6MTk4OTI5NjgwMX0.jcX7WYAImKzfYuLi4exAlvMB1zpfKFf9iWN7_gnbjaI"
HEADERS = {"apikey": SUPABASE_ANON_KEY, "x-client-info": "supabase-py/1.0.0"}
KST = timezone(timedelta(hours=9))
KEY_FILE = os.path.join(DATA_DIR, 'app.key')

# ==============================================================================
# 2. 핵심 로직 클래스 (기존 로직 유지)
# ==============================================================================
class AnalyticsLogger:
    def __init__(self, url: str, key: str):
        self.base_url = url
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        self.analytics_url = f"{self.base_url}/rest/v1/analytics_logs"
        self.reservations_url = f"{self.base_url}/rest/v1/current_reservations"
        self.targets_url = f"{self.base_url}/rest/v1/booking_targets"
        self.target_check_url = f"{self.base_url}/rest/v1/target_check_logs"

    def log_event(self, user_email: str, machine_id: str, event_type: str, event_data: dict):
        threading.Thread(target=self._send_log, args=(user_email, machine_id, event_type, event_data), daemon=True).start()

    def _send_log(self, user_email: str, machine_id: str, event_type: str, event_data: dict):
        try:
            payload = {"user_email": user_email, "machine_id": machine_id, "app_version": APP_VERSION,
                       "event_type": event_type, "event_data": event_data}
            requests.post(self.analytics_url, headers=self.headers, json=payload, timeout=10)
        except Exception: pass

    def sync_reservations(self, user_email: str, reservation_list: List[Dict[str, Any]]):
        threading.Thread(target=self._sync_reservations_worker, args=(user_email, reservation_list), daemon=True).start()

    def _sync_reservations_worker(self, user_email: str, reservation_list: List[Dict[str, Any]]):
        try:
            requests.delete(f"{self.reservations_url}?user_email=eq.{user_email}", headers={**self.headers, "Prefer": "return=minimal"})
            if reservation_list:
                payload = [{"user_email": user_email, "booking_date": res.get("date"),
                            "court_name": f"{res.get('court')}번 코트", "booking_time": res.get("time"),
                            "is_paid": res.get("is_paid", False)} for res in reservation_list]
                requests.post(self.reservations_url, headers=self.headers, json=payload, timeout=10)
        except Exception: pass
    
    def sync_targets(self, user_email: str, targets_list: List[Dict[str, Any]]):
        threading.Thread(target=self._sync_targets_worker, args=(user_email, targets_list), daemon=True).start()

    def _sync_targets_worker(self, user_email: str, targets_list: List[Dict[str, Any]]):
        try:
            requests.delete(f"{self.targets_url}?user_email=eq.{user_email}", headers={**self.headers, "Prefer": "return=minimal"})
            if targets_list:
                payload = [{"user_email": user_email, "booking_date": t.get("date"),
                            "court_number": t.get("court"), "booking_time": t.get("time")} for t in targets_list]
                requests.post(self.targets_url, headers=self.headers, json=payload, timeout=10)
        except Exception: pass

    def log_booking_targets(self, user_email: str, targets_list: List[Dict[str, Any]]):
        threading.Thread(target=self._log_targets_worker, args=(user_email, targets_list), daemon=True).start()

    def _log_targets_worker(self, user_email: str, targets_list: List[Dict[str, Any]]):
        try:
            if targets_list:
                payload = [{"user_email": user_email, "booking_date": t.get("date"),
                            "court_number": t.get("court"), "booking_time": t.get("time")} for t in targets_list]
                requests.post(self.target_check_url, headers=self.headers, json=payload, timeout=10)
        except Exception: pass

def load_key():
    if os.path.exists(KEY_FILE): return open(KEY_FILE, 'rb').read()
    key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as key_file: key_file.write(key)
    return key

cipher_suite = Fernet(load_key())

def encrypt_password(password: str) -> str:
    if not password: return ""
    return base64.urlsafe_b64encode(cipher_suite.encrypt(password.encode())).decode()

def decrypt_password(encrypted_password: str) -> str:
    if not encrypted_password: return ""
    try: return cipher_suite.decrypt(base64.urlsafe_b64decode(encrypted_password.encode())).decode()
    except Exception: return ""

class SongdoTennisBooking:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.auth_token = None
        self.courts_info = None
        self.user_id = None

    def login(self, email: str, password: str) -> tuple[bool, str]:
        try:
            url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
            payload = {"email": email, "password": password}
            response = self.session.post(url, headers={**HEADERS, "Content-Type": "application/json"}, json=payload, timeout=10)
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                self.user_id = data.get('user', {}).get('id')
                self.session.headers['Authorization'] = f'Bearer {self.auth_token}'
                return True, "성공"
            return False, response.json().get('error_description', '로그인 실패')
        except Exception as e: return False, str(e)

    def get_all_courts(self) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            url = f"{SUPABASE_URL}/rest/v1/courts?select=*"
            response = self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10)
            courts = response.json()
            self.courts_info = {int(re.search(r'\d+', c['name']).group()): c['id'] for c in courts if re.search(r'\d+', c.get('name', ''))}
            return courts
        except: return []

    def get_my_reservations_details(self) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            url = f"{SUPABASE_URL}/rest/v1/reservations?select=id,created_at,slot_id,slots(*,courts(*))&order=created_at.desc"
            return self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10).json()
        except: return []

    def get_payment_statuses(self) -> Dict[str, str]:
        if not self.auth_token or not self.user_id: return {}
        try:
            url = f"{SUPABASE_URL}/rest/v1/user_reservations?select=id,payment_status&user_id=eq.{self.user_id}"
            return {item['id']: item.get('payment_status') for item in self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10).json()}
        except: return {}

    def cancel_reservation(self, reservation_id: str) -> tuple[bool, str]:
        if not self.auth_token: return False, "로그인 필요"
        try:
            url = "https://ydiivmmorbqbvrahrutd.functions.supabase.co/register-cancellation-request"
            response = self.session.post(url, json={"reservation_id": reservation_id}, timeout=10)
            if response.status_code == 200: return True, "취소 성공"
            return False, response.json().get('error', '취소 실패')
        except Exception as e: return False, str(e)

    async def get_available_slots_async(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            start_utc = datetime.strptime(start_date, "%Y-%m-%d").astimezone(KST).astimezone(timezone.utc)
            end_utc = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).astimezone(KST).astimezone(timezone.utc)
            url = f"{SUPABASE_URL}/rest/v1/rpc/get_slots_between"
            payload = {"range_start": start_utc.isoformat(), "range_end": end_utc.isoformat()}
            headers = {**HEADERS, "Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=5) as response:
                    if response.status == 200: return [s for s in await response.json() if s.get('is_available')]
            return []
        except: return []

    async def reserve_slot_async(self, session: aiohttp.ClientSession, slot_id: str) -> Dict[str, Any]:
        if not self.auth_token: return {'success': False, 'message': '토큰 없음'}
        try:
            url = f"{SUPABASE_URL}/functions/v1/reserve-slot"
            headers = {**HEADERS, "Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
            async with session.post(url, headers=headers, json={"slotId": slot_id}, timeout=5) as response:
                if response.status == 200: return {'success': True, 'message': '성공'}
                return {'success': False, 'message': f"HTTP {response.status}"}
        except Exception as e: return {'success': False, 'message': str(e)}

# ==============================================================================
# 3. 새로운 UI 클래스 (All-in-One Dashboard Layout)
# ==============================================================================
class TennisBookingGUI:
    def __init__(self):
        # 1. [핵심] 고해상도(High DPI) 모니터 대응 코드 추가
        # 이 코드가 있어야 4K 모니터나 노트북 배율(125%, 150%) 설정 시 UI가 흐릿하지 않고 선명하게 나옵니다.
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass

        # 테마: cosmo (가독성 우수)
        self.root = ttk.Window(themename="cosmo")
        self.root.title(f"송도 테니스 예약 통합 매니저 (v{APP_VERSION})")
        
        # 폰트 설정
        self.default_font = ("Malgun Gothic", 10)
        self.header_font = ("Malgun Gothic", 11, "bold")
        self.style = ttk.Style()
        self.style.configure('.', font=self.default_font)
        self.style.configure('Treeview.Heading', font=self.header_font)
        self.style.configure('Treeview', font=("Malgun Gothic", 10), rowheight=30)
        
        # 해상도 적응형 시작: 화면 전체 크기(Maximized)로 시작
        self.root.state('zoomed')
        
        # 변수 초기화
        self.init_variables()
        
        # UI 생성
        self.create_ui()
        
        # 시스템 초기화
        self.sync_time()
        self.load_config()
        self.update_current_time()

    def init_variables(self):
        self.booking_api = SongdoTennisBooking()
        self.analytics_logger = AnalyticsLogger(ANALYTICS_URL, ANALYTICS_KEY)
        self.is_logged_in = False
        self.is_booking_active = False
        self.config_file = os.path.join(DATA_DIR, "tennis_booking_config.json")
        self.machine_id = self.load_or_create_machine_id()
        self.booking_targets = []
        self.reservation_data = {}
        self.time_offset = 0
        
        # ★ [창 중복 방지용 변수들]
        self.popup_window = None        # 자동 추가 창용
        self.time_setting_window = None # 시간 설정 창용 (새로 추가됨)
        
        # 예약 시작 시간 기본값 (매월 25일 10시)
        now = datetime.now()
        self.target_year = ttk.IntVar(value=now.year)
        self.target_month = ttk.IntVar(value=now.month)
        self.target_day = ttk.IntVar(value=25)      # 25일 고정
        self.target_hour = ttk.IntVar(value=10)     # 10시 고정
        self.target_minute = ttk.IntVar(value=0)
        self.target_second = ttk.IntVar(value=0)

    def load_or_create_machine_id(self):
        mid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
        if os.path.exists(self.config_file):
            try: 
                with open(self.config_file, 'r', encoding='utf-8') as f: mid = json.load(f).get('machine_id', mid)
            except: pass
        return mid

    # ==========================================================================
    # Responsive UI Layout
    # ==========================================================================
    def create_ui(self):
        # 1. 창 최소 크기 설정
        self.root.minsize(1100, 750)
        
        # 2. 전체 그리드 가중치 설정
        self.root.grid_rowconfigure(1, weight=1) 
        self.root.grid_columnconfigure(0, weight=1)

        # 3. 헤더 (상단 고정)
        header_frame = ttk.Frame(self.root, padding=(20, 10), bootstyle="primary")
        header_frame.grid(row=0, column=0, sticky="ew")
        
        ttk.Label(header_frame, text="🎾 송도 테니스 예약 통합 대시보드", font=("Malgun Gothic", 18, "bold"), foreground="white", background="#2780e3").pack(side=LEFT)
        self.server_time_lbl = ttk.Label(header_frame, text="--:--:--", font=("Consolas", 16, "bold"), foreground="white", background="#2780e3")
        self.server_time_lbl.pack(side=RIGHT)

        # 4. 메인 컨테이너 (좌우 분할)
        main_pane = ttk.Panedwindow(self.root, orient=HORIZONTAL)
        main_pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)

        # ======================================================================
        # [핵심 수정] 좌측 패널: Wrapper Frame 사용 (에러 해결)
        # PanedWindow에 바로 ScrolledFrame을 넣으면 에러가 나므로, 일반 Frame을 먼저 넣습니다.
        # ======================================================================
        left_container = ttk.Frame(main_pane) 
        main_pane.add(left_container, weight=0) # PanedWindow에 일반 프레임 추가

        # ScrolledFrame import (경고 메시지 해결을 위한 최신 경로 우선 시도)
        try:
            from ttkbootstrap.widgets import ScrolledFrame
        except ImportError:
            from ttkbootstrap.scrolled import ScrolledFrame

        # 일반 프레임(left_container) 안에 스크롤 프레임을 꽉 차게 배치
        left_scroll = ScrolledFrame(left_container, autohide=False, width=380)
        left_scroll.pack(fill=BOTH, expand=True)
        
        # 내용을 스크롤 프레임 안에 채움
        self.create_left_panel(left_scroll) 

        # ======================================================================
        # [우측 패널]
        # ======================================================================
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame, weight=4) 

        # 우측 상하 분할
        right_split = ttk.Panedwindow(right_frame, orient=VERTICAL)
        right_split.pack(fill=BOTH, expand=True)

        # 우측 상단: 예약 목표
        target_frame = ttk.Labelframe(right_split, text=" 🎯 예약 목표 (Target List) ", padding=10, bootstyle="info")
        right_split.add(target_frame, weight=2)
        self.create_target_view(target_frame)

        # 우측 하단: 결과 및 로그
        bottom_split = ttk.Panedwindow(right_split, orient=HORIZONTAL)
        right_split.add(bottom_split, weight=1)

        result_frame = ttk.Labelframe(bottom_split, text=" 📅 내 예약 현황 ", padding=10, bootstyle="success")
        bottom_split.add(result_frame, weight=1)
        self.create_result_view(result_frame)

        log_frame = ttk.Labelframe(bottom_split, text=" 📝 시스템 로그 ", padding=10, bootstyle="secondary")
        bottom_split.add(log_frame, weight=1)
        self.create_log_view(log_frame)

    def create_left_panel(self, parent):
        # 스크롤바가 있는 부모라면 내부 컨텐츠 프레임에 배치 필요 여부 확인
        # ttkbootstrap ScrolledFrame은 바로 widget을 pack/grid 해도 됨
        
        # Grid 레이아웃을 사용하여 꽉 차게 배치
        parent.columnconfigure(0, weight=1)

        container = ttk.Frame(parent, padding=10)
        container.pack(fill=BOTH, expand=True)

        # 1. 로그인 그룹
        login_group = ttk.Labelframe(container, text="사용자 인증", padding=10, bootstyle="primary")
        login_group.pack(fill=X, pady=(0, 10))
        
        ttk.Label(login_group, text="ID").pack(anchor=W)
        self.entry_id = ttk.Entry(login_group)
        self.entry_id.pack(fill=X, pady=(0, 5))
        
        ttk.Label(login_group, text="PW").pack(anchor=W)
        self.entry_pw = ttk.Entry(login_group, show="●")
        self.entry_pw.pack(fill=X, pady=(0, 5))
        self.entry_pw.bind("<Return>", lambda e: self.login())
        
        btn_f = ttk.Frame(login_group)
        btn_f.pack(fill=X, pady=5)
        # 비율(weight)을 줘서 버튼 크기 균등 분배
        btn_f.columnconfigure(0, weight=1)
        btn_f.columnconfigure(1, weight=1)
        
        self.btn_login = ttk.Button(btn_f, text="로그인", command=self.login, bootstyle="primary")
        self.btn_login.grid(row=0, column=0, sticky="ew", padx=(0, 2))
        
        self.btn_logout = ttk.Button(btn_f, text="로그아웃", command=self.logout, bootstyle="secondary", state=DISABLED)
        self.btn_logout.grid(row=0, column=1, sticky="ew", padx=(2, 0))
        
        self.lbl_login_status = ttk.Label(login_group, text="로그인 필요", foreground="gray", font=("", 9))
        self.lbl_login_status.pack(pady=(5,0))

        # 2. 실행 제어 그룹
        ctrl_group = ttk.Labelframe(container, text="예약 제어", padding=10, bootstyle="success")
        ctrl_group.pack(fill=X, pady=(0, 10))

        ttk.Button(ctrl_group, text="🕒 시간 설정", command=self.open_time_setting, bootstyle="info-outline").pack(fill=X, pady=5)
        self.lbl_target_time = ttk.Label(ctrl_group, text="목표: 미설정", font=("", 10, "bold"), foreground="blue")
        self.lbl_target_time.pack()

        ttk.Separator(ctrl_group).pack(fill=X, pady=10)
        
        self.lbl_countdown = ttk.Label(ctrl_group, text="00:00:00", font=("Helvetica", 28, "bold"), anchor=CENTER, foreground="#d9534f")
        self.lbl_countdown.pack(fill=X)
        
        self.btn_start = ttk.Button(ctrl_group, text="🚀 시작", command=self.start_booking, bootstyle="success", state=NORMAL, padding=10)
        self.btn_start.pack(fill=X, pady=(10, 5))
        self.btn_stop = ttk.Button(ctrl_group, text="⏹ 중지", command=self.stop_booking, bootstyle="danger", state=DISABLED)
        self.btn_stop.pack(fill=X)

        # 3. 자동 추가 도구
        tool_group = ttk.Labelframe(container, text="빠른 추가 도구", padding=10, bootstyle="warning")
        tool_group.pack(fill=X, pady=(0, 10))
        
        ttk.Label(tool_group, text="다음달 자동 추가:", font=("", 9)).pack(anchor=W)
        
        btn_grid = ttk.Frame(tool_group)
        btn_grid.pack(fill=X)
        btn_grid.columnconfigure(0, weight=1)
        btn_grid.columnconfigure(1, weight=1)
        
        ttk.Button(btn_grid, text="평일(월~금)", command=lambda: self.run_auto_add("weekday"), bootstyle="secondary-outline").grid(row=0, column=0, sticky="ew", padx=(0,2))
        ttk.Button(btn_grid, text="주말(토,일)", command=lambda: self.run_auto_add("weekend"), bootstyle="secondary-outline").grid(row=0, column=1, sticky="ew", padx=(2,0))

    def create_target_view(self, parent):
        # [수정] Grid 레이아웃 적용: 창을 줄여도 입력창들이 비율대로 줄어들고 겹치지 않음
        input_frame = ttk.Frame(parent)
        input_frame.pack(fill=X, pady=(0, 10))
        
        # 가중치 설정: 날짜, 코트, 시간 콤보박스가 공간을 나눠가짐 (버튼은 고정)
        input_frame.columnconfigure(0, weight=2) # 날짜
        input_frame.columnconfigure(1, weight=2) # 코트
        input_frame.columnconfigure(2, weight=1) # 시간
        input_frame.columnconfigure(3, weight=0) # 버튼들
        
        # 1. 날짜 입력
        self.cal_target = DateEntry(input_frame, bootstyle="primary", dateformat="%Y-%m-%d")
        self.cal_target.grid(row=0, column=0, sticky="ew", padx=2)
        
        # 2. 코트 선택
        self.combo_court = ttk.Combobox(input_frame, values=[f"{i}번 코트" for i in range(5, 18)], state="readonly")
        self.combo_court.set("5번 코트")
        self.combo_court.grid(row=0, column=1, sticky="ew", padx=2)
        
        # 3. 시간 선택
        self.combo_time = ttk.Combobox(input_frame, values=["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"], state="readonly")
        self.combo_time.set("06:00")
        self.combo_time.grid(row=0, column=2, sticky="ew", padx=2)
        
        # 4. 버튼 그룹 (우측 정렬)
        btn_group = ttk.Frame(input_frame)
        btn_group.grid(row=0, column=3, sticky="e", padx=(5,0))
        
        ttk.Button(btn_group, text="추가", command=self.add_target, bootstyle="primary").pack(side=LEFT, padx=2)
        ttk.Button(btn_group, text="선택삭제", command=self.delete_target, bootstyle="secondary-outline").pack(side=LEFT, padx=2)
        ttk.Button(btn_group, text="전체삭제", command=self.clear_targets, bootstyle="danger-outline").pack(side=LEFT, padx=2)

        # 트리뷰 (리스트)
        cols = ("날짜", "코트", "시간")
        self.tree_targets = ttk.Treeview(parent, columns=cols, show="headings", bootstyle="info")
        for col in cols:
            self.tree_targets.heading(col, text=col)
            self.tree_targets.column(col, anchor=CENTER, width=100) # 기본 너비 설정
        
        sc = ttk.Scrollbar(parent, orient=VERTICAL, command=self.tree_targets.yview)
        self.tree_targets.configure(yscrollcommand=sc.set)
        
        self.tree_targets.pack(side=LEFT, fill=BOTH, expand=True)
        sc.pack(side=RIGHT, fill=Y)

    def create_result_view(self, parent):
        top = ttk.Frame(parent)
        top.pack(fill=X)
        ttk.Button(top, text="새로고침", command=self.load_my_reservations, bootstyle="link", cursor="hand2").pack(anchor=E)

        cols = ("날짜", "시간", "코트", "상태")
        self.tree_results = ttk.Treeview(parent, columns=cols, show="headings", bootstyle="success")
        self.tree_results.heading("날짜", text="날짜"); self.tree_results.column("날짜", width=90, anchor=CENTER)
        self.tree_results.heading("시간", text="시간"); self.tree_results.column("시간", width=60, anchor=CENTER)
        self.tree_results.heading("코트", text="코트"); self.tree_results.column("코트", width=70, anchor=CENTER)
        self.tree_results.heading("상태", text="상태"); self.tree_results.column("상태", width=80, anchor=CENTER)
        
        sc = ttk.Scrollbar(parent, orient=VERTICAL, command=self.tree_results.yview)
        self.tree_results.configure(yscrollcommand=sc.set)
        self.tree_results.pack(side=LEFT, fill=BOTH, expand=True)
        sc.pack(side=RIGHT, fill=Y)
        self.tree_results.bind('<Double-1>', self.on_result_double_click)

    def create_log_view(self, parent):
        self.txt_log = scrolledtext.ScrolledText(parent, state='disabled', font=("Consolas", 9), height=10)
        self.txt_log.pack(fill=BOTH, expand=True)

    # ==========================================================================
    # Logic Implementation
    # ==========================================================================
    def log_message(self, msg, level="info"):
        t = datetime.now().strftime("%H:%M:%S")
        self.txt_log.configure(state='normal')
        self.txt_log.insert(END, f"[{t}] {msg}\n")
        self.txt_log.see(END)
        self.txt_log.configure(state='disabled')
        if level == "error":
            try: ToastNotification(title="오류", message=msg, duration=3000, bootstyle="danger").show_toast()
            except: pass

    def update_current_time(self):
        try:
            now = datetime.now() + timedelta(seconds=self.time_offset)
            self.server_time_lbl.config(text=now.strftime("%H:%M:%S"))
            if hasattr(self, 'booking_target_datetime'):
                diff = self.booking_target_datetime - now
                if diff.total_seconds() > 0:
                    self.lbl_countdown.config(text=str(diff).split('.')[0], bootstyle="primary")
                else:
                    self.lbl_countdown.config(text="00:00:00", bootstyle="danger")
        except: pass
        self.root.after(100, self.update_current_time)

    def sync_time(self): threading.Thread(target=self._sync_time_thread, daemon=True).start()
    def _sync_time_thread(self):
        try:
            self.time_offset = ntplib.NTPClient().request('time.bora.net', version=3).offset
            self.log_message(f"시간 동기화 완료 (오차: {self.time_offset:.3f}초)")
        except: self.log_message("시간 동기화 실패", "error")

    # 로그인 로직
    def login(self):
        eid, epw = self.entry_id.get(), self.entry_pw.get()
        if not eid or not epw: return Messagebox.show_warning("ID/PW 입력 필요", "알림")
        self.btn_login.config(state=DISABLED, text="...")
        threading.Thread(target=self._login_thread, args=(eid, epw), daemon=True).start()

    def _login_thread(self, eid, epw):
        success, msg = self.booking_api.login(eid, epw)
        if success:
            self.is_logged_in = True
            self.booking_api.get_all_courts()
            self.load_my_reservations()
            self.root.after(0, lambda: self._login_success_ui(eid))
        else:
            self.root.after(0, lambda: self._login_fail_ui(msg))

    def _login_success_ui(self, eid):
        self.lbl_login_status.config(text=f"접속중: {eid}", foreground="green")
        self.btn_login.config(text="완료", state=DISABLED)
        self.btn_logout.config(state=NORMAL)
        self.entry_id.config(state=DISABLED); self.entry_pw.config(state=DISABLED)
        self.log_message("로그인 성공")
        self.save_config()

    def _login_fail_ui(self, msg):
        self.btn_login.config(state=NORMAL, text="로그인")
        Messagebox.show_error(msg, "실패")
        self.log_message(f"로그인 실패: {msg}", "error")

    def logout(self):
        self.is_logged_in = False
        self.lbl_login_status.config(text="로그아웃", foreground="gray")
        self.btn_login.config(state=NORMAL, text="로그인")
        self.btn_logout.config(state=DISABLED)
        self.entry_id.config(state=NORMAL); self.entry_pw.config(state=NORMAL)
        self.log_message("로그아웃")

    # 목표 관리
    def add_target(self):
        d = self.cal_target.entry.get()
        c_txt = self.combo_court.get()
        c_num = int(re.search(r'\d+', c_txt).group())
        t_val = self.combo_time.get()
        
        if any(x['date']==d and x['court']==c_num and x['time']==t_val for x in self.booking_targets): return
        self.booking_targets.append({'date': d, 'court': c_num, 'time': t_val})
        self.update_target_list()
        self.log_message(f"추가: {d} {t_val} {c_num}코트")

    def delete_target(self):
        sel = self.tree_targets.selection()
        if not sel: return
        for i in sel:
            v = self.tree_targets.item(i)['values']
            c_num = int(re.search(r'\d+', v[1]).group())
            self.booking_targets = [t for t in self.booking_targets if not (t['date']==v[0] and t['court']==c_num and t['time']==v[2])]
        self.update_target_list()

    def clear_targets(self):
        if Messagebox.okcancel("전체 삭제?", "확인"):
            self.booking_targets = []
            self.update_target_list()

    def update_target_list(self):
        self.tree_targets.delete(*self.tree_targets.get_children())
        for t in sorted(self.booking_targets, key=lambda x: (x['date'], x['time'])):
            self.tree_targets.insert("", END, values=(t['date'], f"{t['court']}번 코트", t['time']))
        if self.is_logged_in: self.analytics_logger.sync_targets(self.entry_id.get(), self.booking_targets)
        self.save_config()

    # ★ 자동 추가 로직 구현
    def run_auto_add(self, mode):
        # 1. 이미 창이 열려있는지 확인 (창이 존재하면 맨 앞으로 가져오고 종료)
        if getattr(self, 'popup_window', None) is not None:
            try:
                if self.popup_window.winfo_exists():
                    self.popup_window.lift()        # 창을 맨 앞으로
                    self.popup_window.focus_force() # 포커스 주기
                    return
            except tk.TclError:
                self.popup_window = None

        try:
            # 2. 새 팝업창 생성
            self.popup_window = ttk.Toplevel(self.root)
            self.popup_window.title(f"다음달 {mode} 일괄 추가")
            self.popup_window.geometry("400x500")
            
            # 중앙 정렬
            x = self.root.winfo_x() + (self.root.winfo_width()//2) - 200
            y = self.root.winfo_y() + (self.root.winfo_height()//2) - 250
            self.popup_window.geometry(f"+{x}+{y}")
            
            # 창 닫힐 때 변수 초기화
            def on_close():
                self.popup_window.destroy()
                self.popup_window = None
            self.popup_window.protocol("WM_DELETE_WINDOW", on_close)

            # -----------------------------------------------------------
            # [Step 1] 시간 및 코트 선택
            # -----------------------------------------------------------
            def build_step_1():
                for w in self.popup_window.winfo_children(): w.destroy()

                f = ttk.Frame(self.popup_window, padding=20)
                f.pack(fill=BOTH, expand=True)

                ttk.Label(f, text="1단계: 시간과 코트 선택", font=("Malgun Gothic", 12, "bold")).pack(pady=(0,15))

                # 시간
                row1 = ttk.Frame(f)
                row1.pack(fill=X, pady=5)
                ttk.Label(row1, text="시간:", width=6).pack(side=LEFT)
                cb_time = ttk.Combobox(row1, values=["06:00","08:00","10:00","12:00","14:00","16:00","18:00","20:00"], state="readonly")
                cb_time.set("06:00")
                cb_time.pack(side=LEFT, fill=X, expand=True)

                # 코트 (다중 선택)
                ttk.Label(f, text="코트 선택 (체크한 코트들이 일괄 추가됨):", font=("Malgun Gothic", 10)).pack(anchor=W, pady=(15, 5))
                court_frame = ttk.Labelframe(f, padding=10)
                court_frame.pack(fill=BOTH, expand=True)

                self.temp_court_vars = {} 
                for i in range(5, 18):
                    v = tk.BooleanVar(value=False)
                    if i == 5: v.set(True)
                    self.temp_court_vars[i] = v
                    chk = ttk.Checkbutton(court_frame, text=f"{i}번", variable=v)
                    row = (i - 5) // 3
                    col = (i - 5) % 3
                    chk.grid(row=row, column=col, sticky=W, padx=10, pady=5)

                def go_next():
                    sel_time = cb_time.get()
                    selected_courts = [c for c, var in self.temp_court_vars.items() if var.get()]
                    if not selected_courts:
                        Messagebox.show_warning("최소한 하나의 코트는 선택해야 합니다.", "알림")
                        return
                    build_step_2(sel_time, selected_courts)

                ttk.Button(f, text="다음 (날짜 선택) >", command=go_next, bootstyle="primary").pack(fill=X, pady=20)

            # -----------------------------------------------------------
            # [Step 2] 날짜 선택
            # -----------------------------------------------------------
            def build_step_2(sel_time, selected_courts):
                for w in self.popup_window.winfo_children(): w.destroy()
                
                # 날짜 계산
                today = datetime.now()
                if today.month == 12: next_month = datetime(today.year + 1, 1, 1)
                else: next_month = datetime(today.year, today.month + 1, 1)
                
                y, m = next_month.year, next_month.month
                _, last_day = calendar.monthrange(y, m)

                candidate_dates = []
                for day in range(1, last_day + 1):
                    dt = datetime(y, m, day)
                    wd = dt.weekday()
                    
                    is_target = False
                    if mode == "weekday" and wd < 5: is_target = True
                    elif mode == "weekend" and wd >= 5: is_target = True
                    
                    if is_target:
                        d_str = dt.strftime("%Y-%m-%d")
                        w_str = ["월","화","수","목","금","토","일"][wd]
                        candidate_dates.append((d_str, w_str))

                if not candidate_dates:
                    Messagebox.show_info("추가할 수 있는 날짜가 없습니다.", "알림")
                    on_close()
                    return

                # UI 구성
                f = ttk.Frame(self.popup_window, padding=20)
                f.pack(fill=BOTH, expand=True)
                
                header_text = f"2단계: 날짜 선택\n(시간: {sel_time} / 코트: {len(selected_courts)}개 선택됨)"
                ttk.Label(f, text=header_text, font=("Malgun Gothic", 11, "bold"), justify=CENTER).pack(pady=(0,10))

                # 스크롤 프레임 사용 (오류 방지 적용)
                try:
                    from ttkbootstrap.widgets import ScrolledFrame
                    sf = ScrolledFrame(f, autohide=True)
                except ImportError:
                    try:
                        from ttkbootstrap.scrolled import ScrolledFrame
                        sf = ScrolledFrame(f, autohide=True)
                    except:
                        sf = ttk.Frame(f)

                sf.pack(fill=BOTH, expand=True, padx=5, pady=5)

                date_vars = {}
                for d_str, w_str in candidate_dates:
                    var = tk.BooleanVar(value=False) # 기본값 체크 해제
                    label_text = f"{d_str} ({w_str})"
                    cb = ttk.Checkbutton(sf, text=label_text, variable=var, bootstyle="round-toggle")
                    cb.pack(anchor=W, pady=2, padx=10)
                    date_vars[d_str] = var

                def do_add():
                    try:
                        added_cnt = 0
                        for d_str, d_var in date_vars.items():
                            if d_var.get():
                                for c_num in selected_courts:
                                    exists = any(t['date']==d_str and t['court']==c_num and t['time']==sel_time for t in self.booking_targets)
                                    if not exists:
                                        self.booking_targets.append({'date': d_str, 'court': c_num, 'time': sel_time})
                                        added_cnt += 1
                        
                        self.update_target_list()
                        Messagebox.show_info(f"총 {added_cnt}건이 추가되었습니다.", "완료")
                        on_close()
                    except Exception as e:
                        Messagebox.show_error(f"오류: {e}", "에러")

                btn_area = ttk.Frame(f)
                btn_area.pack(fill=X, side=BOTTOM, pady=10)

                def toggle_all():
                    if not date_vars: return
                    target = not list(date_vars.values())[0].get()
                    for v in date_vars.values(): v.set(target)

                ttk.Button(btn_area, text="전체 선택/해제", command=toggle_all, bootstyle="info-outline").pack(fill=X, pady=(0,5))
                row_btn = ttk.Frame(btn_area)
                row_btn.pack(fill=X)
                ttk.Button(row_btn, text="< 뒤로", command=build_step_1, bootstyle="secondary").pack(side=LEFT, fill=X, expand=True, padx=(0,5))
                ttk.Button(row_btn, text="최종 추가", command=do_add, bootstyle="primary").pack(side=LEFT, fill=X, expand=True, padx=(5,0))

            build_step_1()
            
        except Exception as e:
            Messagebox.show_error(f"창 열기 실패: {e}", "오류")
            self.popup_window = None

    # 설정 및 예약 실행 로직
    def open_time_setting(self):
        # 1. [중복 방지] 이미 창이 열려있는지 확인
        if getattr(self, 'time_setting_window', None) is not None:
            try:
                if self.time_setting_window.winfo_exists():
                    self.time_setting_window.lift()
                    self.time_setting_window.focus_force()
                    return
            except tk.TclError:
                self.time_setting_window = None

        # 2. 새 설정 창 생성
        self.time_setting_window = ttk.Toplevel(self.root)
        self.time_setting_window.title("시작 시간 설정")
        self.time_setting_window.geometry("350x300")
        
        # 중앙 배치
        x = self.root.winfo_x() + (self.root.winfo_width()//2) - 175
        y = self.root.winfo_y() + (self.root.winfo_height()//2) - 150
        self.time_setting_window.geometry(f"+{x}+{y}")
        
        # 창 닫힘 이벤트 (변수 초기화)
        def on_close():
            self.time_setting_window.destroy()
            self.time_setting_window = None
        self.time_setting_window.protocol("WM_DELETE_WINDOW", on_close)
        
        f = ttk.Frame(self.time_setting_window, padding=20)
        f.pack(fill=BOTH, expand=True)
        
        ttk.Label(f, text="예약 시작 시간", font=("", 11, "bold")).pack(pady=(0, 10))
        
        # --- 날짜 스핀박스 ---
        r1 = ttk.Frame(f); r1.pack(pady=5)
        # 년 (순환 X)
        ttk.Spinbox(r1, from_=2024, to=2030, textvariable=self.target_year, width=5).pack(side=LEFT)
        ttk.Label(r1, text="년").pack(side=LEFT, padx=2)
        # 월 (1~12 순환)
        ttk.Spinbox(r1, from_=1, to=12, textvariable=self.target_month, width=3, wrap=True).pack(side=LEFT)
        ttk.Label(r1, text="월").pack(side=LEFT, padx=2)
        # 일 (1~31 순환)
        ttk.Spinbox(r1, from_=1, to=31, textvariable=self.target_day, width=3, wrap=True).pack(side=LEFT)
        ttk.Label(r1, text="일").pack(side=LEFT)
        
        # --- 시간 스핀박스 (순환 적용됨 wrap=True) ---
        r2 = ttk.Frame(f); r2.pack(pady=5)
        
        # 시 (0~23 순환)
        ttk.Spinbox(r2, from_=0, to=23, textvariable=self.target_hour, width=3, wrap=True).pack(side=LEFT)
        ttk.Label(r2, text="시").pack(side=LEFT, padx=2)
        
        # 분 (0~59 순환)
        ttk.Spinbox(r2, from_=0, to=59, textvariable=self.target_minute, width=3, wrap=True).pack(side=LEFT, padx=2)
        ttk.Label(r2, text="분").pack(side=LEFT, padx=2)
        
        # 초 (0~59 순환)
        ttk.Spinbox(r2, from_=0, to=59, textvariable=self.target_second, width=3, wrap=True).pack(side=LEFT, padx=2)
        ttk.Label(r2, text="초").pack(side=LEFT)
        
        # -----------------------------------------------------
        # 로직 함수들
        # -----------------------------------------------------
        def save():
            self.calc_target_time()
            self.save_config()
            on_close() # 창 닫기
            Messagebox.show_info("설정이 저장되었습니다.\n(이번 달 동안만 유지됩니다)", "저장 완료")

        def reset_default():
            now = datetime.now()
            self.target_year.set(now.year)
            self.target_month.set(now.month)
            self.target_day.set(25)
            self.target_hour.set(10)
            self.target_minute.set(0)
            self.target_second.set(0)
            
            # 메인 화면 즉시 갱신
            self.calc_target_time()
            Messagebox.show_info("이번 달 25일 10시로 초기화되었습니다.", "초기화")

        # -----------------------------------------------------
        # 버튼 영역
        # -----------------------------------------------------
        btn_area = ttk.Frame(f)
        btn_area.pack(fill=X, pady=20)
        
        ttk.Button(btn_area, text="↻ 초기화 (25일 10시)", command=reset_default, bootstyle="secondary-outline").pack(fill=X, pady=2)
        ttk.Button(btn_area, text="💾 설정 저장", command=save, bootstyle="success").pack(fill=X, pady=2)

    def calc_target_time(self):
        try:
            self.booking_target_datetime = datetime(
                self.target_year.get(), self.target_month.get(), self.target_day.get(),
                self.target_hour.get(), self.target_minute.get(), self.target_second.get()
            )
            self.lbl_target_time.config(text=f"목표: {self.booking_target_datetime.strftime('%Y-%m-%d %H:%M:%S')}")
        except: self.lbl_target_time.config(text="시간 오류")

    def start_booking(self):
        if not self.is_logged_in: return Messagebox.show_warning("로그인 필요", "경고")
        if not self.booking_targets: return Messagebox.show_warning("목표 없음", "경고")
        
        self.is_booking_active = True
        self.btn_start.config(state=DISABLED)
        self.btn_stop.config(state=NORMAL)
        self.analytics_logger.log_booking_targets(self.entry_id.get(), self.booking_targets)
        threading.Thread(target=lambda: asyncio.run(self.booking_loop()), daemon=True).start()

    def stop_booking(self):
        self.is_booking_active = False
        self.btn_start.config(state=NORMAL)
        self.btn_stop.config(state=DISABLED)
        self.log_message("예약 프로세스 정지")

    async def booking_loop(self):
        self.log_message("대기 중...")
        while self.is_booking_active:
            now = datetime.now() + timedelta(seconds=self.time_offset)
            rem = (self.booking_target_datetime - now).total_seconds()
            if rem <= 0: break
            await asyncio.sleep(0.05 if rem < 2 else 0.5)
        
        if not self.is_booking_active: return
        self.log_message("🔥 예약 시작!")
        
        dates = sorted(list(set(t['date'] for t in self.booking_targets)))
        if not dates: return
        success_set = set()
        start_t = time.time()
        
        async with aiohttp.ClientSession() as sess:
            while self.is_booking_active:
                if time.time() - start_t > 30: break
                if len(success_set) >= len(self.booking_targets): break
                
                slots = await self.booking_api.get_available_slots_async(dates[0], dates[-1])
                if not slots:
                    await asyncio.sleep(0.1); continue
                
                tasks = []
                for s in slots:
                    try:
                        st = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00')).astimezone(KST)
                        key = f"{st.strftime('%Y-%m-%d')}|{s.get('court_id')}|{st.strftime('%H:%M')}"
                        
                        for t in self.booking_targets:
                            t_cid = self.booking_api.courts_info.get(t['court'])
                            t_key = f"{t['date']}|{t_cid}|{t['time']}"
                            if key == t_key and t_key not in success_set:
                                task = asyncio.create_task(self._try_reserve(sess, s['id'], f"{t['date']} {t['time']}", t_key, success_set))
                                tasks.append(task)
                    except: continue
                if tasks: await asyncio.gather(*tasks)
                await asyncio.sleep(0.2)
        
        self.root.after(0, self.stop_booking)
        self.root.after(0, self.load_my_reservations)

    async def _try_reserve(self, session, slot_id, info, key, success_set):
        # 예약 요청 전송
        res = await self.booking_api.reserve_slot_async(session, slot_id)
        
        # 결과 처리
        if res['success']:
            self.log_message(f"✅ 성공: {info}")
            success_set.add(key)
        else:
            # 실패 시, 서버가 보내준 구체적인 메시지(msg)를 함께 출력
            fail_reason = res.get('message', '알 수 없는 오류')
            self.log_message(f"❌ 실패: {info} -> 사유: {fail_reason}")

    # 예약 조회 및 취소
    def load_my_reservations(self):
        if not self.is_logged_in: return
        threading.Thread(target=self._fetch_reservations, daemon=True).start()

    def _fetch_reservations(self):
        data = self.booking_api.get_my_reservations_details()
        status_map = self.booking_api.get_payment_statuses()
        clean = []
        for d in data:
            try:
                st = datetime.fromisoformat(d['slots']['start_time'].replace('Z', '+00:00')).astimezone(KST)
                pid = d['id']
                paid = status_map.get(pid) in ['paid', 'completed', 'payment_completed']
                clean.append({'id':pid, 'date':st.strftime('%Y-%m-%d'), 'time':st.strftime('%H:%M'), 'court':d['slots']['courts']['name'], 'status':'결제완료' if paid else '미결제', 'paid':paid})
            except: pass
        self.root.after(0, lambda: self._update_res_ui(clean))

    def _update_res_ui(self, data):
        self.tree_results.delete(*self.tree_results.get_children())
        self.reservation_data = {}
        for d in data:
            iid = self.tree_results.insert("", END, values=(d['date'], d['time'], d['court'], d['status']))
            self.reservation_data[iid] = d

    def on_result_double_click(self, event):
        iid = self.tree_results.identify_row(event.y)
        if not iid: return
        d = self.reservation_data.get(iid)
        if not d or d['paid']: return Messagebox.show_info("결제된 건은 취소 불가", "안내")
        if Messagebox.okcancel("예약 취소?", "확인"): threading.Thread(target=lambda: self._cancel_res(d['id']), daemon=True).start()

    def _cancel_res(self, rid):
        ok, msg = self.booking_api.cancel_reservation(rid)
        if ok: self.log_message("취소 성공"); self.load_my_reservations()
        else: self.log_message(f"취소 실패: {msg}", "error")

    # Config
    def save_config(self):
        # 현재 '년-월' 정보를 함께 저장하여, 다음 달이 되면 구별할 수 있게 함
        current_month_str = datetime.now().strftime("%Y-%m")
        
        cfg = {
            'username': self.entry_id.get(),
            'password': encrypt_password(self.entry_pw.get()),
            'machine_id': self.machine_id,
            'booking_targets': self.booking_targets,
            # ★ 저장 시점의 '월' 정보 저장
            'saved_month': current_month_str, 
            'target_time': {
                'year': self.target_year.get(), 'month': self.target_month.get(), 
                'day': self.target_day.get(), 'hour': self.target_hour.get(), 
                'minute': self.target_minute.get(), 'second': self.target_second.get()
            }
        }
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(cfg, f)

    def load_config(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
                
            # 1. 계정 정보 및 예약 리스트 복구 (항상 유지)
            if 'username' in cfg:
                self.entry_id.delete(0, END)
                self.entry_id.insert(0, cfg['username'])
            if 'password' in cfg:
                self.entry_pw.delete(0, END)
                self.entry_pw.insert(0, decrypt_password(cfg['password']))
            
            self.booking_targets = cfg.get('booking_targets', [])
            self.update_target_list()
            
            # 2. 시간 설정 복구 로직 (★ 월 변경 체크)
            saved_month = cfg.get('saved_month', '')
            current_month = datetime.now().strftime("%Y-%m")
            
            # ★ 저장된 달과 현재 달이 같을 때만 사용자 설정 시간을 불러옴
            if saved_month == current_month:
                t = cfg.get('target_time')
                if t:
                    self.target_year.set(t['year'])
                    self.target_month.set(t['month'])
                    self.target_day.set(t['day'])
                    self.target_hour.set(t['hour'])
                    self.target_minute.set(t['minute'])
                    self.target_second.set(t['second'])
            else:
                # 달이 바뀌었으므로 불러오지 않음 -> init_variables의 기본값(25일 10시) 유지
                self.log_message("새로운 달이 되어 예약 시간이 초기화되었습니다.")
                
        except Exception as e:
            print(f"Config load failed: {e}")

        # 화면 갱신
        self.calc_target_time()

if __name__ == "__main__":
    app = TennisBookingGUI()
    app.root.mainloop()