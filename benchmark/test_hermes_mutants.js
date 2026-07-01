/**
 * test_hermes_mutants.js — Cobertura única dos 5000 mutantes contra HERMES DIRETO
 * (sem Oracle). Baseado em test_hermes.js.
 *
 * Objetivo: enviar cada um dos 5000 documentos exatamente UMA vez ao HERMES e
 * observar o que acontece. Como o HERMES não tem porteiro de compliance, espera-se
 * que ele ancore quase tudo — inclusive os 1500 documentos inválidos. Essa é a
 * tese do experimento: SEM o Oracle, declarações inválidas vazam para a blockchain.
 *
 * Métricas:
 *   m1_latencia_e2e_ms / m2_dos_ancoradas / m3_taxa_sucesso  (compat. analise_resultados.py)
 *   vazamento_mutantes   — esperado=reject MAS ancorado pelo HERMES (= VAZAMENTO)
 *   ancoradas_corretas   — esperado=pass  e ancorado (correto)
 *   hermes_rejeitou      — esperado=reject e NÃO ancorado (HERMES barrou — raro, só quebra estrutural)
 *   limpas_perdidas      — esperado=pass  e NÃO ancorado (falso negativo do próprio HERMES)
 *
 * Todas as métricas são taggeadas com { esperado: 'pass'|'reject' } para fatiamento.
 *
 * Pré-requisitos:
 *   - hermes-api-server rodando em BASE_URL
 *   - mutant_payloads.json no mesmo diretório (gerado por prepare_mutant_payloads.py)
 *
 * Execução:
 *   k6 run --env BASE_URL=http://10.10.20.152:3000 \
 *          --env VUS=20 \
 *          --out json=resultados/run_1/k6_mutants_$(date +%Y%m%d_%H%M%S).json \
 *          test_hermes_mutants.js
 */

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Trend, Counter, Rate } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';
import { htmlReport } from 'https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

// ─── Métricas ─────────────────────────────────────────────────────────────────

// Latência REAL do sistema, medida por timestamps server-side do HERMES
// (ancoradoEm - criadoEm). Independe do intervalo de polling do cliente.
const latenciaE2E      = new Trend('m1_latencia_e2e_ms');                  // ancoradoEm - criadoEm
const latenciaCalc      = new Trend('latencia_calc_ms');                    // concluidoEm - criadoEm  (cálculo ICR)
const latenciaFabric    = new Trend('latencia_fabric_ms');                  // ancoradoEm - concluidoEm (ancoragem)
// Latência PERCEBIDA pelo cliente polling — inflada pela granularidade do poll.
// Reportada só para transparência; NÃO atribuir ao HERMES/Fabric.
const latenciaCliente   = new Trend('latencia_cliente_ms');                 // relógio K6: t_detecção - t_submit

const dosAncoradas      = new Counter('m2_dos_ancoradas');
const taxaSucesso       = new Rate('m3_taxa_sucesso');
const latenciaPolling   = new Trend('latencia_polling_ms');
const dosTimeout        = new Counter('dos_timeout');
const dosErro           = new Counter('dos_erro');
const dosErroPolling    = new Counter('dos_erro_polling');

// Específicas da cobertura de mutantes (vazamento)
const vazamentoMutantes = new Counter('vazamento_mutantes');   // reject → ancorado
const ancoradasCorretas = new Counter('ancoradas_corretas');   // pass   → ancorado
const hermesRejeitou    = new Counter('hermes_rejeitou');      // reject → não ancorado
const limpasPerdidas    = new Counter('limpas_perdidas');      // pass   → não ancorado

// ─── Configuração ─────────────────────────────────────────────────────────────

const BASE_URL         = __ENV.BASE_URL || 'http://localhost:3000';
const VUS              = parseInt(__ENV.VUS || '20', 10);
const ITERATIONS       = parseInt(__ENV.ITERATIONS || '5000', 10);  // smoke test: --env ITERATIONS=10
const POLLING_INTERVAL = 1;    // s entre polls
const POLLING_TIMEOUT  = 90;   // s máximos aguardando ancoragem

// ─── Carga de mutantes (compartilhada entre VUs) ──────────────────────────────

const PAYLOADS = new SharedArray('mutantes', function () {
    return JSON.parse(open('./mutant_payloads.json'));
});

// ─── Cenário: cobertura única — cada doc enviado exatamente 1x ────────────────

// Submétricas por tipo × severidade (mesmo esquema do braço COM Oracle) — permitem
// comparar o vazamento por célula: sem porteiro, cada célula vaza ~100%.
const TIPOS = [
    'ERRO_NCM_INELEGIVEL', 'ERRO_FOB_INVERTIDO', 'ERRO_FOB_NAO_POSITIVO',
    'ERRO_PARTICIPACAO_EXCEDE_100', 'ERRO_PAIS_NAO_MEMBRO_ACE55', 'ERRO_CIF_ZERO_COM_PARTICIPACAO',
    'ERRO_PARTICIPACAO_DIVERGENTE', 'ERRO_CIF_TERCEIROS_EXCEDE_FOB',
    'ERRO_CLASSIF_NCM', 'ERRO_VALOR_CIF_SUBFATURADO', 'ERRO_ORIGEM_INCORRETA', 'ERRO_FORNECEDOR_SEM_CERTIFICADO',
];
const SEVS = ['flagrante', 'limitrofe'];

const _thresholds = { 'http_req_failed': ['rate<0.20'] };
for (const t of TIPOS) for (const s of SEVS) {
    _thresholds[`vazamento_mutantes{tipo:${t},severidade:${s}}`] = ['count>=0'];
    _thresholds[`hermes_rejeitou{tipo:${t},severidade:${s}}`]    = ['count>=0'];
}

export const options = {
    scenarios: {
        cobertura: {
            executor: 'shared-iterations',
            vus: VUS,
            iterations: ITERATIONS,  // default 5000 (cada doc 1x); reduza p/ smoke test
            maxDuration: '60m',
            tags: { cenario: 'cobertura_hermes' },
            gracefulStop: '120s',
        },
    },
    thresholds: _thresholds,
};

// ─── Iteração ─────────────────────────────────────────────────────────────────

export default function () {
    // iterationInTest é um contador global 0..4999 — garante cada doc exatamente 1x
    const idx = exec.scenario.iterationInTest;
    const item = PAYLOADS[idx];
    const esperado = item.esperado;            // 'pass' | 'reject'
    const tipo   = (item.tipos && item.tipos.length) ? item.tipos[0] : 'nenhum';
    const sev    = item.severidade || 'na';
    const classe = item.categoria || (esperado === 'reject' ? 'erro' : 'limpo');
    const tag = { esperado, tipo, severidade: sev, classe };

    const t0 = Date.now();

    // ── 1. Submeter a DO (doc já vem sem `auditoria`) ─────────────────────────
    const submitRes = http.post(
        `${BASE_URL}/api/calcular-do`,
        { input: http.file(JSON.stringify(item.doc), `mutant_${idx}.json`, 'application/json') },
        { tags: { etapa: 'submit', esperado }, timeout: '30s' },
    );

    const submitOk = check(submitRes, {
        'submit: status 200':      (r) => r.status === 200,
        'submit: calcId presente': (r) => {
            try { return JSON.parse(r.body)?.calcId !== undefined; }
            catch { return false; }
        },
    });

    if (!submitOk) {
        // HERMES rejeitou já na submissão (provável quebra estrutural)
        dosErro.add(1, tag);
        taxaSucesso.add(false, tag);
        if (esperado === 'reject') hermesRejeitou.add(1, tag);
        else                       limpasPerdidas.add(1, tag);
        return;
    }

    let calcId;
    try { calcId = JSON.parse(submitRes.body).calcId; }
    catch {
        dosErro.add(1, tag);
        taxaSucesso.add(false, tag);
        return;
    }

    // ── 2. Polling até ancoragem ───────────────────────────────────────────────
    let ancorado = false;
    const tPollingStart = Date.now();

    for (let i = 0; i < POLLING_TIMEOUT; i++) {
        sleep(POLLING_INTERVAL);

        const statusRes = http.get(
            `${BASE_URL}/api/calcular-do/${calcId}`,
            { tags: { etapa: 'polling', esperado }, timeout: '10s' },
        );

        if (statusRes.status !== 200) { dosErroPolling.add(1, tag); continue; }

        let doc;
        try { doc = JSON.parse(statusRes.body); }
        catch { continue; }

        if (doc?.ancoradoEm) {
            const tFim = Date.now();

            // ── Latência REAL (server-side, independe do polling) ─────────────
            if (doc.criadoEm) {
                latenciaE2E.add(Math.max(0, doc.ancoradoEm - doc.criadoEm), tag);
                if (doc.concluidoEm) {
                    latenciaCalc.add(Math.max(0, doc.concluidoEm - doc.criadoEm), tag);
                    latenciaFabric.add(Math.max(0, doc.ancoradoEm - doc.concluidoEm), tag);
                }
            } else {
                // fallback: sem criadoEm, usa relógio do cliente
                latenciaE2E.add(Math.max(0, tFim - t0), tag);
            }
            // ── Latência percebida pelo cliente (inflada pelo polling) ────────
            latenciaCliente.add(Math.max(0, tFim - t0), tag);
            latenciaPolling.add(Math.max(0, tFim - tPollingStart), tag);

            dosAncoradas.add(1, tag);
            taxaSucesso.add(true, tag);
            ancorado = true;

            // ── Classificação de vazamento ────────────────────────────────────
            if (esperado === 'reject') vazamentoMutantes.add(1, tag);  // VAZOU
            else                       ancoradasCorretas.add(1, tag);  // ok

            break;
        }
    }

    if (!ancorado) {
        dosTimeout.add(1, tag);
        taxaSucesso.add(false, tag);
        if (esperado === 'reject') hermesRejeitou.add(1, tag);
        else                       limpasPerdidas.add(1, tag);
    }
}

// ─── Relatório final ─────────────────────────────────────────────────────────

function val(metrics, name, field = 'count') {
    return (metrics[name] && metrics[name].values && metrics[name].values[field]) || 0;
}

export function handleSummary(data) {
    const m = data.metrics;
    const vazou     = val(m, 'vazamento_mutantes');
    const okAncora  = val(m, 'ancoradas_corretas');
    const barrou    = val(m, 'hermes_rejeitou');
    const perdidas  = val(m, 'limpas_perdidas');
    const totalRej  = vazou + barrou;        // esperado=reject = 1500
    const totalPass = okAncora + perdidas;   // esperado=pass   = 3500

    const taxaVazamento = totalRej ? (vazou / totalRej * 100) : 0;

    const resumo = `
╔══════════════════════════════════════════════════════════════════╗
║   COBERTURA HERMES DIRETO (sem Oracle) — Vazamento de mutantes     ║
╠══════════════════════════════════════════════════════════════════╣
║  Mutantes (esperado=reject):     ${String(totalRej).padStart(5)}                          ║
║    → VAZARAM (ancorados):        ${String(vazou).padStart(5)}   (${taxaVazamento.toFixed(1).padStart(5)}% de vazamento) ║
║    → barrados pelo HERMES:       ${String(barrou).padStart(5)}                          ║
║  Limpos   (esperado=pass):       ${String(totalPass).padStart(5)}                          ║
║    → ancorados (correto):        ${String(okAncora).padStart(5)}                          ║
║    → perdidos (falha HERMES):    ${String(perdidas).padStart(5)}                          ║
╚══════════════════════════════════════════════════════════════════╝
`;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    return {
        [`resultados/relatorio_mutants_${timestamp}.html`]: htmlReport(data),
        stdout: textSummary(data, { indent: ' ', enableColors: true }) + '\n' + resumo,
        [`resultados/summary_mutants_${timestamp}.json`]: JSON.stringify(data, null, 2),
    };
}
