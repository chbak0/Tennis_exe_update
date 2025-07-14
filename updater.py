import sys
import os
import time
import subprocess

try:
    old_app_name = sys.argv[1]
    new_app_name = sys.argv[2]

    # 1. 메인 프로그램이 완전히 종료될 시간을 줍니다.
    time.sleep(3)

    # 2. 구버전 파일을 .old로 이름을 바꿉니다.
    if os.path.exists(old_app_name):
        os.rename(old_app_name, old_app_name + ".old")

    # 3. 다운로드한 신버전 파일의 이름을 메인 프로그램 이름으로 바꿉니다.
    os.rename(new_app_name, old_app_name)

    # 4. 업데이트된 새 프로그램을 실행합니다.
    subprocess.Popen([old_app_name])

except Exception as e:
    # 오류 발생 시 로그 파일을 남깁니다.
    with open("updater_error.log", "w") as f:
        f.write(str(e))