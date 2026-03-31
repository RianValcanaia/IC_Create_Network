# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Orquestrador de deploy distribuído via SLURM.

Responsável por ler a topologia do network.yaml, gerar um único script bash
com todas as fases do deploy e submetê-lo como um único job SLURM a partir
de uma máquina de login/gerenciamento externa aos nós de compute.

O job aloca todos os nós de uma vez com --exclusive e --time definidos pelo
usuário. Dentro do job, cada fase usa 'srun --nodelist=<nó>' para direcionar
o trabalho ao nó correto — fases paralelas rodam em background com 'wait'.

Fluxo dentro do job:
  [Fase 1] CAs           — srun em paralelo em todos os nós
  [Fase 2] Enroll        — srun no coordenador
  [Fase 3] Artifacts     — srun no coordenador
  [Fase 4] Nodes         — srun em paralelo em todos os nós
  [Fase 5] Channels      — srun no coordenador
  [Fase 6] Chaincode     — srun no coordenador
  [Fase 7] CCAAS         — srun em paralelo nos nós com chaincode

Requisitos:
  - Máquina de submissão tem acesso ao sbatch (nó de login do cluster)
  - Todos os nós de compute acessam o mesmo filesystem compartilhado (NFS/Lustre)
  - Docker disponível nos nós de compute
  - Cada máquina em network.yaml possui os campos 'slurm_node' e 'ip'
  - Exatamente uma máquina marcada como 'coordinator: true'
"""

import subprocess
from ..utils import Colors as co


class SlurmDeployGenerator:

    def __init__(self, config, paths):
        self.config = config
        self.paths  = paths

    # ──────────────────────────────────────────────────────────────────────────
    # Ponto de entrada principal
    # ──────────────────────────────────────────────────────────────────────────

    def deploy(self, time):
        """
        Gera um script bash com todas as fases do deploy e o submete como um
        único job SLURM via SSH no login node. Retorna imediatamente após a submissão.

        Parâmetros:
          time — duração máxima do job no formato HH:MM:SS (ex: '03:00:00')
        """
        machines = self.config['network_topology'].get('machines', {})
        if not machines:
            raise RuntimeError(
                "Seção 'machines' não encontrada no network.yaml. "
                "Defina as máquinas e seus campos 'ip', 'slurm_node' e 'coordinator'."
            )

        for name, m in machines.items():
            if 'slurm_node' not in m:
                raise RuntimeError(
                    f"Máquina '{name}' não possui o campo 'slurm_node' no network.yaml."
                )
            if 'ip' not in m:
                raise RuntimeError(
                    f"Máquina '{name}' não possui o campo 'ip' no network.yaml."
                )

        coordinator = next(
            (name for name, m in machines.items() if m.get('coordinator')),
            None
        )
        if not coordinator:
            raise RuntimeError(
                "Nenhuma máquina marcada como 'coordinator: true' no network.yaml. "
                "O coordenador é o nó que executa enrollment, canais e lifecycle."
            )

        slurm_cfg = self.config['network_topology'].get('slurm', {})
        login_node = slurm_cfg.get('login_node')
        cluster_project_dir = slurm_cfg.get('cluster_project_dir')
        if not login_node:
            raise RuntimeError(
                "Campo 'slurm.login_node' não encontrado no network.yaml."
            )
        if not cluster_project_dir:
            raise RuntimeError(
                "Campo 'slurm.cluster_project_dir' não encontrado no network.yaml."
            )

        coord_node          = machines[coordinator]['slurm_node']
        cluster_log_dir     = f"{cluster_project_dir}/network/logs"
        local_log_dir       = self.paths.network_dir / "logs"
        local_log_dir.mkdir(parents=True, exist_ok=True)

        nodelist  = ",".join(m['slurm_node'] for m in machines.values())
        num_nodes = len(machines)

        co.headerln("Deploy distribuído via SLURM")
        co.infoln(f"Coordenador       : {coordinator} ({coord_node})")
        co.infoln(f"Nós               : {nodelist}")
        co.infoln(f"Login node (SSH)  : {login_node}")
        co.infoln(f"Projeto no cluster: {cluster_project_dir}")
        co.infoln(f"Tempo             : {time}")

        script = self._build_script(
            machines            = machines,
            coordinator         = coordinator,
            coord_node          = coord_node,
            project_dir         = cluster_project_dir,
            log_dir             = cluster_log_dir,
            nodelist            = nodelist,
            num_nodes           = num_nodes,
            time                = time,
        )

        local_script_path = local_log_dir / "fabric-deploy.sh"
        local_script_path.write_text(script)
        local_script_path.chmod(0o755)
        co.actionln(f"Script gerado localmente: {local_script_path}")

        remote_script_path = f"{cluster_log_dir}/fabric-deploy.sh"
        jid = self._sbatch(login_node, local_script_path, remote_script_path, cluster_log_dir)
        co.successln(
            f"\nJob submetido: {jid}\n"
            f"Acompanhe com : ssh {login_node} squeue -j {jid}\n"
            f"Log em        : {cluster_log_dir}/slurm-{jid}-fabric-deploy.log"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Geração do script bash
    # ──────────────────────────────────────────────────────────────────────────

    def _build_script(self, machines, coordinator, coord_node, project_dir,
                      log_dir, nodelist, num_nodes, time):
        """
        Monta o script bash completo que será submetido como job SLURM.
        Cada fase usa 'srun --nodelist=<nó>' para direcionar o trabalho.
        Fases paralelas disparam em background e aguardam com 'wait'.
        """
        ccaas_machines = sorted(set(
            cc.get('machine')
            for cc in self.config['network_topology'].get('chaincodes', [])
            if cc.get('machine')
        ))

        lines = [
            "#!/bin/bash",
            f"#SBATCH --job-name=fabric-deploy",
            f"#SBATCH --nodes={num_nodes}",
            f"#SBATCH --nodelist={nodelist}",
            f"#SBATCH --exclusive",
            f"#SBATCH --time={time}",
            f"#SBATCH --chdir={project_dir}",
            f"#SBATCH --output={log_dir}/slurm-%j-fabric-deploy.log",
            f"#SBATCH --error={log_dir}/slurm-%j-fabric-deploy.err",
            "",
            'set -euo pipefail',
            "",
            "# ── Fase 1: CAs em paralelo ──────────────────────────────────────",
        ]

        for name, m in machines.items():
            node = m['slurm_node']
            lines.append(
                f'srun --nodes=1 --ntasks=1 --nodelist={node} '
                f'python3 main.py --start --machine {name} --phase cas &'
            )
        lines += ["wait", ""]

        lines += [
            "# ── Fase 2: Enrollment (coordenador) ────────────────────────────",
            f"srun --nodes=1 --ntasks=1 --nodelist={coord_node} "
            f"python3 main.py --setup --phase enroll",
            "",
            "# ── Fase 3: Artefatos (coordenador) ─────────────────────────────",
            f"srun --nodes=1 --ntasks=1 --nodelist={coord_node} "
            f"python3 main.py --setup --phase artifacts",
            "",
            "# ── Fase 4: Peers e orderers em paralelo ─────────────────────────",
        ]

        for name, m in machines.items():
            node = m['slurm_node']
            lines.append(
                f'srun --nodes=1 --ntasks=1 --nodelist={node} '
                f'python3 main.py --start --machine {name} --phase nodes &'
            )
        lines += ["wait", ""]

        lines += [
            "# ── Fase 5: Canais (coordenador) ────────────────────────────────",
            f"srun --nodes=1 --ntasks=1 --nodelist={coord_node} "
            f"python3 main.py --setup --phase channels",
            "",
            "# ── Fase 6: Lifecycle do chaincode (coordenador) ─────────────────",
            f"srun --nodes=1 --ntasks=1 --nodelist={coord_node} "
            f"python3 main.py --setup --phase chaincode",
            "",
        ]

        if ccaas_machines:
            lines.append(
                "# ── Fase 7: Containers CCAAS em paralelo ────────────────────────"
            )
            for name in ccaas_machines:
                node = machines[name]['slurm_node']
                lines.append(
                    f'srun --nodes=1 --ntasks=1 --nodelist={node} '
                    f'python3 main.py --start --machine {name} --phase ccaas &'
                )
            lines += ["wait", ""]

        return "\n".join(lines) + "\n"

    # ──────────────────────────────────────────────────────────────────────────
    # Submissão do job
    # ──────────────────────────────────────────────────────────────────────────

    def _sbatch(self, login_node, local_script_path, remote_script_path, remote_log_dir):
        """
        Copia o script para o login node via scp, cria o diretório de logs remoto
        e submete via 'ssh <login_node> sbatch'. Retorna o job ID numérico.
        """
        # Garante que o diretório de logs existe no cluster
        mkdir = subprocess.run(
            ["ssh", login_node, f"mkdir -p {remote_log_dir}"],
            capture_output=True, text=True,
        )
        if mkdir.returncode != 0:
            raise RuntimeError(
                f"Falha ao criar diretório de logs no cluster:\n{mkdir.stderr.strip()}"
            )

        # Copia o script para o cluster
        scp = subprocess.run(
            ["scp", str(local_script_path), f"{login_node}:{remote_script_path}"],
            capture_output=True, text=True,
        )
        if scp.returncode != 0:
            raise RuntimeError(
                f"Falha ao copiar script para {login_node}:\n{scp.stderr.strip()}"
            )
        co.actionln(f"Script copiado para {login_node}:{remote_script_path}")

        # Submete o job
        result = subprocess.run(
            ["ssh", login_node, f"sbatch --parsable {remote_script_path}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"Falha ao submeter job SLURM via ssh {login_node}:\n{result.stderr.strip()}"
            )
        return result.stdout.strip().split(";")[0]
