import sys
import os
import time
import subprocess
import tkinter as tk

def perform_update(root):
    try:
        old_app_name = sys.argv[1]
        new_app_name = sys.argv[2]
        backup_file = old_app_name + ".old"

        # 1. 메인 프로그램이 완전히 종료될 시간을 줍니다.
        time.sleep(3)

        # 2. 만약 이전에 만들어진 .old 백업 파일이 있다면 먼저 삭제합니다.
        if os.path.exists(backup_file):
            os.remove(backup_file)

        # 3. 현재 사용 중인 구버전 앱을 .old로 이름을 바꿉니다.
        if os.path.exists(old_app_name):
            os.rename(old_app_name, backup_file)

        # 4. 다운로드한 신버전 앱의 이름을 원래 이름으로 바꿉니다.
        os.rename(new_app_name, old_app_name)

        # 5. 업데이트된 새 프로그램을 실행합니다.
        subprocess.Popen([old_app_name])

    except Exception as e:
        with open("updater_error.log", "w", encoding='utf-8') as f:
            f.write(f"오류 발생: {e}\n")
            f.write(f"전달받은 인자: {sys.argv}\n")
    finally:
        # 6. 모든 작업 후 업데이터 자신은 종료됩니다.
        root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.attributes('-topmost', True)
    
    label = tk.Label(root, text="업데이트 중입니다...\n잠시 후 프로그램이 다시 시작됩니다.",
                     font=("Malgun Gothic", 12), bg="white", padx=20, pady=20,
                     relief="solid", borderwidth=1)
    label.pack()

    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - root.winfo_width()) // 2
    y = (screen_height - root.winfo_height()) // 2
    root.geometry(f"+{x}+{y}")
    
    root.deiconify()

    root.after(100, lambda: perform_update(root))
    
    root.mainloop()