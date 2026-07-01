/**
 * test_oracle.js — Benchmark Oracle → HERMES → Hyperledger Fabric
 * Copyright (c) 2026 Rian Carlos Valcanaia - Licensed under MIT License
 *
 * Fluxo testado:
 *   K6  →  POST /submit/hermes (Oracle, JSON)
 *       →  Oracle: compliance check
 *       →  Oracle: POST /api/calcular-do (HERMES, multipart) — interno
 *       →  Oracle: polling ancoradoEm
 *       →  Oracle: resposta única com { outcome, transactionId }
 *
 * Métricas cobertas (compatíveis com analise_resultados.py):
 *   M1 — Latência E2E ponta a ponta (Oracle + HERMES + Fabric)   (m1_latencia_e2e_ms)
 *   M2 — DOs ancoradas com sucesso                               (m2_dos_ancoradas)
 *   M3 — Taxa de sucesso global                                  (m3_taxa_sucesso)
 *   M0 — Rejeições pelo Oracle (compliance)                      (m0_oracle_rejeicoes)
 *
 * Execução:
 *   k6 run --env ORACLE_URL=http://<host>:3000 \
 *          --out json=resultados/run_1/k6_oracle_run1_$(date +%Y%m%d_%H%M%S).json \
 *          test_oracle.js
 *
 * Análise pós-teste (mesmo script do benchmark direto):
 *   python3 analise_resultados.py resultados/run_*/k6_oracle_*.json
 */

import http from 'k6/http';
import { check } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';
import { htmlReport } from 'https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

// ─── Métricas — mesmos nomes de test_hermes.js para compatibilidade ───────────

const latenciaE2E     = new Trend('m1_latencia_e2e_ms');
const dosAncoradas    = new Counter('m2_dos_ancoradas');
const taxaSucesso     = new Rate('m3_taxa_sucesso');
const dosErro         = new Counter('dos_erro');
const dosTimeout      = new Counter('dos_timeout');      // 429 rate-limit do Oracle

// Específica do Oracle — rejeições por compliance antes de chegar ao HERMES
const oracleRejeicoes = new Counter('m0_oracle_rejeicoes');

// ─── Configuração ─────────────────────────────────────────────────────────────

const ORACLE_URL  = __ENV.ORACLE_URL || 'http://localhost:3000';

// O documento é o mesmo fixture do test_hermes.js — válido, deve passar o Oracle
const DO_DOCUMENT = JSON.parse(open('./fixture_do.json'));

// ─── Cenários — idênticos ao test_hermes.js para comparação direta ────────────

export const options = {
    scenarios: {
        C1_baseline: {
            executor: 'constant-vus',
            vus: 1,
            duration: '5m',
            startTime: '0s',
            tags: { cenario: 'C1_baseline' },
            gracefulStop: '600s',
        },
        C2_leve: {
            executor: 'constant-vus',
            vus: 10,
            duration: '10m',
            startTime: '10m',
            tags: { cenario: 'C2_leve' },
            gracefulStop: '600s',
        },
        C3_moderada: {
            executor: 'constant-vus',
            vus: 100,
            duration: '10m',
            startTime: '25m',
            tags: { cenario: 'C3_moderada' },
            gracefulStop: '600s',
        },
        C4_alta: {
            executor: 'constant-vus',
            vus: 500,
            duration: '10m',
            startTime: '42m',
            tags: { cenario: 'C4_alta' },
            gracefulStop: '720s',
        },
        C5_maxima: {
            executor: 'constant-vus',
            vus: 1000,
            duration: '10m',
            startTime: '70m',
            tags: { cenario: 'C5_maxima' },
            gracefulStop: '900s',
        },
    },

    // Thresholds ligeiramente mais permissivos: Oracle adiciona overhead de compliance
    thresholds: {
        'm1_latencia_e2e_ms{cenario:C1_baseline}': ['p(95)<8000'],
        'm1_latencia_e2e_ms{cenario:C2_leve}':     ['p(95)<15000'],
        'm1_latencia_e2e_ms{cenario:C3_moderada}': ['p(95)<40000'],
        'm1_latencia_e2e_ms{cenario:C4_alta}':     ['p(95)<100000'],
        'm1_latencia_e2e_ms{cenario:C5_maxima}':   ['p(95)<130000'],

        'm3_taxa_sucesso': ['rate>0.85'],
        'http_req_failed': ['rate<0.10'],
    },
};

// ─── Função principal ─────────────────────────────────────────────────────────

export default function () {
    const t0 = Date.now();

    // Envelope único por iteração (evita colisão de submissionId no MongoDB)
    const payload = JSON.stringify({
        submissionId:         `K6-${__VU}-${__ITER}`,
        participantId:        'K6-LOAD-TEST',
        isAmendment:          false,
        originalSubmissionId: null,
        document:             DO_DOCUMENT,
    });

    // Chamada única e bloqueante — Oracle retorna só após HERMES ancorar no Fabric
    const res = http.post(
        `${ORACLE_URL}/submit/hermes`,
        payload,
        {
            headers: { 'Content-Type': 'application/json' },
            tags:    { etapa: 'oracle_submit' },
            timeout: '150s',   // Oracle espera até 90s pelo HERMES + overhead compliance
        },
    );

    // ── 429: rate limit do Oracle ─────────────────────────────────────────────
    if (res.status === 429) {
        dosTimeout.add(1);
        taxaSucesso.add(false);
        return;
    }

    // ── Erro de rede / servidor ───────────────────────────────────────────────
    if (res.status !== 200) {
        dosErro.add(1);
        taxaSucesso.add(false);
        return;
    }

    let body;
    try {
        body = JSON.parse(res.body);
    } catch {
        dosErro.add(1);
        taxaSucesso.add(false);
        return;
    }

    // ── Oracle rejeitou por compliance (structural / conformity / anomaly) ────
    if (body.outcome !== 'pass') {
        oracleRejeicoes.add(1);
        taxaSucesso.add(false);
        return;
    }

    // ── Verificações de integridade da resposta ───────────────────────────────
    const ok = check(body, {
        'oracle: outcome pass':           (b) => b.outcome === 'pass',
        'oracle: transactionId presente': (b) => !!b.transactionId,
    });

    if (ok) {
        latenciaE2E.add(Date.now() - t0);
        dosAncoradas.add(1);
        taxaSucesso.add(true);
    } else {
        dosErro.add(1);
        taxaSucesso.add(false);
    }
}

// ─── Relatório final ─────────────────────────────────────────────────────────

export function handleSummary(data) {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    return {
        [`resultados/relatorio_oracle_${timestamp}.html`]: htmlReport(data),
        stdout: textSummary(data, { indent: ' ', enableColors: true }),
        [`resultados/summary_oracle_${timestamp}.json`]: JSON.stringify(data, null, 2),
    };
}
