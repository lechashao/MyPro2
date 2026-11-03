import React, {useEffect, useRef, useState} from 'react';
import {createRoot} from 'react-dom/client';

const PAGES = {world:'世界概览',memories:'记忆档案',compare:'平行人生',history:'实验记录'};
const ICONS = {world:'◉',memories:'▤',compare:'⑂',history:'◷'};
const POLICIES = {adaptive:'鲍勃自主决策',balanced:'寻找平衡',career:'事业优先',recovery:'留出余裕'};
const TYPES = {reported_fact:'自述记录',preference:'偏好',goal:'目标',hypothesis:'推测'};
const sourceName = s => s === 'health_assistant' ? '健康助手' : '工作助手';
const localDate = v => new Intl.DateTimeFormat('zh-CN',{dateStyle:'medium',timeZone:'Europe/Istanbul'}).format(new Date(v));
const EXAMPLE = {memories:[{source:'health_assistant',type:'goal',content:'希望每周安排三次散步。',observed_at:'2026-11-03T09:00:00+03:00',confidence:1},{source:'work_assistant',type:'reported_fact',content:'正在负责一个新项目。',observed_at:'2026-11-03T09:00:00+03:00',confidence:1}]};

async function api(path,method='GET',body) {
  const response = await fetch(`/api${path}`,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
  if(!response.ok){const error=await response.json().catch(()=>({}));throw new Error(typeof error.detail === 'string'?error.detail:'输入格式有误，请检查必填字段、日期和数值范围。');}
  return response.json();
}
function Button({children,onClick,variant='secondary',full=false,...props}) {
  return <button className={`button ${variant} ${full?'full':''}`} onClick={onClick} {...props}>{children}</button>;
}
function Tag({children,amber=false}) {return <span className={`tag ${amber?'amber':''}`}>{children}</span>;}
function Empty({title,children}) {return <div className="empty-state"><h3>{title}</h3><p>{children}</p></div>;}
function BranchSelect({world,id,onChange}) {
  return <select value={id||''} onChange={e=>onChange(e.target.value)} aria-label="切换人生分支">{world.branches.map(b=><option key={b.id} value={b.id}>{b.name} · 第 {b.state.day} 天</option>)}</select>;
}

function App() {
  const [world,setWorld]=useState(null),[activeId,setActiveId]=useState(null),[page,setPage]=useState('world');
  const [busy,setBusy]=useState(false),[notice,setNotice]=useState(null),[modal,setModal]=useState(null),[failed,setFailed]=useState(false);
  const lock=useRef(false), timer=useRef();
  const branch=world?.branches.find(b=>b.id===activeId);
  function notify(message,error=false){setNotice({message,error});clearTimeout(timer.current);timer.current=setTimeout(()=>setNotice(null),5000);}
  async function refresh(){const w=await api('/world');setWorld(w);setActiveId(id=>w.branches.some(b=>b.id===id)?id:w.branches[0]?.id);}
  useEffect(()=>{refresh().catch(e=>{setFailed(true);notify(e.message,true);});return()=>clearTimeout(timer.current);},[]);
  async function task(fn,onError){
    if(lock.current)return;
    lock.current=true;setBusy(true);
    try{await fn();}catch(e){notify(e.message,true);onError?.(e);}finally{
      try{await refresh();}catch(e){notify(`无法刷新：${e.message}`,true);}
      lock.current=false;setBusy(false);
    }
  }
  const select=id=>{setActiveId(id);setPage('world');};
  const open=(kind,data={})=>setModal({kind,...data});
  async function start(){await task(async()=>{const b=await api('/branches','POST',{policy:'balanced',seed:42,use_demo:true});setActiveId(b.id);notify('第一段人生已开启，试着作出今天的选择。');});}
  async function autopilot(){await task(async()=>{
    const b=await api('/simulations/auto','POST',{});select(b.id);
    notify(`鲍勃已自主完成七天选择。${b.snapshot.memory_mode==='demo'?'本次使用虚构示例记忆。':'本次使用已导入记忆。'}`);
  });}
  async function advance(days,action){if(!branch)return;await task(async()=>{
    await api(`/branches/${branch.id}/advance`,'POST',{expected_day:branch.state.day,days,...(action?{action}:{})});
    notify(days>1?'七天模拟已完成。':'新的一天，已写入生活的轨迹。');
  });}
  async function experiment(){await task(async()=>{
    const base=branch||await api('/branches','POST',{policy:'balanced',seed:42,use_demo:true});
    for(const policy of ['balanced','career','recovery']){
      const child=await api(`/branches/${base.id}/fork`,'POST',{day:0,policy,name:POLICIES[policy]});
      await api(`/branches/${child.id}/advance`,'POST',{days:7,expected_day:0});
      if(policy==='balanced')setActiveId(child.id);
    }
    setPage('compare');notify('三条路径已完成，使用相同快照与外部事件。');
  });}
  async function exportBranch(id){await task(async()=>{
    const data=await api(`/branches/${id}/export`);
    const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download='bob-branch.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });}
  if(!world)return <div className="loading">{failed?<><h1>暂时无法打开世界</h1><p>请确认服务正在运行，然后刷新页面重试。</p><Button onClick={()=>location.reload()}>重新连接</Button></>:'正在打开鲍勃的世界…'}</div>;
  return <>
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="鲍勃的世界首页"><span className="brand-mark">b<span>·</span></span><span>鲍勃的世界<small>BOB'S WORLD</small></span></a>
      <div className="workspace-label">个人世界 <span>⌄</span></div>
      <nav aria-label="主导航">{Object.entries(PAGES).map(([id,name])=><button key={id} onClick={()=>setPage(id)} className={`nav-item ${page===id?'active':''}`} aria-current={page===id?'page':undefined}><span>{ICONS[id]}</span>{name}{id==='memories'&&<small>{world.memories.length}</small>}</button>)}</nav>
      <div className="sidebar-note"><span className="orbit">✳</span><h3>人生，拥有不止一种可能</h3><p>在这里，为选择留一个<br/>可以重新开始的地方。</p></div>
      <div className="sidebar-bottom"><span className="avatar small">B</span><div>鲍勃的实验室<small>本地私有 · 规则引擎 v{world.engine_version}</small></div></div>
    </aside>
    <div className="shell"><header className="topbar"><span>人生实验室 <span className="crumb">/</span>{PAGES[page]}</span><div className="top-right"><span className="status-dot"/>本地模拟模式<span className="avatar tiny">B</span></div></header>
      <main><div className="page-heading"><div><div className="eyebrow">A LITTLE WORLD, ENDLESS POSSIBILITIES</div><h1>{page==='world'?'你好，鲍勃。':PAGES[page]}</h1><p>{{world:'把生活放慢一点，看看不同选择会通向哪里。',memories:'让经历成为背景，让记忆拥有清晰的来源。',compare:'从同一个起点出发，看见不同的人生路径。',history:'每一次尝试，都值得被记住。'}[page]}</p></div><div className="heading-actions"><Button variant="primary" disabled={busy} onClick={autopilot}>{busy?'正在推演…':'✧ 全自动模拟七天'}</Button><Button disabled={busy} onClick={()=>open('new')}>＋ 开启新分支</Button></div></div>
      {page==='world'&&<div className="world-layout"><section className="main-column">
        <section className="hero"><div className="hero-copy"><span className="pill">✧ 鲍勃的开放世界</span><h2>每一个选择，<br/>都有另一种可能。</h2><p>在健康与工作之间，探索属于自己的节奏。<br/>你来决定方向，让鲍勃走走看。</p><Button variant="dark" disabled={busy} onClick={branch?()=>setPage('compare'):start}>{branch?'比较不同人生 ↗':'开始第一次探索 ↗'}</Button></div><img className="scene" src="/assets/scene.svg" alt="鲍勃坐在窗边，望向城市和远山"/></section>
        <div className="autopilot-note"><strong>全自动模式</strong><span>自动新建七天路径，结合项目进度、精力与作息目标逐日决策。{world.memories.length?'优先使用已导入记忆作为背景。':'尚无真实记忆，将使用虚构示例。'}</span></div>
        {branch?<BranchPanel b={branch} world={world} busy={busy} onSelect={setActiveId} advance={advance} open={open}/>:<section className="card empty-start"><span className="empty-icon">⑂</span><h2>故事从一个选择开始</h2><p>上司邀请鲍勃接手一个重要项目。<br/>是全力争取、协商范围，还是留出更多生活时间？</p><Button variant="primary" disabled={busy} onClick={start}>使用虚构记忆，开启七天实验</Button><p className="fine">也可以先导入你自己的健康与工作记忆。</p></section>}
      </section><aside className="inspector"><ProfileCard p={branch?.snapshot.profile||world.profile} snapshot={!!branch} edit={()=>open('profile')}/><Advisors b={branch}/><div className="note-card"><span>↳ 实验室笔记</span><p>没有唯一正确的路线。试着比较一次“事业优先”和一次“留出余裕”。</p></div></aside></div>}
      {page==='memories'&&<Memories world={world} open={open}/>}
      {page==='compare'&&<Compare world={world} b={branch} onSelect={select} setActiveId={setActiveId} experiment={experiment} busy={busy}/>}
      {page==='history'&&<History branches={world.branches} select={select} open={open} exportBranch={exportBranch} busy={busy}/>}
      <footer>✧ 这是一个情景实验室。精力为游戏资源，结果由公开规则生成，不代表现实预测。</footer></main>
    </div>
    {modal&&<Modal key={`${modal.kind}-${modal.day??''}`} modal={modal} close={()=>setModal(null)} world={world} branch={branch} task={task} notify={notify} select={select} open={open}/>}
    <div id="toast" role="status" aria-live="polite" className={notice?`show ${notice.error?'error':''}`:''}>{notice?.message}</div>
  </>;
}

function ProfileCard({p,snapshot,edit}){
  return <section className="card profile-card"><div className="section-label">主角档案<button className="text-button" onClick={edit}>编辑</button></div><div className="person"><div className="avatar large">B<span/></div><div><h3>{p.name}</h3><p>{p.occupation} · 正在探索生活</p></div></div><div className="profile-goal"><span>当前目标</span><p>{p.goal}</p></div><div className="profile-foot"><span>作息目标</span><strong>{p.sleep_target} 小时 / 晚</strong></div>{snapshot&&<p className="fine">当前显示此分支创建时的档案快照。</p>}</section>;
}
function Advisors({b}){
  return <section className="card advisor-card"><div className="section-label">你的顾问席<Tag>规则策略</Tag></div>{!b?<><p className="muted">开启分支后，健康与工作顾问会从不同角度给出建议。</p><div className="mini-agents"><span>✚ 健康顾问</span><span>▣ 工作顾问</span></div></>:<>{b.advisors.map(a=><article className="advisor" key={a.role}><div className="advisor-title"><span className={`agent-icon ${a.role}`}>{a.role==='health'?'✚':'▣'}</span><strong>{a.name}</strong><span className="agent-state">在线</span></div><p>{a.reason}</p>{a.memory_ids.map(id=>{const m=b.snapshot.memories.find(m=>m.id===id);return m&&<div className="evidence" key={id}>↳ {m.content}<small>{m.is_demo?'虚构示例':sourceName(m.source)} · 背景参考</small></div>;})}</article>)}<p className="fine">记忆作为背景展示；首版数值由行动规则与档案作息目标计算，文本不会自动改变身体状态。</p></>}</section>;
}
function Metric({label,value,unit,symbol}){return <div className="metric"><span>{symbol} {label}</span><div><strong>{value}</strong><small>{unit}</small></div></div>;}
function BranchPanel({b,world,busy,onSelect,advance,open}){
  const s=b.state;
  return <><section className="card branch-card"><div className="section-label"><span>当前人生分支</span><BranchSelect world={world} id={b.id} onChange={onSelect}/></div>
    <div className="branch-title"><h2>{b.name}</h2><div><Tag amber={b.snapshot.memory_mode==='demo'}>{b.snapshot.memory_mode==='demo'?'虚构示例记忆':'已导入记忆'}</Tag><Tag>种子 {b.seed}</Tag></div></div>
    <div className="day-progress"><span>七天生活实验</span><progress value={s.day} max="7" aria-label="模拟进度"/><strong>{s.day} / 7 天</strong></div>
    <div className="metrics"><Metric label="项目进度" value={s.progress} unit="%" symbol="▣"/><Metric label="平均睡眠" value={b.metrics.average_sleep??'—'} unit={s.day?'小时':''} symbol="☾"/><Metric label="模拟精力" value={s.energy} unit="/ 100" symbol="✧"/><Metric label="自由时间" value={s.free_total} unit="小时" symbol="◷"/></div>
    {b.policy==='adaptive'&&!!s.day&&<div className="auto-summary"><h3>鲍勃的自主复盘</h3><p>已自主决定 {b.summary.automatic_days} 天，手动选择 {b.summary.manual_days} 天。全力推进 {b.summary.action_counts.focus} 天，协商推进 {b.summary.action_counts.negotiate} 天，留出休息 {b.summary.action_counts.rest} 天。</p><p>作息目标达成 {b.metrics.sleep_goal_days}/{s.day} 天，累计工作 {s.work_total} 小时。每日候选行动的规则评分可在下方轨迹中查看。</p></div>}
    {s.day<7?<><div className="decision-heading"><div><h3>{s.day?'下一天，怎么过？':'重要的机会，也是一道选择题。'}</h3><p>{s.day?'亲自作出选择，或让鲍勃按当前策略行动。':'新项目来了，鲍勃准备如何安排自己的时间？'}</p></div><Tag>DAY {s.day+1}</Tag></div><div className="choices">{Object.entries(world.actions).map(([id,a],i)=><button className="choice" key={id} disabled={busy} onClick={()=>advance(1,id)}><span className="choice-number">0{i+1}</span><strong>{a.name}</strong><span>工作 {a.work}h · 睡眠 {a.sleep}h</span><b>↗</b></button>)}</div><div className="autoplay"><span>当前自主策略：{POLICIES[b.policy]}</span><div><Button disabled={busy} onClick={()=>advance(1)}>自主推进一天</Button><Button variant="primary" disabled={busy} onClick={()=>advance(7-s.day)}>模拟到第七天 →</Button></div></div></>:<div className="completed"><span>✓</span><div><h3>这一段七天，已经走完。</h3><p>可以回到任意一天，换一种选择再看看。</p></div><Button disabled={busy} onClick={()=>open('fork',{day:0})}>探索另一条路 ↗</Button></div>}
    </section><section className="card timeline-card"><div className="section-label">生活的轨迹<span className="subtle">{b.events.length} 个日常片段</span></div>{!b.events.length?<div className="empty-timeline">◷ 你的第一个选择，将成为故事的起点。</div>:<div className="timeline">{[...b.events].reverse().map(e=><article className="timeline-event" key={e.day}><div className="timeline-day">DAY<strong>{e.day}</strong></div><div className="event-content"><div className="event-title"><h3>{e.action_name}</h3><button className="text-button" onClick={()=>open('event',{day:e.day})}>查看 / 分岔 ↗</button></div><p>{e.external_event}</p><div className="event-tags"><span>☾ {e.schedule.sleep}h 睡眠</span><span>▣ {e.schedule.work}h 工作</span><span>项目 {e.before.progress}% → {e.after.progress}%</span></div></div></article>)}</div>}</section></>;
}
function MemoryList({memories,onDelete}){
  return <div className="memory-list">{memories.map(m=><article className="memory-item" key={m.id}><span className={`agent-icon ${m.source==='health_assistant'?'health':'work'}`}>{m.source==='health_assistant'?'✚':'▣'}</span><div><div className="memory-meta">{sourceName(m.source)}<span>· {localDate(m.observed_at)} · {TYPES[m.type]} · 可信度 {Math.round(m.confidence*100)}%</span></div><p>{m.content}</p></div>{onDelete&&<button className="text-button danger" onClick={()=>onDelete(m.id)}>删除</button>}</article>)}</div>;
}
function Memories({world,open}){
  return <><section className="memory-banner"><span className="empty-icon">▤</span><div><h2>把经历带进世界，把隐私留在本地。</h2><p>仅接收你主动提供的记录。不会自动访问其他助手，也不会将内容发送给外部模型。</p></div><Button variant="primary" onClick={()=>open('import')}>＋ 导入记忆</Button></section><div className="memory-summary"><span>{world.memories.length} 条已导入记录</span><span>{world.memories.filter(m=>m.source==='health_assistant').length} 条健康记忆</span><span>{world.memories.filter(m=>m.source==='work_assistant').length} 条工作记忆</span></div><section className="card"><div className="section-label">你的记忆库<Tag>本地存储</Tag></div>{world.memories.length?<MemoryList memories={world.memories} onDelete={id=>open('delete-memory',{id})}/>:<Empty title="还没有导入真实记忆">支持 JSON 文件或直接粘贴，可以在导入窗口填入格式示例。</Empty>}</section><section className="card spaced"><div className="section-label">虚构示例档案<Tag amber>演示用途 · 与真实记忆分开</Tag></div><MemoryList memories={world.demo_memories}/></section><p className="fine">导入仅影响之后创建的“已导入记忆”分支；现有分支保留创建时的快照。删除记录会同时移除分支中的该条记忆副本。</p></>;
}
function Compare({world,b,onSelect,setActiveId,experiment,busy}){
  const results=world.branches.filter(x=>b&&x.seed===b.seed&&JSON.stringify(x.snapshot)===JSON.stringify(b.snapshot)).slice(0,6);
  return <><section className="compare-intro card"><div><span className="eyebrow">THE ROADS NOT TAKEN</span><h2>如果当时，选了另一条路？</h2><p>从同一份记忆和同一个世界种子出发，比较三种生活策略。</p></div><Button variant="primary" disabled={busy} onClick={experiment}>{busy?'正在推演…':'⑂ 生成三条七天路径'}</Button></section>
    {!!world.branches.length&&<div className="compare-toolbar"><label>比较起点<BranchSelect world={world} id={b?.id} onChange={setActiveId}/></label><span>展示相同档案、记忆与种子的最近 {results.length} 条分支</span></div>}
    {results.length?<><div className="comparison-grid">{results.map(x=><section className={`card result-card ${x.policy}`} key={x.id}><div className="section-label"><span className="policy-dot"/>{x.name}<Tag>{x.state.day}/7 天</Tag></div><div className="result-main"><strong>{x.state.progress}<small>%</small></strong><span>项目完成度</span></div><dl>{[['平均睡眠',`${x.metrics.average_sleep??'—'} 小时`],['作息目标达成',`${x.metrics.sleep_goal_days} / ${x.state.day} 天`],['工作总时长',`${x.state.work_total} 小时`],['自由时间',`${x.state.free_total} 小时`],['模拟精力',`${x.state.energy} / 100`]].map(([label,value])=><div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><Button full onClick={()=>onSelect(x.id)}>进入这条人生 ↗</Button></section>)}</div><section className="card spaced"><div className="section-label">项目进度轨迹<span className="subtle">相同外部事件，观察不同行动</span></div><Chart branches={results}/></section><section className="comparison-note"><h3>怎样理解这些结果？</h3><p>这不是对未来的预测。全力推进每天投入 11 小时工作，协商安排投入 8 小时，减少工作投入 5 小时。所有路径每天固定留出 3 小时处理日常生活，其余计为自由时间。外部事件由共同种子生成，精力只是游戏资源。</p><p>自主策略依据项目进度和精力阈值选择行动；你也可以回到某一天亲自决定。不同推进天数的结果，请先完成到第七天再比较。</p></section></>:<section className="card spaced"><Empty title="还没有可以比较的路径">生成三条路径，让鲍勃分别尝试平衡、事业和休息优先的生活。</Empty></section>}</>;
}
function Chart({branches}){
  const xs=d=>52+d*100,ys=v=>190-v*1.5;
  return <><svg className="chart" viewBox="0 0 790 230" role="img" aria-label="各分支项目进度随天数的变化，详细数值见上方结果卡片">{[0,25,50,75,100].map(v=><g key={v}><line x1="52" y1={ys(v)} x2="752" y2={ys(v)} className="grid-line"/><text x="12" y={ys(v)+4}>{v}%</text></g>)}{Array.from({length:8},(_,d)=><text key={d} x={xs(d)-12} y="220">第{d}天</text>)}{branches.map((b,i)=><g key={b.id}><polyline className={`chart-line line-${i}`} points={[[0,0],...b.events.map(e=>[e.day,e.after.progress])].map(([d,v])=>`${xs(d)},${ys(v)}`).join(' ')}/>{b.events.map(e=><circle key={e.day} className={`chart-point line-${i}`} cx={xs(e.day)} cy={ys(e.after.progress)} r="4"><title>{b.name} 第{e.day}天：{e.after.progress}%</title></circle>)}</g>)}</svg><div className="legend">{branches.map((b,i)=><span key={b.id} className={`line-${i}`}>━ {b.name}</span>)}</div></>;
}
function History({branches,select,open,exportBranch,busy}){
  return <section className="card"><div className="section-label">全部实验<Tag>{branches.length} 条分支</Tag></div>{branches.length?<div className="table-wrap"><table><thead><tr>{['人生分支','背景来源','进度','创建时间','操作'].map(s=><th key={s}>{s}</th>)}</tr></thead><tbody>{branches.map(b=><tr key={b.id}><td><strong>{b.name}</strong><small>{b.parent_id?`从第 ${b.fork_day} 天分岔`:'独立起点'} · 种子 {b.seed}</small></td><td><Tag amber={b.snapshot.memory_mode==='demo'}>{b.snapshot.memory_mode==='demo'?'虚构示例':'已导入记忆'}</Tag></td><td>{b.state.day} / 7 天</td><td>{localDate(b.created_at)}</td><td><div className="row-actions"><button className="text-button" onClick={()=>select(b.id)}>打开</button><button className="text-button" disabled={busy} onClick={()=>exportBranch(b.id)}>导出</button><button className="text-button danger" disabled={busy} onClick={()=>open('delete-branch',{id:b.id})}>删除</button></div></td></tr>)}</tbody></table></div>:<Empty title="实验记录还是空白">开始一条分支，所有选择与事件都会保存在这里。</Empty>}</section>;
}

function Modal({modal:m,close,world,branch,task,notify,select,open}){
  const ref=useRef(),[json,setJson]=useState(''),[error,setError]=useState(''),[saving,setSaving]=useState(false);
  useEffect(()=>{ref.current.showModal();return()=>ref.current?.close();},[]);
  const titles={new:'开启一段新的人生',profile:'编辑鲍勃档案',import:'导入助手记忆',fork:'从这里，走向另一种可能','delete-memory':'确认删除记忆','delete-branch':'确认删除分支',event:`第 ${m.day} 天的选择`};
  const p=world.profile,e=m.kind==='event'?branch?.events.find(e=>e.day===m.day):null;
  async function submit(event){
    event.preventDefault();if(saving)return;
    const values=Object.fromEntries(new FormData(event.target));
    if(m.kind==='import'){
      setSaving(true);setError('');
      try{const payload=JSON.parse(json);await task(async()=>{const result=await api('/memories/import','POST',payload);close();notify(`已导入 ${result.added} 条记忆，跳过 ${result.duplicates} 条重复记录。`);},err=>setError(err.message));}
      catch(err){setError(err instanceof SyntaxError?'JSON 格式有误，请检查引号、逗号和括号。':err.message);}
      finally{setSaving(false);}return;
    }
    setSaving(true);
    await task(async()=>{
      if(m.kind==='new'){
        const b=await api('/branches','POST',{policy:values.policy,seed:Number(values.seed),use_demo:values.mode==='demo',...(values.name.trim()?{name:values.name.trim()}:{})});select(b.id);notify('新的人生分支已创建。');
      }else if(m.kind==='profile'){
        await api('/profile','PUT',{...values,sleep_target:Number(values.sleep_target)});notify('档案已保存，将应用于新分支。');
      }else if(m.kind==='fork'){
        const b=await api(`/branches/${branch.id}/fork`,'POST',{day:Number(values.day),policy:values.policy,...(values.name.trim()?{name:values.name.trim()}:{})});select(b.id);notify('平行分支已创建，原有路径保留。');
      }
      close();
    },err=>setError(err.message));setSaving(false);
  }
  async function remove(){setSaving(true);await task(async()=>{await api(`${m.kind==='delete-memory'?'/memories':'/branches'}/${m.id}`,'DELETE');close();notify('已删除。');});setSaving(false);}
  const policyField=<label>自主行动策略<select name="policy">{Object.entries(POLICIES).map(([id,n])=><option value={id} key={id}>{n}</option>)}</select></label>;
  return <dialog ref={ref} onCancel={close} aria-labelledby="modal-title"><div className="modal-header"><h2 id="modal-title">{titles[m.kind]}</h2><button className="close-button" onClick={close} aria-label="关闭对话框">×</button></div>
    {m.kind==='new'&&<form onSubmit={submit}><p className="muted">七天，一个新项目，以及有限的时间。让鲍勃试试不同的安排。</p><label>分支名称<input name="name" maxLength="60" placeholder="例如：这次试着慢一点"/></label>{policyField}<label>记忆背景<select name="mode"><option value="demo">虚构示例记忆（演示）</option><option value="imported" disabled={!world.memories.length}>已导入记忆（{world.memories.length} 条）</option></select></label><label>世界种子<input name="seed" type="number" min="0" max="2147483647" defaultValue="42" required/></label><p className="fine">相同种子生成相同外部事件。档案与记忆将保存在分支快照中。</p><Button variant="primary" full type="submit" disabled={saving}>开启新分支 →</Button></form>}
    {m.kind==='profile'&&<form onSubmit={submit}><p className="muted">改动用于新分支，现有分支保留原档案。</p><label>名字<input name="name" defaultValue={p.name} maxLength="30" required/></label><label>职业<input name="occupation" defaultValue={p.occupation} maxLength="80" required/></label><label>当前目标<textarea name="goal" rows="3" maxLength="500" defaultValue={p.goal} required/></label><label>每晚作息目标（小时）<input name="sleep_target" type="number" min="4" max="12" step="0.5" defaultValue={p.sleep_target} required/></label><Button variant="primary" full type="submit" disabled={saving}>保存档案</Button></form>}
    {m.kind==='import'&&<form onSubmit={submit}><p className="muted">上传 JSON 或粘贴记录。格式示例仅演示结构，请替换成你希望使用的内容。</p><label className="file-label">选择 JSON 文件<input type="file" accept="application/json,.json" onChange={async event=>{const file=event.target.files[0];if(!file)return;if(file.size>1_000_000){setError('文件不能超过 1 MB。');event.target.value='';return;}try{setJson(await file.text());setError('');}catch{setError('无法读取此文件。');}}}/></label><label>记忆 JSON<textarea name="json" rows="12" value={json} onChange={e=>setJson(e.target.value)} required placeholder={'{"memories": [...]}'}/></label><p className="fine">source：health_assistant / work_assistant。type：reported_fact / preference / goal / hypothesis。最多 200 条、1 MB；重复记录自动跳过。未标时区按 UTC 解释。</p><p id="form-error" role="alert">{error}</p><div className="modal-actions"><Button type="button" onClick={()=>setJson(JSON.stringify(EXAMPLE,null,2))}>填入格式示例</Button><Button variant="primary" type="submit" disabled={saving}>导入到本地记忆库</Button></div></form>}
    {m.kind==='fork'&&branch&&<form onSubmit={submit}><p className="muted">保留分岔点之前的经历和原始记忆，之后由新的策略继续。</p><label>分岔点<select name="day" defaultValue={m.day??0}>{Array.from({length:branch.state.day+1},(_,i)=><option key={i} value={i}>{i===0?'最初起点':`第 ${i} 天结束后`}</option>)}</select></label>{policyField}<label>分支名称<input name="name" maxLength="60" placeholder="为这条路取个名字"/></label><Button variant="primary" full type="submit" disabled={saving}>创建平行分支 →</Button></form>}
    {m.kind.startsWith('delete-')&&<><p>{m.kind==='delete-memory'?'将从记忆库和所有分支快照中移除这条记忆。已有模拟日程保留。':'将永久删除这条分支及其事件记录，其他分支保留。'}</p><div className="modal-actions"><Button onClick={close}>取消</Button><Button variant="danger-button" disabled={saving} onClick={remove}>确认删除</Button></div></>}
    {m.kind!=='import'&&error&&<p className="form-error" role="alert">{error}</p>}
    {e&&<div className="event-detail"><Tag>规则引擎 · 可复现</Tag><h3>{e.action_name}</h3><p>{e.reason}</p>{!!e.decision_scores?.length&&<><h3>选择时的候选评分</h3><div className="table-wrap"><table><thead><tr><th>安排</th><th>工作</th><th>作息 / 精力</th><th>自由时间</th><th>总分</th></tr></thead><tbody>{e.decision_scores.map(r=><tr key={r.action}><td>{world.actions[r.action].name}</td><td>{r.work_score}</td><td>{r.health_score}</td><td>{r.free_time_score}</td><td>{r.score}</td></tr>)}</tbody></table></div><p className="fine">规则分数用于比较本模拟中的安排，不是成功概率或健康评估。决策未使用当天尚未发生的外部事件。</p></>}<h3>今天发生了什么</h3><p>{e.external_event}</p><div className="schedule">{Object.entries({work:'工作',sleep:'睡眠',exercise:'运动',daily_life:'日常生活',free:'自由时间'}).map(([id,name])=><div key={id}><span>{name}</span><strong>{e.schedule[id]} h</strong></div>)}</div><h3>当时的顾问意见</h3>{e.advisors.map(a=><p key={a.role}><strong>{a.name}：</strong>{a.reason}</p>)}<p className="fine">分岔将从这一天开始之前（第 {e.day-1} 天结束时）继续，原分支保持不变。</p><Button variant="primary" full onClick={()=>open('fork',{day:e.day-1})}>回到这次选择，创建另一条路 ↗</Button></div>}
  </dialog>;
}

createRoot(document.getElementById('app')).render(<App/>);
