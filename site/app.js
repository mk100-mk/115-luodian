const SUBJ = ["國","英","數A","數B","自","社","數甲","數乙","物","化","生","歷","地","公","術"];
const SUBJ_TAG = {"國":"學測","英":"學測","數A":"學測","數B":"學測","自":"學測","社":"學測","數甲":"分科","數乙":"分科","物":"分科","化":"分科","生":"分科","歷":"分科","地":"分科","公":"分科","術":"百分制"};
const DEFAULT_SCORES = {"國":0,"英":0,"數A":0,"數B":0,"自":0,"社":0,"數甲":0,"數乙":0,"物":0,"化":0,"生":0,"歷":0,"地":0,"公":0,"術":0}; // 通用版：預設空白，請輸入自己的成績
const DEFAULT_G15 = {"國":14,"英":10,"數A":12,"數B":12,"自":0,"社":14}; // 學測15級分（檢定判定用）
const DEFAULT_ETL = 0; // 英聽級數預設（0=未報考 1=F 2=C 3=B 4=A）；通用版預設未報考
const FIVE = {"國":{"頂":13,"前":12,"均":10,"後":9,"底":7},"英":{"頂":13,"前":11,"均":8,"後":5,"底":3},"數A":{"頂":12,"前":10,"均":8,"後":5,"底":4},"數B":{"頂":11,"前":9,"均":5,"後":3,"底":2},"社":{"頂":13,"前":12,"均":10,"後":8,"底":7},"自":{"頂":13,"前":12,"均":9,"後":7,"底":5}}; // 115學測五標（大考中心115.02.25公告）
let DATA = [];
let COMBO = []; // 115年官方組合排名查詢表（tools/parse_accu.py 產生，見 data.json 的 combo 欄位）

function main(){

let scores = {...DEFAULT_SCORES};
function toG15(v){ return v<=0 ? 0 : Math.ceil(v/4); } // 60級分→15級分（無條件進位/4，經實際成績單驗證）
let state = {q:"", school:"", sort:"pct_desc", eligible:true, same114:false, bands:new Set(), shown:80};

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
  return {rank: b[1], total: g.b[0][1], pr: b[2]};
}

function calc(r){
  let tot=0, missing=[];
  for(const [s,w] of Object.entries(r.w)){
    tot += (scores[s]||0)*w;
    if(!scores[s]) missing.push(s);
  }
  tot = Math.round(tot*100)/100;

  let band='na', pct=null, diff=null, source=null, combo=null, refPr=null;

  // 官方組合排名（僅「115年採計科目加權皆1.00且115年官方組合表查得到」的系組才有 r.cx）
  if(typeof r.cx === 'number' && COMBO[r.cx]){
    combo = comboLookup(r.cx, tot);
    // 落點分級優先用官方排名：把該系組114年最低錄取分代入同一張115組合表換算成「等值PR」，
    // 用今年PR與此基準的百分點差距分級——只在114年採計科目與加權跟115完全相同時才成立
    // （確保是同一把尺，raw分數才可直接互換算PR），否則退回114年比較法。
    if(r.a4 && typeof r.m4 === 'number' && sameW(r.w, r.a4)){
      const ref = comboLookup(r.cx, r.m4);
      refPr = ref.pr;
      diff = Math.round((combo.pr - refPr) * 100) / 100; // PR百分點差
      pct = diff / 100;
      band = diff>=8?'hi':diff>=2?'mh':diff>=-2?'ed':diff>=-8?'lo':'vl';
      source = 'combo';
    }
  }
  if(source !== 'combo' && typeof r.m4 === 'number'){
    diff = Math.round((tot - r.m4)*100)/100;
    pct = (tot - r.m4)/r.m4;
    band = pct>=0.10?'hi':pct>=0.03?'mh':pct>=-0.03?'ed':pct>=-0.10?'lo':'vl';
    source = '114';
  }

  const same = r.a4 ? sameW(r.w, r.a4) : null;
  const eReq = r.e || null;                       // 'A' | 'B' | null
  const ePass = !eReq || etl >= (eReq==='A'?4:3); // 未設英聽檢定視為通過
  const qPass = !r.q || r.q.every(cl => cl.some(([s,d]) => toG15(scores[s]||0) >= FIVE[s][d]));
  const seatChange = (r.st!=null && r.st4!=null) ? r.st - r.st4 : null;
  return {tot, diff, pct, band, missing, same, eReq, ePass, qPass, source, combo, refPr, seatChange};
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
  else if(c.dataset.f==='same114'){state.same114=!state.same114; c.classList.toggle('on');}
  else if(c.dataset.b){
    const b=c.dataset.b;
    state.bands.has(b)?state.bands.delete(b):state.bands.add(b);
    c.classList.toggle('on');
  }
  state.shown=80; render();
};
document.getElementById('moreBtn').onclick = ()=>{state.shown+=120; render(true);};

let cache=[];
function render(keepScroll){
  cache = DATA.map(r=>({r, c:calc(r)}));
  const bandCount={hi:0,mh:0,ed:0,lo:0,vl:0,na:0};
  let rows = cache.filter(({r,c})=>{
    if(state.school && r.s!==state.school) return false;
    if(state.q && !(r.d.includes(state.q)||r.s.includes(state.q))) return false;
    if(state.eligible && (c.missing.length || !c.ePass || !c.qPass)) return false;
    if(state.same114 && c.same!==true) return false;
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
    m4_desc:(a,b)=>(b.r.m4??-1)-(a.r.m4??-1),
    code:(a,b)=>a.r.c.localeCompare(b.r.c)
  };
  rows.sort(S[state.sort]);
  const noInput = SUBJ.every(s=>!scores[s]);
  document.getElementById('stats').innerHTML = noInput
    ? '<span style="color:var(--red);font-weight:700">尚未輸入成績 — 請先在上方「成績輸入卡」填入各科60級分制成績（未報考科目保留0），系統將即時計算全部系組落點。</span>'
    : `符合條件 <b>${rows.length}</b> 系組｜高 <b>${bandCount.hi}</b>・中高 <b>${bandCount.mh}</b>・邊緣 <b>${bandCount.ed}</b>・偏低 <b>${bandCount.lo}</b>・低 <b>${bandCount.vl}</b>`;
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
    const numLabel2 = isCombo ? '官方PR' : '114最低分';
    const numVal2 = isCombo ? (c.combo.pr.toFixed(1)+'%') : (r.m4==null?'—':r.m4.toFixed(2));
    const numLabel3 = isCombo ? 'PR差(百分點)' : '差異';
    const numVal3 = isCombo ? diffTxt+'pp' : diffTxt;

    const sameBadge = c.same===false?'<span class="badge-diff">114採計不同</span>':'';
    const qBadge = (r.q && !c.qPass) ? '<span class="badge-diff">學測檢定未達</span>' : '';
    const etlBadge = c.eReq ? (c.ePass
      ? `<span class="badge-diff" style="color:var(--green);border-color:var(--green)">英聽${c.eReq}級檢定</span>`
      : `<span class="badge-diff">英聽${c.eReq}級未達</span>`) : '';
    const srcBadge = isCombo ? '<span class="badge-src">官方排名佐證</span>' : '';
    let seatBadge = '';
    if(r.st!=null){
      if(c.seatChange==null) seatBadge = `<span class="badge-seat new">115名額${r.st}（新設／較114無對照）</span>`;
      else if(c.seatChange===0) seatBadge = `<span class="badge-seat">115名額${r.st}（與114同）</span>`;
      else seatBadge = `<span class="badge-seat ${c.seatChange>0?'up':'down'}">115名額${r.st}（${c.seatChange>0?'+':''}${c.seatChange} 較114）</span>`;
    }

    let more = `<table>`;
    if(r.k) more += `<tr><td>檢定標準</td><td>${r.k}</td></tr>`;
    more += `<tr><td>同分參酌</td><td>${r.o.join('→')}</td></tr>`;
    if(c.combo){
      more += `<tr><td>115組合排名</td><td>全國第 <b class="yl">${c.combo.rank}</b> / ${c.combo.total} 名（PR ${c.combo.pr.toFixed(2)}）${isCombo?'　<span class="yl">（作為分級依據）</span>':'　<span class="yl">（僅供參考，114採計不同無法作為分級依據）</span>'}</td></tr>`;
    }
    for(const [tag,yl] of [['4','114'],['3','113'],['2','112']]){
      const m=r['m'+tag], a=r['a'+tag];
      if(a===undefined){ more += `<tr><td>${yl}年</td><td>無同名系組（新設／更名／分組）</td></tr>`; continue; }
      const d = sameW(r.w,a)?'':`<span class="badge-diff">與115採計不同</span> <span class="yl">${wtxt(a)}</span>`;
      more += `<tr><td>${yl}年</td><td>最低 <b class="yl">${m==null?'無錄取':m.toFixed(2)}</b> ${d}</td></tr>`;
    }
    more += `</table>`;
    if(c.missing.length) more += `<div style="color:var(--red)">未報考採計科目：${c.missing.join('、')}（此系組不予分發）</div>`;
    if(c.eReq && !c.ePass) more += `<div style="color:var(--red)">英聽檢定要求 ${c.eReq} 級，目前級數未達（此系組不予分發）</div>`;
    if(r.q && !c.qPass) more += `<div style="color:var(--red)">學測檢定未達：${r.k}（此系組不予分發）</div>`;
    return `<div class="rc" data-c="${r.c}">
      <div class="rc-top">
        <div class="rc-main">
          <div class="rc-sch">${r.s}｜${r.c}</div>
          <div class="rc-dep">${r.d}${sameBadge}${qBadge}${etlBadge}</div>
          <div class="rc-adopt">${adopt}</div>
          <div class="rc-meta">${srcBadge}${seatBadge}</div>
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
    const rc = e.target.closest('.rc'); if(rc) rc.classList.toggle('open');
  };
}
render();
}

fetch('data/data.json')
  .then(r => { if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
  .then(d => { DATA = d.rows; COMBO = d.combo; main(); })
  .catch(err => {
    const el = document.getElementById('rlist') || document.body;
    el.innerHTML = '<div style="padding:24px;text-align:center;color:#a33">資料載入失敗（' + err.message + '），請重新整理頁面。</div>';
  });
