# Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
"""
Orquestrador de deploy distribuído via SLURM.

Responsável por ler a topologia do network.yaml e submeter a sequência
completa de jobs SLURM necessários para subir a rede Fabric em múltiplas
máquinas. A máquina de gerenciamento executa apenas este módulo — todo o
processamento real (containers, enrollment, canais) corre nos nós de compute.

Fluxo de jobs submetidos:
  [Fase 1] CAs           — paralelo em todos os nós
  [Fase 2] Enroll        — coordenador, após todas as CAs
  [Fase 3] Artifacts     — coordenador, após enroll
  [Fase 4] Nodes         — paralelo em todos os nós, após artifacts
  [Fase 5] Channels      — coordenador, após todos os nós
  [Fase 6] Chaincode     — coordenador, após channels
  [Fase 7] CCAAS         — nós com chaincode atribuído, após lifecycle

Cada job executa 'python3 main.py --start' ou '--setup' com os parâmetros
corretos. As dependências são encadeadas via '--dependency=afterok:JOBID',
garantindo a ordem sem polling manual.

Requisitos:
  - Todos os nós acessam o mesmo sistema de arquivos compartilhado
  - Docker disponível nos nós de compute
  - Cada máquina em network.yaml possui os campos 'slurm_node' e 'ip'
  - Exatamente uma máquina marcada como 'coordinator: true'
"""

import subprocess
from pathlib import Path
from ..utils import Colors as co


class SlurmDeployGenerator:

    def __init__(self, config, paths):
        self.config = config
        self.paths  = paths

    # ──────────────────────────────────────────────────────────────────────────
    # Ponto de entrada principal
    # ──────────────────────────────────────────────────────────────────────────

    def deploy(self):
        """
        Orquestra o deploy completo submetendo todos os jobs SLURM necessários.
        Retorna imediatamente após a submissão — os jobs correm de forma
        assíncrona no cluster. Use 'squeue -u $USER' para acompanhar.
        """
        machines = self.config['network_topology'].get('machines', {})
        if not machines:
            raise RuntimeError(
                "Seção 'machines' não encontrada no network.yaml. "
                "Defina as máquinas e seus campos 'ip', 'slurm_node' e 'coordinator'."
            )

        # Valida campos obrigatórios em cada máquina
        for name, m in machines.items():
            if 'slurm_node' not in m:
                raise RuntimeError(
                    f"Máquina '{name}' não possui o campo 'slurm_node' no network.yaml."
                )
            if 'ip' not in m:
                raise RuntimeError(
                    f"Máquina '{name}' não possui o campo 'ip' no network.yaml."
                )

        # Identifica o nó coordenador (roda enrollment, canais, lifecycle)
        coordinator = next(
            (name for name, m in machines.items() if m.get('coordinator')),
            None
        )
        if not coordinator:
            raise RuntimeError(
                "Nenhuma máquina marcada como 'coordinator: true' no network.yaml. "
                "O coordenador é o nó que executa enrollment, canais e lifecycle."
            )

        coord_node  = machines[coordinator]['slurm_node']
        project_dir = str(self.paths.base_dir)

        # Garante que o diretório de logs existe antes de submeter os jobs
        log_dir = self.paths.network_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        co.headerln("Deploy distribuído via SLURM")
        co.infoln(f"Coordenador: {coordinator} ({coord_node})")
        co.infoln(f"Nós de compute: {list(machines.keys())}")

        # ── Fase 1: CAs em todos os nós (paralelo) ────────────────────────────
        co.infoln("\n[Fase 1] Subindo CAs...")
        ca_jids = []
        for name, m in machines.items():
            jid = self._sbatch(
                node       = m['slurm_node'],
                cmd        = f"python3 main.py --start --machine {name} --phase cas",
                job_name   = f"fabric-cas-{name}",
                workdir    = project_dir,
                log_dir    = str(log_dir),
            )
            ca_jids.append(jid)
            co.actionln(f"  {name} ({m['slurm_node']}) → job {jid}")

        dep_cas = "afterok:" + ":".join(ca_jids)

        # ── Fase 2: Enrollment (coordenador, após todas as CAs) ───────────────
        co.infoln("\n[Fase 2] Enrollment...")
        jid_enroll = self._sbatch(
            node       = coord_node,
            cmd        = "python3 main.py --setup --phase enroll",
            job_name   = "fabric-enroll",
            workdir    = project_dir,
            log_dir    = str(log_dir),
            dependency = dep_cas,
        )
        co.actionln(f"  {coordinator} ({coord_node}) → job {jid_enroll}")

        # ── Fase 3: Artefatos (coordenador, após enroll) ──────────────────────
        co.infoln("\n[Fase 3] Gerando artefatos...")
        jid_artifacts = self._sbatch(
            node       = coord_node,
            cmd        = "python3 main.py --setup --phase artifacts",
            job_name   = "fabric-artifacts",
            workdir    = project_dir,
            log_dir    = str(log_dir),
            dependency = f"afterok:{jid_enroll}",
        )
        co.actionln(f"  {coordinator} ({coord_node}) → job {jid_artifacts}")

        # ── Fase 4: Peers e orderers em todos os nós (paralelo, após artifacts)
        co.infoln("\n[Fase 4] Subindo peers e orderers...")
        node_jids = []
        for name, m in machines.items():
            jid = self._sbatch(
                node       = m['slurm_node'],
                cmd        = f"python3 main.py --start --machine {name} --phase nodes",
                job_name   = f"fabric-nodes-{name}",
                workdir    = project_dir,
                log_dir    = str(log_dir),
                dependency = f"afterok:{jid_artifacts}",
            )
            node_jids.append(jid)
            co.actionln(f"  {name} ({m['slurm_node']}) → job {jid}")

        dep_nodes = "afterok:" + ":".join(node_jids)

        # ── Fase 5: Canais (coordenador, após todos os nós) ───────────────────
        co.infoln("\n[Fase 5] Configurando canais...")
        jid_channels = self._sbatch(
            node       = coord_node,
            cmd        = "python3 main.py --setup --phase channels",
            job_name   = "fabric-channels",
            workdir    = project_dir,
            log_dir    = str(log_dir),
            dependency = dep_nodes,
        )
        co.actionln(f"  {coordinator} ({coord_node}) → job {jid_channels}")

        # ── Fase 6: Lifecycle do chaincode (coordenador, após canais) ─────────
        co.infoln("\n[Fase 6] Lifecycle do chaincode...")
        jid_chaincode = self._sbatch(
            node       = coord_node,
            cmd        = "python3 main.py --setup --phase chaincode",
            job_name   = "fabric-chaincode",
            workdir    = project_dir,
            log_dir    = str(log_dir),
            dependency = f"afterok:{jid_channels}",
        )
        co.actionln(f"  {coordinator} ({coord_node}) → job {jid_chaincode}")

        # ── Fase 7: Containers CCAAS nos nós designados (após lifecycle) ──────
        ccaas_machines = sorted(set(
            cc.get('machine')
            for cc in self.config['network_topology'].get('chaincodes', [])
            if cc.get('machine')
        ))

        if ccaas_machines:
            co.infoln("\n[Fase 7] Iniciando containers CCAAS...")
            for name in ccaas_machines:
                m = machines[name]
                jid = self._sbatch(
                    node       = m['slurm_node'],
                    cmd        = f"python3 main.py --start --machine {name} --phase ccaas",
                    job_name   = f"fabric-ccaas-{name}",
                    workdir    = project_dir,
                    log_dir    = str(log_dir),
                    dependency = f"afterok:{jid_chaincode}",
                )
                co.actionln(f"  {name} ({m['slurm_node']}) → job {jid}")

        co.successln(
            "\nTodos os jobs submetidos com sucesso.\n"
            "Acompanhe o progresso com:  squeue -u $USER\n"
            f"Logs disponíveis em:        {log_dir}/"
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Submissão de job SLURM
    # ──────────────────────────────────────────────────────────────────────────

    def _sbatch(self, node, cmd, job_name, workdir, log_dir, dependency=None):
        """
        Submete um job SLURM via sbatch e retorna o job ID numérico.

        Parâmetros:
          node       — nome do nó SLURM (campo 'slurm_node' no network.yaml)
          cmd        — comando a executar no nó (python3 main.py ...)
          job_name   — nome do job para identificação no squeue
          workdir    — diretório de trabalho (raiz do projeto, filesystem compartilhado)
          log_dir    — diretório para stdout/stderr do job
          dependency — string de dependência SLURM (ex: 'afterok:123:456')

        --parsable faz o sbatch retornar apenas 'JOBID' ou 'JOBID;CLUSTER',
        simplificando a captura do ID para encadear dependências.
        """
        sbatch_args = [
            "sbatch",
            "--parsable",
            f"--nodelist={node}",
            f"--job-name={job_name}",
            f"--chdir={workdir}",
            "--nodes=1",
            "--ntasks=1",
            "--output", f"{log_dir}/slurm-%j-{job_name}.log",
            "--error",  f"{log_dir}/slurm-%j-{job_name}.err",
        ]
        if dependency:
            sbatch_args.append(f"--dependency={dependency}")
        sbatch_args += ["--wrap", cmd]

        result = subprocess.run(sbatch_args, capture_output=True, text=True)

        if result.returncode != 0:
            raise RuntimeError(
                f"Falha ao submeter job '{job_name}' para nó '{node}':\n"
                f"{result.stderr.strip()}"
            )

        # --parsable retorna "JOBID" ou "JOBID;CLUSTER" — pegamos só o ID
        return result.stdout.strip().split(";")[0]
