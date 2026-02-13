# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Utilitários para formatação de saída no terminal (CLI).

Define códigos de cores ANSI e métodos estáticos para padronizar a exibição
de mensagens de log (INFO, SUCESSO, AVISO, ERRO), melhorando a experiência
do usuário.
"""

class Colors:
    RESET = "\033[0m"
    BLUE = "\033[34m"
    GREEN = "\033[32m"
    RED = "\033[31m"
    YELLOW = "\033[33m"

    @staticmethod
    def headerln(msg: str):
        print(f"{Colors.BLUE}[INFO] === {msg.upper()} ==={Colors.RESET}")

    @staticmethod
    def infoln(msg: str):
        print(f"{Colors.BLUE}[INFO] --- {msg} ---{Colors.RESET}")

    @staticmethod
    def actionln(msg: str):
        print(f"{Colors.BLUE}[INFO] > {msg}{Colors.RESET}")

    @staticmethod
    def successln(msg: str):
        print(f"{Colors.GREEN}[SUCESSO] [✓] {msg}{Colors.RESET}")

    @staticmethod
    def errorln(msg: str):
        print(f"{Colors.RED}[ERRO] [X] {msg}{Colors.RESET}")

    @staticmethod
    def warnln(msg: str):
        print(f"{Colors.YELLOW}[AVISO] [!] {msg}{Colors.RESET}")