/**
 * test_oracle_mutants.js — Cobertura única dos 5000 mutantes COM Oracle
 *   K6 → POST /submit/hermes (Oracle) → compliance → (se pass) HERMES → Fabric
 *
 * Par do test_hermes_mutants.js. Mesma carga, mesmos 5000 docs 1× cada — agora
 * passando pelo Oracle. Mede:
 *
 *   FILTRAGEM (matriz de confusão no nível Oracle):
 *     esperado=reject & outcome!=pass  → TP (Oracle barrou corretamente)
 *     esperado=reject & outcome==pass  → FN = VAZAMENTO (Oracle deixou passar)
 *     esperado=pass   & outcome==pass  → TN (Oracle aprovou corretamente)
 *     esperado=pass   & outcome!=pass  → FP (Oracle barrou doc bom)
 *
 *   LATÊNCIA (decomposta, sem artefato de polling):
 *     m1_latencia_e2e_ms          — latência REAL do HERMES (ancoradoEm-criadoEm), via hermesTimings
 *     latencia_calc_ms            — concluidoEm - criadoEm
 *     latencia_fabric_ms          — ancoradoEm - concluidoEm
 *     latencia_oracle_compliance_ms — custo de compute do Oracle (complianceDurationMs) ← LATÊNCIA INSERIDA
 *     latencia_cliente_ms         — relógio K6 (chamada bloqueante total) — inclui polling do Oracle (artefato)
 *     latencia_overhead_resid_ms  — cliente - compliance - hermes_e2e (forward + polling do Oracle; rotulado)
 *
 * Execução:
 *   k6 run --env ORACLE_URL=http://<oracle-host>:3000 \
 *          --env PARTICIPANT=EXPORTADOR-EVAL-001 --env VUS=20 \
 *          --out json=resultados/run_1/k6_oracle_mutants_$(date +%Y%m%d_%H%M%S).json \
 *          test_oracle_mutants.js
 */

import http from 'k6/http';
import { Counter, Rate, Trend } from 'k6/metrics';
import { SharedArray } from 'k6/data';
import exec from 'k6/execution';
import { htmlReport } from 'https://raw.githubusercontent.com/benc-uk/k6-reporter/main/dist/bundle.js';
import { textSummary } from 'https://jslib.k6.io/k6-summary/0.0.1/index.js';

// ─── Latência ─────────────────────────────────────────────────────────────────

const latenciaE2E        = new Trend('m1_latencia_e2e_ms');                // HERMES real (ancoradoEm-criadoEm)
const latenciaCalc        = new Trend('latencia_calc_ms');
const latenciaFabric      = new Trend('latencia_fabric_ms');
const latenciaCompliance  = new Trend('latencia_oracle_compliance_ms');     // ← latência inserida pelo Oracle
const latenciaCliente     = new Trend('latencia_cliente_ms');              // relógio K6 (com polling do Oracle)
const latenciaResidual    = new Trend('latencia_overhead_resid_ms');       // forward + polling Oracle (artefato)

const dosAncoradas        = new Counter('m2_dos_ancoradas');
const taxaSucesso         = new Rate('m3_taxa_sucesso');
const dosErro             = new Counter('dos_erro');
const dosTimeout          = new Counter('dos_timeout');

// ─── Filtragem (matriz de confusão Oracle) ────────────────────────────────────

// Visão binária "ancorado vs não" (= a tese; compatível com comparar_mutantes.py)
const tpBloqueouCorreto   = new Counter('oracle_tp_bloqueou');    // reject → NÃO ancorado (acerto)
const fnVazamento         = new Counter('vazamento_mutantes');    // reject → ancorado     (VAZAMENTO)
const tnAprovouCorreto    = new Counter('oracle_tn_aprovou');     // pass   → ancorado     (acerto)
const fpFalsoPositivo     = new Counter('oracle_fp_falso_pos');   // pass   → NÃO ancorado (erro)

// Granularidade dos 4 outcomes: separa rejeição DURA de envio a REVIEW.
// (light_review/heavy_review não são rejeição — são revisão humana.)
const mutViaReject        = new Counter('mut_via_reject');        // mutante → reject (barra dura)
const mutViaReview        = new Counter('mut_via_review');        // mutante → review (agregado light+heavy)
const limpoViaReject      = new Counter('limpo_via_reject');      // limpo   → reject (FP duro)
const limpoViaReview      = new Counter('limpo_via_review');      // limpo   → review (agregado light+heavy)

// Split fino da revisão (light vs heavy) — antes só existia no /logs do Oracle.
const mutViaLightReview   = new Counter('mut_via_light_review');
const mutViaHeavyReview   = new Counter('mut_via_heavy_review');
const limpoViaLightReview = new Counter('limpo_via_light_review');
const limpoViaHeavyReview = new Counter('limpo_via_heavy_review');

// ─── Configuração ─────────────────────────────────────────────────────────────

const ORACLE_URL  = __ENV.ORACLE_URL || 'http://localhost:3000';
// Vazio por padrão → usa participantId único BENCH-<idx> por doc (reputação neutra).
// Passe --env PARTICIPANT=X para forçar um participante fixo (modo single).
const PARTICIPANT = __ENV.PARTICIPANT || '';
const VUS         = parseInt(__ENV.VUS || '20', 10);
const ITERATIONS  = parseInt(__ENV.ITERATIONS || '5000', 10);
// Prefixo único por execução: evita colisão E11000 no submissionId (unique) do
// Oracle entre runs. idx já é único dentro de um run; o prefixo separa os runs.
const RUN_ID      = __ENV.RUN_ID || String(Date.now());

const PAYLOADS = new SharedArray('mutantes', function () {
    return JSON.parse(open('./mutant_payloads.json'));
});

// ─── Categorização por tipo × severidade ──────────────────────────────────────
// Submétricas (thresholds com seletor de tag e `count>=0`, que nunca falha) forçam
// o k6 a materializar cada célula no summary JSON. comparar_mutantes.py as lê por nome.
const TIPOS = [
    'ERRO_NCM_INELEGIVEL', 'ERRO_FOB_INVERTIDO', 'ERRO_FOB_NAO_POSITIVO',
    'ERRO_PARTICIPACAO_EXCEDE_100', 'ERRO_PAIS_NAO_MEMBRO_ACE55', 'ERRO_CIF_ZERO_COM_PARTICIPACAO',
    'ERRO_PARTICIPACAO_DIVERGENTE', 'ERRO_CIF_TERCEIROS_EXCEDE_FOB',
    'ERRO_CLASSIF_NCM', 'ERRO_VALOR_CIF_SUBFATURADO', 'ERRO_ORIGEM_INCORRETA', 'ERRO_FORNECEDOR_SEM_CERTIFICADO',
];
const SEVS         = ['flagrante', 'limitrofe'];
const CLASSES_PASS = ['limpo', 'quase_limite', 'sub_limiar'];

const _thresholds = { 'http_req_failed': ['rate<0.20'] };
for (const t of TIPOS) for (const s of SEVS) {
    _thresholds[`oracle_tp_bloqueou{tipo:${t},severidade:${s}}`] = ['count>=0'];
    _thresholds[`vazamento_mutantes{tipo:${t},severidade:${s}}`] = ['count>=0'];
}
for (const c of CLASSES_PASS) {
    _thresholds[`oracle_tn_aprovou{classe:${c}}`]  = ['count>=0'];
    _thresholds[`oracle_fp_falso_pos{classe:${c}}`] = ['count>=0'];
}

export const options = {
    scenarios: {
        cobertura: {
            executor: 'shared-iterations',
            vus: VUS,
            iterations: ITERATIONS,
            maxDuration: '90m',
            tags: { cenario: 'cobertura_oracle' },
            gracefulStop: '180s',
        },
    },
    thresholds: _thresholds,
};

// ─── Iteração ─────────────────────────────────────────────────────────────────

export default function () {
    const idx = exec.scenario.iterationInTest;
    const item = PAYLOADS[idx];
    const esperado = item.esperado;            // 'pass' | 'reject'
    // Tags para a matriz por célula (tipo × severidade p/ reject; classe p/ pass).
    const tipo   = (item.tipos && item.tipos.length) ? item.tipos[0] : 'nenhum';
    const sev    = item.severidade || 'na';
    const classe = item.categoria || (esperado === 'reject' ? 'erro' : 'limpo');
    const tag = { esperado, tipo, severidade: sev, classe };

    // participantId único por doc (BENCH-<idx>) → histórico vazio → reputação
    // neutra (65) constante, sem drift. Requer o pool BENCH-N semeado no Oracle.
    // Se PARTICIPANT for passado via env, usa fixo (modo single-participant).
    const participantId = PARTICIPANT || `BENCH-${idx}`;

    const body = JSON.stringify({
        submissionId:         `${RUN_ID}-MUT-${idx}`,
        participantId,
        isAmendment:          false,
        originalSubmissionId: null,
        document:             item.doc,        // já sem `auditoria`
    });

    const t0 = Date.now();
    const res = http.post(`${ORACLE_URL}/submit/hermes`, body, {
        headers: { 'Content-Type': 'application/json' },
        tags:    { etapa: 'oracle_submit', esperado },
        timeout: '150s',
    });
    const tFim = Date.now();

    if (__ENV.DEBUG && res.status !== 200) {
        console.log(`[DEBUG] idx=${idx} status=${res.status} body=${String(res.body).slice(0, 400)}`);
    }

    // ── Erros de transporte / rate-limit ──────────────────────────────────────
    if (res.status === 429) { dosTimeout.add(1, tag); taxaSucesso.add(false, tag); return; }

    // Oracle pode barrar via sanitizer (400) OU via decisão (200 outcome!=pass).
    // Ambos significam "não ancorado". 401 = problema de auth (não deveria ocorrer).
    let decision = null;
    if (res.status === 200) {
        try { decision = JSON.parse(res.body); }
        catch { dosErro.add(1, tag); taxaSucesso.add(false, tag); return; }
    } else if (res.status !== 400) {
        dosErro.add(1, tag); taxaSucesso.add(false, tag); return;
    }

    taxaSucesso.add(true, tag);   // request processado sem erro de sistema

    const outcome = decision ? decision.outcome : 'reject';   // 400 = barrado (reject)
    const anchored = outcome === 'pass' && decision && decision.transactionId;
    const isReview = outcome === 'light_review' || outcome === 'heavy_review';

    // ── Matriz de confusão (filtragem) ────────────────────────────────────────
    // Visão binária: "ancorado" (pass) vs "não ancorado" (reject OU review).
    if (esperado === 'reject') {
        if (anchored) {
            fnVazamento.add(1, tag);                   // VAZOU — mutante ancorado
        } else {
            tpBloqueouCorreto.add(1, tag);             // barrado (acerto)
            if (isReview) {
                mutViaReview.add(1, tag);
                (outcome === 'heavy_review' ? mutViaHeavyReview : mutViaLightReview).add(1, tag);
            } else {
                mutViaReject.add(1, tag);
            }
        }
    } else {
        if (anchored) {
            tnAprovouCorreto.add(1, tag);              // aprovado e ancorado (acerto)
        } else {
            fpFalsoPositivo.add(1, tag);               // doc bom não ancorado
            if (isReview) {
                limpoViaReview.add(1, tag);
                (outcome === 'heavy_review' ? limpoViaHeavyReview : limpoViaLightReview).add(1, tag);
            } else {
                limpoViaReject.add(1, tag);
            }
        }
    }

    // ── Custo de compute do Oracle (sempre disponível na resposta 200) ────────
    if (decision && typeof decision.complianceDurationMs === 'number') {
        latenciaCompliance.add(decision.complianceDurationMs, tag);
    }

    // ── Latência do HERMES (só quando ancorado) via hermesTimings ─────────────
    if (anchored && decision.hermesTimings) {
        const ht = decision.hermesTimings;
        let hermesE2E = 0;
        if (ht.criadoEm && ht.ancoradoEm) {
            hermesE2E = Math.max(0, ht.ancoradoEm - ht.criadoEm);
            latenciaE2E.add(hermesE2E, tag);
            if (ht.concluidoEm) {
                latenciaCalc.add(Math.max(0, ht.concluidoEm - ht.criadoEm), tag);
                latenciaFabric.add(Math.max(0, ht.ancoradoEm - ht.concluidoEm), tag);
            }
        }
        dosAncoradas.add(1, tag);

        // Cliente e residual (forward + polling do Oracle, rotulado como artefato)
        const cliente = Math.max(0, tFim - t0);
        latenciaCliente.add(cliente, tag);
        const compliance = (decision.complianceDurationMs || 0);
        latenciaResidual.add(Math.max(0, cliente - compliance - hermesE2E), tag);
    }
}

// ─── Relatório final ─────────────────────────────────────────────────────────

function val(metrics, name, field = 'count') {
    return (metrics[name] && metrics[name].values && metrics[name].values[field]) || 0;
}

export function handleSummary(data) {
    const m = data.metrics;
    const tp = val(m, 'oracle_tp_bloqueou');
    const fn = val(m, 'vazamento_mutantes');
    const tn = val(m, 'oracle_tn_aprovou');
    const fp = val(m, 'oracle_fp_falso_pos');

    const totalRej = tp + fn;            // esperado=reject = 1500
    const totalOk  = tn + fp;            // esperado=pass   = 3500
    const precision = (tp + fp) ? tp / (tp + fp) : 0;
    const recall    = totalRej   ? tp / totalRej : 0;
    const f1        = (precision + recall) ? 2 * precision * recall / (precision + recall) : 0;
    const vazamento = totalRej ? fn / totalRej * 100 : 0;

    const mutReject   = val(m, 'mut_via_reject');
    const mutReview   = val(m, 'mut_via_review');
    const limpoReject = val(m, 'limpo_via_reject');
    const limpoReview = val(m, 'limpo_via_review');

    const complianceMean = val(m, 'latencia_oracle_compliance_ms', 'avg');
    const hermesMean     = val(m, 'm1_latencia_e2e_ms', 'avg');

    const resumo = `
╔══════════════════════════════════════════════════════════════════╗
║   COBERTURA COM ORACLE — Filtragem + Latência inserida            ║
╠══════════════════════════════════════════════════════════════════╣
║  Matriz de confusão — ancorado(pass) vs não-ancorado:             ║
║    TP barrou mutante:   ${String(tp).padStart(5)}   FN VAZAMENTO:   ${String(fn).padStart(5)}        ║
║    TN aprovou limpo:    ${String(tn).padStart(5)}   FP não-ancorou: ${String(fp).padStart(5)}        ║
║    Precision ${precision.toFixed(3)}  Recall ${recall.toFixed(3)}  F1 ${f1.toFixed(3)}              ║
║    Vazamento: ${vazamento.toFixed(1).padStart(5)}% dos mutantes passaram                   ║
╠══════════════════════════════════════════════════════════════════╣
║  Quebra por outcome (não-ancorados):                              ║
║    Mutante → reject: ${String(mutReject).padStart(5)}   → review: ${String(mutReview).padStart(5)}           ║
║    Limpo   → reject: ${String(limpoReject).padStart(5)}   → review: ${String(limpoReview).padStart(5)}  (FP duro vs suave)║
╠══════════════════════════════════════════════════════════════════╣
║  Latência média:                                                  ║
║    Oracle (compliance): ${complianceMean.toFixed(0).padStart(6)} ms  ← inserida pelo Oracle  ║
║    HERMES (real e2e):   ${hermesMean.toFixed(0).padStart(6)} ms                          ║
╚══════════════════════════════════════════════════════════════════╝
`;

    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    return {
        [`resultados/relatorio_oracle_mutants_${timestamp}.html`]: htmlReport(data),
        stdout: textSummary(data, { indent: ' ', enableColors: true }) + '\n' + resumo,
        [`resultados/summary_oracle_mutants_${timestamp}.json`]: JSON.stringify(data, null, 2),
    };
}
