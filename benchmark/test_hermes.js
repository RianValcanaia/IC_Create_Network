/**
 * test_hermes.js — Benchmark Hermes + Hyperledger Fabric 3.0
 * Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
 *
 * Métricas cobertas:
 *   M1 — Latência end-to-end P50/P95/P99      (Trend: latencia_e2e_ms)
 *   M2 — Throughput / TPS                      (Counter: dos_ancoradas → rate)
 *   M3 — Taxa de sucesso                       (check rate padrão do k6)
 *   M4 — L_fabric isolado                      (via OpenTelemetry — coletado pelo Aspire)
 *   M5 — Overhead blockchain (M4/M1)           (calculado em pós-processamento)
 *   M6 — Conflitos MVCC                        (via Prometheus após o teste)
 *
 * Pré-requisitos:
 *   - hermes-api-server rodando em BASE_URL
 *   - fixture_do.json presente no mesmo diretório deste script
 *   - campo ancoradoEm sendo salvo no MongoDB após ancoragem (ver patch hermes-api-service.ts)
 *
 * Execução:
 *   k6 run --out json=resultados/k6_$(date +%Y%m%d_%H%M%S).json test_hermes.js
 *
 * Análise pós-teste:
 *   python3 analise_resultados.py resultados/k6_*.json
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter, Rate, Gauge } from 'k6/metrics';
import { htmlReport } from 'https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

// ─── Métricas customizadas ────────────────────────────────────────────────────

const latenciaE2E        = new Trend('m1_latencia_e2e_ms');                // M1 — valores em ms
const dosAncoradas       = new Counter('m2_dos_ancoradas');                 // M2 (rate = TPS)
const taxaSucesso        = new Rate('m3_taxa_sucesso');                     // M3
const latenciaPolling    = new Trend('latencia_polling_ms');                // diagnóstico
const dosTimeout         = new Counter('dos_timeout');                      // diagnóstico
const dosErro            = new Counter('dos_erro');                         // diagnóstico — falha no submit
const dosErroPolling     = new Counter('dos_erro_polling');                 // diagnóstico — falha HTTP no polling

// ─── Configuração ─────────────────────────────────────────────────────────────

const BASE_URL          = __ENV.BASE_URL || 'http://localhost:3000';
const POLLING_INTERVAL  = 1;    // segundos entre cada poll de status
const POLLING_TIMEOUT   = 90;   // segundos máximos aguardando ancoragem

// ─── Cenários ─────────────────────────────────────────────────────────────────
//
// C1 Baseline  — 1 VU,  5 min  — latência sem concorrência
// C2 Leve      — 5 VUs, 10 min — comportamento sob uso normal
// C3 Moderada  — 15 VUs, 10 min — início de degradação
// C4 Alta      — 30 VUs, 10 min — saturação e limite de throughput
//
// Os cenários são sequenciais com 2 min de pausa entre eles
// para o sistema estabilizar antes do próximo cenário.

export const options = {
    scenarios: {
        // C1 — Baseline: comportamento sem concorrência
        // Duração: 5min + gracefulStop 60s
        C1_baseline: {
            executor: 'constant-vus',
            vus: 1,
            duration: '5m',
            startTime: '0s',
            tags: { cenario: 'C1_baseline' },
            gracefulStop: '600s',
        },
        // C2 — Carga moderada: início de concorrência
        // startTime: 5min C1 + 1min graceful + 4min cooldown = 10min
        C2_leve: {
            executor: 'constant-vus',
            vus: 10,
            duration: '10m',
            startTime: '10m',
            tags: { cenario: 'C2_leve' },
            gracefulStop: '600s',
        },
        // C3 — Carga alta: estresse significativo
        // startTime: 10min + 10min C2 + 1min graceful + 4min cooldown = 25min
        C3_moderada: {
            executor: 'constant-vus',
            vus: 100,
            duration: '10m',
            startTime: '25m',
            tags: { cenario: 'C3_moderada' },
            gracefulStop: '600s',
        },
        // C4 — Carga extrema: saturação da rede
        // startTime: 25min + 10min C3 + 2min graceful + 5min cooldown = 42min
        // gracefulStop longo: 500 VUs com polling de 90s precisam de tempo para encerrar
        C4_alta: {
            executor: 'constant-vus',
            vus: 500,
            duration: '10m',
            startTime: '42m',
            tags: { cenario: 'C4_alta' },
            gracefulStop: '720s',
        },
    },

    // ── Thresholds — critérios de aceitação ───────────────────────────────────
    thresholds: {
        // M1 — Latência e2e por cenário (thresholds mais permissivos para carga extrema)
        'm1_latencia_e2e_ms{cenario:C1_baseline}': ['p(95)<5000'],
        'm1_latencia_e2e_ms{cenario:C2_leve}':     ['p(95)<10000'],
        'm1_latencia_e2e_ms{cenario:C3_moderada}': ['p(95)<30000'],
        'm1_latencia_e2e_ms{cenario:C4_alta}':     ['p(95)<90000'],

        // M3 — Taxa de sucesso global
        'm3_taxa_sucesso': ['rate>0.90'],  // 90% — mais permissivo para carga extrema

        // HTTP failures
        'http_req_failed': ['rate<0.05'],  // até 5% sob carga extrema
    },
};

// ─── Fixture DO ──────────────────────────────────────────────────────────────

// Carrega o arquivo de DO de exemplo no início do teste
// O arquivo deve estar no mesmo diretório do script
const DO_FIXTURE = open('./fixture_do.json');

// ─── Função principal ─────────────────────────────────────────────────────────

export default function () {
    const t0 = Date.now();

    // ── 1. Submeter a DO ──────────────────────────────────────────────────────
    const submitRes = http.post(
        `${BASE_URL}/api/calcular-do`,
        {
            input: http.file(DO_FIXTURE, 'fixture_do.json', 'application/json'),
        },
        {
            tags: { etapa: 'submit' },
            timeout: '30s',
        }
    );

    const submitOk = check(submitRes, {
        'submit: status 200':       (r) => r.status === 200,
        'submit: calcId presente':  (r) => {
            try { return JSON.parse(r.body)?.calcId !== undefined; }
            catch { return false; }
        },
    });

    if (!submitOk) {
        dosErro.add(1);
        taxaSucesso.add(false);
        return;
    }

    let calcId;
    try {
        calcId = JSON.parse(submitRes.body).calcId;
    } catch {
        dosErro.add(1);
        taxaSucesso.add(false);
        return;
    }

    // ── 2. Polling até ancoragem confirmada ───────────────────────────────────
    //
    // Aguarda o campo `ancoradoEm` aparecer no documento MongoDB.
    // Esse campo é setado pelo hermes-api-service APÓS a confirmação
    // da transação no Fabric (patch necessário — ver hermes-api-service.patch.ts).
    //
    // Checks explícitos garantem visibilidade total no sumário do k6:
    //   ✓/✗ submit: status 200
    //   ✓/✗ submit: calcId presente
    //   ✓/✗ ancoragem: confirmada dentro do timeout
    //   ✓/✗ ancoragem: latencia e2e dentro do threshold do cenario

    let ancorado = false;
    const tPollingStart = Date.now();

    for (let i = 0; i < POLLING_TIMEOUT; i++) {
        sleep(POLLING_INTERVAL);

        const statusRes = http.get(
            `${BASE_URL}/api/calcular-do/${calcId}`,
            { tags: { etapa: 'polling' }, timeout: '10s' }
        );

        if (statusRes.status !== 200) {
            dosErroPolling.add(1);
            continue;
        }

        let doc;
        try { doc = JSON.parse(statusRes.body); }
        catch { continue; }

        // Aguarda ancoradoEm (campo setado após confirmação no Fabric)
        if (doc?.ancoradoEm) {
            const tFim = Date.now();
            const latenciaTotal = Math.max(0, tFim - t0);

            latenciaE2E.add(latenciaTotal);
            dosAncoradas.add(1);
            taxaSucesso.add(true);
            ancorado = true;

            // Diagnóstico: tempo gasto só no polling
            latenciaPolling.add(Math.max(0, tFim - tPollingStart));

            // Check explícito de ancoragem — aparece no sumário do k6
            check(doc, {
                'ancoragem: documento possui ancoradoEm': (d) => !!d.ancoradoEm,
                'ancoragem: txId presente no documento':   (d) => !!d.txId,
                'ancoragem: hash presente no documento':   (d) => !!d.hash,
            });

            break;
        }
    }

    // Check explícito de timeout — falha visível no sumário do k6
    // Não usa fail() para não interromper o cenário, mas registra
    // a falha em todos os checks relacionados à ancoragem.
    const ancoracaoOk = check(null, {
        'ancoragem: confirmada dentro do timeout': () => ancorado,
    });

    if (!ancoracaoOk) {
        dosTimeout.add(1);
        taxaSucesso.add(false);
        // latenciaE2E NÃO recebe valor — M1 mede apenas ancoragens confirmadas
        // dos_timeout contabiliza separadamente as falhas por timeout
    }
}

// ─── Relatório final ─────────────────────────────────────────────────────────

export function handleSummary(data) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    return {
        // Relatório HTML visual
        [`resultados/relatorio_${timestamp}.html`]: htmlReport(data),
        // Resumo em texto no stdout
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
        // JSON completo para pós-processamento
        [`resultados/summary_${timestamp}.json`]: JSON.stringify(data, null, 2),
    };
}