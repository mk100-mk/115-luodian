/* 116學年度分科分發 落點試算 — 前端邏輯
 *
 * 相較 115 版的變更：
 *  1. 比較基準年由 114 改為 115（115 已放榜，成為最近一屆完整正式資料）
 *  2. 新增「同分參酌風險提示」：採計總分與該系最低分差距 ±2 分內時，顯示參酌順序與逐科比對
 *  3. 新增「回流名額」與「申請/分發占比」資訊欄
 *  4. 三年歷史（115/114/113）改為卡片內可獨立展開的區塊，並顯示全國排名趨勢
 *
 * 資料由 data/data.json 載入（tools/make_data.py 產生）。成績僅在裝置端計算，不上傳。
 */
const SUBJ = ["國","英","數A","數B","自","社","數甲","數乙","物","化","生","歷","地","公","術"];
const SUBJ_TAG = {"國":"學測","英":"學測","數A":"學測","數B":"學測","自":"學測","社":"學測","數甲":"分科","數乙":"分科","物":"分科","化":"分科","生":"分科","歷":"分科","地":"分科","公":"分科","術":"百分制"};
const SUBJ_NAME = {"國":"國文","英":"英文","數A":"數學A","數B":"數學B","自":"自然","社":"社會","數甲":"數學甲","數乙":"數學乙","物":"物理","化":"化學","生":"生物","歷":"歷史","地":"地理","公":"公民與社會","術":"術科"};
const DEFAULT_SCORES = {"國":0,"英":0,"數A":0,"數B":0,"自":0,"社":0,"數甲":0,"數乙":0,"物":0,"化":0,"生":0,"歷":0,"地":0,"公":0,"術":0}; // 通用版：預設空白，請輸入自己的成績
const DEFAULT_G15 = {"國":14,"英":10,"數A":12,"數B":12,"自":0,"社":14}; // 學測15級分（檢定判定用）
const DEFAULT_ETL = 0; // 英聽級數預設（0=未報考 1=F 2=C 3=B 4=A）；通用版預設未報考
const FIVE = {"國":{"頂":13,"前":12,"均":10,"後":9,"底":7},"英":{"頂":13,"前":11,"均":8,"後":5,"底":3},"數A":{"頂":12,"前":10,"均":8,"後":5,"底":4},"數B":{"頂":11,"前":9,"均":5,"後":3,"底":2},"社":{"頂":13,"前":12,"均":10,"後":8,"底":7},"自":{"頂":13,"前":12,"均":9,"後":7,"底":5}}; // 暫用115學測五標；116學測五標公告後須更新
const TIE_WINDOW = 2; // 同分參酌警示窗：與最低分差距在 ±2 分內即提示（見 CLAUDE.md 鐵則）
let DATA = [];
let COMBO = []; // 115年官方組合排名查詢表（tools/parse_accu.py 產生，見 data.json 的 combo 欄位）
let META = {};

function main(){

let scores = {...DEFAULT_SCORES};
function toG15(v){ return v<=0 ? 0 : Math.ceil(v/4); } // 60級分→15級分（無條件進位/4，經實際成績單驗證）
let state = {q:"", school:"", sort:"pct_desc", eligible:true, same115:false, tieOnly:false, bands:new Set(), shown:80};

const grid = document.getElementById('scGrid');
SUBJ.forEach(s=>{
  const cell = document.createElement('div');
  cell.className = 'sc-cell' + (scores[s]?'':' zero');
  const g15in = (s in DEFAULT_G15)
    ? `<div style="display:flex;align-items:center;gap:4px;border-top:1px dotted var(--line);margin-top:3px;padding-top:2px">
         <span class="tag">級分(自動)</span>
         <span data-g15="${s}" style="font:600 13px var(--mono);color:var(--green)">${toG15(scores[s])}</span>
       </div>` : '';
  cell.innerHTML = `<label>${s} <span class="tag">${SUBJ_TAG[s]}</span></label>
    <input inputmode="numeric" pattern="[0-9]*" value="${scores[s]}" data-s="${s}" aria-label="${s}成績">${g15in}`;
  grid.appendChild(cell);
});
// 英聽級數選擇
const eCell = document.createElement('div');
eCell.className = 'sc-cell';
eCell.innerHTML = `<label>英聽 <span class="tag">聽力測驗</span></label>
  <select id="etl" aria-label="英聽級數" style="width:100%;border:none;background:transparent;font:600 16px var(--sans);color:var(--ink);outline:none;padding:4px 0">
    <option value="0"${DEFAULT_ETL===0?' selected':''}>未報考</option><option value="1"${DEFAULT_ETL===1?' selected':''}>F級</option><option value="2"${DEFAULT_ETL===2?' selected':''}>C級</option><option value="3"${DEFAULT_ETL===3?' selected':''}>B級</option><option value="4"${DEFAULT_ETL===4?' selected':''}>A級</option>
  </select>`;
grid.appendChild(eCell);
let etl = DEFAULT_ETL;
eCell.querySelector('#etl').addEventListener('change', e=>{
  etl = parseInt(e.target.value); state.shown=80; render();
});
grid.addEventListener('input', e=>{
  const s = e.target.dataset.s; if(!s) return;
  let v = parseFloat(e.target.value); if(isNaN(v)||v<0) v=0;
  const max = s==='術'?100:60; if(v>max) v=max;
  scores[s]=v;
  e.target.closest('.sc-cell').classList.toggle('zero', v===0);
  const g = e.target.closest('.sc-cell').querySelector('[data-g15]');
  if(g) g.textContent = toG15(v);
  state.shown=80; render();
});
document.getElementById('scToggle').onclick = function(){
  const b = document.getElementById('scBody');
  const open = b.style.display !== 'none';
  b.style.display = open ? 'none' : '';
  this.textContent = open ? '展開' : '收合';
  this.setAttribute('aria-expanded', String(!open));
};

// 在組合表 bands（依 upper 由低到高排序的 [上限分數,累計人數(從高到低),累計百分比PR] 陣列）中，
// 找出「上一區間上限 < 分數 <= 本區間上限」的那一格；僅最低區間為 [0,上限] 全含。
function findComboBand(bands, score){
  for(const b of bands){ if(score <= b[0]) return b; }
  return bands[bands.length-1];
}
// 用同一張115年組合表查任一分數的全國名次/總人數/PR
function comboLookup(cx, score){
  const g = COMBO[cx]; if(!g || !g.b.length) return null;
  const b = findComboBand(g.b, score);
  return {rank: b[1], total: g.t, pr: b[2]};
}

function calc(r){
  let tot=0, missing=[];
  for(const [s,w] of Object.entries(r.w)){
    tot += (scores[s]||0)*w;
    if(!scores[s]) missing.push(s);
  }
  tot = Math.round(tot*100)/100;

  let band='na', pct=null, diff=null, source=null, combo=null;

  // ① 官方組合排名法（優先）：僅限 115 採計加權皆1.00 且官方有對照組別者
  if(typeof r.cx === 'number' && COMBO[r.cx]){
    combo = comboLookup(r.cx, tot);
    // 分級依據：把該系 115 最低錄取分的 PR（建置期已預算為 r.pr5）與使用者今年的 PR 相比。
    // 僅在「115年採計科目與加權跟本年度簡章完全相同」時成立——否則不是同一把尺。
    if(r.a5 && typeof r.m5 === 'number' && typeof r.pr5 === 'number' && sameW(r.w, r.a5)){
      diff = Math.round((combo.pr - r.pr5) * 100) / 100; // PR百分點差
      pct = diff / 100;
      band = diff>=8?'hi':diff>=2?'mh':diff>=-2?'ed':diff>=-8?'lo':'vl';
      source = 'combo';
    }
  }
  // ② 歷年比較法（其餘系組）：與 115 最低錄取分直接比較
  if(source !== 'combo' && typeof r.m5 === 'number'){
    diff = Math.round((tot - r.m5)*100)/100;
    pct = (tot - r.m5)/r.m5;
    band = pct>=0.10?'hi':pct>=0.03?'mh':pct>=-0.03?'ed':pct>=-0.10?'lo':'vl';
    source = '115';
  }

  // ③ 同分參酌風險：採計總分與 115 最低分差距在 ±2 分內
  //    CLAUDE.md 鐵則：總分打平最低分時，系統以第一層參酌科目做最後篩選，總分達標不等於錄取。
  //    115學年度台大歷史(262=262)、台大社會(251=251)皆因此壓線落空，屬已驗證之真實案例。
  let tieRisk = null;
  if(typeof r.m5 === 'number' && Math.abs(tot - r.m5) <= TIE_WINDOW && !missing.length){
    tieRisk = {
      gap: Math.round((tot - r.m5)*100)/100,
      levels: (r.tb5 || []).map(([s,min,stage])=>{
        const mine = scores[s];
        // 只有「級分」階段能與使用者輸入的60級分制成績直接比對；「實得分數」階段無從比對
        const cmp = stage==='級分' ? (mine>=min ? 'ok' : 'ng') : 'na';
        return {s, min, stage, mine, cmp};
      }),
      hadTie: !!(r.tb5 && r.tb5.length),
      always: !!r.tbA
    };
  }

  const same = r.a5 ? sameW(r.w, r.a5) : null;
  const eReq = r.e || null;                       // 'A' | 'B' | null
  const ePass = !eReq || etl >= (eReq==='A'?4:3); // 未設英聽檢定視為通過
  const qPass = !r.q || r.q.every(cl => cl.some(([s,d]) => toG15(scores[s]||0) >= FIVE[s][d]));
  const seatChange = (r.st!=null && r.st4!=null) ? r.st - r.st4 : null;
  return {tot, diff, pct, band, missing, same, eReq, ePass, qPass, source, combo, seatChange, tieRisk};
}
function sameW(a,b){
  const ka=Object.keys(a), kb=Object.keys(b);
  if(ka.length!==kb.length) return false;
  return ka.every(k=> b[k]===a[k]);
}
function wtxt(w){ return SUBJ.filter(s=>s in w).map(s=>`${s}×${w[s].toFixed(2)}`).join(' '); }
const BAND_LABEL={hi:'高',mh:'中高',ed:'邊緣',lo:'偏低',vl:'低',na:'無比較資料'};

const selSchool = document.getElementById('fSchool');
[...new Set(DATA.map(r=>r.s))].forEach(s=>{
  const o=document.createElement('option'); o.value=s; o.textContent=s; selSchool.appendChild(o);
});
selSchool.onchange = e=>{state.school=e.target.value; state.shown=80; render();};
document.getElementById('q').oninput = e=>{state.q=e.target.value.trim(); state.shown=80; render();};
document.getElementById('fSort').onchange = e=>{state.sort=e.target.value; render();};
document.getElementById('chips').onclick = e=>{
  const c = e.target.closest('.chip'); if(!c) return;
  if(c.dataset.f==='eligible'){state.eligible=!state.eligible; c.classList.toggle('on');}
  else if(c.dataset.f==='same115'){state.same115=!state.same115; c.classList.toggle('on');}
  else if(c.dataset.f==='tie'){state.tieOnly=!state.tieOnly; c.classList.toggle('on');}
  else if(c.dataset.b){
    const b=c.dataset.b;
    state.bands.has(b)?state.bands.delete(b):state.bands.add(b);
    c.classList.toggle('on');
  }
  state.shown=80; render();
};
document.getElementById('moreBtn').onclick = ()=>{state.shown+=120; render(true);};

// 三年歷史區塊（115/114/113）：最低分、錄取人數、全國排名、同分參酌、採計差異
function historyBlock(r){
  let rowsHtml = '';
  let rankTrend = [];
  for(const [tag,yl] of [['5','115'],['4','114'],['3','113']]){
    const m=r['m'+tag], a=r['a'+tag], n=r['n'+tag], rk=r['rk'+tag], pr=r['pr'+tag], tb=r['tb'+tag];
    if(a===undefined){
      rowsHtml += `<tr><td class="yy">${yl}</td><td colspan="4">無同名系組（新設／更名／分組調整）</td></tr>`;
      continue;
    }
    if(typeof rk === 'number') rankTrend.push({yl, rk});
    const diffW = sameW(r.w,a) ? '' : `<span class="badge-diff">採計不同</span><span class="yl"> ${wtxt(a)}</span>`;
    const rkTxt = (typeof rk==='number') ? `第 <b class="yl">${rk}</b> 名<span class="sub2"> PR ${pr}</span>` : '<span class="sub2">無官方組合對照</span>';
    const tbTxt = tb && tb.length
      ? tb.map(([s,min,stage])=>`${SUBJ_NAME[s]||s}≥${min}${stage==='實得'?'<span class="sub2">(實得)</span>':''}`).join(' → ')
      : '<span class="sub2">未啟動</span>';
    rowsHtml += `<tr><td class="yy">${yl}</td>
      <td><b class="yl">${m==null?'無錄取':m.toFixed(2)}</b>${diffW}</td>
      <td>${n==null?'—':n+' 人'}</td>
      <td>${rkTxt}</td>
      <td>${tbTxt}</td></tr>`;
  }
  let trendNote = '';
  if(rankTrend.length>=2){
    const first = rankTrend[rankTrend.length-1], last = rankTrend[0];
    const move = first.rk - last.rk; // 正 = 名次前進（變難）
    trendNote = `<div class="trend">排名趨勢：${first.yl}年第 ${first.rk} 名 → ${last.yl}年第 ${last.rk} 名，`
      + (move>0 ? `門檻名次前進 <b class="up">${move}</b> 名（競爭轉趨激烈）`
         : move<0 ? `門檻名次後退 <b class="down">${-move}</b> 名（競爭略為緩和）`
         : `門檻名次持平`)
      + `。<span class="sub2">排名比分數穩定，優先參考此欄。</span></div>`;
  }
  return `<details class="hist"><summary>三年歷史（115 / 114 / 113）</summary>
    <table class="histtb">
      <tr class="hh"><td>年度</td><td>最低錄取分</td><td>錄取人數</td><td>全國組合排名</td><td>同分參酌門檻</td></tr>
      ${rowsHtml}
    </table>${trendNote}</details>`;
}

// 同分參酌風險提示區塊
function tieBlock(c, r){
  const t = c.tieRisk; if(!t) return '';
  const gapTxt = t.gap===0 ? '與 115 年最低錄取分<b>完全打平</b>'
    : (t.gap>0 ? `僅高出 115 年最低錄取分 <b>${t.gap.toFixed(2)}</b> 分` : `低於 115 年最低錄取分 <b>${(-t.gap).toFixed(2)}</b> 分`);
  let body = `<div class="tie-line">您的採計總分${gapTxt}。分發採「同分參酌」機制：總分打平時由參酌科目決定勝負，<b>總分達標不等於錄取</b>。</div>`;
  if(t.hadTie){
    const lv = t.levels.map((l,i)=>{
      const name = SUBJ_NAME[l.s]||l.s;
      if(l.cmp==='na') return `<li><span class="lvn">${i+1}</span> ${name} ≥ ${l.min}<span class="sub2">（實得分數階段，無法以級分比對）</span></li>`;
      const mark = l.cmp==='ok' ? `<span class="ok">您 ${l.mine}，達標</span>` : `<span class="ng">您 ${l.mine}，未達</span>`;
      return `<li><span class="lvn">${i+1}</span> ${name} ≥ ${l.min} 級分　${mark}</li>`;
    }).join('');
    body += `<div class="tie-line">此系 115 年曾啟動同分參酌，實際參酌順序與門檻：</div><ol class="tie-lv">${lv}</ol>`;
    if(t.always) body += `<div class="tie-line warn2">⚑ 此系 <b>113/114/115 三年皆啟動</b>同分參酌，屬壓線高風險系組。</div>`;
  } else {
    body += `<div class="tie-line">此系 115 年最低錄取分無同分情形，官方未公布參酌門檻——<b>但這不代表 116 年不會啟動</b>。壓線志願仍應保留安全邊際。</div>`;
  }
  return `<div class="tiebox"><div class="tie-h">⚠ 同分參酌風險</div>${body}</div>`;
}

// 名額結構區塊（回流名額與申請/分發占比）
function quotaRows(r){
  let html = '';
  if(r.st!=null){
    if(r.sa!=null){
      const sign = r.rf>0?'+':'';
      html += `<tr><td>115分發名額</td><td>核定 <b class="yl">${r.sa}</b> → 回流後 <b class="yl">${r.st}</b>`
        + ` <span class="${r.rf>0?'pos':(r.rf<0?'neg':'')}">（回流 ${sign}${r.rf}，${sign}${r.rp}%）</span>`
        + `<div class="sub2">分發名額＝核定名額＋申請入學缺額回流，回流比例因校因系差異極大</div></td></tr>`;
    } else {
      html += `<tr><td>115分發名額</td><td><b class="yl">${r.st}</b><span class="sub2">（無核定名額對照，回流量不明）</span></td></tr>`;
    }
  }
  if(r.ap!=null && r.dp!=null){
    html += `<tr><td>入學管道占比</td><td>申請入學 <b class="yl">${r.ap}%</b>｜考試分發 <b class="yl">${r.dp}%</b>`
      + (r.y5t!=null?`<span class="sub2">（115核定招生總量 ${r.y5t} 名${r.y4t!=null?`，114為 ${r.y4t} 名`:''}）</span>`:'')
      + `</td></tr>`;
  }
  return html;
}

let cache=[];
function render(keepScroll){
  cache = DATA.map(r=>({r, c:calc(r)}));
  const bandCount={hi:0,mh:0,ed:0,lo:0,vl:0,na:0};
  let rows = cache.filter(({r,c})=>{
    if(state.school && r.s!==state.school) return false;
    if(state.q && !(r.d.includes(state.q)||r.s.includes(state.q))) return false;
    if(state.eligible && (c.missing.length || !c.ePass || !c.qPass)) return false;
    if(state.same115 && c.same!==true) return false;
    if(state.tieOnly && !c.tieRisk) return false;
    return true;
  });
  rows.forEach(({c})=>bandCount[c.band]++);
  document.querySelectorAll('.chip.band').forEach(ch=>{
    ch.querySelector('.n').textContent = bandCount[ch.dataset.b];
  });
  if(state.bands.size) rows = rows.filter(({c})=>state.bands.has(c.band));
  const S={
    pct_desc:(a,b)=>(b.c.pct??-9)-(a.c.pct??-9),
    pct_asc:(a,b)=>(a.c.pct??9)-(b.c.pct??9),
    tot_desc:(a,b)=>b.c.tot-a.c.tot,
    m5_desc:(a,b)=>(b.r.m5??-1)-(a.r.m5??-1),
    rk5_asc:(a,b)=>(a.r.rk5??9e9)-(b.r.rk5??9e9),
    rp_desc:(a,b)=>(b.r.rp??-9e9)-(a.r.rp??-9e9),
    code:(a,b)=>a.r.c.localeCompare(b.r.c)
  };
  rows.sort(S[state.sort]);
  const noInput = SUBJ.every(s=>!scores[s]);
  const tieN = rows.filter(({c})=>c.tieRisk).length;
  document.getElementById('stats').innerHTML = noInput
    ? '<span style="color:var(--red);font-weight:700">尚未輸入成績 — 請先在上方「成績輸入卡」填入各科60級分制成績（未報考科目保留0），系統將即時計算全部系組落點。</span>'
    : `符合條件 <b>${rows.length}</b> 系組｜高 <b>${bandCount.hi}</b>・中高 <b>${bandCount.mh}</b>・邊緣 <b>${bandCount.ed}</b>・偏低 <b>${bandCount.lo}</b>・低 <b>${bandCount.vl}</b>`
      + (tieN?`　<span style="color:var(--amber);font-weight:700">⚠ ${tieN} 個系組落在同分參酌警示範圍（±${TIE_WINDOW}分）</span>`:'');
  const list = document.getElementById('rlist');
  const view = rows.slice(0, state.shown);
  list.innerHTML = view.map(({r,c})=>{
    const adopt = SUBJ.filter(s=>s in r.w).map(s=>{
      const miss = !scores[s] ? ' class="miss"' : '';
      return `<span${miss}>${s}×${r.w[s].toFixed(2)}</span>`;
    }).join(' ');
    const isCombo = c.source==='combo';
    const pctTxt = c.pct==null?'—':isCombo
      ? (c.diff>0?'+':'')+c.diff.toFixed(1)+'pp'
      : (c.pct>0?'+':'')+(c.pct*100).toFixed(1)+'%';
    const diffTxt = c.diff==null?'—':(c.diff>0?'+':'')+c.diff.toFixed(2);
    const cls = c.diff==null?'':(c.diff>=0?'pos':'neg');
    const numLabel2 = isCombo ? '115最低分PR' : '115最低分';
    const numVal2 = isCombo ? (r.pr5.toFixed(1)+'%') : (r.m5==null?'—':r.m5.toFixed(2));
    const numLabel3 = isCombo ? 'PR差(百分點)' : '差異';
    const numVal3 = isCombo ? diffTxt+'pp' : diffTxt;

    const sameBadge = c.same===false?'<span class="badge-diff">115採計不同</span>':'';
    const qBadge = (r.q && !c.qPass) ? '<span class="badge-diff">學測檢定未達</span>' : '';
    const etlBadge = c.eReq ? (c.ePass
      ? `<span class="badge-diff" style="color:var(--green);border-color:var(--green)">英聽${c.eReq}級檢定</span>`
      : `<span class="badge-diff">英聽${c.eReq}級未達</span>`) : '';
    const srcBadge = isCombo ? '<span class="badge-src">官方排名佐證</span>' : '';
    const tieBadge = c.tieRisk ? '<span class="badge-tie">同分參酌風險</span>' : '';
    const alwaysBadge = r.tbA ? '<span class="badge-tie always">三年皆壓線</span>' : '';
    let seatBadge = '';
    if(r.st!=null){
      if(r.rf!=null) seatBadge = `<span class="badge-seat ${r.rf>0?'up':(r.rf<0?'down':'')}">分發名額 ${r.st}（核定${r.sa}${r.rf>0?' +':' '}${r.rf}）</span>`;
      else seatBadge = `<span class="badge-seat">115名額 ${r.st}</span>`;
    }

    let more = tieBlock(c, r) + `<table>`;
    if(r.k) more += `<tr><td>檢定標準</td><td>${r.k}</td></tr>`;
    more += `<tr><td>採計順序</td><td>${r.o.join(' → ')}</td></tr>`;
    if(c.combo){
      more += `<tr><td>您的全國排名</td><td>同組合（${COMBO[r.cx].su.join('/')}）第 <b class="yl">${c.combo.rank}</b> / ${c.combo.total} 名（PR ${c.combo.pr.toFixed(2)}）`
        + (isCombo?'　<span class="yl">（作為分級依據）</span>':'　<span class="yl">（僅供參考，115採計不同無法作為分級依據）</span>') + `</td></tr>`;
    }
    more += quotaRows(r);
    more += `</table>`;
    more += historyBlock(r);
    if(c.missing.length) more += `<div style="color:var(--red)">未報考採計科目：${c.missing.join('、')}（此系組不予分發）</div>`;
    if(c.eReq && !c.ePass) more += `<div style="color:var(--red)">英聽檢定要求 ${c.eReq} 級，目前級數未達（此系組不予分發）</div>`;
    if(r.q && !c.qPass) more += `<div style="color:var(--red)">學測檢定未達：${r.k}（此系組不予分發）</div>`;
    return `<div class="rc${c.tieRisk?' tie':''}" data-c="${r.c}">
      <div class="rc-top">
        <div class="rc-main">
          <div class="rc-sch">${r.s}｜${r.c}</div>
          <div class="rc-dep">${r.d}${sameBadge}${qBadge}${etlBadge}</div>
          <div class="rc-adopt">${adopt}</div>
          <div class="rc-meta">${srcBadge}${tieBadge}${alwaysBadge}${seatBadge}</div>
          <div class="rc-nums">
            <div class="num"><div class="l">採計總分</div><div class="v">${c.tot.toFixed(2)}</div></div>
            <div class="num"><div class="l">${numLabel2}</div><div class="v">${numVal2}</div></div>
            <div class="num"><div class="l">${numLabel3}</div><div class="v ${cls}">${numVal3}</div></div>
          </div>
        </div>
        <div class="stamp">
          <span class="seal ${c.band}">${BAND_LABEL[c.band]}</span>
          <div class="pct ${cls}">${pctTxt}</div>
        </div>
      </div>
      <div class="rc-more">${more}</div>
    </div>`;
  }).join('');
  document.getElementById('moreBtn').hidden = rows.length <= state.shown;
  list.onclick = e=>{
    // 三年歷史 <details> 自行展開，不應連帶收合整張卡片
    if(e.target.closest('details')) return;
    const rc = e.target.closest('.rc'); if(rc) rc.classList.toggle('open');
  };
}
render();
}

fetch('data/data.json')
  .then(r => { if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
  .then(d => { DATA = d.rows; COMBO = d.combo; META = d.meta || {}; main(); })
  .catch(err => {
    const el = document.getElementById('rlist') || document.body;
    el.innerHTML = '<div style="padding:24px;text-align:center;color:#a33">資料載入失敗（' + err.message + '），請重新整理頁面。</div>';
  });
