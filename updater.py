import sys
import os
import time
import subprocess
import tkinter as tk

def perform_update(root):
    try:
        old_app_name = sys.argv[1]
        new_app_name = sys.argv[2]

        time.sleep(3)

        if os.path.exists(old_app_name):
            os.rename(old_app_name, old_app_name + ".old")

        os.rename(new_app_name, old_app_name)

        subprocess.Popen([old_app_name])

    except Exception as e:
        with open("updater_error.log", "w") as f:
            f.write(str(e))
    finally:
        root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw() # 창 숨기기
    
    # 작은 안내 창 스타일 설정
    root.overrideredirect(True) # 창 테두리 없애기
    root.attributes('-topmost', True) # 항상 위에 표시
    
    # 안내 메시지
    label = tk.Label(root, text="업데이트 중입니다...\n잠시 후 프로그램이 다시 시작됩니다.",
                     font=("Malgun Gothic", 12), bg="white", padx=20, pady=20,
                     relief="solid", borderwidth=1)
    label.pack()

    # 창을 화면 정중앙에 위치시키기
    root.update_idletasks()
    screen_width = root.winfo_screenwidth()
    screen_height = root.winfo_screenheight()
    x = (screen_width - root.winfo_width()) // 2
    y = (screen_height - root.winfo_height()) // 2
    root.geometry(f"+{x}+{y}")
    
    root.deiconify() # 창 표시

    # GUI가 표시된 후 실제 업데이트 작업을 수행
    root.after(100, lambda: perform_update(root))
    
    root.mainloop()