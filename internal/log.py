from datetime import datetime

def log_info(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("log.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} ℹ️ {message}\n")
    print(f"{timestamp} ℹ️ \033[36m{message}\033[0m")

def log_warning(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("log.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} ⚠️ {message}\n")
    print(f"{timestamp} ⚠️️\033[33m{message}\033[0m")

def log_error(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open("log.log", "a", encoding="utf-8") as log_file:
        log_file.write(f"{timestamp} ❌ {message}\n")
    print(f"{timestamp} ❌ \033[31m{message}\033[0m")