def log_info(message: str) -> None:
    print(f"ℹ️ \033[36m{message}\033[0m")

def log_warning(message: str) -> None:
    print(f"⚠️️\033[33m{message}\033[0m")

def log_error(message: str) -> None:
    print(f"❌ \033[31m{message}\033[0m")