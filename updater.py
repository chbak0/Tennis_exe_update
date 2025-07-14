import sys
import os
import time
import subprocess

# 이 스크립트는 3개의 인자(argument)를 받습니다.
# sys.argv[0]: 스크립트 자기 자신 (updater.py)
# sys.argv[1]: 구버전 메인 프로그램 파일명 (예: 송도테니스예약.exe)
# sys.argv[2]: 다운로드한 신버전 프로그램 파일명 (예: app_new.exe)

try:
    old_app_name = sys.argv[1]
    new_app_name = sys.argv[2]

    # 1. 메인 프로그램이 완전히 종료될 시간을 벌어줍니다. (3초 대기)
    time.sleep(3)

    # 2. 구버전 파일을 .old로 이름을 변경하여 백업합니다.
    if os.path.exists(old_app_name):
        os.rename(old_app_name, old_app_name + ".old")

    # 3. 다운로드한 신버전 파일의 이름을 메인 프로그램 이름으로 변경합니다.
    os.rename(new_app_name, old_app_name)

    # 4. 업데이트된 새로운 메인 프로그램을 실행합니다.
    subprocess.Popen([old_app_name])

except Exception as e:
    # 혹시 오류가 발생하면 파일에 기록합니다.
    with open("updater_error.log", "w") as f:
        f.write(str(e))