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

    def infoln(msg: str):
        print(f"{Colors.BLUE}[INFO] {msg}{Colors.RESET}")

    def successln(msg: str):
        print(f"{Colors.GREEN}[SUCESSO] {msg}{Colors.RESET}")

    def errorln(msg: str):
        print(f"{Colors.RED}[ERRO] {msg}{Colors.RESET}")

    def warnln(msg: str):
        print(f"{Colors.YELLOW}[AVISO] {msg}{Colors.RESET}")
