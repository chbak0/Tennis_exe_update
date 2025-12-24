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
import subprocess

# 🎨 현대적인 UI 라이브러리
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.widgets import DateEntry

# ==============================================================================
# 1. 로깅 설정
# ==============================================================================
DATA_DIR = "app_data"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

LOG_FILE_BASENAME = os.path.join(DATA_DIR, 'app.log')
file_handler = None

def setup_logging():
    global file_handler
    logger = logging.getLogger()
    for handler in logger.handlers[:]:
        handler.close()
        logger.removeHandler(handler)
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler = logging.handlers.TimedRotatingFileHandler(
        LOG_FILE_BASENAME, when='midnight', interval=1, backupCount=30, encoding='utf-8')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    logging.error("예외 발생:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception
setup_logging()

# ==============================================================================
# 2. 설정 및 상수
# ==============================================================================
ANALYTICS_URL = "https://uppuyydtqhaulobevczk.supabase.co"
ANALYTICS_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVwcHV5eWR0cWhhdWxvYmV2Y3prIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI0ODE5NTQsImV4cCI6MjA2ODA1Nzk1NH0.yHz7U7XXV34Dlvs8PAoZ6EyD6vz1y77dAFpbh0_7noc"
APP_VERSION = "1.2.0 Pro"
GITHUB_REPO = "chbak0/Tennis_exe_update"

SUPABASE_URL = "https://ydiivmmorbqbvrahrutd.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlkaWl2bW1vcmJxYnZyYWhydXRkIiwicm9sZSI6ImFub24iLCJpYXQiOjE2NzM3MjA4MDEsImV4cCI6MTk4OTI5NjgwMX0.jcX7WYAImKzfYuLi4exAlvMB1zpfKFf9iWN7_gnbjaI"
HEADERS = {"apikey": SUPABASE_ANON_KEY, "x-client-info": "supabase-py/1.0.0"}
KST = timezone(timedelta(hours=9))
KEY_FILE = os.path.join(DATA_DIR, 'app.key')

# ==============================================================================
# 3. 핵심 로직 클래스 (Analytics, Crypto, API)
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
# 4. Admin Dialog
# ==============================================================================
class AdminPasswordDialog(ttk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.password = None
        self.title("관리자 인증")
        self.geometry("320x150")
        self.resizable(False, False)
        
        # 화면 중앙 배치
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

        main = ttk.Frame(self, padding=20)
        main.pack(fill=BOTH, expand=True)
        ttk.Label(main, text="관리자 비밀번호 입력:", bootstyle="inverse-primary").pack(fill=X, pady=5)
        self.pw_entry = ttk.Entry(main, show="●")
        self.pw_entry.pack(fill=X, pady=5)
        self.pw_entry.focus_set()
        self.pw_entry.bind("<Return>", self.on_ok)
        
        btn_f = ttk.Frame(main)
        btn_f.pack(pady=10)
        ttk.Button(btn_f, text="확인", command=self.on_ok, bootstyle="success", width=8).pack(side=LEFT, padx=5)
        ttk.Button(btn_f, text="취소", command=self.on_cancel, bootstyle="secondary", width=8).pack(side=LEFT, padx=5)

    def on_ok(self, event=None):
        self.password = self.pw_entry.get()
        self.destroy()
    def on_cancel(self):
        self.destroy()

# ==============================================================================
# 5. 메인 GUI 클래스 (UI 디자인 전면 리뉴얼)
# ==============================================================================
class TennisBookingGUI:
    def __init__(self):
        # 테마: cosmo (깔끔한 플랫 디자인)
        self.root = ttk.Window(themename="cosmo")
        self.root.title(f"송도 테니스 예약 매니저 Pro (v{APP_VERSION})")
        
        self.time_offset = 0
        self.analytics_logger = AnalyticsLogger(ANALYTICS_URL, ANALYTICS_KEY)
        
        # 반응형 화면 중앙 배치
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(1200, int(sw * 0.85)), min(900, int(sh * 0.85))
        self.root.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
        self.root.minsize(1000, 700)
        
        # 변수 초기화
        self.booking_api = SongdoTennisBooking()
        self.is_logged_in = False
        self.is_booking_active = False
        self.config_file = os.path.join(DATA_DIR, "tennis_booking_config.json")
        self.machine_id = self.load_or_create_machine_id()
        self.booking_targets = []
        self.reservation_data = {}
        
        now = datetime.now()
        self.booking_year_var = ttk.IntVar(value=now.year)
        self.booking_month_var = ttk.IntVar(value=now.month)
        self.booking_day_var = ttk.IntVar(value=25)
        self.booking_hour_var = ttk.IntVar(value=10)
        self.booking_minute_var = ttk.IntVar(value=0)
        self.booking_second_var = ttk.IntVar(value=0)

        # UI 생성
        self.create_modern_ui()
        
        # 초기화 작업
        self.sync_time()
        self.load_config()
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        threading.Thread(target=self.cleanup_after_update, daemon=True).start()

    def load_or_create_machine_id(self):
        mid = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
        if os.path.exists(self.config_file):
            try: 
                with open(self.config_file, 'r', encoding='utf-8') as f: mid = json.load(f).get('machine_id', mid)
            except: pass
        return mid

    # --- UI Layout ---
    def create_modern_ui(self):
        container = ttk.Frame(self.root, padding=15)
        container.pack(fill=BOTH, expand=True)

        # Split View
        main_pane = ttk.Panedwindow(container, orient=HORIZONTAL)
        main_pane.pack(fill=BOTH, expand=True)

        # [좌측 패널] - 제어
        left_panel = ttk.Frame(main_pane)
        main_pane.add(left_panel, weight=4)

        # 1. 로그인 카드
        self._create_login_card(left_panel)
        
        # 2. 메인 탭 (대시보드 / 목표)
        self.notebook = ttk.Notebook(left_panel, bootstyle="primary")
        self.notebook.pack(fill=BOTH, expand=True, pady=10)
        
        dash_tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(dash_tab, text=" 📊 대시보드 ")
        self._create_dashboard_tab(dash_tab)
        
        target_tab = ttk.Frame(self.notebook, padding=15)
        self.notebook.add(target_tab, text=" 🎯 예약 목표 관리 ")
        self._create_target_tab(target_tab)

        # [우측 패널] - 정보
        right_panel = ttk.Frame(main_pane, padding=(10, 0, 0, 0))
        main_pane.add(right_panel, weight=5)

        # 1. 예약 현황
        self._create_my_bookings_card(right_panel)
        
        # 2. 로그
        self._create_log_card(right_panel)

        self.calculate_booking_time()
        self.update_countdown()
        self.update_current_time()

    def _create_login_card(self, parent):
        card = ttk.Labelframe(parent, text="사용자 인증", padding=15, bootstyle="info")
        card.pack(fill=X, pady=(0, 5))
        
        row1 = ttk.Frame(card)
        row1.pack(fill=X, pady=5)
        
        ttk.Label(row1, text="이메일", width=8).pack(side=LEFT)
        self.username_entry = ttk.Entry(row1)
        self.username_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        
        ttk.Label(row1, text="비밀번호", width=8).pack(side=LEFT, padx=(10, 0))
        self.password_entry = ttk.Entry(row1, show="●")
        self.password_entry.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.password_entry.bind("<Return>", lambda e: self.login())

        row2 = ttk.Frame(card)
        row2.pack(fill=X, pady=(10, 0))
        
        self.login_button = ttk.Button(row2, text="로그인", command=self.login, bootstyle="primary", width=10)
        self.login_button.pack(side=LEFT)
        self.logout_button = ttk.Button(row2, text="로그아웃", command=self.logout, bootstyle="secondary-outline", state=DISABLED, width=10)
        self.logout_button.pack(side=LEFT, padx=5)
        self.login_status_label = ttk.Label(row2, text="로그아웃 상태", bootstyle="inverse-danger", padding=5)
        self.login_status_label.pack(side=RIGHT)

    def _create_dashboard_tab(self, parent):
        hero = ttk.Frame(parent)
        hero.pack(fill=X, pady=10)
        
        self.current_time_label = ttk.Label(hero, text="--:--:--", font=("Consolas", 14), foreground="gray")
        self.current_time_label.pack(anchor="center")
        
        self.countdown_label = ttk.Label(hero, text="READY", font=("Helvetica", 42, "bold"), bootstyle="primary")
        self.countdown_label.pack(anchor="center", pady=(5, 10))
        
        self.booking_time_label = ttk.Label(hero, text="다음 예약 목표: 미설정", font=("Malgun Gothic", 11, "bold"), bootstyle="info")
        self.booking_time_label.pack(anchor="center")
        
        ttk.Separator(parent, orient=HORIZONTAL).pack(fill=X, pady=20)

        ctrl = ttk.Frame(parent)
        ctrl.pack(fill=X, pady=10)
        
        self.start_button = ttk.Button(ctrl, text="🚀 예약 시작", command=self.start_booking, bootstyle="success", padding=15)
        self.start_button.pack(fill=X, pady=5)
        
        self.stop_button = ttk.Button(ctrl, text="⏹ 예약 중지", command=self.stop_booking, state=DISABLED, bootstyle="danger", padding=10)
        self.stop_button.pack(fill=X, pady=5)
        
        settings = ttk.Labelframe(parent, text="설정 관리", padding=10, bootstyle="default")
        settings.pack(fill=X, side=BOTTOM, pady=10)
        
        gf = ttk.Frame(settings)
        gf.pack(fill=X)
        ttk.Button(gf, text="⏰ 시간 설정", command=self.show_booking_time_setting, bootstyle="info-outline").pack(side=LEFT, fill=X, expand=True, padx=2)
        ttk.Button(gf, text="💾 저장", command=self.save_config, bootstyle="secondary-outline").pack(side=LEFT, fill=X, expand=True, padx=2)
        ttk.Button(gf, text="📂 불러오기", command=self.load_config, bootstyle="secondary-outline").pack(side=LEFT, fill=X, expand=True, padx=2)
        ttk.Button(gf, text="🗑 초기화", command=self.reset_all_settings, bootstyle="warning-outline").pack(side=LEFT, fill=X, expand=True, padx=2)

    def _create_target_tab(self, parent):
        form = ttk.Frame(parent)
        form.pack(fill=X, pady=(0, 10))
        
        ttk.Label(form, text="날짜").pack(side=LEFT, padx=(0,5))
        self.target_calendar = DateEntry(form, bootstyle="primary", width=10, dateformat="%Y-%m-%d")
        self.target_calendar.pack(side=LEFT, padx=(0, 10))
        
        ttk.Label(form, text="코트").pack(side=LEFT, padx=(0,5))
        self.target_court_var = ttk.StringVar(value="5번 코트")
        ttk.Combobox(form, textvariable=self.target_court_var, values=[f"{i}번 코트" for i in range(5, 18)], width=8, state="readonly").pack(side=LEFT, padx=(0, 10))
        
        ttk.Label(form, text="시간").pack(side=LEFT, padx=(0,5))
        self.target_time_var = ttk.StringVar(value="06:00")
        ttk.Combobox(form, textvariable=self.target_time_var, values=["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"], width=8, state="readonly").pack(side=LEFT, padx=(0, 10))
        
        ttk.Button(form, text="추가 +", command=self.add_booking_target, bootstyle="primary").pack(side=LEFT, fill=X, expand=True)

        tree_f = ttk.Frame(parent)
        tree_f.pack(fill=BOTH, expand=True)
        
        cols = ('날짜', '코트', '시간')
        self.targets_tree = ttk.Treeview(tree_f, columns=cols, show='headings', bootstyle="primary", height=10)
        for c in cols:
            self.targets_tree.heading(c, text=c)
            self.targets_tree.column(c, anchor="center")
        
        sb = ttk.Scrollbar(tree_f, orient=VERTICAL, command=self.targets_tree.yview)
        self.targets_tree.configure(yscrollcommand=sb.set)
        self.targets_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        act = ttk.Frame(parent, padding=(0, 10, 0, 0))
        act.pack(fill=X)
        ttk.Button(act, text="선택 삭제", command=self.remove_booking_target, bootstyle="secondary").pack(side=LEFT, expand=True, fill=X, padx=2)
        ttk.Button(act, text="전체 삭제", command=self.clear_all_targets, bootstyle="danger-outline").pack(side=LEFT, expand=True, fill=X, padx=2)
        ttk.Button(act, text="평일 자동", command=lambda: self.show_auto_add_dialog("평일"), bootstyle="info-outline").pack(side=LEFT, expand=True, fill=X, padx=2)
        ttk.Button(act, text="주말 자동", command=lambda: self.show_auto_add_dialog("주말"), bootstyle="info-outline").pack(side=LEFT, expand=True, fill=X, padx=2)

    def _create_my_bookings_card(self, parent):
        card = ttk.Labelframe(parent, text="내 예약 현황", padding=10, bootstyle="success")
        card.pack(fill=BOTH, expand=True, pady=(0, 5))
        
        tb = ttk.Frame(card)
        tb.pack(fill=X, pady=(0, 5))
        ttk.Button(tb, text="🔄 새로고침", command=self.load_my_reservations, bootstyle="link", cursor="hand2").pack(side=RIGHT)
        
        cols = ('날짜', '시간', '코트', '상태')
        self.my_bookings_tree = ttk.Treeview(card, columns=cols, show='headings', bootstyle="success", height=8)
        self.my_bookings_tree.heading('날짜', text='날짜'); self.my_bookings_tree.column('날짜', width=80, anchor=CENTER)
        self.my_bookings_tree.heading('시간', text='시간'); self.my_bookings_tree.column('시간', width=60, anchor=CENTER)
        self.my_bookings_tree.heading('코트', text='코트'); self.my_bookings_tree.column('코트', width=60, anchor=CENTER)
        self.my_bookings_tree.heading('상태', text='상태'); self.my_bookings_tree.column('상태', width=80, anchor=CENTER)
        
        sb = ttk.Scrollbar(card, orient=VERTICAL, command=self.my_bookings_tree.yview)
        self.my_bookings_tree.configure(yscrollcommand=sb.set)
        self.my_bookings_tree.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)
        self.my_bookings_tree.bind('<Button-1>', self.handle_tree_click)

    def _create_log_card(self, parent):
        card = ttk.Labelframe(parent, text="시스템 로그", padding=10, bootstyle="secondary")
        card.pack(fill=BOTH, expand=True, pady=5)
        
        head = ttk.Frame(card)
        head.pack(fill=X)
        ttk.Button(head, text="관리자 메뉴", command=self.prompt_admin_password, bootstyle="secondary-link", cursor="hand2").pack(side=RIGHT)

        self.log_text = scrolledtext.ScrolledText(card, height=8, state='normal', font=("Consolas", 9))
        self.log_text.pack(fill=BOTH, expand=True)

    # --- Methods ---
    def log_message(self, message: str, level: str = 'info'):
        t = self.get_synced_time().strftime('%H:%M:%S')
        msg = f"[{t}] {message}"
        logging.log(getattr(logging, level.upper(), logging.INFO), message)
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.insert(tk.END, msg + "\n")
            self.log_text.see(tk.END)

    def update_countdown(self):
        if hasattr(self, 'next_booking_time'):
            diff = self.next_booking_time - self.get_synced_time()
            if diff.total_seconds() > 0:
                self.countdown_label.config(text=str(diff).split('.')[0], bootstyle="primary")
            else:
                self.countdown_label.config(text="00:00:00", bootstyle="danger")
        self.root.after(500, self.update_countdown)

    def update_current_time(self):
        self.current_time_label.config(text=self.get_synced_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3])
        self.root.after(100, self.update_current_time)

    def sync_time(self): threading.Thread(target=self._sync_time_worker, daemon=True).start()
    def _sync_time_worker(self):
        try:
            self.time_offset = ntplib.NTPClient().request('time.bora.net', version=3).offset
            self.log_message(f"서버 시간 동기화 완료 (오차: {self.time_offset:.4f}초)")
        except: self.log_message("시간 동기화 실패", "warning")
    def get_synced_time(self): return datetime.now() + timedelta(seconds=self.time_offset)
    def check_for_updates(self): pass 
    def cleanup_after_update(self): pass

    # Login
    def login(self):
        e, p = self.username_entry.get(), self.password_entry.get()
        if not e or not p: return Messagebox.show_warning("ID와 PW를 입력하세요.", "입력 오류")
        threading.Thread(target=self._login_worker, args=(e,p), daemon=True).start()

    def _login_worker(self, e, p):
        ok, msg = self.booking_api.login(e, p)
        if ok:
            self.is_logged_in = True
            self.login_status_label.config(text="로그인 됨", bootstyle="inverse-success")
            self.login_button.config(state=DISABLED); self.logout_button.config(state=NORMAL)
            self.load_my_reservations()
            self.booking_api.get_all_courts()
            self.log_message("로그인 성공")
            threading.Thread(target=self._heartbeat_worker, daemon=True).start()
        else:
            Messagebox.show_error(msg, "로그인 실패")

    def logout(self):
        self.is_logged_in = False
        self.login_status_label.config(text="로그아웃 상태", bootstyle="inverse-danger")
        self.login_button.config(state=NORMAL); self.logout_button.config(state=DISABLED)
        self.log_message("로그아웃")

    def _heartbeat_worker(self):
        while self.is_logged_in:
            time.sleep(600)
            if self.is_logged_in: self.analytics_logger.log_event(self.username_entry.get(), self.machine_id, "heartbeat", {})

    def calculate_booking_time(self):
        try:
            self.next_booking_time = datetime(
                self.booking_year_var.get(), self.booking_month_var.get(), self.booking_day_var.get(),
                self.booking_hour_var.get(), self.booking_minute_var.get(), self.booking_second_var.get()
            )
            self.booking_time_label.config(text=f"목표: {self.next_booking_time.strftime('%Y-%m-%d %H:%M:%S')}")
        except: pass

    # Targets
    def add_booking_target(self):
        d = self.target_calendar.entry.get()
        c_str = self.target_court_var.get()
        c = int(re.search(r'\d+', c_str).group())
        t = self.target_time_var.get()
        if any(x['date']==d and x['court']==c and x['time']==t for x in self.booking_targets): return
        self.booking_targets.append({'date': d, 'court': c, 'time': t})
        self.refresh_target_tree()
        self.analytics_logger.sync_targets(self.username_entry.get(), self.booking_targets)

    def remove_booking_target(self):
        sel = self.targets_tree.selection()
        if not sel: return
        for i in sel:
            v = self.targets_tree.item(i)['values']
            c_num = int(re.search(r'\d+', str(v[1])).group())
            self.booking_targets = [x for x in self.booking_targets if not (x['date']==v[0] and x['court']==c_num and x['time']==v[2])]
        self.refresh_target_tree()
        self.analytics_logger.sync_targets(self.username_entry.get(), self.booking_targets)

    def clear_all_targets(self):
        if Messagebox.okcancel("전체 삭제하시겠습니까?", "확인"):
            self.booking_targets = []
            self.refresh_target_tree()
            self.analytics_logger.sync_targets(self.username_entry.get(), self.booking_targets)

    def refresh_target_tree(self):
        self.targets_tree.delete(*self.targets_tree.get_children())
        for t in self.booking_targets:
            self.targets_tree.insert('', 'end', values=(t['date'], f"{t['court']}번 코트", t['time']))

    # Reservations
    def load_my_reservations(self):
        if not self.is_logged_in: return
        threading.Thread(target=self._load_res_worker, daemon=True).start()
    
    def _load_res_worker(self):
        res = self.booking_api.get_my_reservations_details()
        status_map = self.booking_api.get_payment_statuses()
        parsed = []
        for r in res:
            try:
                st = datetime.fromisoformat(r['slots']['start_time'].replace('Z', '+00:00')).astimezone(KST)
                pid = r['id']
                is_paid = status_map.get(pid) in ['paid', 'completed', 'payment_completed']
                parsed.append({'id':pid, 'date':st.strftime('%Y-%m-%d'), 'time':st.strftime('%H:%M'), 'court':r['slots']['courts']['name'], 'is_paid':is_paid})
            except: pass
        self.root.after(0, self.update_res_tree, parsed)

    def update_res_tree(self, data):
        self.my_bookings_tree.delete(*self.my_bookings_tree.get_children())
        self.reservation_data = {}
        for d in data:
            status = "결제완료" if d['is_paid'] else "취소가능"
            iid = self.my_bookings_tree.insert('', 'end', values=(d['date'], d['time'], d['court'], status))
            self.reservation_data[iid] = d

    def handle_tree_click(self, event):
        item = self.my_bookings_tree.identify_row(event.y)
        col = self.my_bookings_tree.identify_column(event.x)
        if item and col == '#4':
            d = self.reservation_data.get(item)
            if d and not d['is_paid']:
                if Messagebox.okcancel("예약을 취소하시겠습니까?", "취소 확인"):
                    threading.Thread(target=lambda: self._cancel_worker(d['id']), daemon=True).start()

    def _cancel_worker(self, rid):
        ok, msg = self.booking_api.cancel_reservation(rid)
        self.log_message(f"취소: {msg}")
        if ok: self.load_my_reservations()

    # Settings
    def save_config(self):
        cfg = {
            'username': self.username_entry.get(), 'password': encrypt_password(self.password_entry.get()),
            'machine_id': self.machine_id, 'booking_targets': self.booking_targets,
            'booking_time': {'year': self.booking_year_var.get(), 'month': self.booking_month_var.get(),
                             'day': self.booking_day_var.get(), 'hour': self.booking_hour_var.get(),
                             'minute': self.booking_minute_var.get(), 'second': self.booking_second_var.get()}
        }
        with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(cfg, f)
        Messagebox.show_info("설정이 저장되었습니다.", "저장 완료")

    def load_config(self):
        if not os.path.exists(self.config_file): return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: cfg = json.load(f)
            self.username_entry.delete(0, END); self.username_entry.insert(0, cfg.get('username',''))
            self.password_entry.delete(0, END); self.password_entry.insert(0, decrypt_password(cfg.get('password','')))
            self.booking_targets = cfg.get('booking_targets', [])
            self.refresh_target_tree()
            t = cfg.get('booking_time')
            if t:
                self.booking_year_var.set(t['year']); self.booking_month_var.set(t['month'])
                self.booking_day_var.set(t['day']); self.booking_hour_var.set(t['hour'])
                self.booking_minute_var.set(t['minute']); self.booking_second_var.set(t['second'])
            self.calculate_booking_time()
        except: pass

    def reset_all_settings(self):
        if Messagebox.okcancel("모든 설정을 초기화하시겠습니까?", "초기화"):
            if os.path.exists(self.config_file): os.remove(self.config_file)
            self.username_entry.delete(0, END); self.password_entry.delete(0, END)
            self.booking_targets = []; self.refresh_target_tree()

    # Dialogs
    def show_booking_time_setting(self):
        win = ttk.Toplevel(self.root)
        win.title("예약 시간 설정")
        f = ttk.Frame(win, padding=20)
        f.pack()
        
        ttk.Label(f, text="예약 시작 시간을 설정하세요", font=("", 11, "bold")).pack(pady=(0, 10))
        
        # 년/월/일
        r1 = ttk.Frame(f); r1.pack(pady=5)
        ttk.Spinbox(r1, from_=2024, to=2030, textvariable=self.booking_year_var, width=5).pack(side=LEFT)
        ttk.Label(r1, text="년").pack(side=LEFT)
        ttk.Spinbox(r1, from_=1, to=12, textvariable=self.booking_month_var, width=3).pack(side=LEFT)
        ttk.Label(r1, text="월").pack(side=LEFT)
        ttk.Spinbox(r1, from_=1, to=31, textvariable=self.booking_day_var, width=3).pack(side=LEFT)
        ttk.Label(r1, text="일").pack(side=LEFT)
        
        # 시/분/초
        r2 = ttk.Frame(f); r2.pack(pady=5)
        ttk.Spinbox(r2, from_=0, to=23, textvariable=self.booking_hour_var, width=3).pack(side=LEFT)
        ttk.Label(r2, text="시").pack(side=LEFT)
        ttk.Spinbox(r2, from_=0, to=59, textvariable=self.booking_minute_var, width=3).pack(side=LEFT)
        ttk.Label(r2, text="분").pack(side=LEFT)
        ttk.Spinbox(r2, from_=0, to=59, textvariable=self.booking_second_var, width=3).pack(side=LEFT)
        ttk.Label(r2, text="초").pack(side=LEFT)
        
        def save():
            self.calculate_booking_time()
            win.destroy()
            
        ttk.Button(f, text="저장", command=save, bootstyle="success").pack(pady=10)
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')
        
    def show_auto_add_dialog(self, day_type):
        win = ttk.Toplevel(self.root)
        win.title(f"{day_type} 자동 추가 도구")
        
        f = ttk.Frame(win, padding=20)
        f.pack(fill=BOTH, expand=True)
        
        # 다음달 계산
        now = datetime.now()
        nm = now.replace(day=28) + timedelta(days=4)
        ny, nmonth = nm.year, nm.month
        
        ttk.Label(f, text=f"{ny}년 {nmonth}월 {day_type} 일괄 추가", font=("", 11, "bold")).pack(pady=(0,10))
        
        # 요일 선택
        lf_days = ttk.Labelframe(f, text="요일 선택", padding=10)
        lf_days.pack(fill=X, pady=5)
        
        day_vars = {}
        target_days = range(5) if day_type == "평일" else range(5, 7)
        for i in target_days:
            v = tk.BooleanVar(value=True)
            day_vars[i] = v
            ttk.Checkbutton(lf_days, text="월화수목금토일"[i], variable=v).pack(side=LEFT, padx=5)
            
        # 시간 선택
        lf_time = ttk.Labelframe(f, text="시간 선택", padding=10)
        lf_time.pack(fill=X, pady=5)
        time_vars = {}
        for t in ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]:
            v = tk.BooleanVar(value=(t=="06:00"))
            time_vars[t] = v
            ttk.Checkbutton(lf_time, text=t, variable=v).pack(side=LEFT, padx=2)
            
        # 코트 선택
        lf_court = ttk.Labelframe(f, text="코트 선택", padding=10)
        lf_court.pack(fill=X, pady=5)
        court_vars = {}
        for c in range(5, 18):
            v = tk.BooleanVar(value=(c==5))
            court_vars[c] = v
            ttk.Checkbutton(lf_court, text=str(c), variable=v).pack(side=LEFT, padx=2)
            
        def run_add():
            sel_d = [k for k, v in day_vars.items() if v.get()]
            sel_t = [k for k, v in time_vars.items() if v.get()]
            sel_c = [k for k, v in court_vars.items() if v.get()]
            
            _, last_day = calendar.monthrange(ny, nmonth)
            count = 0
            for d in range(1, last_day+1):
                dt = datetime(ny, nmonth, d)
                if dt.weekday() in sel_d:
                    dstr = dt.strftime("%Y-%m-%d")
                    for t in sel_t:
                        for c in sel_c:
                            if not any(x['date']==dstr and x['court']==c and x['time']==t for x in self.booking_targets):
                                self.booking_targets.append({'date': dstr, 'court': c, 'time': t})
                                count += 1
            self.refresh_target_tree()
            self.analytics_logger.sync_targets(self.username_entry.get(), self.booking_targets)
            Messagebox.show_info(f"{count}건의 목표가 추가되었습니다.", "완료")
            win.destroy()
            
        ttk.Button(f, text="실행", command=run_add, bootstyle="primary").pack(pady=10)
        
        win.update_idletasks()
        w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        win.geometry(f'{w}x{h}+{(sw-w)//2}+{(sh-h)//2}')

    def prompt_admin_password(self):
        d = AdminPasswordDialog(self.root)
        self.root.wait_window(d)
        if d.password == "admin123":
            # 로그 파일 열기
            try: os.startfile(LOG_FILE_BASENAME)
            except: Messagebox.show_info("로그 파일을 열 수 없습니다.", "알림")
        elif d.password:
            Messagebox.show_error("비밀번호가 틀렸습니다.", "오류")

    # Booking Logic
    def start_booking(self):
        if not self.is_logged_in: return Messagebox.show_warning("로그인이 필요합니다.", "경고")
        if not self.booking_targets: return Messagebox.show_warning("예약 목표가 없습니다.", "경고")
        
        self.is_booking_active = True
        self.start_button.config(state=DISABLED); self.stop_button.config(state=NORMAL)
        self.notebook.select(0)
        
        self.analytics_logger.log_booking_targets(self.username_entry.get(), self.booking_targets)
        threading.Thread(target=lambda: asyncio.run(self.optimized_booking_loop()), daemon=True).start()

    def stop_booking(self):
        self.is_booking_active = False
        self.start_button.config(state=NORMAL); self.stop_button.config(state=DISABLED)
        self.log_message("예약 중지됨")

    async def optimized_booking_loop(self):
        self.log_message("예약 대기 중...")
        while self.is_booking_active:
            rem = (self.next_booking_time - self.get_synced_time()).total_seconds()
            if rem <= 0.05: break
            await asyncio.sleep(0.05 if rem < 2 else 0.5)
        
        if not self.is_booking_active: return
        self.log_message("🚀 고속 예약 시작!")
        
        dates = sorted(list(set(t['date'] for t in self.booking_targets)))
        if not dates: return
        
        success_keys = set()
        pending = set()
        start_t = time.time()
        
        async with aiohttp.ClientSession() as sess:
            while self.is_booking_active:
                if time.time() - start_t > 30: break
                if len(success_keys) >= len(self.booking_targets): break
                
                slots = await self.booking_api.get_available_slots_async(dates[0], dates[-1])
                if not slots:
                    await asyncio.sleep(0.05); continue
                    
                for s in slots:
                    try:
                        st = datetime.fromisoformat(s['start_time'].replace('Z', '+00:00')).astimezone(KST)
                        s_key = f"{st.strftime('%Y-%m-%d')}|{s.get('court_id')}|{st.strftime('%H:%M')}"
                        
                        for t in self.booking_targets:
                            cid = self.booking_api.courts_info.get(t['court'])
                            t_key = f"{t['date']}|{cid}|{t['time']}"
                            if s_key == t_key and t_key not in success_keys:
                                task = asyncio.create_task(self._res_task(sess, s['id'], t, t_key, success_keys))
                                pending.add(task)
                                task.add_done_callback(pending.discard)
                    except: continue
                await asyncio.sleep(0.2)
        
        self.log_message("예약 프로세스 종료")
        self.root.after(0, self.stop_booking)
        self.root.after(0, self.load_my_reservations)

    async def _res_task(self, sess, sid, t, k, success_set):
        r = await self.booking_api.reserve_slot_async(sess, sid)
        info = f"{t['date']} {t['time']} {t['court']}코트"
        if r['success']:
            self.log_message(f"✅ 성공: {info}")
            success_set.add(k)
        else:
            self.log_message(f"❌ 실패: {info} ({r['message']})")

if __name__ == "__main__":
    app = TennisBookingGUI()
    app.root.mainloop()