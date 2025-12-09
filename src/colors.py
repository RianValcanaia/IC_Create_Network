class Colors:
    RESET = "\033[0m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"

    def infoln(msg: str):
        print(f"{Colors.BLUE}[INFO] {msg}{Colors.RESET}")

    def successln(msg: str):
        print(f"{Colors.GREEN}[SUCESSO] {msg}{Colors.RESET}")

    def errorln(msg: str):
        print(f"{Colors.RED}[ERRO] {msg}{Colors.RESET}")

    def warnln(msg: str):
        print(f"{Colors.YELLOW}[AVISO] {msg}{Colors.RESET}")
