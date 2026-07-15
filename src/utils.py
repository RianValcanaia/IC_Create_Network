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

def get_bind_ip(config, default="0.0.0.0"):
    """Retorna o IP definido no network_BFT.yaml (raiz), ou um default."""
    return config['network_topology'].get('ip', default)

def get_connect_host(config, default="localhost"):
    """IP/host que os scripts CLI (fabric-ca-client, peer, osnadmin) devem usar."""
    return config['network_topology'].get('ip', default)