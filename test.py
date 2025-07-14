import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from tkcalendar import DateEntry
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
import webbrowser

# ==============================================================================
# 1. 로깅 설정
# ==============================================================================
LOG_FILE_BASENAME = 'app.log'
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
    if 'app' in globals() and isinstance(app, TennisBookingGUI) and hasattr(app, 'analytics_logger'):
        app.analytics_logger.log_event(
            user_email=app.username_entry.get() if hasattr(app, 'username_entry') else "unknown",
            machine_id=app.machine_id if hasattr(app, 'machine_id') else "unknown",
            event_type="fatal_error",
            event_data={"error_type": str(exc_type), "error_value": str(exc_value)})
    logging.error("처리되지 않은 예외가 발생했습니다:", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception
setup_logging()

# ==============================================================================
# 2. 기본 설정
# ==============================================================================
# 🚨🚨🚨 아래 4개의 설정값을 본인의 정보로 꼭 채워주세요! 🚨🚨🚨
ANALYTICS_URL = "https://uppuyydtqhaulobevczk.supabase.co" # 질문자님의 Supabase URL
ANALYTICS_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InVwcHV5eWR0cWhhdWxvYmV2Y3prIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTI0ODE5NTQsImV4cCI6MjA2ODA1Nzk1NH0.yHz7U7XXV34Dlvs8PAoZ6EyD6vz1y77dAFpbh0_7noc" # 질문자님의 Supabase anon key
APP_VERSION = "1.0.3"  # 새 버전을 배포할 때마다 이 숫자를 올려주세요 (예: "1.0.1")
GITHUB_REPO = "chbak0/Tennis_exe_update" # 질문자님의 GitHub 아이디/저장소이름

# --- 기존 예약 시스템 API 정보 ---
SUPABASE_URL = "https://ydiivmmorbqbvrahrutd.supabase.co"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InlkaWl2bW1vcmJxYnZyYWhydXRkIiwicm9sZSI6ImFub24iLCJpYXQiOjE2NzM3MjA4MDEsImV4cCI6MTk4OTI5NjgwMX0.jcX7WYAImKzfYuLi4exAlvMB1zpfKFf9iWN7_gnbjaI"
HEADERS = {"apikey": SUPABASE_ANON_KEY, "x-client-info": "supabase-py/1.0.0"}
KST = timezone(timedelta(hours=9))
KEY_FILE = 'app.key'

class AnalyticsLogger:
    def __init__(self, url: str, key: str):
        self.url = f"{url}/rest/v1/analytics_logs"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
    def log_event(self, user_email: str, machine_id: str, event_type: str, event_data: dict):
        threading.Thread(target=self._send_log, args=(user_email, machine_id, event_type, event_data), daemon=True).start()
    def _send_log(self, user_email: str, machine_id: str, event_type: str, event_data: dict):
        try:
            payload = {"user_email": user_email, "machine_id": machine_id, "app_version": APP_VERSION,
                       "event_type": event_type, "event_data": event_data}
            requests.post(self.url, headers=self.headers, json=payload, timeout=15)
        except Exception as e:
            logging.warning(f"Analytics log submission failed: {e}")

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

# ==============================================================================
# 3. API 통신 클래스
# ==============================================================================
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
                if not self.auth_token or not self.user_id: return False, "로그인 응답에 토큰 또는 사용자 ID가 없습니다."
                self.session.headers['Authorization'] = f'Bearer {self.auth_token}'
                return True, "로그인 성공!"
            return False, f"로그인 실패: {response.json().get('error_description', '알 수 없는 오류')}"
        except Exception as e: return False, f"네트워크 오류: {e}"
    def get_all_courts(self) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            url = f"{SUPABASE_URL}/rest/v1/courts?select=*"
            response = self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10)
            response.raise_for_status()
            courts = response.json()
            self.courts_info = {int(re.search(r'\d+', c['name']).group()): c['id'] for c in courts if re.search(r'\d+', c.get('name', ''))}
            return courts
        except Exception as e: logging.error(f"코트 정보 조회 오류: {e}"); return []
    def get_my_reservations_details(self) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            url = f"{SUPABASE_URL}/rest/v1/reservations?select=id,created_at,slot_id,slots(*,courts(*))&order=created_at.desc"
            response = self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e: logging.error(f"예약 상세 정보 조회 오류: {e}"); return []
    def get_payment_statuses(self) -> Dict[str, str]:
        if not self.auth_token or not self.user_id: return {}
        try:
            url = f"{SUPABASE_URL}/rest/v1/user_reservations?select=id,payment_status&user_id=eq.{self.user_id}"
            response = self.session.get(url, headers={**HEADERS, "Authorization": f"Bearer {self.auth_token}"}, timeout=10)
            response.raise_for_status()
            return {item['id']: item.get('payment_status') for item in response.json()}
        except Exception as e: logging.error(f"결제 상태 조회 오류: {e}"); return {}
    def cancel_reservation(self, reservation_id: str) -> tuple[bool, str]:
        if not self.auth_token: return False, "로그인이 필요합니다."
        try:
            url = "https://ydiivmmorbqbvrahrutd.functions.supabase.co/register-cancellation-request"
            payload = {"reservation_id": reservation_id}
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code == 200: return True, "예약이 성공적으로 취소되었습니다."
            error_message = response.json().get('error', response.text)
            return False, f"취소 실패 (서버 응답: {response.status_code}): {error_message}"
        except Exception as e: return False, f"취소 중 네트워크 오류 발생: {e}"
    async def get_available_slots_async(self, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        if not self.auth_token: return []
        try:
            start_utc = datetime.strptime(start_date, "%Y-%m-%d").astimezone(KST).astimezone(timezone.utc)
            end_utc = (datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)).astimezone(KST).astimezone(timezone.utc)
            url = f"{SUPABASE_URL}/rest/v1/rpc/get_slots_between"
            payload = {"range_start": start_utc.isoformat(), "range_end": end_utc.isoformat()}
            headers = {**HEADERS, "Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                    if response.status == 200: return [s for s in await response.json() if s.get('is_available')]
            return []
        except Exception as e: logging.error(f"슬롯 조회 오류: {e}"); return []
    async def reserve_slot_async(self, session: aiohttp.ClientSession, slot_id: str) -> Dict[str, Any]:
        if not self.auth_token: return {'success': False, 'message': '인증 토큰 없음'}
        try:
            url = f"{SUPABASE_URL}/functions/v1/reserve-slot"
            payload = {"slotId": slot_id}
            headers = {**HEADERS, "Authorization": f"Bearer {self.auth_token}", "Content-Type": "application/json"}
            async with session.post(url, headers=headers, json=payload, timeout=10) as response:
                if response.status == 200: return {'success': True, 'message': '예약 성공!'}
                return {'success': False, 'message': f"HTTP {response.status}: {await response.text()}"}
        except Exception as e: return {'success': False, 'message': f"오류: {e}"}

# ==============================================================================
# 4. 커스텀 다이얼로그 클래스
# ==============================================================================
class AdminPasswordDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.password = None
        self.title("관리자 인증")
        self.geometry("320x130")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        main_frame = ttk.Frame(self, padding="15")
        main_frame.pack(fill="both", expand=True)
        ttk.Label(main_frame, text="비밀번호를 입력하세요:", font=("", 10)).pack(pady=(0, 5), anchor='w')
        self.password_entry = ttk.Entry(main_frame, show="*", font=("", 10))
        self.password_entry.pack(fill="x", ipady=2)
        self.password_entry.focus_set()
        self.password_entry.bind("<Return>", self.on_ok)
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=(15, 0))
        ttk.Button(btn_frame, text="확인", command=self.on_ok, width=10).pack(side="left", padx=5)
        ttk.Button(btn_frame, text="취소", command=self.on_cancel, width=10).pack(side="left", padx=5)
    def on_ok(self, event=None): self.password = self.password_entry.get(); self.destroy()
    def on_cancel(self): self.password = None; self.destroy()

# ==============================================================================
# 5. 메인 GUI 클래스
# ==============================================================================
class TennisBookingGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"송도 테니스 예약 자동화 (v{APP_VERSION})")
        self.time_offset = 0
        self.analytics_logger = AnalyticsLogger(ANALYTICS_URL, ANALYTICS_KEY)
        
        # 화면 정보 가져오기
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        
        # 해상도별 적응적 크기 설정
        if screen_width >= 2800:  # 갤럭시북5프로 16인치 (2880x1800)
            width_ratio = 0.55  # 갤럭시북5프로 전용 최적화
            height_ratio = 0.6  
        elif screen_width >= 2000:  # 기타 고해상도 노트북
            width_ratio = 0.6   
            height_ratio = 0.65 
        elif screen_width >= 1920:  # FHD 모니터 (일반 노트북)
            width_ratio = 0.5   
            height_ratio = 0.6  
        elif screen_width >= 1500:  # 중간 해상도
            width_ratio = 0.65  
            height_ratio = 0.7  
        elif screen_width >= 1366:  # 중간 크기 모니터
            width_ratio = 0.75
            height_ratio = 0.75
        else:  # 작은 화면
            width_ratio = 0.85
            height_ratio = 0.8
            
        # 창 크기 계산
        window_width = int(screen_width * width_ratio)
        window_height = int(screen_height * height_ratio)
        
        # 최소/최대 크기 제한 (해상도 기반)
        min_width = min(1200, int(screen_width * 0.75))
        min_height = min(800, int(screen_height * 0.7))
        max_width = int(screen_width * 0.95)
        max_height = int(screen_height * 0.9)
        
        # 크기 제한 적용
        window_width = max(min_width, min(window_width, max_width))
        window_height = max(min_height, min(window_height, max_height))
        
        # 최소 크기 설정
        self.root.minsize(min_width, min_height)
        
        # 창을 화면 정중앙에 위치시키기
        center_x = (screen_width - window_width) // 2
        center_y = (screen_height - window_height) // 2
        
        # 위치가 음수가 되지 않도록 보정
        center_x = max(0, center_x)
        center_y = max(0, center_y)
        
        self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
        
        style = ttk.Style(); style.theme_use('clam')
        self.booking_api = SongdoTennisBooking()
        self.is_logged_in = False
        self.is_booking_active = False
        self.config_file = "tennis_booking_config.json"
        self.machine_id = self.load_or_create_machine_id()
        self.session_start_time = datetime.now()
        self.booking_targets: List[Dict[str, Any]] = []
        self.reservation_data: Dict[str, Dict[str, Any]] = {}
        now = datetime.now()
        self.booking_year_var = tk.IntVar(value=now.year)
        self.booking_month_var = tk.IntVar(value=now.month)
        self.booking_day_var = tk.IntVar(value=25)
        self.booking_hour_var = tk.IntVar(value=10)
        self.booking_minute_var = tk.IntVar(value=0)
        self.booking_second_var = tk.IntVar(value=0)
        self.my_bookings_sort_col = '예약 날짜'
        self.my_bookings_sort_rev = False
        self.create_widgets()
        self.sync_time()
        self.load_config()
        threading.Thread(target=self.check_for_updates, daemon=True).start()

    def load_or_create_machine_id(self) -> str:
        config = {}
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f: config = json.load(f)
            except (json.JSONDecodeError, IOError): pass
        machine_id = config.get('machine_id')
        if not machine_id:
            machine_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(uuid.getnode())))
            config['machine_id'] = machine_id
            try:
                full_config = {}
                if os.path.exists(self.config_file):
                    with open(self.config_file, 'r', encoding='utf-8') as f_read:
                        full_config = json.load(f_read)
                full_config['machine_id'] = machine_id
                with open(self.config_file, 'w', encoding='utf-8') as f_write:
                    json.dump(full_config, f_write, indent=2)
                self.log_message(f"새로운 Machine ID 생성 및 저장: {machine_id}")
            except Exception as e:
                self.log_message(f"Machine ID 저장 실패: {e}", level='error')
                return "ID_GENERATION_FAILED"
        return machine_id

    def sync_time(self):
        threading.Thread(target=self._sync_time_worker, daemon=True).start()

    def _sync_time_worker(self):
        try:
            client = ntplib.NTPClient()
            response = client.request('time.bora.net', version=3)
            self.time_offset = response.offset
            self.session_start_time = self.get_synced_time()
            self.log_message(f"✅ 서버 시간 동기화 완료 (오차: {self.time_offset:.4f}초)")
        except Exception as e:
            self.log_message(f"❌ 서버 시간 동기화 실패: {e}", level='warning')

    def get_synced_time(self) -> datetime:
        return datetime.now() + timedelta(seconds=self.time_offset)
    
    def check_for_updates(self):
        if not GITHUB_REPO or "YourGitHubUsername" in GITHUB_REPO:
            return
        try:
            response = requests.get(f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest", timeout=5)
            if response.status_code != 200: return

            latest_release = response.json()
            latest_version = latest_release.get("tag_name", "v0.0.0").replace('v', '')
            current_version = APP_VERSION

            if latest_version > current_version:
                message = f"새로운 버전(v{latest_version})이 출시되었습니다! 지금 자동으로 업데이트하시겠습니까?"
                if not messagebox.askyesno("업데이트 가능", message):
                    return

                self.log_message(f"v{latest_version} 자동 업데이트를 시작합니다...")
                
                # 릴리즈에서 앱과 업데이터의 다운로드 URL을 찾습니다.
                app_url, updater_url = None, None
                for asset in latest_release.get('assets', []):
                    if asset['name'].endswith('.exe') and 'updater' not in asset['name']:
                        app_url = asset['browser_download_url']
                    elif asset['name'] == 'updater.exe':
                        updater_url = asset['browser_download_url']
                
                if not app_url or not updater_url:
                    messagebox.showerror("업데이트 실패", "GitHub 릴리즈에서 업데이트 파일(프로그램, 업데이터)을 찾을 수 없습니다.")
                    return

                # 새 버전 앱과 업데이터를 임시 파일로 다운로드합니다.
                self.log_message("새 버전 다운로드 중...")
                with open("app_new.exe", "wb") as f:
                    f.write(requests.get(app_url).content)

                self.log_message("업데이터 다운로드 중...")
                with open("updater_temp.exe", "wb") as f:
                    f.write(requests.get(updater_url).content)
                
                self.log_message("다운로드 완료. 프로그램을 재시작하여 업데이트를 완료합니다.")

                # 현재 실행중인 파일 이름을 찾습니다.
                current_executable = os.path.basename(sys.executable if getattr(sys, 'frozen', False) else sys.argv[0])

                # 업데이터를 실행하고, 현재 프로그램은 종료합니다.
                subprocess.Popen(['updater_temp.exe', current_executable, 'app_new.exe'])
                self.root.destroy()

        except Exception as e:
            self.log_message(f"업데이트 확인 중 오류 발생: {e}", level='warning')
            messagebox.showerror("업데이트 오류", f"업데이트 중 오류가 발생했습니다:\n{e}")

    def create_widgets(self):
        self.root.columnconfigure(0, weight=3)
        self.root.columnconfigure(1, weight=2)
        self.root.rowconfigure(0, weight=1)
        
        left_panel = ttk.Frame(self.root, padding="10")
        left_panel.grid(row=0, column=0, sticky="nsew", pady=0)
        left_panel.columnconfigure(0, weight=1)
        # 왼쪽 패널에서는 '예약 목표' 부분이 세로 공간을 차지하도록 변경
        left_panel.rowconfigure(1, weight=1) 

        right_panel = ttk.Frame(self.root, padding="10")
        right_panel.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=0)
        # 오른쪽 패널을 위아래로 1:1 비율로 나누도록 설정
        right_panel.rowconfigure(0, weight=1) 
        right_panel.rowconfigure(1, weight=1)
        right_panel.columnconfigure(0, weight=1)
        
        # 위젯 생성 함수 호출 순서 변경
        self._create_login_widgets(left_panel)
        self._create_settings_widgets(left_panel)
        self._create_booking_widgets(left_panel)
        self._create_my_bookings_widgets(right_panel) # 오른쪽 위
        self._create_log_widgets(right_panel)        # 오른쪽 아래
        
        self.calculate_booking_time()
        self.update_countdown()
        self.update_current_time()

    def center_window(self, window):
        """다이얼로그 창을 화면 중앙에 배치하는 개선된 메서드"""
        window.update_idletasks()
        
        # 창 크기 정보
        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        
        # 창 크기가 0인 경우 실제 크기 사용
        if width <= 1:
            width = window.winfo_width()
        if height <= 1:
            height = window.winfo_height()
            
        # 화면 크기 정보
        screen_width = window.winfo_screenwidth()
        screen_height = window.winfo_screenheight()
        
        # 중앙 위치 계산
        x = (screen_width - width) // 2
        y = (screen_height - height) // 2
        
        # 화면 경계를 벗어나지 않도록 보정
        x = max(0, min(x, screen_width - width))
        y = max(0, min(y, screen_height - height))
        
        window.geometry(f'{width}x{height}+{x}+{y}')

    def _create_login_widgets(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="로그인 정보", padding="10")
        frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        
        # 프레임의 열 가중치 설정으로 공간 효율적 배분
        frame.columnconfigure(1, weight=2)  # 이메일 입력 필드
        frame.columnconfigure(3, weight=1)  # 비밀번호 입력 필드
        
        # 첫 번째 줄: 모든 요소를 한 줄에 배치
        ttk.Label(frame, text="ID:").grid(row=0, column=0, padx=(0, 3), pady=5, sticky="w")
        self.username_entry = ttk.Entry(frame)
        self.username_entry.grid(row=0, column=1, padx=3, pady=5, sticky="ew")
        
        ttk.Label(frame, text="PW:").grid(row=0, column=2, padx=3, pady=5, sticky="w")
        self.password_entry = ttk.Entry(frame, show="*")
        self.password_entry.grid(row=0, column=3, padx=3, pady=5, sticky="ew")
        self.password_entry.bind("<Return>", lambda event: self.login())
        
        self.login_button = ttk.Button(frame, text="로그인", command=self.login)
        self.login_button.grid(row=0, column=4, padx=3, pady=5)
        
        self.logout_button = ttk.Button(frame, text="로그아웃", command=self.logout, state=tk.DISABLED)
        self.logout_button.grid(row=0, column=5, padx=3, pady=5)
        
        # 두 번째 줄: 로그인 상태만 표시
        self.login_status_label = ttk.Label(frame, text="로그인 상태: 로그아웃", foreground="red")
        self.login_status_label.grid(row=1, column=0, columnspan=6, pady=(5, 0))
        
    def _create_settings_widgets(self, parent: ttk.Frame):
        # 이 프레임이 부모(left_panel) 안에서 세로 공간을 차지하도록 expand=True 추가
        frame = ttk.LabelFrame(parent, text="예약 목표 설정", padding="10")
        frame.grid(row=1, column=0, sticky="nsew", pady=(0, 10))
        # 이 프레임 내부에서 Treeview가 담긴 list_frame이 늘어나도록 설정
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)

        add_frame = ttk.Frame(frame)
        add_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5) # pack 대신 grid 사용
        
        ttk.Label(add_frame, text="새 목표:", font="TkDefaultFont 9 bold").grid(row=0, column=0, padx=(0,5))
        self.target_calendar = DateEntry(add_frame, width=12, date_pattern='y-mm-dd'); self.target_calendar.grid(row=0, column=1, padx=5)
        court_display_values = [f"{i}번 코트" for i in range(5, 18)]
        self.target_court_var = tk.StringVar(value="5번 코트")
        ttk.Combobox(add_frame, textvariable=self.target_court_var, values=court_display_values, width=10, state="readonly").grid(row=0, column=2, padx=5)
        self.target_time_var = tk.StringVar(value="06:00"); ttk.Combobox(add_frame, textvariable=self.target_time_var, values=["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"], width=8, state="readonly").grid(row=0, column=3, padx=5)
        ttk.Button(add_frame, text="추가", command=self.add_booking_target).grid(row=0, column=4, padx=5)
        
        list_frame = ttk.Frame(frame)
        # Treeview가 프레임의 모든 공간을 채우도록 sticky="nsew" 사용
        list_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(0, weight=1)

        columns = ('날짜', '코트', '시간'); self.targets_tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=7)
        for col in columns: self.targets_tree.heading(col, text=col); self.targets_tree.column(col, width=120, anchor=tk.CENTER)
        self.targets_tree.grid(row=0, column=0, sticky="nsew")
        targets_scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.targets_tree.yview); targets_scrollbar.grid(row=0, column=1, sticky="ns")
        self.targets_tree.configure(yscrollcommand=targets_scrollbar.set)
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=2, column=0, pady=5) # pack 대신 grid 사용
        ttk.Button(btn_frame, text="선택 삭제", command=self.remove_booking_target).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="전체 삭제", command=self.clear_all_targets).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="다음달 평일 자동추가", command=lambda: self.show_auto_add_dialog("평일")).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="다음달 주말 자동추가", command=lambda: self.show_auto_add_dialog("주말")).pack(side=tk.LEFT, padx=5)

    def _create_booking_widgets(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="예약 실행", padding="10"); frame.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        status_font = ("TkDefaultFont", 11, "bold")
        self.current_time_label = ttk.Label(frame, text="현재 시간:", font=status_font); self.current_time_label.pack(pady=2)
        self.booking_time_label = ttk.Label(frame, text="다음 예약 시간:", font=status_font); self.booking_time_label.pack(pady=2)
        self.countdown_label = ttk.Label(frame, text="", font=status_font, foreground="blue"); self.countdown_label.pack(pady=5)
        btn_frame_1 = ttk.Frame(frame); btn_frame_1.pack(pady=5)
        ttk.Button(btn_frame_1, text="⚙️ 예약 시간 설정", command=self.show_booking_time_setting).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_1, text="🗑️ 모든 설정 초기화", command=self.reset_all_settings).pack(side=tk.LEFT, padx=5)
        btn_frame_2 = ttk.Frame(frame); btn_frame_2.pack(pady=5)
        self.start_button = ttk.Button(btn_frame_2, text="예약 시작", command=self.start_booking); self.start_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(btn_frame_2, text="예약 중지", command=self.stop_booking, state=tk.DISABLED); self.stop_button.pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_2, text="설정 저장", command=self.save_config).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame_2, text="설정 불러오기", command=self.load_config).pack(side=tk.LEFT, padx=5)

    def _create_log_widgets(self, parent: ttk.Frame):
        container = ttk.Frame(parent)
        # 로그 위젯을 부모(right_panel)의 1번 행(아래쪽 절반)에 배치
        container.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        
        header_frame = ttk.Frame(container)
        header_frame.grid(row=0, column=0, sticky="ew")
        log_label = ttk.Label(header_frame, text="실행 로그", font="TkDefaultFont 9 bold")
        log_label.pack(side=tk.LEFT, anchor='w', pady=2)
        admin_btn = ttk.Button(header_frame, text="⚙️ 관리자 설정", command=self.prompt_admin_password)
        admin_btn.pack(side=tk.LEFT, padx=10, anchor='w')
        
        self.log_text = scrolledtext.ScrolledText(container, height=10, wrap=tk.WORD)
        self.log_text.grid(row=1, column=0, sticky="nsew", pady=(5, 0))

    def _create_my_bookings_widgets(self, parent: ttk.Frame):
        frame = ttk.LabelFrame(parent, text="내 예약 현황", padding="10")
        frame.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        frame.rowconfigure(1, weight=1) # <<< Treeview가 들어갈 행의 비중 설정
        frame.columnconfigure(0, weight=1) # <<< Treeview가 들어갈 열의 비중 설정
        
        top_frame = ttk.Frame(frame)
        top_frame.grid(row=0, column=0, sticky="e", pady=5)
        ttk.Button(top_frame, text="새로고침", command=self.load_my_reservations).pack()
        
        cols = ('예약 날짜', '코트', '시간', '예약 상태'); self.my_bookings_tree = ttk.Treeview(frame, columns=cols, show='headings')
        for col in cols:
            self.my_bookings_tree.heading(col, text=col, command=lambda c=col: self.sort_my_bookings_tree(c))
            self.my_bookings_tree.column(col, width=120, anchor=tk.CENTER)
        self.my_bookings_tree.tag_configure('cancellable', foreground='blue'); self.my_bookings_tree.tag_configure('non_cancellable', foreground='red', background='#f0f0f0')
        self.my_bookings_tree.grid(row=1, column=0, sticky="nsew") # <<< sticky="nsew"로 상하좌우 모두 붙임
        
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=self.my_bookings_tree.yview); scrollbar.grid(row=1, column=1, sticky="ns")
        self.my_bookings_tree.configure(yscrollcommand=scrollbar.set)
        self.my_bookings_tree.bind('<Button-1>', self.handle_tree_click)

    def prompt_admin_password(self):
        dialog = AdminPasswordDialog(self.root)
        self.center_window(dialog)
        self.root.wait_window(dialog)
        password = dialog.password
        if password == "admin123": self.open_admin_window()
        elif password is not None: messagebox.showerror("인증 실패", "비밀번호가 올바르지 않습니다.")

    def open_admin_window(self):
        admin_win = tk.Toplevel(self.root)
        admin_win.title("관리자 설정 - 로그 관리")
        screen_width = admin_win.winfo_screenwidth()
        screen_height = admin_win.winfo_screenheight()
        admin_width = max(700, int(screen_width * 0.75))
        admin_height = max(500, int(screen_height * 0.75))
        
        # 중앙 위치 계산
        center_x = (screen_width - admin_width) // 2
        center_y = (screen_height - admin_height) // 2
        
        # 크기와 위치를 한 번에 설정
        admin_win.geometry(f"{admin_width}x{admin_height}+{center_x}+{center_y}")
        main_frame = ttk.Frame(admin_win, padding=10)
        main_frame.pack(fill="both", expand=True)
        main_frame.rowconfigure(1, weight=1); main_frame.columnconfigure(1, weight=1)
        list_frame = ttk.Frame(main_frame)
        list_frame.grid(row=1, column=0, sticky='ns', padx=(0, 10))
        list_frame.rowconfigure(0, weight=1)
        ttk.Label(list_frame, text="로그 파일 목록").pack()
        log_listbox = tk.Listbox(list_frame, exportselection=False, width=30)
        log_listbox.pack(fill='y', expand=True)
        list_scrollbar = ttk.Scrollbar(list_frame, orient='vertical', command=log_listbox.yview)
        list_scrollbar.pack(side='right', fill='y')
        log_listbox.config(yscrollcommand=list_scrollbar.set)
        content_frame = ttk.Frame(main_frame)
        content_frame.grid(row=1, column=1, sticky='nsew')
        content_frame.rowconfigure(0, weight=1); content_frame.columnconfigure(0, weight=1)
        log_display = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, state='disabled')
        log_display.grid(row=0, column=0, sticky='nsew')
        top_btn_frame = ttk.Frame(main_frame)
        top_btn_frame.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 10))
        def populate_log_file_list():
            log_listbox.delete(0, tk.END)
            log_files = sorted(glob.glob(f'{LOG_FILE_BASENAME}*'), reverse=True)
            for log_file in log_files: log_listbox.insert(tk.END, os.path.basename(log_file))
        def on_log_file_select(event):
            selected_indices = log_listbox.curselection()
            if not selected_indices: return
            selected_file = log_listbox.get(selected_indices[0])
            log_display.config(state='normal'); log_display.delete('1.0', tk.END)
            try:
                with open(selected_file, 'r', encoding='utf-8') as f: log_display.insert(tk.END, f.read())
            except Exception as e: log_display.insert(tk.END, f"로그 파일을 읽는 중 오류 발생: {e}")
            log_display.config(state='disabled'); log_display.see(tk.END)
        log_listbox.bind('<<ListboxSelect>>', on_log_file_select)
        def safe_file_operation(operation, filepath=None):
            global file_handler
            if file_handler and file_handler in logging.getLogger().handlers:
                file_handler.close()
                logging.getLogger().removeHandler(file_handler)
            try: operation(filepath)
            except Exception as e: messagebox.showerror("파일 작업 오류", f"파일 작업 중 오류가 발생했습니다: {e}", parent=admin_win)
            setup_logging()
        def delete_file_op(filepath):
            if os.path.exists(filepath): os.remove(filepath)
        def delete_selected_file():
            selected_indices = log_listbox.curselection()
            if not selected_indices:
                messagebox.showwarning("선택 오류", "삭제할 로그 파일을 목록에서 선택해주세요.", parent=admin_win); return
            selected_file = log_listbox.get(selected_indices[0])
            if messagebox.askyesno("파일 삭제 확인", f"'{selected_file}' 파일을 정말 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.", parent=admin_win, icon='warning'):
                safe_file_operation(delete_file_op, selected_file)
                self.log_message(f"관리자가 로그 파일 '{selected_file}'을(를) 삭제했습니다.", level='warning')
                populate_log_file_list()
                log_display.config(state='normal'); log_display.delete('1.0', tk.END); log_display.config(state='disabled')
        def delete_all_files():
            if messagebox.askyesno("전체 삭제 확인", "모든 로그 파일을 정말 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.", parent=admin_win, icon='warning'):
                log_files = glob.glob(f'{LOG_FILE_BASENAME}*')
                for log_file in log_files: safe_file_operation(delete_file_op, log_file)
                self.log_message(f"관리자가 {len(log_files)}개의 로그 파일을 모두 삭제했습니다.", level='warning')
                populate_log_file_list()
                log_display.config(state='normal'); log_display.delete('1.0', tk.END); log_display.config(state='disabled')
        ttk.Button(top_btn_frame, text="새로고침", command=populate_log_file_list).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn_frame, text="선택 파일 삭제", command=delete_selected_file).pack(side=tk.LEFT, padx=5)
        ttk.Button(top_btn_frame, text="전체 파일 삭제", command=delete_all_files).pack(side=tk.LEFT, padx=5)
        populate_log_file_list()
        admin_win.grab_set()
        self.root.wait_window(admin_win)

    def handle_tree_click(self, event: tk.Event):
        region = self.my_bookings_tree.identify("region", event.x, event.y)
        if region != "cell": return
        column_id = self.my_bookings_tree.identify_column(event.x)
        if column_id != f'#{len(self.my_bookings_tree["columns"])}': return
        item_id = self.my_bookings_tree.identify_row(event.y)
        if not item_id: return
        res_data = self.reservation_data.get(item_id)
        if not res_data:
            messagebox.showerror("오류", "예약 정보를 찾을 수 없습니다."); return
        if res_data.get('is_paid'):
            messagebox.showinfo("취소 불가", "결제가 완료된 예약은 취소할 수 없습니다.\n취소를 원하시면 웹사이트를 방문해주세요."); return
        date, court, time = res_data['values']
        if messagebox.askyesno("예약 취소 확인", f"정말 아래 예약을 취소하시겠습니까?\n\n- 날짜: {date}\n- 코트: {court}\n- 시간: {time}"):
            res_id_to_cancel = res_data['id']
            self.log_message(f"[{date} {court} {time}] 예약 취소를 시작합니다...")
            threading.Thread(target=self._cancel_worker, args=(res_id_to_cancel,), daemon=True).start()

    def _is_payment_completed(self, payment_status: Any) -> bool:
        if not payment_status: return False
        if isinstance(payment_status, str):
            status_lower = payment_status.lower().strip()
            paid_keywords = ['paid', 'completed', '결제완료', 'payment_completed']
            return status_lower in paid_keywords
        return False

    def sort_my_bookings_tree(self, col: str):
        data = [(self.my_bookings_tree.item(item)['values'], item) for item in self.my_bookings_tree.get_children('')]
        reverse = self.my_bookings_sort_col == col and not self.my_bookings_sort_rev
        self.my_bookings_sort_col, self.my_bookings_sort_rev = col, reverse
        col_map = {heading: i for i, heading in enumerate(self.my_bookings_tree['columns'])}
        def sort_key(item_tuple: tuple):
            values = item_tuple[0]
            try:
                date_val = datetime.strptime(values[col_map['예약 날짜']], '%Y-%m-%d').date()
                court_val = int(re.search(r'\d+', values[col_map['코트']]).group())
                time_val = datetime.strptime(values[col_map['시간']], '%H:%M').time()
                sort_priority = (date_val, time_val, court_val)
                if col == '예약 날짜': return sort_priority
                if col == '코트': return (court_val, date_val, time_val)
                if col == '시간': return (time_val, date_val, court_val)
                return sort_priority
            except (ValueError, IndexError, AttributeError): return (datetime.min.date(), datetime.min.time(), 99)
        data.sort(key=sort_key, reverse=reverse)
        for index, item_tuple in enumerate(data): self.my_bookings_tree.move(item_tuple[1], '', index)
        for c in self.my_bookings_tree['columns']:
            if c == '예약 상태': continue
            arrow = " ↓" if reverse else " ↑"
            self.my_bookings_tree.heading(c, text=c + (arrow if c == col else ""))

    def calculate_booking_time(self):
        try:
            year, month, day, hour, minute, second = (self.booking_year_var.get(), self.booking_month_var.get(), self.booking_day_var.get(), self.booking_hour_var.get(), self.booking_minute_var.get(), self.booking_second_var.get())
            self.next_booking_time = datetime(year, month, day, hour, minute, second)
        except ValueError:
            self.next_booking_time = datetime.now()
            self.log_message("❌ 유효하지 않은 예약 날짜가 설정되었습니다.", level='error')
        if hasattr(self, 'booking_time_label'): self.update_booking_time_label()

    def update_booking_time_label(self):
        if hasattr(self, 'next_booking_time'): self.booking_time_label.config(text=f"다음 예약 시간: {self.next_booking_time.strftime('%Y-%m-%d %H:%M:%S')}")

    def update_current_time(self):
        self.current_time_label.config(text=f"현재 시간: {self.get_synced_time().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        self.root.after(100, self.update_current_time)

    def update_countdown(self):
        if hasattr(self, 'next_booking_time'):
            time_diff = self.next_booking_time - self.get_synced_time()
            if time_diff.total_seconds() > 0:
                days, rem = divmod(time_diff.total_seconds(), 86400); hours, rem = divmod(rem, 3600); mins, secs = divmod(rem, 60)
                self.countdown_label.config(text=f"남은 시간: {int(days)}일 {int(hours)}시간 {int(mins)}분 {int(secs)}초")
            else: self.countdown_label.config(text="예약 시간이 지났습니다!")
        self.root.after(1000, self.update_countdown)

    def login(self):
        email, password = self.username_entry.get(), self.password_entry.get()
        if not email or not password: return messagebox.showerror("입력 오류", "이메일과 비밀번호를 입력해주세요.")
        self.log_message(f"{email} 로그인 시도 중...")
        threading.Thread(target=self._login_worker, args=(email, password), daemon=True).start()

    def _login_worker(self, email: str, password: str):
        success, message = self.booking_api.login(email, password)
        self.root.after(0, self.handle_login_result, success, message)

    def logout(self):
        self.is_logged_in = False
        self.booking_api.auth_token = None
        self.booking_api.user_id = None
        self.login_button.config(state=tk.NORMAL)
        self.logout_button.config(state=tk.DISABLED)
        self.login_status_label.config(text="로그인 상태: 로그아웃", foreground="red")
        self.password_entry.delete(0, tk.END)
        self.reservation_data.clear()
        for i in self.my_bookings_tree.get_children(): self.my_bookings_tree.delete(i)
        self.log_message("로그아웃되었습니다.")

    def handle_login_result(self, success: bool, message: str):
        if success:
            self.is_logged_in = True
            self.analytics_logger.log_event(
                user_email=self.username_entry.get(),
                machine_id=self.machine_id,
                event_type="app_start",
                event_data={"message": "Login successful"})
            self.login_status_label.config(text="로그인 상태: 로그인 성공", foreground="green")
            self.log_message("로그인 성공! 코트와 예약 정보를 불러옵니다.")
            self.login_button.config(state=tk.DISABLED)
            self.logout_button.config(state=tk.NORMAL)
            self.load_courts_info()
            self.load_my_reservations()
        else:
            self.analytics_logger.log_event(
                user_email=self.username_entry.get(),
                machine_id=self.machine_id,
                event_type="login_fail",
                event_data={"message": message})
            self.is_logged_in = False
            self.login_status_label.config(text="로그인 상태: 로그인 실패", foreground="red")
            self.log_message(f"로그인 실패: {message}", level='error')
            messagebox.showerror("로그인 실패", message)

    def load_courts_info(self):
        self.log_message("코트 정보 로딩 중...")
        threading.Thread(target=self._load_courts_worker, daemon=True).start()

    def _load_courts_worker(self):
        courts = self.booking_api.get_all_courts()
        if courts: self.log_message(f"{len(courts)}개 코트 정보 로드 완료.")
        else: self.log_message("코트 정보 로드 실패.", level='warning')

    def load_my_reservations(self):
        if not self.is_logged_in: return
        self.log_message("내 예약 정보를 불러옵니다...")
        threading.Thread(target=self._load_reservations_worker, daemon=True).start()

    def _load_reservations_worker(self):
        # 1. 내 예약의 상세 정보를 가져옵니다. (슬롯, 코트 정보 포함)
        reservations_details = self.booking_api.get_my_reservations_details()
        
        # 예약 정보가 없으면 빈 리스트로 화면을 업데이트하고 종료합니다.
        if not reservations_details or not isinstance(reservations_details, list):
            self.root.after(0, self.update_my_bookings_tree, [])
            return
            
        # 2. 별도로 결제 상태 목록을 가져옵니다.
        payment_statuses = self.booking_api.get_payment_statuses()
        
        # 3. 두 정보를 합쳐서 최종 예약 목록을 만듭니다.
        enriched_reservations = []
        for res_detail in reservations_details:
            if not isinstance(res_detail, dict):
                continue
            
            # 예약 ID를 기준으로 결제 상태를 찾아 추가합니다.
            res_id = res_detail.get('id')
            if res_id:
                res_detail['payment_status'] = payment_statuses.get(res_id)
            
            enriched_reservations.append(res_detail)
            
        # 4. 정보가 합쳐진 최종 목록으로 화면을 업데이트합니다.
        self.root.after(0, self.update_my_bookings_tree, enriched_reservations)

    def update_my_bookings_tree(self, reservations: List[Dict[str, Any]]):
        for i in self.my_bookings_tree.get_children(): self.my_bookings_tree.delete(i)
        self.reservation_data.clear()
        
        if not reservations: 
            self.log_message("예약된 내역이 없습니다.")
            self.analytics_logger.log_event(
                user_email=self.username_entry.get(), machine_id=self.machine_id,
                event_type="load_reservations",
                event_data={"reservation_count": 0, "reservations": []})
            return

        items_added = 0
        loaded_reservations_details = []
        
        for res in reservations:
            try:
                if not isinstance(res, dict): continue
                slot_info = res.get('slots');
                if not isinstance(slot_info, dict): continue
                res_id_for_cancel = res.get('id')
                if not res_id_for_cancel: continue 
                kst = datetime.fromisoformat(slot_info['start_time'].replace('Z', '+00:00')).astimezone(KST)
                date_str, time_str = kst.strftime("%Y-%m-%d"), kst.strftime("%H:%M")
                court_name = slot_info.get('courts', {}).get('name', '정보 없음')
                court_number_match = re.search(r'\d+', court_name)
                court_number = int(court_number_match.group()) if court_number_match else 99
                payment_status = res.get('payment_status')
                is_paid = self._is_payment_completed(payment_status)
                status_text = "취소 불가 (결제완료)" if is_paid else "클릭하여 취소"
                tag = 'non_cancellable' if is_paid else 'cancellable'
                values = (date_str, court_name, time_str, status_text)
                item_id = self.my_bookings_tree.insert('', 'end', values=values, tags=(tag,))
                items_added += 1
                original_values = (date_str, court_name, time_str)
                self.reservation_data[item_id] = {'id': res_id_for_cancel, 'payment_status': payment_status, 'values': original_values, 'is_paid': is_paid}
                loaded_reservations_details.append({"date": date_str, "court": court_number, "time": time_str})
            except Exception as e:
                self.log_message(f"예약 정보 파싱 오류: {e}", level='error')

        loaded_reservations_details.sort(key=lambda x: (x['date'], x['court'], x['time']))
        self.sort_my_bookings_tree('예약 날짜')
        self.log_message(f"📋 총 {items_added}개의 예약 정보를 화면에 표시했습니다.")
        final_log_data = {"reservation_count": items_added, "reservations": loaded_reservations_details}
        self.analytics_logger.log_event(
            user_email=self.username_entry.get(),
            machine_id=self.machine_id,
            event_type="load_reservations",
            event_data=final_log_data)

    def _cancel_worker(self, reservation_id: str):
        success, message = self.booking_api.cancel_reservation(reservation_id)
        if success:
            self.log_message(f"✅ 예약 취소 성공: {message}")
            self.root.after(0, self.load_my_reservations)
        else:
            self.log_message(f"❌ 예약 취소 실패: {message}", level='error')
            self.root.after(0, messagebox.showerror, "취소 실패", message)

    def add_booking_target(self):
        court_str = self.target_court_var.get()
        court_number = int(re.search(r'\d+', court_str).group())
        date, time = self.target_calendar.get_date().strftime("%Y-%m-%d"), self.target_time_var.get()
        if any(t['date'] == date and t['court'] == court_number and t['time'] == time for t in self.booking_targets):
            return messagebox.showwarning("중복", "이미 추가된 예약 목표입니다.")
        self.booking_targets.append({'date': date, 'court': court_number, 'time': time})
        self.targets_tree.insert('', 'end', values=(date, f"{court_number}번 코트", time))
        self.log_message(f"목표 추가: {date} {court_number}번 코트 {time}")

    def remove_booking_target(self):
        if not self.targets_tree.selection(): return messagebox.showwarning("선택 오류", "삭제할 목표를 선택해주세요.")
        for item in self.targets_tree.selection():
            date, court_str, time = self.targets_tree.item(item, 'values')
            court = int(court_str.replace('번 코트', ''))
            self.booking_targets = [t for t in self.booking_targets if not (t['date'] == date and t['court'] == court and t['time'] == time)]
            self.targets_tree.delete(item)
            self.log_message(f"목표 삭제: {date} {court}번 코트 {time}")

    def clear_all_targets(self):
        if messagebox.askyesno("확인", "모든 예약 목표를 삭제하시겠습니까?"):
            self.booking_targets.clear(); [self.targets_tree.delete(i) for i in self.targets_tree.get_children()]
            self.log_message("모든 목표 삭제 완료")

    def show_auto_add_dialog(self, day_type: str):
        dialog = tk.Toplevel(self.root)
        dialog.withdraw()
        dialog.title(f"다음달 {day_type} 자동 추가")
        main_frame = ttk.Frame(dialog, padding="15")
        main_frame.pack(fill="both", expand=True)
        vars_dict: Dict[str, Any] = {'weekdays': {}, 'dates': {}, 'times': {}, 'courts': {}}
        now = datetime.now()
        next_month_date = now.replace(day=28) + timedelta(days=4)
        next_year, next_month = next_month_date.year, next_month_date.month
        _, last_day = calendar.monthrange(next_year, next_month)
        ttk.Label(main_frame, text=f"{next_year}년 {next_month}월 {day_type} 자동 추가", font=("Arial", 14, "bold")).pack(pady=15)
        weekday_frame = ttk.LabelFrame(main_frame, text="요일 선택", padding="10")
        weekday_frame.pack(fill="x", pady=5, padx=10)
        weekdays_to_show = range(5) if day_type == "평일" else range(5, 7)
        for i in weekdays_to_show:
            var = tk.BooleanVar(value=True)
            ttk.Checkbutton(weekday_frame, text="월화수목금토일"[i], variable=var, command=lambda: update_date_list()).pack(side="left", padx=15, expand=True)
            vars_dict['weekdays'][i] = var
        date_outer_frame = ttk.LabelFrame(main_frame, text="날짜 선택", padding="10")
        date_outer_frame.pack(fill="x", pady=5, padx=10)
        date_check_frame = ttk.Frame(date_outer_frame)
        date_check_frame.pack(expand=True)
        for i in range(7): date_check_frame.columnconfigure(i, weight=1)
        def update_date_list():
            for w in date_check_frame.winfo_children(): w.destroy()
            vars_dict['dates'].clear()
            selected_weekdays = {k for k, v in vars_dict['weekdays'].items() if v.get()}
            col, row = 0, 0
            for day in range(1, last_day + 1):
                date_obj = datetime(next_year, next_month, day)
                if date_obj.weekday() in selected_weekdays:
                    var = tk.BooleanVar(value=True)
                    cb = ttk.Checkbutton(date_check_frame, text=date_obj.strftime("%d일(%a)"), variable=var)
                    cb.grid(row=row, column=col, sticky="w", padx=10, pady=5)
                    vars_dict['dates'][date_obj.strftime("%Y-%m-%d")] = var
                    col += 1
                    if col >= 7: col = 0; row += 1
        time_frame = ttk.LabelFrame(main_frame, text="시간 선택", padding="10")
        time_frame.pack(fill="x", pady=5, padx=10)
        times_grid = ttk.Frame(time_frame)
        times_grid.pack(expand=True)
        all_times = ["06:00", "08:00", "10:00", "12:00", "14:00", "16:00", "18:00", "20:00"]
        for i, t in enumerate(all_times):
            var = tk.BooleanVar(value=((day_type == "주말" and t in ["06:00", "08:00"]) or (day_type == "평일" and t == "06:00")))
            cb = ttk.Checkbutton(times_grid, text=t, variable=var)
            cb.grid(row=0, column=i, sticky="w", padx=5)
            vars_dict['times'][t] = var
        court_frame = ttk.LabelFrame(main_frame, text="코트 선택", padding="10")
        court_frame.pack(fill="x", pady=5, padx=10)
        court_grid_frame = ttk.Frame(court_frame)
        court_grid_frame.pack(expand=True)
        for i in range(5, 18):
            var = tk.BooleanVar(value=(i == 5))
            cb = ttk.Checkbutton(court_grid_frame, text=f"{i}번", variable=var)
            cb.grid(row=(i - 5) // 7, column=(i - 5) % 7, sticky="w", padx=20, pady=8)
            vars_dict['courts'][i] = var
        for i in range(7): court_grid_frame.columnconfigure(i, weight=1)
        def add_targets():
            added, dates, times, courts = 0, [d for d, v in vars_dict['dates'].items() if v.get()], \
                                          [t for t, v in vars_dict['times'].items() if v.get()], \
                                          [c for c, v in vars_dict['courts'].items() if v.get()]
            if not all([dates, times, courts]):
                return messagebox.showwarning("선택 오류", "날짜, 시간, 코트를 하나 이상 선택해야 합니다.", parent=dialog)
            for d in dates:
                for t in times:
                    for c in courts:
                        if not any(x['date'] == d and x['court'] == c and x['time'] == t for x in self.booking_targets):
                            self.booking_targets.append({'date': d, 'court': c, 'time': t})
                            self.targets_tree.insert('', 'end', values=(d, f"{c}번 코트", t))
                            added += 1
            if added > 0:
                self.log_message(f"{day_type} 목표 {added}개 추가 완료")
                dialog.destroy()
        btn_frame = ttk.Frame(main_frame)
        btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="목표 추가", command=add_targets).pack(side="left", padx=10)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side="left", padx=10)
        update_date_list()
        dialog.update_idletasks()
        self.center_window(dialog)
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.deiconify()

    def show_booking_time_setting(self):
        win = tk.Toplevel(self.root); win.title("⏰ 예약 시간 설정")
        win.withdraw()
        frame = ttk.Frame(win, padding=20); frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="예약 시작 시간 설정", font=("Arial", 16, "bold")).pack(pady=(0, 15))
        temp_vars = {'year': tk.IntVar(value=self.booking_year_var.get()), 'month': tk.IntVar(value=self.booking_month_var.get()),
                     'day': tk.IntVar(value=self.booking_day_var.get()), 'hour': tk.IntVar(value=self.booking_hour_var.get()),
                     'minute': tk.IntVar(value=self.booking_minute_var.get()), 'second': tk.IntVar(value=self.booking_second_var.get())}
        time_frame = ttk.Frame(frame); time_frame.pack(pady=10)
        now = datetime.now()
        ttk.Spinbox(time_frame, from_=now.year, to=now.year + 5, width=7, textvariable=temp_vars['year']).grid(row=0, column=0)
        ttk.Label(time_frame, text="년").grid(row=0, column=1, padx=(0, 10))
        ttk.Spinbox(time_frame, from_=1, to=12, width=5, textvariable=temp_vars['month'], wrap=True).grid(row=0, column=2)
        ttk.Label(time_frame, text="월").grid(row=0, column=3, padx=(0, 10))
        ttk.Spinbox(time_frame, from_=1, to=31, width=5, textvariable=temp_vars['day'], wrap=True).grid(row=0, column=4)
        ttk.Label(time_frame, text="일").grid(row=0, column=5, padx=(0, 10))
        ttk.Spinbox(time_frame, from_=0, to=23, width=5, textvariable=temp_vars['hour'], wrap=True).grid(row=0, column=6)
        ttk.Label(time_frame, text="시").grid(row=0, column=7)
        ttk.Spinbox(time_frame, from_=0, to=59, width=5, textvariable=temp_vars['minute'], wrap=True).grid(row=0, column=8)
        ttk.Label(time_frame, text="분").grid(row=0, column=9)
        ttk.Spinbox(time_frame, from_=0, to=59, width=5, textvariable=temp_vars['second'], wrap=True).grid(row=0, column=10)
        ttk.Label(time_frame, text="초").grid(row=0, column=11)
        def apply_settings():
            for key, var in temp_vars.items(): getattr(self, f"booking_{key}_var").set(var.get())
            self.calculate_booking_time()
            self.log_message("예약 시간 설정 변경 완료.")
            win.destroy()
        def reset_to_default():
            now = datetime.now()
            booking_day_setting = 25
            target_date = now if now.day <= booking_day_setting else now.replace(day=28) + timedelta(days=4)
            temp_vars['year'].set(target_date.year)
            temp_vars['month'].set(target_date.month)
            temp_vars['day'].set(booking_day_setting)
            temp_vars['hour'].set(10)
            temp_vars['minute'].set(0)
            temp_vars['second'].set(0)
        btn_frame = ttk.Frame(frame); btn_frame.pack(pady=15)
        ttk.Button(btn_frame, text="적용", command=apply_settings).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="기본값으로 초기화", command=reset_to_default).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="취소", command=win.destroy).pack(side=tk.LEFT, padx=10)
        win.update_idletasks()
        self.center_window(win)
        win.resizable(False, False)
        win.deiconify()

    def save_config(self):
        config = {'username': self.username_entry.get(), 'password': encrypt_password(self.password_entry.get()),
                  'machine_id': self.machine_id, 'booking_targets': self.booking_targets,
                  'booking_time': {'year': self.booking_year_var.get(), 'month': self.booking_month_var.get(),
                                   'day': self.booking_day_var.get(), 'hour': self.booking_hour_var.get(),
                                   'minute': self.booking_minute_var.get(), 'second': self.booking_second_var.get()}}
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f: json.dump(config, f, indent=2)
            self.log_message("설정이 안전하게 저장되었습니다."); messagebox.showinfo("저장 완료", "설정이 저장되었습니다.")
        except Exception as e: messagebox.showerror("저장 실패", f"설정 저장 실패: {e}")

    def load_config(self):
        if not os.path.exists(self.config_file):
            self.auto_set_default_booking_time(); self.calculate_booking_time(); return
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f: config = json.load(f)
            self.username_entry.delete(0, tk.END); self.username_entry.insert(0, config.get('username', ''))
            self.password_entry.delete(0, tk.END); self.password_entry.insert(0, decrypt_password(config.get('password', '')))
            self.machine_id = config.get('machine_id', self.machine_id)
            self.booking_targets = config.get('booking_targets', [])
            for i in self.targets_tree.get_children(): self.targets_tree.delete(i)
            for target in self.booking_targets: self.targets_tree.insert('', 'end', values=(target['date'], f"{target['court']}번 코트", target['time']))
            time_settings = config.get('booking_time')
            if time_settings:
                self.booking_year_var.set(time_settings.get('year')); self.booking_month_var.set(time_settings.get('month'))
                self.booking_day_var.set(time_settings.get('day')); self.booking_hour_var.set(time_settings.get('hour'))
                self.booking_minute_var.set(time_settings.get('minute')); self.booking_second_var.set(time_settings.get('second'))
            else: self.auto_set_default_booking_time()
            self.calculate_booking_time()
            self.log_message("저장된 설정을 불러왔습니다.")
        except Exception as e:
            self.log_message(f"설정 불러오기 실패: {e}", level='error'); self.auto_set_default_booking_time(); self.calculate_booking_time()

    def auto_set_default_booking_time(self):
        now = datetime.now(); booking_day_setting = 25
        target_date = now if now.day <= booking_day_setting else now.replace(day=28) + timedelta(days=4)
        self.booking_year_var.set(target_date.year); self.booking_month_var.set(target_date.month); self.booking_day_var.set(booking_day_setting)
        self.booking_hour_var.set(10); self.booking_minute_var.set(0); self.booking_second_var.set(0)
        self.log_message("기본 예약 시간이 자동으로 설정되었습니다.")

    def reset_all_settings(self):
        if messagebox.askyesno("경고", "모든 설정을 초기화하시겠습니까?\n저장된 아이디, 비밀번호, 예약 목표가 모두 삭제되며 복구할 수 없습니다.", icon='warning'):
            self.username_entry.delete(0, tk.END); self.password_entry.delete(0, tk.END)
            self.booking_targets.clear()
            for i in self.targets_tree.get_children(): self.targets_tree.delete(i)
            if os.path.exists(self.config_file): os.remove(self.config_file)
            self.log_message("모든 설정이 초기화되었습니다."); messagebox.showinfo("완료", "모든 설정이 초기화되었습니다.")

    def log_message(self, message: str, level: str = 'info'):
        log_entry = f"[{self.get_synced_time().strftime('%H:%M:%S')}] {message}"
        log_level = getattr(logging, level.upper(), logging.INFO)
        logging.log(log_level, message)
        if hasattr(self, 'log_text') and self.log_text.winfo_exists():
            self.log_text.insert(tk.END, log_entry + "\n"); self.log_text.see(tk.END)

    def start_booking(self):
        if not self.is_logged_in: return messagebox.showerror("오류", "먼저 로그인해주세요.")
        if not self.booking_targets: return messagebox.showerror("오류", "예약 목표를 추가해주세요.")
        if not self.booking_api.courts_info: return messagebox.showerror("오류", "코트 정보가 없습니다.")
        self.is_booking_active = True; self.start_button.config(state=tk.DISABLED); self.stop_button.config(state=tk.NORMAL)
        self.log_message("예약 시작!")
        threading.Thread(target=lambda: asyncio.run(self.booking_worker_async(self.booking_targets)), daemon=True).start()

    def stop_booking(self):
        self.is_booking_active = False
        self.reset_booking_state()
        self.log_message("예약 중지!")

    def reset_booking_state(self):
        self.is_booking_active = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)

    async def booking_worker_async(self, targets: List[Dict[str, Any]]):
        self.root.after(0, self.log_message, f"예약 시간({self.next_booking_time.strftime('%H:%M:%S')})까지 대기...")
        while self.is_booking_active and (self.next_booking_time - self.get_synced_time()).total_seconds() > 0.05:
            await asyncio.sleep(0.05)
        if not self.is_booking_active: return
        self.root.after(0, self.log_message, "고속 동시 예약 시작!")
        all_dates = sorted(list(set(t['date'] for t in targets)))
        start_date, end_date = all_dates[0], all_dates[-1]
        successful = set()
        failures = []
        start_t = time.time()
        
        # 모든 목표를 추적하기 위한 세트 생성
        all_target_keys = set(f"{t['date']}|{t['court']}|{t['time']}" for t in targets)
        attempted_targets = set()  # 실제로 시도한 목표들
        
        async with aiohttp.ClientSession() as session:
            while self.is_booking_active and (time.time() - start_t) < 30 and len(successful) < len(targets):
                try:
                    slots = await self.booking_api.get_available_slots_async(start_date, end_date)
                    tasks, pending = [], []
                    if not slots: await asyncio.sleep(0.1); continue
                    for slot in slots:
                        s_time = datetime.fromisoformat(slot['start_time'].replace('Z', '+00:00')).astimezone(KST)
                        s_date, s_time_str, s_court = s_time.strftime('%Y-%m-%d'), s_time.strftime('%H:%M'), slot.get('court_id')
                        for t in targets:
                            t_key = f"{t['date']}|{t['court']}|{t['time']}"
                            if t_key in successful or t_key in pending: continue
                            if t['date'] == s_date and t['time'] == s_time_str and self.booking_api.courts_info.get(t['court']) == s_court:
                                tasks.append(self.booking_api.reserve_slot_async(session, slot['id']))
                                pending.append(t_key)
                                attempted_targets.add(t_key)  # 시도한 목표로 추가
                                self.root.after(0, self.log_message, f"🎯 [{t['date']} {t['court']}번 {t['time']}] 작업 추가!")
                                break
                    if tasks:
                        results = await asyncio.gather(*tasks)
                        for i, res in enumerate(results):
                            t_key = pending[i]
                            if t_key not in successful:
                                t_date_str, t_court_str, t_time_str = t_key.split('|')
                                self.root.after(0, self.log_message,
                                                f"✅ [{t_date_str} {t_court_str}번 {t_time_str}] 성공!" if res[
                                                    'success'] else f"❌ [{t_date_str} {t_court_str}번 {t_time_str}] 실패: {res['message']}")
                                if res['success']:
                                    successful.add(t_key)
                                else:
                                    # 시도했지만 실패한 경우
                                    failures.append({"target": {"date": t_date_str, "court": int(t_court_str), "time": t_time_str}, "reason": res['message']})
                except Exception as e:
                    self.log_message(f"Booking loop error: {e}", level='error')

        # 사용자가 중지한 경우의 실패 처리
        if not self.is_booking_active:
            for t in targets:
                t_key = f"{t['date']}|{t['court']}|{t['time']}"
                if t_key not in successful:
                    failures.append({"target": t, "reason": "사용자가 직접 중지"})
        else:
            # 60초 시간 제한 또는 모든 슬롯 확인 후 미처리 목표들 실패 처리
            for t_key in all_target_keys:
                if t_key not in successful and t_key not in attempted_targets:
                    t_date_str, t_court_str, t_time_str = t_key.split('|')
                    target_dict = {"date": t_date_str, "court": int(t_court_str), "time": t_time_str}
                    failures.append({"target": target_dict, "reason": "해당 시간대에 예약 가능한 슬롯을 찾을 수 없음"})
                    self.root.after(0, self.log_message, f"❌ [{t_date_str} {t_court_str}번 {t_time_str}] 실패: 해당 시간대에 예약 가능한 슬롯을 찾을 수 없음")

        successful_list = []
        for s_key in successful:
            try:
                s_date, s_court, s_time = s_key.split('|')
                successful_list.append({"date": s_date, "court": int(s_court), "time": s_time})
            except ValueError: continue
        summary_data = {"targets_attempted": len(targets), "success_count": len(successful), "failure_count": len(failures),
                        "successful_bookings": successful_list, "failed_bookings": failures}
        self.analytics_logger.log_event(
            user_email=self.username_entry.get(),
            machine_id=self.machine_id,
            event_type="booking_summary",
            event_data=summary_data
        )
        self.root.after(0, self.log_message, f"🎉 프로세스 종료. 성공: {len(successful)}개, 실패: {len(failures)}개")
        self.root.after(0, self.reset_booking_state)
        self.root.after(0, self.load_my_reservations)

# ==============================================================================
# 6. 프로그램 실행
# ==============================================================================
def main():
    root = tk.Tk()
    global app
    app = TennisBookingGUI(root)
    def on_closing():
        if app.is_booking_active and not messagebox.askokcancel("종료", "예약이 실행 중입니다. 정말 종료하시겠습니까?"): return
        app.stop_booking()
        if app.is_logged_in:
            duration = (app.get_synced_time() - app.session_start_time).total_seconds()
            app.analytics_logger.log_event(
                user_email=app.username_entry.get(),
                machine_id=app.machine_id,
                event_type="app_close",
                event_data={"duration_seconds": int(duration)})
            time.sleep(0.5)
        logging.shutdown()
        root.destroy()
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.critical("프로그램 실행 중 치명적인 오류 발생", exc_info=True)
        messagebox.showerror("치명적 오류", f"프로그램 실행 중 심각한 오류가 발생했습니다.\n로그 파일(app.log)을 확인해주세요.\n\n오류: {e}")