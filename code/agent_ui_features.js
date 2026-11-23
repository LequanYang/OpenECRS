/* ==========================================================================
 * OpenECRS · feature panels front-end (framework-free, no build step).
 *
 * Loaded by agent_ui.html via:
 *   <link rel="stylesheet" href="/agent_ui_features.css">
 *   <script defer src="/agent_ui_features.js"></script>
 *
 * Host contract (window.OCFeatures):
 *   mount(ctx)                  ctx = {t, lang, esc, getRole, getScenarios, openChat, notify}
 *   open(name, opts?)           name = wizard|evidence|poc|portfolio|workspace|videos
 *   openDetail(scenarioId)      scenario detail panel (also wired to [data-open-detail])
 *   close()
 *   isOpen()
 *
 * Entry points in the host UI:
 *   [data-feature="wizard|evidence|poc|portfolio|workspace|videos"]  → open(name)
 *   [data-open-detail="<scenario id>"]                              → openDetail(id)
 *
 * Panels cover: decision wizard, evidence explorer, PoC plan, portfolio,
 * saved-scenario workspace, external videos, scenario detail with SVG trend.
 * All network errors are caught and rendered as readable inline states.
 * ======================================================================== */
(function () {
  'use strict';

  var VERSION = '1.0.0';
  var FEATURES = ['wizard', 'evidence', 'poc', 'portfolio', 'workspace', 'videos'];

  /* ======================================================================
   * Shared state
   * ==================================================================== */
  var F = {
    ctx: null,
    lang: 'zh',
    scenarios: null,
    scenariosPromise: null,
    overlay: null,
    maskEl: null,
    dialogEl: null,
    titleEl: null,
    subEl: null,
    bodyEl: null,
    footEl: null,
    closeBtn: null,
    lastFocus: null,
    current: null,
    bound: false,
    closing: false,
    closeTimer: null,
    reqSeq: 0,
    toastEl: null,
    toastTimer: null
  };

  /* ======================================================================
   * i18n (self-contained; the host supplies ctx.lang)
   * ==================================================================== */
  var STR = {
    zh: {
      close: '关闭',
      retry: '重试',
      cancel: '取消',
      loading: '加载中…',
      working: '处理中…',
      computing: '计算中…',
      errorTitle: '请求失败',
      errorHint: '请确认本地服务已启动（python code/agent_app.py），或稍后重试。',
      chatUnavailable: '主界面未提供对话入口，无法把结果发给 Agent。',
      copy: '复制',
      copied: '已复制到剪贴板',
      copyFail: '复制失败，请手动选择文本',
      heuristic: '启发式估算',
      agentAnalyze: '让 Agent 详细分析',
      agentAnalyzeOne: '详细分析这个',
      narrativeMissing: '当前未生成 LLM 叙述（未配置模型或生成失败）；以下排序与估算仍由确定性规则给出。',
      narrativeTitle: 'Agent 叙述',
      llmNarrative: 'LLM 生成',
      roles: '角色',
      metrics: '指标',
      data_compliance: '数据合规',
      risks: '风险',
      summary: '摘要',
      emptyGeneric: '暂无数据',

      wizardTitle: '决策向导',
      wizardSub: '输入 6 个约束 → 得到 3 个优先场景',
      wizardHint: '排序由确定性公式计算；LLM 叙述可选（未配置模型时仍然可用）。',
      wizardFoot: '分数为 0–100 综合分；机会/可行性/缺口展示原始指标。排序逻辑可复现，叙述由 LLM 生成。',
      role: '角色',
      roleFounder: '创始人 / 独立开发者',
      roleEnterprise: '企业创新团队',
      roleInvestor: '投资人',
      rolePm: '产品经理',
      goal: '目标',
      goalPlaceholder: '例如：8 周内做出能收钱的 AI 产品',
      teamSize: '团队规模',
      teamSizeUnit: '人',
      budget: '预算（USD）',
      horizon: '周期（周）',
      risk: '风险偏好',
      riskLow: '低',
      riskMedium: '中',
      riskHigh: '高',
      submitWizard: '生成优先级排序',
      shortlist: '优先场景 shortlist',
      fitReasons: '适配理由',
      watchouts: '注意点',
      route: '建议路线',
      score: '综合分',
      opportunity: '机会分',
      demand: '需求',
      gap: '缺口',
      feasibility: '可行性',
      value: '价值',
      wizardEmpty: '没有返回候选场景，请调整约束后重试。',

      evidenceTitle: '证据检索',
      evidenceSub: '按场景/来源/年份/倾向检索引用证据',
      evidenceFoot: '证据来自离线证据库；置信度为规则审查得分，不代表真实概率。',
      allScenarios: '全部场景',
      allSources: '全部来源',
      allYears: '全部年份',
      kind: '倾向',
      kindAll: '全部',
      kindPositive: '正向',
      kindNegative: '负向',
      search: '检索',
      searchPlaceholder: '搜索标题或引用内容…',
      reset: '重置',
      evidenceTotal: function (n) { return '共 ' + n + ' 条证据'; },
      evidenceEmpty: '没有匹配的证据，试试放宽筛选条件。',
      confidence: '置信度',
      fourGates: '四门通过',
      loadMore: '加载更多',
      source: '来源',
      year: '年份',

      pocTitle: 'PoC 计划',
      pocSub: '选择场景与周期，生成里程碑、资源与合规清单',
      pocHint: '工作量与成本为启发式估算，仅用于排期参考。',
      pocFoot: '所有工作量/成本均为启发式估算（heuristic），不是报价；里程碑可按团队情况裁剪。',
      scenario: '场景',
      weeks: '周期',
      weekUnit: function (n) { return '第 ' + n + ' 周'; },
      submitPoc: '生成 PoC 计划',
      milestones: '里程碑时间线',
      deliverables: '交付物',
      exitCriteria: '退出标准',
      effort: '工作量',
      effortUnit: '人周',
      cost: '成本区间',
      copyResult: '复制结果',
      pocEmpty: '没有返回计划，请更换场景或周期后重试。',

      portfolioTitle: '项目组合',
      portfolioSub: '按团队/周期/预算生成验证与建设组合',
      portfolioHint: '组合按确定性贪心算法生成，总工作量为启发式估算。',
      portfolioFoot: '组合与工作量为启发式估算（heuristic）；phase=validate 表示先做验证，build 表示可以进入建设。',
      goalLabel: '目标（可选）',
      submitPortfolio: '生成组合',
      picks: '入选场景',
      excluded: '未入选',
      why: '原因',
      totalEffort: '总工作量',
      phase: '阶段',
      phaseValidate: '验证 validate',
      phaseBuild: '建设 build',
      portfolioEmpty: '没有返回组合，请调整预算或周期后重试。',

      workspaceTitle: '工作区',
      workspaceSub: '收藏的场景、备注与一键对比',
      workspaceHint: '添加备注后点“保存备注”；移除需要二次确认。',
      workspaceFoot: '收藏保存在本地 outputs/agent_ui/workspace.json，不会上传。',
      addScenario: '添加场景',
      addNote: '备注（可选）',
      addNotePlaceholder: '为什么关注这个场景…',
      addBtn: '添加',
      compareSaved: '对比收藏的场景',
      workspaceEmpty: '还没有收藏场景。在上方选择场景并添加，或从场景详情里点“收藏”。',
      saveNote: '保存备注',
      noteSaved: '备注已保存',
      compare: '对比',
      remove: '移除',
      confirmRemove: '确认移除',
      cancelRemove: '再想想',
      added: '已加入工作区',
      removed: '已移除',
      savedCount: function (n) { return '已收藏 ' + n + ' 个场景'; },
      comparePrompt: function (names) { return '对比收藏的场景：' + names + '。请给出优先级排序、四门证据、主要风险与 8 周落地建议。'; },
      workspaceNoScenario: '场景列表加载失败，请重试。',

      videosTitle: '视频参考',
      videosSub: '外部视频搜索链接（非证据库内容）',
      videosHint: '这些是外部搜索页，点击将在新标签页打开；内容不受 OpenECRS 控制。',
      videosFoot: '外部视频仅作参考，不作为机会评分证据；评分与引用仍来自证据库。',
      videoEmpty: '这个场景暂时没有视频链接。',
      openExternal: '在新标签页打开',
      popupBlocked: '浏览器拦截了新标签页，请允许弹窗后重试。',
      disclaimer: '外部内容，非证据库',

      detailTitle: '场景详情',
      detailSub: '指标、趋势、来源结构与证据摘录',
      addFav: '收藏到工作区',
      favAdded: '已收藏',
      genPoc: '生成 PoC 计划',
      watchVideos: '看视频',
      analyze: '让 Agent 分析',
      trend: '年度趋势',
      sourceMix: '来源分布',
      supply: '供给镜像',
      signals: '信号指标',
      evidenceExcerpts: '证据摘录',
      noTrend: '暂无年度趋势数据。',
      rank: '综合排名',
      samples: '样本量',
      supplyRepos: '仓库',
      supplyStars: 'Star 合计',
      supplyPapers: '论文',
      supplyShow: 'Show HN',
      supplyProducts: 'Product Hunt',
      needRate: '需求率 need_rate',
      wtpRate: '付费意愿 wtp_rate',
      valueRate: '价值信号 value_rate',
      urgencyRate: '紧迫度 urgency_rate',
      growthSlope: '增长斜率 growth',
      answerRate: '可回答率 answer_rate',
      barrier: '专家壁垒 barrier',
      detailMissing: '缺少场景 id，无法加载详情。',
      detailEmpty: '没有找到这个场景。',

      errNetwork: '网络请求失败：',
      errBadJson: '服务端返回了无法解析的内容（不是 JSON）。',
      errTimeout: '请求超时，请检查本地服务或稍后重试。',
      errHttp: '请求失败（HTTP ',
      errNotFound: '接口不存在或场景未找到（HTTP 404）。',
      errUnknown: '未知错误'
    },
    en: {
      close: 'Close',
      retry: 'Retry',
      cancel: 'Cancel',
      loading: 'Loading…',
      working: 'Working…',
      computing: 'Working…',
      errorTitle: 'Request failed',
      errorHint: 'Make sure the local service is running (python code/agent_app.py), then retry.',
      chatUnavailable: 'The host chat entry point is not available.',
      copy: 'Copy',
      copied: 'Copied to clipboard',
      copyFail: 'Copy failed — please select the text manually',
      heuristic: 'heuristic',
      agentAnalyze: 'Ask the agent to analyse',
      agentAnalyzeOne: 'Analyse this one',
      narrativeMissing: 'No LLM narrative was generated (model not configured or generation failed); the ranking and estimates below are still deterministic.',
      narrativeTitle: 'Agent narrative',
      llmNarrative: 'LLM written',
      roles: 'Roles',
      metrics: 'Metrics',
      data_compliance: 'Data compliance',
      risks: 'Risks',
      summary: 'Summary',
      emptyGeneric: 'No data yet',

      wizardTitle: 'Decision wizard',
      wizardSub: 'Six constraints → three priority scenarios',
      wizardHint: 'Ranking is computed deterministically; the LLM narrative is optional (the wizard still works without a model).',
      wizardFoot: 'Scores are 0–100 composite scores; opportunity/feasibility/gap show the raw metrics. Ranking is reproducible; the narrative is LLM-written.',
      role: 'Role',
      roleFounder: 'Founder / indie',
      roleEnterprise: 'Enterprise innovation',
      roleInvestor: 'Investor',
      rolePm: 'Product manager',
      goal: 'Goal',
      goalPlaceholder: 'e.g. ship a revenue-ready AI product in 8 weeks',
      teamSize: 'Team size',
      teamSizeUnit: 'people',
      budget: 'Budget (USD)',
      horizon: 'Horizon (weeks)',
      risk: 'Risk appetite',
      riskLow: 'Low',
      riskMedium: 'Medium',
      riskHigh: 'High',
      submitWizard: 'Rank scenarios',
      shortlist: 'Shortlist',
      fitReasons: 'Why it fits',
      watchouts: 'Watchouts',
      route: 'Suggested route',
      score: 'Score',
      opportunity: 'Opportunity',
      demand: 'Demand',
      gap: 'Gap',
      feasibility: 'Feasibility',
      value: 'Value',
      wizardEmpty: 'No shortlist returned; adjust the constraints and retry.',

      evidenceTitle: 'Evidence explorer',
      evidenceSub: 'Filter quoted evidence by scenario, source, year and polarity',
      evidenceFoot: 'Evidence comes from the offline evidence base; confidence is a rule-based review score, not a calibrated probability.',
      allScenarios: 'All scenarios',
      allSources: 'All sources',
      allYears: 'All years',
      kind: 'Polarity',
      kindAll: 'All',
      kindPositive: 'Positive',
      kindNegative: 'Negative',
      search: 'Search',
      searchPlaceholder: 'Search titles or quotes…',
      reset: 'Reset',
      evidenceTotal: function (n) { return n + ' evidence records'; },
      evidenceEmpty: 'No matching evidence. Try relaxing the filters.',
      confidence: 'confidence',
      fourGates: 'four gates',
      loadMore: 'Load more',
      source: 'Source',
      year: 'Year',

      pocTitle: 'PoC plan',
      pocSub: 'Pick a scenario and horizon to get milestones, roles and compliance checks',
      pocHint: 'Effort and cost are heuristic estimates, for planning only.',
      pocFoot: 'Effort and cost are heuristic estimates, not a quote; milestones can be trimmed for your team.',
      scenario: 'Scenario',
      weeks: 'Horizon',
      weekUnit: function (n) { return 'Week ' + n; },
      submitPoc: 'Generate PoC plan',
      milestones: 'Milestone timeline',
      deliverables: 'Deliverables',
      exitCriteria: 'Exit criteria',
      effort: 'Effort',
      effortUnit: 'person-weeks',
      cost: 'Cost range',
      copyResult: 'Copy result',
      pocEmpty: 'No plan returned; try another scenario or horizon.',

      portfolioTitle: 'Portfolio',
      portfolioSub: 'Validate/build mix under team, time and budget constraints',
      portfolioHint: 'The mix is a deterministic greedy selection; total effort is a heuristic estimate.',
      portfolioFoot: 'Portfolio and effort are heuristic estimates; phase=validate means test first, build means ready to build.',
      goalLabel: 'Goal (optional)',
      submitPortfolio: 'Build portfolio',
      picks: 'Picks',
      excluded: 'Excluded',
      why: 'Why',
      totalEffort: 'Total effort',
      phase: 'Phase',
      phaseValidate: 'Validate',
      phaseBuild: 'Build',
      portfolioEmpty: 'No portfolio returned; adjust budget or horizon and retry.',

      workspaceTitle: 'Workspace',
      workspaceSub: 'Saved scenarios, notes and one-click comparison',
      workspaceHint: 'Save a note after editing; removal asks for confirmation.',
      workspaceFoot: 'Saved locally in outputs/agent_ui/workspace.json — nothing is uploaded.',
      addScenario: 'Add scenario',
      addNote: 'Note (optional)',
      addNotePlaceholder: 'Why this scenario matters…',
      addBtn: 'Add',
      compareSaved: 'Compare saved scenarios',
      workspaceEmpty: 'No saved scenarios yet. Add one above, or use “Save to workspace” on a scenario detail.',
      saveNote: 'Save note',
      noteSaved: 'Note saved',
      compare: 'Compare',
      remove: 'Remove',
      confirmRemove: 'Confirm remove',
      cancelRemove: 'Keep it',
      added: 'Added to workspace',
      removed: 'Removed',
      savedCount: function (n) { return n + ' saved'; },
      comparePrompt: function (names) { return 'Compare my saved scenarios: ' + names + '. Rank them, cite four-gate evidence, list the main risks and give an 8-week rollout plan.'; },
      workspaceNoScenario: 'Could not load scenarios. Please retry.',

      videosTitle: 'Videos',
      videosSub: 'External video search links (not part of the evidence base)',
      videosHint: 'These open external search pages in a new tab; content is not controlled by OpenECRS.',
      videosFoot: 'External videos are references only and are not used for opportunity scoring.',
      videoEmpty: 'No video links for this scenario yet.',
      openExternal: 'Open in a new tab',
      popupBlocked: 'The browser blocked the new tab; allow pop-ups and retry.',
      disclaimer: 'External content, not evidence',

      detailTitle: 'Scenario detail',
      detailSub: 'Metrics, trend, source mix and quoted evidence',
      addFav: 'Save to workspace',
      favAdded: 'Saved',
      genPoc: 'Generate PoC plan',
      watchVideos: 'Videos',
      analyze: 'Ask the agent',
      trend: 'Yearly trend',
      sourceMix: 'Source mix',
      supply: 'Supply mirror',
      signals: 'Signal metrics',
      evidenceExcerpts: 'Evidence excerpts',
      noTrend: 'No yearly trend data available.',
      rank: 'Rank',
      samples: 'Samples',
      supplyRepos: 'Repos',
      supplyStars: 'Stars total',
      supplyPapers: 'Papers',
      supplyShow: 'Show HN',
      supplyProducts: 'Product Hunt',
      needRate: 'need_rate',
      wtpRate: 'wtp_rate',
      valueRate: 'value_rate',
      urgencyRate: 'urgency_rate',
      growthSlope: 'growth slope',
      answerRate: 'answer_rate',
      barrier: 'barrier',
      detailMissing: 'Missing scenario id; cannot load detail.',
      detailEmpty: 'Scenario not found.',

      errNetwork: 'Network request failed: ',
      errBadJson: 'The server returned a response that is not valid JSON.',
      errTimeout: 'Request timed out. Check the local service or retry.',
      errHttp: 'Request failed (HTTP ',
      errNotFound: 'Endpoint missing or scenario not found (HTTP 404).',
      errUnknown: 'Unknown error'
    }
  };

  function s(key) {
    var dict = STR[F.lang] || STR.zh;
    var v = dict[key];
    if (v === undefined) v = STR.zh[key];
    if (typeof v === 'function') return v.apply(null, Array.prototype.slice.call(arguments, 1));
    return v === undefined || v === null ? String(key) : String(v);
  }

  /* ======================================================================
   * Small utilities
   * ==================================================================== */
  function escapeHtml(value) {
    return String(value === null || value === undefined ? '' : value).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function E(value) {
    try {
      if (F.ctx && typeof F.ctx.esc === 'function') return F.ctx.esc(value);
    } catch (err) { /* fall back to the local encoder */ }
    return escapeHtml(value);
  }

  function arr(value) {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === '') return [];
    return [value];
  }

  function str(value) {
    return value === null || value === undefined ? '' : String(value).trim();
  }

  function num(value, digits) {
    if (value === null || value === undefined || value === '') return '—';
    var n = Number(value);
    if (!isFinite(n)) return '—';
    if (digits === undefined) return String(n);
    return n.toFixed(digits);
  }

  function pctSigned(value) {
    if (value === null || value === undefined || value === '') return '—';
    var n = Number(value);
    if (!isFinite(n)) return '—';
    return (n >= 0 ? '+' : '') + (n * 100).toFixed(2) + '%';
  }

  function metricNum(value) {
    if (value === null || value === undefined || value === '') return '—';
    var n = Number(value);
    if (!isFinite(n)) return '—';
    return Math.abs(n) <= 1 ? n.toFixed(2) : n.toFixed(1);
  }

  function money(value) {
    var n = Number(value);
    if (!isFinite(n)) return '—';
    try {
      return '$' + Math.round(n).toLocaleString(F.lang === 'zh' ? 'zh-CN' : 'en-US');
    } catch (err) {
      return '$' + Math.round(n);
    }
  }

  function intOr(value, fallback, min, max) {
    var n = Math.round(Number(value));
    if (!isFinite(n)) n = fallback;
    if (min !== undefined && n < min) n = min;
    if (max !== undefined && n > max) n = max;
    return n;
  }

  function firstNum(obj, keys) {
    var o = obj || {};
    for (var i = 0; i < keys.length; i += 1) {
      var v = o[keys[i]];
      if (v !== null && v !== undefined && v !== '' && isFinite(Number(v))) return Number(v);
    }
    return null;
  }

  function textOf(value) {
    if (value === null || value === undefined) return '';
    if (typeof value === 'string') return value.trim();
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (typeof value === 'object') {
      return str(value.text || value.title || value.name || value.label || value.risk ||
        value.why || value.detail || value.description || '');
    }
    return '';
  }

  function dateText(value) {
    var raw = str(value);
    if (!raw) return '';
    var m = raw.match(/^\d{4}-\d{2}-\d{2}/);
    return m ? m[0] : raw.slice(0, 16);
  }

  function safeUrl(value) {
    var raw = str(value);
    if (!raw) return '';
    return /^https?:\/\//i.test(raw) ? raw : '';
  }

  function notify(text) {
    var msg = str(text);
    if (!msg) return;
    try {
      if (F.ctx && typeof F.ctx.notify === 'function') {
        F.ctx.notify(msg);
        return;
      }
    } catch (err) { /* fall through to the built-in toast */ }
    showToast(msg);
  }

  function showToast(text) {
    if (typeof document === 'undefined') return;
    if (!F.toastEl) {
      F.toastEl = document.createElement('div');
      F.toastEl.className = 'feat-toast';
      document.body.appendChild(F.toastEl);
    }
    F.toastEl.textContent = text;
    F.toastEl.classList.remove('feat-toast-out');
    clearTimeout(F.toastTimer);
    F.toastTimer = setTimeout(function () {
      if (!F.toastEl) return;
      F.toastEl.classList.add('feat-toast-out');
      setTimeout(function () {
        if (F.toastEl && F.toastEl.parentNode) F.toastEl.parentNode.removeChild(F.toastEl);
        F.toastEl = null;
      }, 170);
    }, 2400);
  }

  function copyText(text) {
    var value = String(text || '');
    if (!value) return Promise.resolve(false);
    if (typeof navigator !== 'undefined' && navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(value).then(function () {
        notify(s('copied'));
        return true;
      }).catch(function () { return legacyCopy(value); });
    }
    return Promise.resolve(legacyCopy(value));
  }

  function legacyCopy(value) {
    try {
      if (typeof document === 'undefined') return false;
      var area = document.createElement('textarea');
      area.value = value;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.top = '-1000px';
      area.style.left = '-1000px';
      document.body.appendChild(area);
      area.select();
      var ok = document.execCommand && document.execCommand('copy');
      document.body.removeChild(area);
      notify(ok ? s('copied') : s('copyFail'));
      return !!ok;
    } catch (err) {
      notify(s('copyFail'));
      return false;
    }
  }

  function roleLabel(value) {
    var key = 'role' + (str(value).charAt(0).toUpperCase() + str(value).slice(1).toLowerCase());
    if (['founder', 'enterprise', 'investor', 'pm'].indexOf(str(value)) < 0) return s('roleFounder');
    return s(key);
  }

  function riskLabel(value) {
    var key = 'risk' + (str(value).charAt(0).toUpperCase() + str(value).slice(1).toLowerCase());
    if (['low', 'medium', 'high'].indexOf(str(value)) < 0) return s('riskMedium');
    return s(key);
  }

  function normRole(value) {
    var role = str(value).toLowerCase();
    return ['founder', 'enterprise', 'investor', 'pm'].indexOf(role) >= 0 ? role : '';
  }

  function hostRole() {
    try {
      if (F.ctx && typeof F.ctx.getRole === 'function') return normRole(F.ctx.getRole());
    } catch (err) { /* ignore */ }
    return '';
  }

  /* ======================================================================
   * Network layer: JSON only, readable errors, timeouts, no uncaught rejects
   * ==================================================================== */
  var TIMEOUT_GET = 20000;
  var TIMEOUT_POST = 150000;

  function makeError(message, kind, status, payload) {
    var err = new Error(message);
    err.userMessage = message;
    err.kind = kind || 'error';
    err.status = status || 0;
    err.payload = payload || null;
    return err;
  }

  function errText(err) {
    if (!err) return s('errUnknown');
    if (err.userMessage) return err.userMessage;
    if (err.message) return err.message;
    return String(err);
  }

  function request(path, options, timeoutMs) {
    var opts = options || {};
    var timeout = timeoutMs || TIMEOUT_GET;
    var controller = null;
    var timer = null;
    var init = { cache: 'no-store', headers: {} };
    if (typeof AbortController !== 'undefined') {
      controller = new AbortController();
      init.signal = controller.signal;
      timer = setTimeout(function () { controller.abort(); }, timeout);
    }
    if (opts.method) init.method = opts.method;
    if (opts.headers) {
      for (var key in opts.headers) {
        if (Object.prototype.hasOwnProperty.call(opts.headers, key)) init.headers[key] = opts.headers[key];
      }
    }
    if (opts.body !== undefined) init.body = opts.body;

    return fetch(path, init).then(function (res) {
      clearTimeout(timer);
      var ctype = (res.headers && res.headers.get && res.headers.get('content-type')) || '';
      var isJson = /json/i.test(ctype);
      var parse = isJson
        ? res.json().catch(function () { return null; })
        : Promise.resolve(null);
      return parse.then(function (data) {
        if (!res.ok) {
          var serverMsg = data && (data.error || data.hint) ? str(data.error || data.hint) : '';
          if (data && data.error && data.hint && data.error !== data.hint) serverMsg += ' · ' + str(data.hint);
          var message = serverMsg || (s('errHttp') + res.status + '）');
          if (res.status === 404) message = serverMsg || s('errNotFound');
          throw makeError(message, 'http', res.status, data);
        }
        if (data === null || data === undefined) throw makeError(s('errBadJson'), 'json', res.status);
        if (data && data.error) {
          throw makeError(str(data.error) + (data.hint ? ' · ' + str(data.hint) : ''), 'api', res.status, data);
        }
        return data;
      });
    }).catch(function (err) {
      clearTimeout(timer);
      if (err && err.userMessage) throw err;
      if (err && err.name === 'AbortError') throw makeError(s('errTimeout'), 'timeout');
      throw makeError(s('errNetwork') + (err && err.message ? err.message : s('errUnknown')), 'network');
    });
  }

  function queryString(params) {
    var parts = [];
    if (!params) return '';
    Object.keys(params).forEach(function (key) {
      var value = params[key];
      if (value === null || value === undefined || value === '') return;
      parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(String(value)));
    });
    return parts.length ? '?' + parts.join('&') : '';
  }

  function getJSON(path, params, timeout) {
    return request(path + queryString(params), {}, timeout || TIMEOUT_GET);
  }

  function postJSON(path, body, timeout) {
    return request(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {})
    }, timeout || TIMEOUT_POST);
  }

  /* ======================================================================
   * Scenario cache + naming
   * ==================================================================== */
  function normalizeScenarioList(list) {
    return arr(list).map(function (item) {
      if (typeof item === 'string') return { id: item, name: item, name_en: item };
      if (!item || typeof item !== 'object') return null;
      return {
        id: str(item.id || item.scenario || item.name || item.name_en),
        name: str(item.name || item.id || item.name_en),
        name_en: str(item.name_en || item.name || item.id),
        rank: item.rank,
        opportunity: item.opportunity,
        route: item.route,
        route_en: item.route_en
      };
    }).filter(function (item) { return item && item.id; });
  }

  function assignScenarios(list) {
    F.scenarios = normalizeScenarioList(list);
    return F.scenarios;
  }

  function getScenarios() {
    if (F.scenarios && F.scenarios.length) return Promise.resolve(F.scenarios);
    if (F.scenariosPromise) return F.scenariosPromise;

    var fromHost = null;
    try {
      if (F.ctx && typeof F.ctx.getScenarios === 'function') fromHost = F.ctx.getScenarios();
    } catch (err) { fromHost = null; }

    if (Array.isArray(fromHost) && fromHost.length) return Promise.resolve(assignScenarios(fromHost));

    F.scenariosPromise = Promise.resolve(fromHost).then(function (resolved) {
      if (Array.isArray(resolved) && resolved.length) return assignScenarios(resolved);
      return getJSON('/api/data', {}, 15000).then(function (data) {
        assignScenarios(data && data.scenarios);
        return F.scenarios || [];
      });
    }).catch(function () {
      F.scenarios = F.scenarios || [];
      return F.scenarios;
    }).then(function (value) {
      F.scenariosPromise = null;
      return value;
    });

    return F.scenariosPromise;
  }

  function findScenario(raw) {
    if (raw === null || raw === undefined) return null;
    var key = typeof raw === 'object'
      ? str(raw.id || raw.scenario || raw.name || raw.name_en)
      : str(raw);
    if (!key) return null;
    var list = F.scenarios || [];
    for (var i = 0; i < list.length; i += 1) {
      var item = list[i];
      if (item.id === key || item.name === key || item.name_en === key) return item;
    }
    return null;
  }

  function scenarioId(raw) {
    var hit = findScenario(raw);
    if (hit) return hit.id;
    if (raw && typeof raw === 'object') return str(raw.id || raw.scenario || raw.name || raw.name_en);
    return str(raw);
  }

  function scenarioName(raw) {
    var hit = findScenario(raw);
    if (hit) return F.lang === 'zh' ? (hit.name || hit.id) : (hit.name_en || hit.name || hit.id);
    if (raw && typeof raw === 'object') return pickName(raw);
    return str(raw);
  }

  function pickName(obj) {
    if (obj === null || obj === undefined) return '';
    if (typeof obj === 'string') return scenarioName(obj);
    var zh = str(obj.name || obj.name_zh || obj.scenario || obj.id);
    var en = str(obj.name_en || obj.nameEn || obj.name || obj.scenario || obj.id);
    return F.lang === 'zh' ? (zh || en) : (en || zh);
  }

  function scenarioRoute(obj) {
    if (!obj || typeof obj !== 'object') return '';
    return F.lang === 'zh'
      ? str(obj.route || obj.route_en)
      : str(obj.route_en || obj.route);
  }

  function scenarioOptions(selected, extraOptions) {
    var list = (F.scenarios || []).slice();
    var html = '';
    if (extraOptions) {
      html += '<option value=""' + (selected ? '' : ' selected') + '>' + E(extraOptions) + '</option>';
    }
    list.forEach(function (item) {
      var label = F.lang === 'zh' ? (item.name || item.id) : (item.name_en || item.name || item.id);
      if (item.rank !== undefined && item.rank !== null) label += ' · #' + item.rank;
      html += '<option value="' + E(item.id) + '"' +
        (scenarioId(selected) === item.id ? ' selected' : '') + '>' + E(label) + '</option>';
    });
    return html;
  }

  /* ======================================================================
   * Prompt builders (handed to the host chat via ctx.openChat)
   * ==================================================================== */
  function openChatPrompt(prompt) {
    var text = str(prompt);
    if (!text) return;
    var ctx = F.ctx || {};
    if (typeof ctx.openChat === 'function') {
      try {
        close();
        var result = ctx.openChat(text);
        if (result && typeof result.catch === 'function') {
          result.catch(function (err) { notify(errText(err)); });
        }
        return;
      } catch (err) {
        notify(errText(err));
        return;
      }
    }
    notify(s('chatUnavailable'));
  }

  function wizardPrompt(state, onlyIndex) {
    var data = state.data || {};
    var list = wizShortlist(data);
    var form = state.form || {};
    var picked = list.slice(0, 3);
    if (onlyIndex !== null && onlyIndex !== undefined) {
      picked = picked.filter(function (_, i) { return i === onlyIndex; });
    }
    var lines = [];
    var candidateLines = picked.map(function (item, index) {
      var parts = [];
      parts.push(pickName(item) || s('scenario'));
      var score = firstNum(item, ['score', 'total_score', 'opportunity']);
      if (score !== null) parts.push(s('score') + ' ' + score.toFixed(1));
      var opp = metricOf(item, 'opportunity');
      var feas = metricOf(item, 'feasibility');
      var gap = metricOf(item, 'gap');
      var bits = [];
      if (opp !== null) bits.push(s('opportunity') + ' ' + metricNum(opp));
      if (feas !== null) bits.push(s('feasibility') + ' ' + metricNum(feas));
      if (gap !== null) bits.push(s('gap') + ' ' + metricNum(gap));
      if (bits.length) parts.push('(' + bits.join(', ') + ')');
      var route = scenarioRoute(item);
      if (route) parts.push(s('route') + ': ' + route);
      return '  ' + (index + 1) + '. ' + parts.join(' · ');
    });
    if (F.lang === 'zh') {
      lines.push('我在 OpenECRS 决策向导里得到以下候选场景，请做详细分析：');
      lines.push('- 角色：' + roleLabel(form.role));
      if (str(form.goal)) lines.push('- 目标：' + str(form.goal));
      lines.push('- 团队规模：' + intOr(form.team_size, 1, 1) + ' 人；预算：' + money(form.budget_usd) +
        '；周期：' + intOr(form.horizon_weeks, 1, 1) + ' 周；风险偏好：' + riskLabel(form.risk));
      lines.push('- 候选场景：');
      lines = lines.concat(candidateLines);
      lines.push('请：1) 解释排序依据并引用四门证据；2) 指出最大风险与前置验证；3) 给出 ' +
        Math.min(intOr(form.horizon_weeks, 8, 1), 8) + ' 周内的 PoC 计划与里程碑；4) 明确继续/放弃的判断标准。');
    } else {
      lines.push('These candidate scenarios came out of the OpenECRS decision wizard. Please analyse them in depth:');
      lines.push('- Role: ' + roleLabel(form.role));
      if (str(form.goal)) lines.push('- Goal: ' + str(form.goal));
      lines.push('- Team: ' + intOr(form.team_size, 1, 1) + '; budget: ' + money(form.budget_usd) +
        '; horizon: ' + intOr(form.horizon_weeks, 1, 1) + ' weeks; risk appetite: ' + riskLabel(form.risk));
      lines.push('- Candidates:');
      lines = lines.concat(candidateLines);
      lines.push('Please: 1) explain the ranking with four-gate evidence; 2) name the biggest risks and the prerequisite validation; ' +
        '3) give a PoC plan and milestones within ' + Math.min(intOr(form.horizon_weeks, 8, 1), 8) + ' weeks; ' +
        '4) state explicit go/no-go criteria.');
    }
    return lines.join('\n');
  }

  function comparePrompt(names) {
    var list = arr(names).map(function (name) { return scenarioName(name); })
      .filter(function (name, index, all) { return name && all.indexOf(name) === index; });
    return s('comparePrompt', list.slice(0, 3).join(F.lang === 'zh' ? '、' : ', '));
  }

  function detailPrompt(name) {
    if (F.lang === 'zh') {
      return '请详细分析「' + name + '」这个场景：机会分、需求、供给缺口、可行性、商业价值、四门证据、主要风险，并给出 8 周 PoC 计划。';
    }
    return 'Analyse the scenario "' + name + '": opportunity score, demand, supply gap, feasibility, business value, ' +
      'four-gate evidence, main risks, and an 8-week PoC plan.';
  }

  /* ======================================================================
   * Overlay shell
   * ==================================================================== */
  function isOpen() {
    return !!(F.overlay && !F.overlay.hidden);
  }

  function ensureOverlay() {
    if (F.overlay || typeof document === 'undefined' || !document.body) return;
    var overlay = document.createElement('div');
    overlay.className = 'feat-overlay';
    overlay.hidden = true;
    overlay.setAttribute('aria-hidden', 'true');

    var mask = document.createElement('div');
    mask.className = 'feat-mask';
    mask.setAttribute('data-feat-close', '1');

    var dialog = document.createElement('div');
    dialog.className = 'feat-dialog';
    dialog.setAttribute('role', 'dialog');
    dialog.setAttribute('aria-modal', 'true');
    dialog.setAttribute('aria-labelledby', 'featTitle');
    dialog.setAttribute('tabindex', '-1');
    dialog.innerHTML =
      '<div class="feat-head">' +
      '  <div class="feat-heading">' +
      '    <h2 class="feat-title" id="featTitle"></h2>' +
      '    <p class="feat-sub" id="featSub"></p>' +
      '  </div>' +
      '  <button type="button" class="feat-close" data-feat-close="1" aria-label="Close">' +
      '    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round">' +
      '      <path d="M6 6l12 12M18 6L6 18"/></svg>' +
      '  </button>' +
      '</div>' +
      '<div class="feat-body" id="featBody"></div>' +
      '<div class="feat-foot" id="featFoot" hidden></div>';

    overlay.appendChild(mask);
    overlay.appendChild(dialog);
    document.body.appendChild(overlay);

    F.overlay = overlay;
    F.maskEl = mask;
    F.dialogEl = dialog;
    F.titleEl = dialog.querySelector('.feat-title');
    F.subEl = dialog.querySelector('.feat-sub');
    F.bodyEl = dialog.querySelector('.feat-body');
    F.footEl = dialog.querySelector('.feat-foot');
    F.closeBtn = dialog.querySelector('.feat-close');

    overlay.addEventListener('click', function (ev) {
      var target = ev.target;
      if (target && target.closest && target.closest('[data-feat-close]')) {
        ev.preventDefault();
        close();
      }
    });

    bindBodyEvents();
  }

  function lockScroll() {
    if (typeof document === 'undefined') return;
    document.documentElement.classList.add('feat-lock');
    document.body.classList.add('feat-lock');
  }

  function unlockScroll() {
    if (typeof document === 'undefined') return;
    if (isOpen()) return;
    document.documentElement.classList.remove('feat-lock');
    document.body.classList.remove('feat-lock');
  }

  function applyHead(panel, state) {
    var head = null;
    try { head = panel.head ? panel.head(state) : null; } catch (err) { head = null; }
    var title = head && head[0] ? head[0] : s(panel.titleKey || 'detailTitle');
    var sub = head && head[1] ? head[1] : '';
    if (F.titleEl) F.titleEl.textContent = title;
    if (F.subEl) F.subEl.textContent = sub;
  }

  function applyFoot(panel, state) {
    if (!F.footEl) return;
    var foot = '';
    try { foot = panel.foot ? (panel.foot(state) || '') : ''; } catch (err) { foot = ''; }
    if (foot) {
      F.footEl.innerHTML = foot;
      F.footEl.hidden = false;
    } else {
      F.footEl.innerHTML = '';
      F.footEl.hidden = true;
    }
  }

  function renderBody(resetScroll) {
    if (!F.overlay || !F.current || !F.bodyEl) return;
    var panelName = F.current.panel;
    var state = F.current.state;
    var panel = Panels[panelName];
    if (!panel) return;

    var previousScroll = F.bodyEl.scrollTop;
    applyHead(panel, state);
    applyFoot(panel, state);

    var html = '';
    try {
      html = panel.render(state) || '';
    } catch (err) {
      html = errorHtml(errText(err));
    }
    F.bodyEl.innerHTML = html;
    F.bodyEl.scrollTop = resetScroll ? 0 : previousScroll;
  }

  function isCurrentState(state) {
    return !!(isOpen() && F.current && F.current.state === state && !F.closing);
  }

  function runRequest(state, worker) {
    if (!isCurrentState(state)) return;
    var token = ++F.reqSeq;
    state.loading = true;
    state.error = null;
    renderBody(false);
    Promise.resolve().then(worker).catch(function (err) {
      if (token === F.reqSeq) state.error = errText(err);
    }).then(function () {
      if (token !== F.reqSeq || !isCurrentState(state)) return;
      state.loading = false;
      renderBody(false);
    });
  }

  function retryCurrent() {
    if (!F.current) return;
    var state = F.current.state;
    var panel = Panels[F.current.panel];
    if (!panel) return;
    if (panel.retry) {
      runRequest(state, function () { return panel.retry(state); });
      return;
    }
    if (panel.load) {
      runRequest(state, function () { return panel.load(state); });
      return;
    }
    renderBody(false);
  }

  function open(name, opts) {
    if (typeof document === 'undefined') return;
    var panel = Panels[name];
    if (!panel) return;
    ensureOverlay();
    if (!F.overlay) return;
    bindBodyEvents();
    if (F.closeTimer) {
      clearTimeout(F.closeTimer);
      F.closeTimer = null;
    }
    F.closing = false;
    F.overlay.classList.remove('feat-closing');

    var wasClosed = !isOpen();
    if (wasClosed) F.lastFocus = document.activeElement;
    lockScroll();

    var state = null;
    try { state = panel.init ? (panel.init(opts || {}) || {}) : {}; } catch (err) { state = {}; }
    state.loading = !!state.loading;
    state.error = state.error || null;
    F.current = { panel: name, state: state };

    F.overlay.hidden = false;
    F.overlay.setAttribute('aria-hidden', 'false');
    var size = panel.size || 'md';
    if (F.dialogEl) F.dialogEl.setAttribute('data-size', size);

    renderBody(true);
    setTimeout(function () {
      if (F.current && F.current.state === state && F.dialogEl) {
        try { F.dialogEl.focus(); } catch (err) { /* ignore */ }
      }
    }, 30);

    if (panel.load) {
      state.loading = true;
      runRequest(state, function () { return panel.load(state); });
    }
  }

  function close() {
    if (typeof document === 'undefined') return;
    if (!isOpen() || F.closing) return;
    var restore = F.lastFocus;
    F.lastFocus = null;
    F.current = null;
    F.reqSeq += 1;
    F.closing = true;
    unlockScroll();
    F.overlay.classList.add('feat-closing');
    F.closeTimer = setTimeout(function () {
      F.closeTimer = null;
      F.closing = false;
      if (!F.overlay) return;
      F.overlay.hidden = true;
      F.overlay.classList.remove('feat-closing');
      F.overlay.setAttribute('aria-hidden', 'true');
      if (F.bodyEl) F.bodyEl.innerHTML = '';
      if (F.footEl) F.footEl.hidden = true;
      unlockScroll();
      if (restore && typeof restore.focus === 'function') {
        try { restore.focus(); } catch (err) { /* ignore */ }
      }
    }, 150);
  }

  function focusableInDialog() {
    if (!F.dialogEl) return [];
    var nodes = F.dialogEl.querySelectorAll(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), ' +
      'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    var list = [];
    for (var i = 0; i < nodes.length; i += 1) {
      var node = nodes[i];
      if (node.offsetParent !== null || node === F.closeBtn) list.push(node);
    }
    return list;
  }

  function bindGlobal() {
    if (F.bound || typeof document === 'undefined') return;
    F.bound = true;

    document.addEventListener('click', function (ev) {
      var target = ev.target;
      if (!target || !target.closest) return;
      if (F.overlay && !F.overlay.hidden && F.overlay.contains(target)) return;

      var feature = target.closest('[data-feature]');
      if (feature) {
        var name = str(feature.getAttribute('data-feature'));
        if (FEATURES.indexOf(name) >= 0) {
          ev.preventDefault();
          open(name);
        }
        return;
      }
      var detail = target.closest('[data-open-detail]');
      if (detail) {
        ev.preventDefault();
        openDetail(detail.getAttribute('data-open-detail'));
      }
    });

    document.addEventListener('keydown', function (ev) {
      if (!isOpen()) return;
      if (ev.key === 'Escape' || ev.key === 'Esc') {
        ev.preventDefault();
        close();
        return;
      }
      if (ev.key === 'Tab') {
        var list = focusableInDialog();
        if (!list.length) return;
        var first = list[0];
        var last = list[list.length - 1];
        var active = document.activeElement;
        if (!F.dialogEl || !F.dialogEl.contains(active)) {
          ev.preventDefault();
          first.focus();
          return;
        }
        if (ev.shiftKey && active === first) {
          ev.preventDefault();
          last.focus();
        } else if (!ev.shiftKey && active === last) {
          ev.preventDefault();
          first.focus();
        }
      }
    });

    if (F.bodyEl) bindBodyEvents();
  }

  /* ======================================================================
   * Delegated events inside the dialog body
   * ==================================================================== */
  function panelNow() {
    return F.current ? Panels[F.current.panel] : null;
  }

  function stateNow() {
    return F.current ? F.current.state : null;
  }

  function bindBodyEvents() {
    if (!F.bodyEl || F.bodyEl.__featBound) return;
    F.bodyEl.__featBound = true;

    F.bodyEl.addEventListener('submit', function (ev) {
      var form = ev.target;
      if (!form || !form.closest || !form.closest('form[data-form]')) return;
      ev.preventDefault();
      var panel = panelNow();
      var state = stateNow();
      if (!panel || !state || state.loading) return;
      if (panel.onSubmit) {
        try {
          var result = panel.onSubmit(state, form);
          if (result && typeof result.catch === 'function') {
            result.catch(function (err) { notify(errText(err)); });
          }
        } catch (err) {
          notify(errText(err));
        }
      }
    });

    F.bodyEl.addEventListener('click', function (ev) {
      var target = ev.target;
      if (!target || !target.closest) return;
      var trigger = target.closest('[data-act]');
      if (!trigger) return;
      ev.preventDefault();
      var act = str(trigger.getAttribute('data-act'));
      if (!act) return;
      if (act === 'retry') {
        retryCurrent();
        return;
      }
      var panel = panelNow();
      var state = stateNow();
      if (!panel || !state || !panel.onAction) return;
      try {
        var result = panel.onAction(state, act, trigger, ev);
        if (result && typeof result.catch === 'function') {
          result.catch(function (err) { notify(errText(err)); });
        }
      } catch (err) {
        notify(errText(err));
      }
    });

    F.bodyEl.addEventListener('input', function (ev) {
      onFieldChange(ev.target, false);
    });
    F.bodyEl.addEventListener('change', function (ev) {
      onFieldChange(ev.target, true);
    });
    F.bodyEl.addEventListener('keydown', function (ev) {
      var target = ev.target;
      if (!target || !target.getAttribute) return;
      if (ev.key === 'Enter' && !ev.isComposing) {
        var enterAct = target.getAttribute('data-enter-act');
        if (enterAct && !target.tagName.match(/^TEXTAREA$/i)) {
          ev.preventDefault();
          var panel = panelNow();
          var state = stateNow();
          if (panel && state && panel.onAction) {
            try {
              var result = panel.onAction(state, enterAct, target, ev);
              if (result && typeof result.catch === 'function') result.catch(function (err) { notify(errText(err)); });
            } catch (err) { notify(errText(err)); }
          }
        }
      }
    });
  }

  function onFieldChange(el, isChange) {
    if (!el || !el.getAttribute) return;
    var panel = panelNow();
    var state = stateNow();
    if (!panel || !state) return;
    var name = el.getAttribute('name');
    var noteIdx = el.getAttribute('data-note-idx');
    var value = el.value;
    if (panel.sync && (name || noteIdx !== null)) {
      try { panel.sync(state, el, name, noteIdx, value, isChange); } catch (err) { /* ignore */ }
    }
  }

  /* ======================================================================
   * Reusable renderers
   * ==================================================================== */
  function svgIcon(name) {
    var paths = {
      inbox: '<path d="M4 6h16v12H4z"/><path d="M4 13h4l2 3h4l2-3h4"/>',
      alert: '<path d="M12 4l9 16H3z"/><path d="M12 10v4M12 17h.01"/>',
      chart: '<path d="M4 20V8M10 20V4M16 20v-7M22 20V10"/>',
      video: '<path d="M4 6h11v12H4z"/><path d="M15 10l5-3v10l-5-3"/>',
      star: '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>'
    };
    return '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round">' + (paths[name] || paths.inbox) + '</svg>';
  }

  function loadingBlock(text) {
    return '<div class="feat-loading-block"><span class="feat-spinner"></span><span>' +
      E(text || s('loading')) + '</span></div>';
  }

  function skeletonList(rows) {
    var count = rows || 3;
    var html = '<div class="feat-skeleton">';
    for (var i = 0; i < count; i += 1) {
      html += '<div class="feat-skeleton-row feat-w60"></div>' +
        '<div class="feat-skeleton-row feat-w80"></div>' +
        '<div class="feat-skeleton-row feat-w40"></div>';
    }
    return html + '</div>';
  }

  function emptyHtml(text, icon) {
    return '<div class="feat-empty">' +
      '<div class="feat-empty-icon">' + svgIcon(icon || 'inbox') + '</div>' +
      '<div>' + E(text || s('emptyGeneric')) + '</div>' +
      '</div>';
  }

  function errorHtml(message, withRetry) {
    var retry = withRetry === false ? '' :
      '<div class="feat-error-actions"><button type="button" class="feat-btn feat-btn-sm" data-act="retry">' +
      E(s('retry')) + '</button></div>';
    return '<div class="feat-error">' +
      '<div class="feat-error-title">' + E(s('errorTitle')) + '</div>' +
      '<div>' + E(message || s('errUnknown')) + '</div>' +
      '<div class="feat-error-hint">' + E(s('errorHint')) + '</div>' +
      retry +
      '</div>';
  }

  function sectionTitle(text) {
    return '<div class="feat-section-title">' + E(text) + '</div>';
  }

  function badge(text, kind) {
    return '<span class="feat-badge' + (kind ? ' feat-badge-' + kind : '') + '">' + E(text) + '</span>';
  }

  function narrativeHtml(narrative) {
    if (!narrative) return '';
    var summary = '';
    var bullets = [];
    var risks = [];
    if (typeof narrative === 'string') {
      summary = narrative;
    } else if (typeof narrative === 'object') {
      summary = str(narrative.summary || narrative.overview || '');
      bullets = arr(narrative.bullets || narrative.points).map(textOf).filter(Boolean);
      risks = arr(narrative.risks || narrative.watchouts).map(textOf).filter(Boolean);
    }
    if (!summary && !bullets.length && !risks.length) return '';
    var html = '<div class="feat-narrative">' +
      '<div class="feat-narrative-head"><span class="feat-kicker">' + E(s('narrativeTitle')) + '</span>' +
      badge(s('llmNarrative'), 'agent') + '</div>';
    if (summary) html += '<p class="feat-narrative-summary">' + E(summary) + '</p>';
    if (bullets.length) {
      html += '<ul class="feat-list">' + bullets.map(function (item) {
        return '<li>' + E(item) + '</li>';
      }).join('') + '</ul>';
    }
    if (risks.length) {
      html += '<div class="feat-riskbox"><span class="feat-risklabel">' + E(s('risks')) + '</span>' +
        '<ul class="feat-list">' + risks.map(function (item) {
          return '<li>' + E(item) + '</li>';
        }).join('') + '</ul></div>';
    }
    return html + '</div>';
  }

  function listHtml(items, emptyText) {
    var list = arr(items).map(textOf).filter(Boolean);
    if (!list.length) return emptyText ? '<p class="feat-hint">' + E(emptyText) + '</p>' : '';
    return '<ul class="feat-list">' + list.map(function (item) {
      return '<li>' + E(item) + '</li>';
    }).join('') + '</ul>';
  }

  function tagsHtml(items) {
    var list = arr(items).map(textOf).filter(Boolean);
    if (!list.length) return '<p class="feat-hint">—</p>';
    return '<div class="feat-tags">' + list.map(function (item) {
      return '<span class="feat-chip">' + E(item) + '</span>';
    }).join('') + '</div>';
  }

  function evidenceScenarioName(ev) {
    if (!ev) return '';
    if (F.lang === 'zh') return scenarioName(ev.scenario || ev.scenario_en || '');
    return scenarioName(ev.scenario_en || ev.scenario || '');
  }

  function evidenceItemHtml(ev) {
    if (!ev || typeof ev !== 'object') return '';
    var url = safeUrl(ev.url);
    var gates = arr(ev.gates).map(textOf).filter(Boolean);
    var html = '<li class="feat-ev"><div class="feat-ev-meta">';
    if (str(ev.source)) html += '<span class="feat-chip">' + E(ev.source) + '</span>';
    if (str(ev.year)) html += '<span>' + E(ev.year) + '</span>';
    if (ev.confidence !== null && ev.confidence !== undefined && isFinite(Number(ev.confidence))) {
      html += '<span>' + E(s('confidence')) + ' ' + E(num(ev.confidence, 2)) + '</span>';
    }
    if (gates.length) {
      html += '<span class="feat-gates">' + gates.map(function (gate) {
        return '<span class="feat-gate">' + E(gate) + '</span>';
      }).join('') + '</span>';
    }
    if (ev.is_opportunity) html += badge(s('fourGates'), 'ok');
    var scen = evidenceScenarioName(ev);
    if (scen) html += '<span class="feat-muted">' + E(scen) + '</span>';
    html += '</div>';
    if (str(ev.title)) html += '<div class="feat-ev-title">' + E(ev.title) + '</div>';
    if (str(ev.quote)) html += '<blockquote class="feat-ev-quote">' + E(ev.quote) + '</blockquote>';
    if (url) {
      html += '<a class="feat-ev-url" href="' + E(url) + '" target="_blank" rel="noopener noreferrer">' +
        E(url) + '</a>';
    }
    return html + '</li>';
  }

  function evidenceListHtml(items, emptyText) {
    var list = arr(items).filter(function (item) { return item && typeof item === 'object'; });
    if (!list.length) return emptyHtml(emptyText || s('evidenceEmpty'), 'inbox');
    return '<ul class="feat-ev-list">' + list.map(evidenceItemHtml).join('') + '</ul>';
  }

  /* --------------------------------------------------- wizard normalizers */
  function wizShortlist(data) {
    if (!data || typeof data !== 'object') return [];
    return arr(data.shortlist || data.items || data.results || data.ranked);
  }

  function metricOf(item, key) {
    if (!item || typeof item !== 'object') return null;
    var metrics = item.metrics && typeof item.metrics === 'object' ? item.metrics : null;
    var raw = item[key];
    if ((raw === null || raw === undefined || raw === '') && metrics) raw = metrics[key];
    if (raw === null || raw === undefined || raw === '') return null;
    var n = Number(raw);
    return isFinite(n) ? n : null;
  }

  /* ------------------------------------------------------ poc normalizers */
  function pocMilestones(data) {
    return arr(data && data.milestones).map(function (item, index) {
      if (!item || typeof item !== 'object') {
        return { week: index + 1, title: textOf(item), deliverables: [], exit: '' };
      }
      var week = Number(item.week !== undefined ? item.week
        : (item.start_week !== undefined ? item.start_week
          : (item.week_no !== undefined ? item.week_no : index + 1)));
      return {
        week: isFinite(week) ? week : index + 1,
        title: str(item.title || item.name || item.goal || ''),
        deliverables: arr(item.deliverables || item.outputs || item.tasks).map(textOf).filter(Boolean),
        exit: textOf(item.exit_criteria || item.exit || item.done_when || item.acceptance)
      };
    });
  }

  function costRangeText(value) {
    if (!value) return '—';
    if (Array.isArray(value) && value.length >= 2) return money(value[0]) + ' – ' + money(value[1]);
    if (typeof value === 'object') {
      if (value.low !== undefined && value.high !== undefined) return money(value.low) + ' – ' + money(value.high);
      if (value.min !== undefined && value.max !== undefined) return money(value.min) + ' – ' + money(value.max);
      return '—';
    }
    if (typeof value === 'number') return money(value);
    return str(value) || '—';
  }

  function customMetricText(item) {
    if (item === null || item === undefined) return '';
    if (typeof item === 'string') return item.trim();
    if (typeof item === 'object') {
      var label = str(item.label || item.name || item.metric || item.title || '');
      var value = item.value !== undefined ? item.value
        : (item.target !== undefined ? item.target : (item.threshold !== undefined ? item.threshold : ''));
      if (label && value !== '') return label + ' · ' + value;
      return label || str(value);
    }
    return String(item);
  }

  function metricListHtml(items) {
    var list = arr(items).map(customMetricText).filter(Boolean);
    if (!list.length) return '<p class="feat-hint">—</p>';
    return '<ul class="feat-list">' + list.map(function (item) {
      return '<li>' + E(item) + '</li>';
    }).join('') + '</ul>';
  }

  /* ----------------------------------------------------------- trend chart */
  function trendPairs(trend) {
    if (!trend) return [];
    if (Array.isArray(trend)) {
      return trend.map(function (item) {
        if (!item || typeof item !== 'object') return null;
        var count = Number(item.count !== undefined ? item.count : item.value);
        if (!isFinite(count)) return null;
        return { year: str(item.year !== undefined ? item.year : (item.label || '')), count: count };
      }).filter(Boolean);
    }
    if (typeof trend !== 'object') return [];
    var years = arr(trend.years);
    var counts = arr(trend.counts);
    if (years.length && years.length === counts.length) {
      var pairs = [];
      years.forEach(function (year, index) {
        var count = Number(counts[index]);
        if (isFinite(count)) pairs.push({ year: str(year), count: count });
      });
      return pairs;
    }
    var out = [];
    Object.keys(trend).forEach(function (key) {
      var count = Number(trend[key]);
      if (isFinite(count)) out.push({ year: key, count: count });
    });
    return out;
  }

  function trendSvg(trend) {
    var pairs = trendPairs(trend);
    if (!pairs.length) return '<div class="feat-empty feat-empty-sm">' + E(s('noTrend')) + '</div>';
    var W = 640;
    var H = 190;
    var padL = 38;
    var padR = 16;
    var padT = 16;
    var padB = 30;
    var plotW = W - padL - padR;
    var plotH = H - padT - padB;
    var maxCount = 1;
    pairs.forEach(function (pair) { if (pair.count > maxCount) maxCount = pair.count; });
    var stepX = pairs.length > 1 ? plotW / (pairs.length - 1) : 0;
    function xAt(index) {
      return pairs.length > 1 ? padL + index * stepX : padL + plotW / 2;
    }
    function yAt(count) {
      return padT + plotH * (1 - count / maxCount);
    }

    var grid = '';
    for (var g = 0; g <= 3; g += 1) {
      var value = (maxCount * g) / 3;
      var y = yAt(value);
      grid += '<line class="feat-svg-grid" x1="' + padL + '" y1="' + y.toFixed(1) +
        '" x2="' + (W - padR) + '" y2="' + y.toFixed(1) + '"/>';
      grid += '<text class="feat-svg-axis" x="' + (padL - 7) + '" y="' + (y + 3.5).toFixed(1) +
        '" text-anchor="end">' + E(Math.round(value)) + '</text>';
    }

    var points = pairs.map(function (pair, index) {
      return { x: xAt(index), y: yAt(pair.count), pair: pair };
    });
    var line = points.map(function (point) {
      return point.x.toFixed(1) + ',' + point.y.toFixed(1);
    }).join(' ');
    var area = 'M' + points[0].x.toFixed(1) + ',' + (H - padB) + ' L' +
      points.map(function (point) {
        return point.x.toFixed(1) + ',' + point.y.toFixed(1);
      }).join(' L') + ' L' + points[points.length - 1].x.toFixed(1) + ',' + (H - padB) + ' Z';

    var labelEvery = Math.max(1, Math.ceil(pairs.length / 8));
    var labels = pairwiseLabels(points, labelEvery);

    var dots = points.map(function (point) {
      return '<circle class="feat-svg-dot" cx="' + point.x.toFixed(1) + '" cy="' + point.y.toFixed(1) +
        '" r="3"><title>' + E(str(point.pair.year) + ': ' + point.pair.count) + '</title></circle>';
    }).join('');

    return '<div class="feat-chart">' +
      '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + E(s('trend')) + '">' +
      grid +
      '<path class="feat-svg-area" d="' + area + '"/>' +
      '<polyline class="feat-svg-line" points="' + line + '"/>' +
      dots + labels +
      '</svg></div>';
  }

  function pairwiseLabels(points, every) {
    var html = '';
    points.forEach(function (point, index) {
      if (index % every !== 0 && index !== points.length - 1) return;
      html += '<text class="feat-svg-axis" x="' + point.x.toFixed(1) + '" y="' + (190 - 10) +
        '" text-anchor="middle">' + E(str(point.pair.year)) + '</text>';
    });
    return html;
  }

  function sourceMixHtml(sourceMix) {
    var list = arr(sourceMix).map(function (item) {
      if (!item || typeof item !== 'object') return null;
      var count = Number(item.count);
      if (!isFinite(count)) return null;
      return { source: str(item.source || '—'), count: count };
    }).filter(Boolean);
    if (!list.length) return '<p class="feat-hint">' + E(s('emptyGeneric')) + '</p>';
    var max = 1;
    list.forEach(function (item) { if (item.count > max) max = item.count; });
    return '<div class="feat-bars">' + list.map(function (item) {
      var width = Math.max(2, (item.count / max) * 100);
      return '<div class="feat-barrow">' +
        '<span class="feat-barname" title="' + E(item.source) + '">' + E(item.source) + '</span>' +
        '<span class="feat-bartrack"><span class="feat-barfill" style="width:' + width.toFixed(1) + '%"></span></span>' +
        '<span class="feat-barnum">' + E(item.count) + '</span>' +
        '</div>';
    }).join('') + '</div>';
  }

  /* ======================================================================
   * Panels
   * ==================================================================== */
  var Panels = {};

  /* ---------------------------------------------------------------- wizard */
  Panels.wizard = {
    titleKey: 'wizardTitle',
    size: 'md',
    init: function (opts) {
      return {
        scenarios: [],
        form: {
          role: normRole((opts && opts.role) || hostRole()) || 'founder',
          goal: (opts && opts.goal) || '',
          team_size: (opts && opts.team_size) || '5',
          budget_usd: (opts && opts.budget_usd) || '20000',
          horizon_weeks: (opts && opts.horizon_weeks) || '8',
          risk: 'medium'
        },
        data: null,
        loading: false,
        error: null
      };
    },
    head: function () { return [s('wizardTitle'), s('wizardSub')]; },
    foot: function () { return s('wizardFoot'); },
    render: function (state) {
      return wizardFormHtml(state) + wizardResultHtml(state);
    },
    sync: function (state, el, name) {
      if (name) state.form[name] = el.value;
    },
    submit: function (state) {
      var form = state.form || {};
      var payload = {
        role: normRole(form.role) || 'founder',
        goal: str(form.goal),
        team_size: intOr(form.team_size, 3, 1, 200),
        budget_usd: intOr(form.budget_usd, 0, 0, 100000000),
        horizon_weeks: intOr(form.horizon_weeks, 8, 1, 104),
        risk: ['low', 'medium', 'high'].indexOf(str(form.risk)) >= 0 ? str(form.risk) : 'medium',
        lang: F.lang
      };
      return postJSON('/api/wizard', payload, TIMEOUT_POST).then(function (data) {
        state.data = data;
      });
    },
    onSubmit: function (state) {
      runRequest(state, function () { return Panels.wizard.submit(state); });
    },
    retry: function (state) {
      return Panels.wizard.submit(state);
    },
    onAction: function (state, act, el) {
      if (act === 'chat') {
        var idx = el.getAttribute('data-idx');
        openChatPrompt(wizardPrompt(state, idx === null ? null : Number(idx)));
        return;
      }
      if (act === 'rerank') {
        retryCurrent();
        return;
      }
      if (act === 'reset') {
        state.data = null;
        state.error = null;
        renderBody(false);
      }
    }
  };

  function wizardFormHtml(state) {
    var form = state.form || {};
    var loading = !!state.loading;
    return '<form class="feat-form" data-form="wizard" autocomplete="off">' +
      '<div class="feat-grid">' +
      wizSelectField('role', s('role'), [
        { value: 'founder', label: s('roleFounder') },
        { value: 'enterprise', label: s('roleEnterprise') },
        { value: 'investor', label: s('roleInvestor') },
        { value: 'pm', label: s('rolePm') }
      ], form.role, loading) +
      wizSelectField('risk', s('risk'), [
        { value: 'low', label: s('riskLow') },
        { value: 'medium', label: s('riskMedium') },
        { value: 'high', label: s('riskHigh') }
      ], form.risk, loading) +
      '<label class="feat-field feat-field-wide"><span class="feat-label">' + E(s('goal')) + '</span>' +
      '<input class="feat-input" type="text" name="goal" value="' + E(form.goal || '') + '" placeholder="' +
      E(s('goalPlaceholder')) + '"' + (loading ? ' disabled' : '') + '></label>' +
      wizNumberField('team_size', s('teamSize'), form.team_size, 1, 200, 1, loading) +
      wizNumberField('budget_usd', s('budget'), form.budget_usd, 0, 100000000, 500, loading) +
      wizNumberField('horizon_weeks', s('horizon'), form.horizon_weeks, 1, 104, 1, loading) +
      '</div>' +
      '<div class="feat-row" style="margin-top:14px">' +
      '<button type="submit" class="feat-btn feat-btn-primary"' + (loading ? ' disabled' : '') + '>' +
      E(loading ? s('computing') : s('submitWizard')) + '</button>' +
      '<span class="feat-hint" style="margin:0">' + E(s('wizardHint')) + '</span>' +
      '</div></form>';
  }

  function wizSelectField(name, label, options, value, disabled) {
    var html = '<label class="feat-field"><span class="feat-label">' + E(label) + '</span>' +
      '<select class="feat-select" name="' + E(name) + '"' + (disabled ? ' disabled' : '') + '>';
    options.forEach(function (option) {
      html += '<option value="' + E(option.value) + '"' +
        (String(value) === String(option.value) ? ' selected' : '') + '>' + E(option.label) + '</option>';
    });
    return html + '</select></label>';
  }

  function wizNumberField(name, label, value, min, max, step, disabled) {
    return '<label class="feat-field"><span class="feat-label">' + E(label) + '</span>' +
      '<input class="feat-input" type="number" name="' + E(name) + '" value="' + E(value === undefined ? '' : value) +
      '" min="' + min + '" max="' + max + '" step="' + step + '"' + (disabled ? ' disabled' : '') + '></label>';
  }

  function wizardResultHtml(state) {
    if (state.loading) return loadingBlock(s('computing'));
    if (state.error) return errorHtml(state.error);
    if (!state.data) return '<p class="feat-hint">' + E(s('wizardHint')) + '</p>';
    var data = state.data || {};
    var list = wizShortlist(data);
    var html = narrativeHtml(data.narrative);
    if (data.narrative === null || data.narrative === undefined) {
      html += '<p class="feat-hint">' + E(s('narrativeMissing')) + '</p>';
    }
    if (!list.length) return html + emptyHtml(s('wizardEmpty'), 'chart');
    html += '<div class="feat-section">' + sectionTitle(s('shortlist')) + '<div class="feat-cards">';
    list.slice(0, 3).forEach(function (item, index) {
      html += wizardCardHtml(item, index);
    });
    html += '</div></div>';
    html += '<div class="feat-row feat-row-end" style="margin-top:14px">' +
      '<button type="button" class="feat-btn feat-btn-primary" data-act="chat">' +
      E(s('agentAnalyze')) + '</button></div>';
    return html;
  }

  function wizardCardHtml(item, index) {
    var name = pickName(item);
    var score = firstNum(item, ['score', 'total_score', 'opportunity']);
    var opp = metricOf(item, 'opportunity');
    var feas = metricOf(item, 'feasibility');
    var gap = metricOf(item, 'gap');
    var route = scenarioRoute(item);
    var fit = arr(item.fit_reasons || item.reasons).map(textOf).filter(Boolean);
    var watch = arr(item.watchouts || item.watchout).map(textOf).filter(Boolean);
    var html = '<div class="feat-card">' +
      '<div class="feat-card-head">' +
      '<span class="feat-card-rank">' + E(index + 1) + '</span>' +
      '<div style="flex:1;min-width:0">' +
      '<div class="feat-card-name">' + E(name || s('scenario')) + '</div>' +
      '<div class="feat-card-meta">' +
      (route ? '<span class="feat-chip">' + E(s('route')) + ': ' + E(route) + '</span>' : '') +
      (item.rank !== undefined && item.rank !== null ? '<span class="feat-chip">#' + E(item.rank) + '</span>' : '') +
      '</div></div>' +
      '<div class="feat-score"><div class="feat-score-value">' + E(score === null ? '—' : score.toFixed(1)) +
      '</div><div class="feat-score-label">' + E(s('score')) + '</div></div>' +
      '</div>' +
      '<div class="feat-card-stats">' +
      miniStat(s('opportunity'), opp) +
      miniStat(s('feasibility'), feas) +
      miniStat(s('gap'), gap) +
      '</div>';
    if (fit.length) {
      html += '<div class="feat-fit"><span class="feat-fit-label">' + E(s('fitReasons')) + '</span>' +
        '<ul class="feat-fit-list">' + fit.map(function (reason) {
          return '<li>' + E(reason) + '</li>';
        }).join('') + '</ul></div>';
    }
    if (watch.length) {
      html += '<div class="feat-watch"><span class="feat-watch-label">' + E(s('watchouts')) + '</span>' +
        '<ul class="feat-watch-list">' + watch.map(function (reason) {
          return '<li>' + E(reason) + '</li>';
        }).join('') + '</ul></div>';
    }
    html += '<div class="feat-card-actions">' +
      '<button type="button" class="feat-btn feat-btn-sm" data-act="chat" data-idx="' + index + '">' +
      E(s('agentAnalyzeOne')) + '</button>' +
      '</div></div>';
    return html;
  }

  function miniStat(label, value) {
    return '<div class="feat-mini"><div class="feat-mini-label">' + E(label) + '</div>' +
      '<div class="feat-mini-value">' + E(value === null || value === undefined ? '—' : metricNum(value)) + '</div></div>';
  }

  /* -------------------------------------------------------------- evidence */
  Panels.evidence = {
    titleKey: 'evidenceTitle',
    size: 'lg',
    init: function (opts) {
      var filters = {
        scenario: scenarioId((opts && opts.scenario) || ''),
        source: '',
        year: '',
        kind: ((opts && opts.kind) || 'all'),
        q: (opts && opts.q) || ''
      };
      return {
        filters: filters,
        facets: null,
        items: [],
        total: 0,
        limit: 100,
        loading: true,
        error: null
      };
    },
    head: function () { return [s('evidenceTitle'), s('evidenceSub')]; },
    foot: function () { return s('evidenceFoot'); },
    load: function (state) {
      var params = {
        scenario: state.filters.scenario || '',
        source: state.filters.source || '',
        year: state.filters.year || '',
        kind: state.filters.kind || 'all',
        q: state.filters.q || '',
        limit: state.limit || 100
      };
      return Promise.all([
        getScenarios().catch(function () { return F.scenarios || []; }),
        getJSON('/api/evidence', params)
      ]).then(function (results) {
        state.scenarios = results[0];
        var data = results[1] || {};
        state.facets = data.facets || null;
        state.items = arr(data.items);
        var total = Number(data.total);
        state.total = isFinite(total) ? total : state.items.length;
      });
    },
    retry: function (state) {
      return Panels.evidence.load(state);
    },
    sync: function (state, el, name, noteIdx, value, isChange) {
      if (name && Object.prototype.hasOwnProperty.call(state.filters, name)) {
        state.filters[name] = value;
        if (isChange && (name === 'scenario' || name === 'source' || name === 'year')) {
          reloadEvidence(state);
        }
      }
    },
    render: function (state) {
      return evidenceFiltersHtml(state) +
        (state.loading ? skeletonList(3)
          : (state.error ? errorHtml(state.error)
            : evidenceResultsHtml(state)));
    },
    onAction: function (state, act, el) {
      if (act === 'kind') {
        state.filters.kind = el.getAttribute('data-val') || 'all';
        reloadEvidence(state);
        return;
      }
      if (act === 'search') {
        reloadEvidence(state);
        return;
      }
      if (act === 'reset') {
        state.filters = { scenario: '', source: '', year: '', kind: 'all', q: '' };
        state.limit = 100;
        reloadEvidence(state);
        return;
      }
      if (act === 'more') {
        state.limit = Math.min(200, (state.limit || 100) + 50);
        reloadEvidence(state);
      }
    }
  };

  function reloadEvidence(state) {
    runRequest(state, function () { return Panels.evidence.load(state); });
  }

  function evidenceFilterValue(state, key) {
    return (state.filters && state.filters[key]) || '';
  }

  function evidenceFilterOptions(state, key) {
    var values = [];
    if (key === 'scenario') {
      (state.scenarios || F.scenarios || []).forEach(function (item) {
        values.push({
          value: item.id,
          label: F.lang === 'zh' ? (item.name || item.id) : (item.name_en || item.name || item.id)
        });
      });
      if (!values.length && state.facets) {
        arr(state.facets.scenarios).forEach(function (item) {
          values.push({ value: scenarioId(item), label: scenarioName(item) });
        });
      }
    } else if (key === 'source') {
      var sources = state.facets && state.facets.sources ? state.facets.sources : null;
      if (!sources) {
        sources = [];
        (state.items || []).forEach(function (item) {
          if (str(item.source) && sources.indexOf(item.source) < 0) sources.push(item.source);
        });
      }
      arr(sources).forEach(function (source) { values.push({ value: source, label: source }); });
    } else if (key === 'year') {
      var years = state.facets && state.facets.years ? state.facets.years : null;
      if (!years) {
        years = [];
        (state.items || []).forEach(function (item) {
          if (item.year !== undefined && item.year !== null && years.indexOf(item.year) < 0) years.push(item.year);
        });
      }
      arr(years).forEach(function (year) { values.push({ value: String(year), label: String(year) }); });
    }
    return values;
  }

  function evidenceFiltersHtml(state) {
    var kinds = [
      { value: 'all', label: s('kindAll') },
      { value: 'positive', label: s('kindPositive') },
      { value: 'negative', label: s('kindNegative') }
    ];
    var kind = state.filters.kind || 'all';
    var html = '<div class="feat-filters"><div class="feat-grid feat-grid-3">';
    html += filterSelectHtml('scenario', s('scenario'), evidenceFilterOptions(state, 'scenario'),
      evidenceFilterValue(state, 'scenario'), s('allScenarios'));
    html += filterSelectHtml('source', s('source'), evidenceFilterOptions(state, 'source'),
      evidenceFilterValue(state, 'source'), s('allSources'));
    html += filterSelectHtml('year', s('year'), evidenceFilterOptions(state, 'year'),
      evidenceFilterValue(state, 'year'), s('allYears'));
    html += '</div><div class="feat-filter-actions">' +
      '<div class="feat-field" style="flex:1;min-width:200px">' +
      '<span class="feat-label">' + E(s('kind')) + '</span>' +
      '<div class="feat-row"><div class="feat-seg">' + kinds.map(function (option) {
        return '<button type="button" class="' + (kind === option.value ? 'feat-is-active' : '') +
          '" data-act="kind" data-val="' + E(option.value) + '">' + E(option.label) + '</button>';
      }).join('') + '</div></div></div>' +
      '<div class="feat-field" style="flex:2;min-width:220px">' +
      '<span class="feat-label">' + E(s('search')) + '</span>' +
      '<input class="feat-input" type="search" name="q" data-enter-act="search" value="' +
      E(state.filters.q || '') + '" placeholder="' + E(s('searchPlaceholder')) + '"></div>' +
      '<button type="button" class="feat-btn feat-btn-primary" data-act="search">' + E(s('search')) + '</button>' +
      '<button type="button" class="feat-btn" data-act="reset">' + E(s('reset')) + '</button>' +
      '</div></div>';
    return html;
  }

  function filterSelectHtml(name, label, options, value, allLabel) {
    var html = '<label class="feat-field"><span class="feat-label">' + E(label) + '</span>' +
      '<select class="feat-select" name="' + E(name) + '">' +
      '<option value="">' + E(allLabel) + '</option>';
    options.forEach(function (option) {
      html += '<option value="' + E(option.value) + '"' +
        (String(value) === String(option.value) ? ' selected' : '') + '>' + E(option.label) + '</option>';
    });
    return html + '</select></label>';
  }

  function evidenceResultsHtml(state) {
    var total = state.total || state.items.length || 0;
    var html = '<div class="feat-statsbar">' +
      '<b>' + E(total) + '</b><span>' + E(s('evidenceTotal', total)) + '</span>' +
      (state.filters.scenario ? '<span class="feat-chip">' + E(scenarioName(state.filters.scenario)) + '</span>' : '') +
      (state.filters.kind && state.filters.kind !== 'all'
        ? '<span class="feat-chip">' + E(state.filters.kind === 'positive' ? s('kindPositive') : s('kindNegative')) + '</span>' : '') +
      (state.filters.q ? '<span class="feat-chip">“' + E(state.filters.q) + '”</span>' : '') +
      '</div>';
    if (!state.items.length) return html + emptyHtml(s('evidenceEmpty'), 'inbox');
    html += evidenceListHtml(state.items);
    if (state.items.length < total) {
      html += '<div class="feat-row feat-row-end" style="margin-top:12px">' +
        '<button type="button" class="feat-btn" data-act="more">' + E(s('loadMore')) + ' · ' +
        E(state.items.length) + '/' + E(total) + '</button></div>';
    }
    return html;
  }

  /* ------------------------------------------------------------------- poc */
  Panels.poc = {
    titleKey: 'pocTitle',
    size: 'lg',
    init: function (opts) {
      return {
        scenarios: [],
        form: {
          scenario: scenarioId((opts && opts.scenario) || ''),
          weeks: String((opts && opts.weeks) || 4),
          team_size: String((opts && opts.team_size) || 3)
        },
        data: null,
        narrative: null,
        loading: true,
        error: null
      };
    },
    head: function () { return [s('pocTitle'), s('pocSub')]; },
    foot: function () { return s('pocFoot'); },
    load: function (state) {
      return getScenarios().then(function (list) {
        state.scenarios = list || [];
        if (!state.form.scenario && list && list.length) state.form.scenario = list[0].id;
      });
    },
    sync: function (state, el, name) {
      if (name && Object.prototype.hasOwnProperty.call(state.form, name)) state.form[name] = el.value;
    },
    submit: function (state) {
      var form = state.form || {};
      if (!form.scenario) return Promise.resolve();
      var payload = {
        scenario: form.scenario,
        weeks: intOr(form.weeks, 4, 2, 8),
        team_size: intOr(form.team_size, 3, 1, 50),
        lang: F.lang,
        role: hostRole() || 'founder'
      };
      return postJSON('/api/poc', payload, TIMEOUT_POST).then(function (data) {
        state.data = data;
      });
    },
    onSubmit: function (state) {
      runRequest(state, function () { return Panels.poc.submit(state); });
    },
    retry: function (state) {
      if (!state.scenarios || !state.scenarios.length) return Panels.poc.load(state);
      return Panels.poc.submit(state);
    },
    onAction: function (state, act, el) {
      if (act === 'weeks') {
        state.form.weeks = el.getAttribute('data-val') || '4';
        renderBody(false);
        return;
      }
      if (act === 'copy') {
        copyText(pocCopyText(state));
        return;
      }
      if (act === 'chat') {
        var plan = state.data || {};
        var name = scenarioName(plan.scenario) || scenarioName(state.form.scenario);
        var prompt = F.lang === 'zh'
          ? '把「' + name + '」的 ' + intOr(state.form.weeks, 4, 2, 8) + ' 周 PoC 计划展开成可执行任务清单：里程碑、负责人、依赖、验收标准与风险应对。'
          : 'Turn the ' + intOr(state.form.weeks, 4, 2, 8) + '-week PoC plan for "' + name +
            '" into an executable task list: milestones, owners, dependencies, acceptance criteria and risk responses.';
        openChatPrompt(prompt);
        return;
      }
      if (act === 'reset') {
        state.data = null;
        state.error = null;
        renderBody(false);
      }
    },
    render: function (state) {
      return pocFormHtml(state) + pocResultHtml(state);
    }
  };

  function pocFormHtml(state) {
    var form = state.form || {};
    var loading = !!state.loading;
    var scenariosEmpty = !state.scenarios || !state.scenarios.length;
    var html = '<form class="feat-form" data-form="poc" autocomplete="off"><div class="feat-grid">' +
      '<label class="feat-field feat-field-wide"><span class="feat-label">' + E(s('scenario')) + '</span>' +
      '<select class="feat-select" name="scenario"' + (loading ? ' disabled' : '') + '>' +
      (scenariosEmpty ? '<option value="">' + E(loading ? s('loading') : s('workspaceNoScenario')) + '</option>' : '') +
      scenarioOptions(form.scenario, '') +
      '</select></label>' +
      '</div>' +
      '<div class="feat-grid feat-grid-3" style="margin-top:12px">' +
      '<div class="feat-field"><span class="feat-label">' + E(s('weeks')) + '</span>' +
      '<div class="feat-seg">' + [2, 4, 8].map(function (weeks) {
        return '<button type="button" class="' + (String(form.weeks) === String(weeks) ? 'feat-is-active' : '') +
          '" data-act="weeks" data-val="' + weeks + '">' + weeks + 'w</button>';
      }).join('') + '</div></div>' +
      '<label class="feat-field"><span class="feat-label">' + E(s('teamSize')) + '</span>' +
      '<input class="feat-input" type="number" name="team_size" min="1" max="50" value="' +
      E(form.team_size || 3) + '"' + (loading ? ' disabled' : '') + '></label>' +
      '</div>' +
      '<div class="feat-row" style="margin-top:14px">' +
      '<button type="submit" class="feat-btn feat-btn-primary"' + (loading || scenariosEmpty ? ' disabled' : '') + '>' +
      E(loading ? s('computing') : s('submitPoc')) + '</button>' +
      '<span class="feat-hint" style="margin:0">' + E(s('pocHint')) + '</span>' +
      '</div></form>';
    return html;
  }

  function pocResultHtml(state) {
    if (state.loading) return loadingBlock(s('computing'));
    if (state.error) return errorHtml(state.error);
    var data = state.data;
    if (!data) return '<p class="feat-hint">' + E(s('pocHint')) + '</p>';
    var plan = data;
    var name = scenarioName(plan.scenario) || scenarioName(state.form.scenario);
    var milestones = pocMilestones(plan);
    var heuristic = plan.heuristic !== false;
    var html = '<div class="feat-section">' + sectionTitle((name || s('pocTitle')) + ' · ' +
      intOr(plan.weeks, intOr(state.form.weeks, 4, 2, 8), 1) + 'w') + '</div>';
    html += '<div class="feat-summary-grid">' +
      summaryHtml(s('effort'), E(num(plan.effort_person_weeks, 1)) + '<small>' + E(s('effortUnit')) + '</small>') +
      summaryHtml(s('cost'), E(costRangeText(plan.cost_range_usd))) +
      summaryHtml(s('weeks'), E(intOr(plan.weeks, intOr(state.form.weeks, 4, 2, 8), 1)) + '<small>w</small>') +
      summaryHtml(s('teamSize'), E(intOr(state.form.team_size, 3, 1)) + '<small>' + E(s('teamSizeUnit')) + '</small>') +
      '</div>';
    if (heuristic) {
      html += '<p class="feat-hint" style="margin-top:-8px">' + badge(s('heuristic'), 'warn') + ' ' + E(s('pocHint')) + '</p>';
    }
    html += narrativeHtml(plan.narrative);
    if (milestones.length) {
      html += '<div class="feat-section">' + sectionTitle(s('milestones')) +
        '<ol class="feat-timeline">' + milestones.map(function (item, index) {
          var body = '';
          if (item.deliverables.length) {
            body += '<div class="feat-tl-body"><ul class="feat-list">' + item.deliverables.map(function (task) {
              return '<li>' + E(task) + '</li>';
            }).join('') + '</ul></div>';
          }
          if (item.exit) {
            body += '<div class="feat-tl-exit"><b>' + E(s('exitCriteria')) + '</b><span>' + E(item.exit) + '</span></div>';
          }
          return '<li class="feat-tl-item"><span class="feat-tl-dot">' + E(index + 1) + '</span>' +
            '<div class="feat-tl-week">' + E(s('weekUnit', item.week)) + '</div>' +
            '<div class="feat-tl-title">' + E(item.title || s('weeks')) + '</div>' + body + '</li>';
        }).join('') + '</ol></div>';
    }
    html += '<div class="feat-split">' +
      '<div class="feat-section">' + sectionTitle(s('roles')) + tagsHtml(plan.roles) + '</div>' +
      '<div class="feat-section">' + sectionTitle(s('metrics')) + metricListHtml(plan.metrics) + '</div>' +
      '</div>';
    html += '<div class="feat-split">' +
      '<div class="feat-section">' + sectionTitle(s('data_compliance')) + listHtml(plan.data_compliance) + '</div>' +
      '<div class="feat-section">' + sectionTitle(s('risks')) + listHtml(plan.risks) + '</div>' +
      '</div>';
    html += '<div class="feat-row" style="margin-top:4px">' +
      '<button type="button" class="feat-btn" data-act="copy">' + E(s('copyResult')) + '</button>' +
      '<button type="button" class="feat-btn" data-act="chat">' + E(s('agentAnalyze')) + '</button>' +
      '<button type="button" class="feat-btn feat-btn-ghost" data-act="reset">' + E(s('cancel')) + '</button>' +
      '</div>';
    return html;
  }

  function summaryHtml(label, valueHtml) {
    return '<div class="feat-summary"><div class="feat-summary-label">' + E(label) + '</div>' +
      '<div class="feat-summary-value">' + valueHtml + '</div></div>';
  }

  function pocCopyText(state) {
    var data = state.data || {};
    var name = scenarioName(data.scenario) || scenarioName(state.form.scenario);
    var lines = [];
    lines.push((F.lang === 'zh' ? 'PoC 计划 · ' : 'PoC plan · ') + name);
    lines.push(s('weeks') + ': ' + intOr(data.weeks, 4, 1) +
      ' | ' + s('teamSize') + ': ' + intOr(state.form.team_size, 3, 1) +
      ' | ' + s('effort') + ': ' + num(data.effort_person_weeks, 1) + ' ' + s('effortUnit') +
      ' | ' + s('cost') + ': ' + costRangeText(data.cost_range_usd) + ' (' + s('heuristic') + ')');
    var milestones = pocMilestones(data);
    if (milestones.length) {
      lines.push(s('milestones') + ':');
      milestones.forEach(function (item) {
        lines.push('  ' + s('weekUnit', item.week) + ' · ' + (item.title || ''));
        item.deliverables.forEach(function (task) { lines.push('    - ' + task); });
        if (item.exit) lines.push('    ' + s('exitCriteria') + ': ' + item.exit);
      });
    }
    var roles = arr(data.roles).map(textOf).filter(Boolean);
    if (roles.length) lines.push(s('roles') + ': ' + roles.join(', '));
    var metrics = arr(data.metrics).map(customMetricText).filter(Boolean);
    if (metrics.length) lines.push(s('metrics') + ': ' + metrics.join('; '));
    var compliance = arr(data.data_compliance).map(textOf).filter(Boolean);
    if (compliance.length) lines.push(s('data_compliance') + ': ' + compliance.join('; '));
    var risks = arr(data.risks).map(textOf).filter(Boolean);
    if (risks.length) lines.push(s('risks') + ': ' + risks.join('; '));
    return lines.join('\n');
  }

  /* ------------------------------------------------------------- portfolio */
  Panels.portfolio = {
    titleKey: 'portfolioTitle',
    size: 'md',
    init: function (opts) {
      return {
        form: {
          team_size: String((opts && opts.team_size) || 4),
          weeks: String((opts && opts.weeks) || 12),
          budget_usd: String((opts && opts.budget_usd) || 30000),
          goal: (opts && opts.goal) || ''
        },
        data: null,
        loading: false,
        error: null
      };
    },
    head: function () { return [s('portfolioTitle'), s('portfolioSub')]; },
    foot: function () { return s('portfolioFoot'); },
    sync: function (state, el, name) {
      if (name && Object.prototype.hasOwnProperty.call(state.form, name)) state.form[name] = el.value;
    },
    submit: function (state) {
      var form = state.form || {};
      var payload = {
        team_size: intOr(form.team_size, 4, 1, 200),
        weeks: intOr(form.weeks, 12, 1, 104),
        budget_usd: intOr(form.budget_usd, 0, 0, 100000000),
        goal: str(form.goal),
        lang: F.lang,
        role: hostRole() || 'founder'
      };
      return postJSON('/api/portfolio', payload, TIMEOUT_POST).then(function (data) {
        state.data = data;
      });
    },
    onSubmit: function (state) {
      runRequest(state, function () { return Panels.portfolio.submit(state); });
    },
    retry: function (state) {
      return Panels.portfolio.submit(state);
    },
    onAction: function (state, act) {
      if (act === 'reset') {
        state.data = null;
        state.error = null;
        renderBody(false);
      }
    },
    render: function (state) {
      return portfolioFormHtml(state) + portfolioResultHtml(state);
    }
  };

  function portfolioFormHtml(state) {
    var form = state.form || {};
    var loading = !!state.loading;
    return '<form class="feat-form" data-form="portfolio" autocomplete="off">' +
      '<div class="feat-grid feat-grid-3">' +
      wizNumberField('team_size', s('teamSize'), form.team_size, 1, 200, 1, loading) +
      wizNumberField('weeks', s('horizon'), form.weeks, 1, 104, 1, loading) +
      wizNumberField('budget_usd', s('budget'), form.budget_usd, 0, 100000000, 500, loading) +
      '<label class="feat-field feat-field-wide"><span class="feat-label">' + E(s('goalLabel')) + '</span>' +
      '<input class="feat-input" type="text" name="goal" value="' + E(form.goal || '') + '"' +
      (loading ? ' disabled' : '') + '></label>' +
      '</div>' +
      '<div class="feat-row" style="margin-top:14px">' +
      '<button type="submit" class="feat-btn feat-btn-primary"' + (loading ? ' disabled' : '') + '>' +
      E(loading ? s('computing') : s('submitPortfolio')) + '</button>' +
      '<span class="feat-hint" style="margin:0">' + E(s('portfolioHint')) + '</span>' +
      '</div></form>';
  }

  function portfolioResultHtml(state) {
    if (state.loading) return loadingBlock(s('computing'));
    if (state.error) return errorHtml(state.error);
    var data = state.data;
    if (!data) return '<p class="feat-hint">' + E(s('portfolioHint')) + '</p>';
    var picks = arr(data.picks);
    var excluded = arr(data.excluded);
    var html = '<div class="feat-summary-grid">' +
      summaryHtml(s('totalEffort'), E(num(data.total_effort, 1)) + '<small>' + E(s('effortUnit')) + '</small>') +
      summaryHtml(s('budget'), E(money(data.budget_usd !== undefined ? data.budget_usd : state.form.budget_usd))) +
      summaryHtml(s('teamSize'), E(intOr(data.team_size, intOr(state.form.team_size, 4, 1))) + '<small>' + E(s('teamSizeUnit')) + '</small>') +
      summaryHtml(s('weeks'), E(intOr(data.weeks, intOr(state.form.weeks, 12, 1))) + '<small>w</small>') +
      '</div>';
    if (data.heuristic !== false) {
      html += '<p class="feat-hint" style="margin-top:-8px">' + badge(s('heuristic'), 'warn') + ' ' + E(s('portfolioHint')) + '</p>';
    }
    html += narrativeHtml(data.narrative);
    if (picks.length) {
      html += '<div class="feat-section">' + sectionTitle(s('picks')) + picks.map(function (pick) {
        var phase = str(pick.phase);
        var phaseLabel = phase === 'build' ? s('phaseBuild') : (phase === 'validate' ? s('phaseValidate') : phase);
        return '<div class="feat-pick">' +
          '<span class="feat-badge feat-badge-phase">' + E(phaseLabel || s('phase')) + '</span>' +
          '<div class="feat-pick-body">' +
          '<div class="feat-pick-name">' + E(pickName(pick) || s('scenario')) + '</div>' +
          (pick.why ? '<p class="feat-pick-why">' + E(textOf(pick.why)) + '</p>' : '') +
          '</div>' +
          '<span class="feat-score"><span class="feat-score-value">' +
          E(firstNum(pick, ['score']) === null ? '—' : firstNum(pick, ['score']).toFixed(1)) +
          '</span><span class="feat-score-label">' + E(s('score')) + '</span></span>' +
          '</div>';
      }).join('') + '</div>';
    }
    if (excluded.length) {
      html += '<div class="feat-section">' + sectionTitle(s('excluded')) + '<ul class="feat-excluded">' +
        excluded.map(function (item) {
          return '<li><span class="feat-ex-name">' + E(pickName(item) || s('scenario')) + '</span>' +
            '<span class="feat-ex-why">' + E(textOf(item.why) || '—') + '</span></li>';
        }).join('') + '</ul></div>';
    }
    if (!picks.length && !excluded.length) return html + emptyHtml(s('portfolioEmpty'), 'chart');
    return html;
  }

  /* ------------------------------------------------------------- workspace */
  Panels.workspace = {
    titleKey: 'workspaceTitle',
    size: 'md',
    init: function () {
      return {
        scenarios: [],
        items: [],
        addScenario: '',
        addNote: '',
        notes: {},
        pendingRemove: null,
        loading: true,
        error: null
      };
    },
    head: function (state) {
      var count = (state.items || []).length;
      return [s('workspaceTitle'), count ? s('savedCount', count) : s('workspaceSub')];
    },
    foot: function () { return s('workspaceFoot'); },
    load: function (state) {
      return Promise.all([
        getScenarios().catch(function () { return F.scenarios || []; }),
        getJSON('/api/workspace')
      ]).then(function (results) {
        state.scenarios = results[0] || [];
        var data = results[1] || {};
        state.items = normalizeWorkspaceItems(data.items);
        state.notes = {};
        if (!state.addScenario && state.scenarios.length) {
          state.addScenario = firstUnsavedScenario(state);
        }
      });
    },
    retry: function (state) {
      return Panels.workspace.load(state);
    },
    sync: function (state, el, name, noteIdx, value) {
      if (name === 'add_scenario') state.addScenario = value;
      if (noteIdx === 'add') state.addNote = value;
      else if (noteIdx !== null && noteIdx !== undefined && noteIdx !== '') {
        state.notes[noteIdx] = value;
      }
    },
    render: function (state) {
      if (state.loading && !state.items.length) return loadingBlock(s('loading'));
      return workspaceAddHtml(state) + workspaceListHtml(state);
    },
    onAction: function (state, act, el) {
      var idx = Number(el.getAttribute('data-idx'));
      var item = isFinite(idx) ? state.items[idx] : null;
      if (act === 'add') {
        var scenario = state.addScenario || (state.scenarios[0] && state.scenarios[0].id);
        if (!scenario) {
          notify(s('workspaceNoScenario'));
          return;
        }
        var addNote = state.addNote;
        runRequest(state, function () {
          return postJSON('/api/workspace', { action: 'add', scenario: scenario, note: addNote }, TIMEOUT_GET)
            .then(function (data) {
              state.items = normalizeWorkspaceItems(data.items);
              state.addNote = '';
              state.notes = {};
              state.pendingRemove = null;
              state.addScenario = firstUnsavedScenario(state);
              notify(s('added'));
            });
        });
        return;
      }
      if (!item) return;
      if (act === 'save-note') {
        var ownNote = state.notes[idx] !== undefined ? state.notes[idx] : item.note;
        runRequest(state, function () {
          return postJSON('/api/workspace', { action: 'note', scenario: item.scenario, note: ownNote }, TIMEOUT_GET)
            .then(function (data) {
              state.items = normalizeWorkspaceItems(data.items);
              state.notes = {};
              notify(s('noteSaved'));
            });
        });
        return;
      }
      if (act === 'remove') {
        if (state.pendingRemove !== idx) {
          state.pendingRemove = idx;
          renderBody(false);
          return;
        }
        runRequest(state, function () {
          return postJSON('/api/workspace', { action: 'remove', scenario: item.scenario }, TIMEOUT_GET)
            .then(function (data) {
              state.items = normalizeWorkspaceItems(data.items);
              state.pendingRemove = null;
              state.notes = {};
              notify(s('removed'));
            });
        });
        return;
      }
      if (act === 'cancel-remove') {
        state.pendingRemove = null;
        renderBody(false);
        return;
      }
      if (act === 'compare' || act === 'compare-all') {
        var names = saveNames(state, act === 'compare' ? item : null);
        if (names.length >= 2) openChatPrompt(comparePrompt(names));
        else if (names.length === 1) openChatPrompt(detailPrompt(names[0]));
        return;
      }
    }
  };

  function normalizeWorkspaceItems(raw) {
    return arr(raw).map(function (item) {
      if (typeof item === 'string') return { scenario: item, note: '', created_at: '', updated_at: '' };
      if (!item || typeof item !== 'object') return null;
      return {
        scenario: str(item.scenario || item.id || item.name),
        note: str(item.note || ''),
        created_at: str(item.created_at || ''),
        updated_at: str(item.updated_at || '')
      };
    }).filter(function (item) { return item && item.scenario; });
  }

  function firstUnsavedScenario(state) {
    var saved = {};
    (state.items || []).forEach(function (item) { saved[item.scenario] = true; });
    for (var i = 0; i < state.scenarios.length; i += 1) {
      if (!saved[state.scenarios[i].id]) return state.scenarios[i].id;
    }
    return state.scenarios.length ? state.scenarios[0].id : '';
  }

  function saveNames(state, focusItem) {
    var names = [];
    if (focusItem) {
      names.push(scenarioName(focusItem.scenario));
    } else {
      (state.items || []).forEach(function (item) { names.push(scenarioName(item.scenario)); });
    }
    return names.filter(function (name, index, all) { return name && all.indexOf(name) === index; }).slice(0, 3);
  }

  function workspaceAddHtml(state) {
    var loading = !!state.loading;
    var options = (state.scenarios || []).map(function (item) {
      var label = F.lang === 'zh' ? (item.name || item.id) : (item.name_en || item.name || item.id);
      return '<option value="' + E(item.id) + '"' +
        (scenarioId(state.addScenario) === item.id ? ' selected' : '') + '>' + E(label) + '</option>';
    }).join('');
    var html = '<div class="feat-ws-add">' +
      '<label class="feat-field"><span class="feat-label">' + E(s('addScenario')) + '</span>' +
      '<select class="feat-select" name="add_scenario"' + (loading ? ' disabled' : '') + '>' +
      (options || '<option value="">' + E(s('workspaceNoScenario')) + '</option>') +
      '</select></label>' +
      '<label class="feat-field"><span class="feat-label">' + E(s('addNote')) + '</span>' +
      '<input class="feat-input" type="text" data-note-idx="add" value="' + E(state.addNote || '') +
      '" data-enter-act="add" placeholder="' + E(s('addNotePlaceholder')) + '"' + (loading ? ' disabled' : '') + '></label>' +
      '<button type="button" class="feat-btn feat-btn-primary" data-act="add"' +
      (loading ? ' disabled' : '') + '>' + E(s('addBtn')) + '</button>' +
      '</div>';
    return html;
  }

  function workspaceListHtml(state) {
    if (state.error) return errorHtml(state.error);
    if (!state.items.length) {
      return emptyHtml(s('workspaceEmpty'), 'star');
    }
    var html = '<div class="feat-row" style="margin-bottom:10px">' +
      '<span class="feat-kicker">' + E(s('savedCount', state.items.length)) + '</span>' +
      '<span class="feat-spacer"></span>' +
      (state.items.length >= 2
        ? '<button type="button" class="feat-btn feat-btn-primary feat-btn-sm" data-act="compare-all">' +
          E(s('compareSaved')) + '</button>'
        : '') +
      '</div><ul class="feat-ws-list">';
    html += state.items.map(function (item, index) {
      var noteValue = state.notes[index] !== undefined ? state.notes[index] : item.note;
      var date = dateText(item.updated_at || item.created_at);
      var pending = state.pendingRemove === index;
      return '<li class="feat-ws-item">' +
        '<div class="feat-ws-head">' +
        '<span class="feat-ws-name">' + E(scenarioName(item.scenario)) + '</span>' +
        (date ? '<span class="feat-ws-date">' + E(date) + '</span>' : '') +
        '</div>' +
        '<div class="feat-ws-note-row">' +
        '<input class="feat-input" type="text" data-note-idx="' + index + '" value="' + E(noteValue) + '" placeholder="' +
        E(s('addNotePlaceholder')) + '"' + (state.loading ? ' disabled' : '') + '>' +
        '<button type="button" class="feat-btn feat-btn-sm" data-act="save-note" data-idx="' + index + '"' +
        (state.loading ? ' disabled' : '') + '>' + E(s('saveNote')) + '</button>' +
        '</div>' +
        '<div class="feat-ws-actions">' +
        '<button type="button" class="feat-btn feat-btn-sm" data-act="compare" data-idx="' + index + '">' +
        E(s('compare')) + '</button>' +
        (pending
          ? '<button type="button" class="feat-btn feat-btn-sm feat-btn-danger" data-act="remove" data-idx="' + index + '">' +
            E(s('confirmRemove')) + '</button>' +
            '<button type="button" class="feat-btn feat-btn-sm feat-btn-ghost" data-act="cancel-remove" data-idx="' + index + '">' +
            E(s('cancelRemove')) + '</button>'
          : '<button type="button" class="feat-btn feat-btn-sm feat-btn-ghost" data-act="remove" data-idx="' + index + '">' +
            E(s('remove')) + '</button>') +
        '</div></li>';
    }).join('');
    return html + '</ul>';
  }

  /* ---------------------------------------------------------------- videos */
  Panels.videos = {
    titleKey: 'videosTitle',
    size: 'md',
    init: function (opts) {
      return {
        scenarios: [],
        scenario: scenarioId((opts && opts.scenario) || ''),
        items: [],
        loading: true,
        error: null
      };
    },
    head: function () { return [s('videosTitle'), s('videosSub')]; },
    foot: function () { return s('videosFoot'); },
    load: function (state) {
      var ensure = state.scenarios && state.scenarios.length
        ? Promise.resolve(state.scenarios)
        : getScenarios().catch(function () { return []; });
      return ensure.then(function (list) {
        state.scenarios = list || [];
        if (!state.scenario && state.scenarios.length) state.scenario = state.scenarios[0].id;
        if (!state.scenario) {
          state.items = [];
          return;
        }
        return getJSON('/api/videos', { scenario: state.scenario, lang: F.lang }).then(function (data) {
          state.items = arr(data && data.items);
        });
      });
    },
    sync: function (state, el, name, noteIdx, value, isChange) {
      if (name === 'scenario' && isChange) {
        state.scenario = value;
        runRequest(state, function () { return Panels.videos.load(state); });
      }
    },
    render: function (state) {
      var select = '<label class="feat-field"><span class="feat-label">' + E(s('scenario')) + '</span>' +
        '<select class="feat-select" name="scenario"' + (state.loading ? ' disabled' : '') + '>' +
        scenarioOptions(state.scenario, '') + '</select></label>';
      var html = '<div class="feat-filters"><div class="feat-grid">' + select + '</div></div>' +
        '<p class="feat-hint" style="margin:-4px 0 14px">' + E(s('videosHint')) + '</p>';
      if (state.loading) return html + skeletonList(2);
      if (state.error) return html + errorHtml(state.error);
      if (!state.items.length) return html + emptyHtml(s('videoEmpty'), 'video');
      html += '<div class="feat-video-grid">' + state.items.map(function (item, index) {
        var platform = str(item.platform).toLowerCase();
        var kind = platform === 'youtube' ? 'youtube' : (platform === 'bilibili' ? 'bilibili' : 'other');
        var url = safeUrl(item.url);
        return '<button type="button" class="feat-video-card" data-act="video" data-idx="' + index + '"' +
          (url ? '' : ' disabled') + '>' +
          '<span class="feat-video-top">' +
          '<span class="feat-platform feat-platform-' + kind + '">' +
          E(platform ? platform.toUpperCase() : s('source')) + '</span>' +
          '<span class="feat-badge feat-badge-soft">' + E(item.kind === 'search' ? s('disclaimer') : s('openExternal')) + '</span>' +
          '</span>' +
          '<span class="feat-video-title">' + E(textOf(item.title) || s('videosTitle')) + '</span>' +
          (item.note ? '<span class="feat-video-note">' + E(textOf(item.note)) + '</span>' : '') +
          '<span class="feat-video-open">' + E(s('openExternal')) + ' ↗</span>' +
          '</button>';
      }).join('') + '</div>';
      return html;
    },
    onAction: function (state, act, el) {
      if (act !== 'video') return;
      var idx = Number(el.getAttribute('data-idx'));
      var item = state.items[idx];
      var url = item && safeUrl(item.url);
      if (!url) return;
      try {
        var win = window.open(url, '_blank', 'noopener');
        if (!win) notify(s('popupBlocked'));
      } catch (err) {
        notify(errText(err));
      }
    }
  };

  /* ---------------------------------------------------------------- detail */
  Panels.detail = {
    titleKey: 'detailTitle',
    size: 'lg',
    init: function (opts) {
      return {
        id: str((opts && (opts.id || opts.scenario)) || ''),
        data: null,
        loading: true,
        error: null,
        faved: false
      };
    },
    head: function (state) {
      if (state.data) {
        var name = F.lang === 'zh' ? (state.data.name || state.data.id) : (state.data.name_en || state.data.name || state.data.id);
        return [name || s('detailTitle'), s('detailSub')];
      }
      return [s('detailTitle'), s('detailSub')];
    },
    foot: function () { return s('evidenceFoot'); },
    load: function (state) {
      if (!state.id) return Promise.reject(makeError(s('detailMissing'), 'input'));
      return getJSON('/api/scenario_detail', { name: state.id, lang: F.lang }).then(function (data) {
        state.data = data;
        state.id = str(data.id || state.id);
      });
    },
    retry: function (state) {
      return Panels.detail.load(state);
    },
    render: function (state) {
      if (state.loading && !state.data) return loadingBlock(s('loading'));
      if (state.error) return errorHtml(state.error);
      if (!state.data) return emptyHtml(s('detailEmpty'), 'chart');
      return detailHtml(state);
    },
    onAction: function (state, act) {
      if (act === 'fav') {
        if (!state.id) return;
        runRequest(state, function () {
          return postJSON('/api/workspace', { action: 'add', scenario: state.id, note: '' }, TIMEOUT_GET)
            .then(function () {
              state.faved = true;
              notify(s('favAdded'));
            });
        });
        return;
      }
      if (act === 'poc') {
        open('poc', { scenario: state.id });
        return;
      }
      if (act === 'videos') {
        open('videos', { scenario: state.id });
        return;
      }
      if (act === 'chat') {
        var data = state.data || {};
        var name = F.lang === 'zh' ? (data.name || data.id) : (data.name_en || data.name || data.id);
        openChatPrompt(detailPrompt(name || s('detailTitle')));
      }
    }
  };

  function detailHtml(state) {
    var data = state.data || {};
    var metrics = data.metrics && typeof data.metrics === 'object' ? data.metrics : data;
    var name = F.lang === 'zh' ? (data.name || data.id) : (data.name_en || data.name || data.id);
    var scenario = { id: data.id || state.id, name: data.name || name, name_en: data.name_en };
    var rank = firstNum(metrics, ['rank']);
    var nDocs = firstNum(metrics, ['n_docs']);
    var html = '<div class="feat-metrics">' +
      detailMetric(s('opportunity'), metrics.opportunity, true) +
      detailMetric(s('demand'), metrics.demand) +
      detailMetric(s('gap'), metrics.gap) +
      detailMetric(s('feasibility'), metrics.feasibility) +
      detailMetric(s('value'), metrics.value) +
      '</div>';
    html += '<div class="feat-row" style="margin:-6px 0 16px;gap:6px">' +
      (rank !== null ? '<span class="feat-chip">' + E(s('rank')) + ' #' + E(rank) + '</span>' : '') +
      (nDocs !== null ? '<span class="feat-chip">' + E(s('samples')) + ' ' + E(nDocs) + '</span>' : '') +
      (str(scenarioRoute(metrics)) || str(data.route)
        ? '<span class="feat-chip">' + E(s('route')) + ': ' + E(scenarioRoute(metrics) || data.route) + '</span>' : '') +
      '</div>';
    html += '<div class="feat-quick">' +
      '<button type="button" class="feat-btn feat-btn-primary" data-act="fav">' +
      E(state.faved ? s('favAdded') : s('addFav')) + '</button>' +
      '<button type="button" class="feat-btn" data-act="poc">' + E(s('genPoc')) + '</button>' +
      '<button type="button" class="feat-btn" data-act="videos">' + E(s('watchVideos')) + '</button>' +
      '<button type="button" class="feat-btn" data-act="chat">' + E(s('analyze')) + '</button>' +
      '</div>';

    var trendData = data.trend || (data.insights && data.insights.trend);
    html += '<div class="feat-section">' + sectionTitle(s('trend')) + trendSvg(trendData) + '</div>';
    html += '<div class="feat-split">' +
      '<div class="feat-section">' + sectionTitle(s('sourceMix')) +
      sourceMixHtml(data.source_mix || (data.insights && data.insights.source_mix)) + '</div>' +
      '<div class="feat-section">' + sectionTitle(s('signals')) + signalsHtml(data) + '</div>' +
      '</div>';
    html += '<div class="feat-section">' + sectionTitle(s('supply')) + supplyHtml(data) + '</div>';
    var evidence = arr(data.evidence);
    html += '<div class="feat-section">' + sectionTitle(s('evidenceExcerpts')) +
      evidenceListHtml(evidence, s('evidenceEmpty')) + '</div>';
    return html;
  }

  function detailMetric(label, value, primary) {
    var display = value === null || value === undefined ? '—' : metricNum(value);
    return '<div class="feat-metric"><div class="feat-metric-label">' + E(label) + '</div>' +
      '<div class="feat-metric-value">' + E(display) +
      (primary && value !== null && value !== undefined ? '<small>/100</small>' : '') + '</div></div>';
  }

  function signalsHtml(data) {
    var metrics = data.metrics && typeof data.metrics === 'object' ? data.metrics : data;
    var signals = data.signals && typeof data.signals === 'object' ? data.signals : {};
    function pick(key) {
      if (signals[key] !== undefined && signals[key] !== null) return signals[key];
      return metrics[key];
    }
    var rows = [
      [s('needRate'), pick('need_rate'), 'num'],
      [s('wtpRate'), pick('wtp_rate'), 'num'],
      [s('valueRate'), pick('value_rate'), 'num'],
      [s('urgencyRate'), pick('urgency_rate'), 'num'],
      [s('growthSlope'), pick('growth_slope'), 'pct'],
      [s('answerRate'), pick('answer_rate'), 'num'],
      [s('barrier'), pick('barrier'), 'num']
    ];
    return '<div class="feat-signals">' + rows.map(function (row) {
      var value = row[1];
      var display = row[2] === 'pct' ? pctSigned(value) : num(value, 2);
      return '<div class="feat-signal"><div class="feat-signal-label">' + E(row[0]) + '</div>' +
        '<div class="feat-signal-value">' + E(display) + '</div></div>';
    }).join('') + '</div>';
  }

  function supplyHtml(data) {
    var metrics = data.metrics && typeof data.metrics === 'object' ? data.metrics : data;
    var supply = data.supply && typeof data.supply === 'object' ? data.supply : {};
    function pick(key) {
      return supply[key] !== undefined && supply[key] !== null ? supply[key] : metrics[key];
    }
    var rows = [
      [s('supplyRepos'), pick('repo_n')],
      [s('supplyStars'), pick('repo_stars_sum')],
      [s('supplyPapers'), pick('paper_n')],
      [s('supplyShow'), pick('show_n')],
      [s('supplyProducts'), pick('product_n')]
    ];
    return '<div class="feat-supply">' + rows.map(function (row) {
      var value = row[1];
      var display = value === null || value === undefined || value === ''
        ? '—'
        : Number(value).toLocaleString(F.lang === 'zh' ? 'zh-CN' : 'en-US');
      return '<div class="feat-supply-item"><div class="feat-supply-label">' + E(row[0]) + '</div>' +
        '<div class="feat-supply-value">' + E(display) + '</div></div>';
    }).join('') + '</div>';
  }

  /* ======================================================================
   * Public API
   * ==================================================================== */
  function onScenarios(list) {
    try {
      if (Array.isArray(list) && list.length) assignScenarios(list);
    } catch (err) { /* keep the previous cache */ }
    return F.scenarios || [];
  }

  function openDetail(scenarioIdValue) {
    var id = str(scenarioIdValue);
    if (!id) return;
    if (F.current && F.current.panel === 'detail' && isOpen() && F.current.state.id === id) return;
    open('detail', { id: id });
  }

  function detectLang() {
    try {
      if (typeof document !== 'undefined') {
        var saved = null;
        try { saved = localStorage.getItem('openecrs-lang'); } catch (err) { saved = null; }
        if (saved === 'zh' || saved === 'en') return saved;
        var docLang = (document.documentElement.getAttribute('lang') || '').toLowerCase();
        if (docLang.indexOf('zh') === 0) return 'zh';
        if (docLang.indexOf('en') === 0) return 'en';
      }
    } catch (err) { /* ignore */ }
    return 'zh';
  }

  function mount(ctx) {
    F.ctx = ctx && typeof ctx === 'object' ? ctx : {};
    if (F.ctx.lang === 'zh' || F.ctx.lang === 'en') F.lang = F.ctx.lang;
    else F.lang = detectLang();
    F.scenarios = null;
    F.scenariosPromise = null;
    bindGlobal();
    ensureOverlay();
    if (F.bodyEl) bindBodyEvents();
    if (F.closeBtn) F.closeBtn.setAttribute('aria-label', s('close'));
    OCFeatures.openDetail = openDetail;
    OCFeatures.open = open;
    OCFeatures.close = close;
    OCFeatures.mount = mount;
    OCFeatures.onScenarios = onScenarios;
    OCFeatures.lang = F.lang;
    return OCFeatures;
  }

  var OCFeatures = {
    version: VERSION,
    mount: mount,
    open: open,
    openDetail: openDetail,
    onScenarios: onScenarios,
    close: close,
    isOpen: isOpen,
    panels: FEATURES.slice(),
    _internals: {
      escapeHtml: escapeHtml,
      trendPairs: trendPairs,
      trendSvg: trendSvg,
      sourceMixHtml: sourceMixHtml,
      costRangeText: costRangeText,
      pocMilestones: pocMilestones,
      normalizeWorkspaceItems: normalizeWorkspaceItems,
      scenarioId: scenarioId,
      money: money,
      metricNum: metricNum,
      setLang: function (lang) { if (lang === 'zh' || lang === 'en') F.lang = lang; },
      setScenarios: function (list) { assignScenarios(list); }
    }
  };

  if (typeof window !== 'undefined') {
    window.OCFeatures = OCFeatures;
    if (typeof document !== 'undefined') bindGlobal();
  }
  if (typeof module !== 'undefined' && module.exports) module.exports = OCFeatures;
})();
