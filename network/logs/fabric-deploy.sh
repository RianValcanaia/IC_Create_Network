#!/bin/bash
#SBATCH --job-name=fabric-deploy
#SBATCH --nodes=3
#SBATCH --nodelist=baia1,baia2,baia4
#SBATCH --exclusive
#SBATCH --time=23:00:00
#SBATCH --chdir=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network
#SBATCH --output=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/logs/slurm-%j-fabric-deploy.log
#SBATCH --error=/mnt/prj/g11718038933/new_HERMESSC/IC_Create_Network/network/logs/slurm-%j-fabric-deploy.err

set -euo pipefail

# ── Fase -3: Pull de imagens Docker em todos os nós (paralelo) ───
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "docker pull hyperledger/fabric-ca:1.5.13 && docker pull hyperledger/fabric-peer:3.1.1 && docker pull hyperledger/fabric-orderer:3.1.1 && docker pull hyperledger/fabric-ccenv:3.1.1" &
srun --nodes=1 --ntasks=1 --nodelist=baia2 sg docker -c "docker pull hyperledger/fabric-ca:1.5.13 && docker pull hyperledger/fabric-peer:3.1.1 && docker pull hyperledger/fabric-orderer:3.1.1 && docker pull hyperledger/fabric-ccenv:3.1.1" &
wait

# ── Fase -2: Clean nos (paralelo) ───────────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --start --machine maquina_1 --phase clean" &
srun --nodes=1 --ntasks=1 --nodelist=baia2 sg docker -c "python3 main.py --start --machine maquina_2 --phase clean" &
wait

# ── Fase -1: Clean artefatos NFS (coordenador) ───────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase clean"

# ── Fase 0: Pré-requisitos (coordenador) ─────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase prereqs"

# ── Fase 1: CAs em paralelo ──────────────────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --start --machine maquina_1 --phase cas" &
srun --nodes=1 --ntasks=1 --nodelist=baia2 sg docker -c "python3 main.py --start --machine maquina_2 --phase cas" &
wait

# ── Fase 2: Enrollment (coordenador) ────────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase enroll"

# ── Fase 3: Artefatos (coordenador) ─────────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase artifacts"

# ── Fase 4: Peers e orderers em paralelo ─────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --start --machine maquina_1 --phase nodes" &
srun --nodes=1 --ntasks=1 --nodelist=baia2 sg docker -c "python3 main.py --start --machine maquina_2 --phase nodes" &
wait

# ── Fase 5: Canais (coordenador) ────────────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase channels"

# ── Fase 6: Lifecycle do chaincode (coordenador) ─────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --setup --phase chaincode"

# ── Fase 7: Containers CCAAS em paralelo ────────────────────────
srun --nodes=1 --ntasks=1 --nodelist=baia1 sg docker -c "python3 main.py --start --machine maquina_1 --phase ccaas" &
wait

# ── Mantém o job vivo até --time expirar ou scancel ─────────────
sleep infinity
