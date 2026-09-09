/* El iframe conserva la consulta al cerrar el panel. */
(() => {
  'use strict';
  if (window.self !== window.top || location.pathname === '/asistente') return;
  const host = document.createElement('div'); host.id = 'pengui';
  const root = host.attachShadow({mode:'open'});
  root.innerHTML = `<style>
    :host{position:fixed;bottom:max(16px,env(safe-area-inset-bottom));left:max(16px,env(safe-area-inset-left));z-index:900;font:13px system-ui;color:#111}
    *{box-sizing:border-box}button{font:inherit;cursor:pointer}button:focus-visible,a:focus-visible{outline:3px solid #ffd400;outline-offset:4px}
    .launch{display:flex;align-items:center;gap:3px;background:none;border:0;padding:0;color:inherit}
    svg{width:72px;height:86px;filter:drop-shadow(0 4px 4px #0003);transform-origin:50% 90%}
    .name{background:#fff;padding:8px 12px;border:1px solid #d4d4d4;border-radius:20px;box-shadow:0 3px 12px #0002;font-weight:650}
    .jump{animation:saludo .65s ease}.launch:hover svg{transform:rotate(-5deg)}
    @keyframes saludo{0%,100%{transform:translateY(0) rotate(0)}25%{transform:translateY(-18px) rotate(-12deg)}55%{transform:translateY(-8px) rotate(12deg)}80%{transform:rotate(-5deg)}}
    .chat{position:absolute;bottom:98px;left:0;width:min(420px,calc(100vw - 32px));height:min(640px,calc(100dvh - 140px));display:flex;flex-direction:column;border-radius:16px;overflow:hidden;border:1px solid #d4d4d4;box-shadow:0 16px 60px #0005;background:white}
    [hidden]{display:none!important}.head{display:flex;align-items:center;padding:13px 16px;background:#0b0b0b;color:white;gap:12px;border-bottom:3px solid #ffd400}.head div{flex:1}.head small{display:block;color:#cfcfcf;font-size:11px;margin-top:3px}.head button,.head a{border:0;background:transparent;color:white;padding:7px;text-decoration:none;font-size:20px;border-radius:6px}
    iframe{border:0;width:100%;flex:1;min-height:0;background:#f5f5f2}
    @media(max-width:600px){.name{display:none}svg{width:58px;height:70px}.chat{bottom:82px;height:min(640px,calc(100dvh - 116px))}}
    @media(prefers-reduced-motion:reduce){.jump{animation:none}.launch:hover svg{transform:none}}
    @media print{:host{display:none}}
  </style>
  <section class="chat" hidden role="dialog" aria-label="Pengui, el asistente de IA">
    <div class="head"><div><strong>Pengui</strong><small>El asistente de IA · Diemar</small></div><a href="/asistente" aria-label="Abrir chat en pantalla completa" title="Pantalla completa">↗</a><button class="close" aria-label="Cerrar chat">×</button></div>
  </section>
  <button class="launch" aria-label="Hablar con Pengui, el asistente de IA" aria-expanded="false">
    <svg viewBox="0 0 100 120" aria-hidden="true">
      <ellipse cx="50" cy="112" rx="28" ry="5" fill="#000" opacity=".12"/>
      <ellipse cx="33" cy="106" rx="16" ry="7" fill="#ffd400"/><ellipse cx="67" cy="106" rx="16" ry="7" fill="#ffd400"/>
      <path d="M25 51C4 58 7 88 17 83L30 68M75 51C93 40 100 48 86 64L75 73" fill="#242424"/>
      <path d="M20 62C15 13 35 7 50 7S85 13 80 62C93 108 69 111 50 111S7 108 20 62" fill="#0b0b0b"/>
      <ellipse cx="50" cy="76" rx="27" ry="31" fill="#f4f7fa"/>
      <ellipse cx="37" cy="40" rx="17" ry="22" fill="#f4f7fa"/><ellipse cx="63" cy="40" rx="17" ry="22" fill="#f4f7fa"/>
      <ellipse cx="39" cy="39" rx="4" ry="6" fill="#0b0b0b"/><ellipse cx="61" cy="39" rx="4" ry="6" fill="#0b0b0b"/>
      <circle cx="40" cy="37" r="1.5" fill="white"/><circle cx="62" cy="37" r="1.5" fill="white"/>
      <path d="M40 49Q50 43 60 49L50 59Z" fill="#ffd400"/>
      <path d="M24 61Q50 71 76 61L76 70Q50 80 24 70Z" fill="#ffd400"/><path d="M66 70L76 70L77 89L66 85Z" fill="#ffd400"/>
    </svg><span class="name">Pengui</span>
  </button>`;
  const launch=root.querySelector('.launch'),chat=root.querySelector('.chat'),close=root.querySelector('.close');let frame;
  function shut(){chat.hidden=true;launch.setAttribute('aria-expanded','false');launch.focus();}
  launch.onclick=()=>{
    if(!chat.hidden){shut();return;}
    const svg=root.querySelector('svg');svg.classList.remove('jump');void svg.getBoundingClientRect();svg.classList.add('jump');
    chat.hidden=false;launch.setAttribute('aria-expanded','true');
    if(!frame){frame=document.createElement('iframe');frame.title='Conversación con Pengui';frame.src='/asistente?embed=1';chat.append(frame);}close.focus();
  };
  close.onclick=shut;
  document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!chat.hidden)shut();});
  window.addEventListener('message',e=>{if(e.origin===location.origin&&frame&&e.source===frame.contentWindow&&e.data==='pengui:close')shut();});
  document.body.append(host);
})();
