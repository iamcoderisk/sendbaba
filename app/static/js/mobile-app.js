(function(){
if(window.innerWidth>768)return;
document.addEventListener('DOMContentLoaded',function(){
if(document.querySelector('.mob-nav'))return;
var nav=document.createElement('nav');
nav.className='mob-nav';
nav.innerHTML='<button class="on" onclick="MB.go(\'INBOX\',this)"><i class="fas fa-inbox"></i><span>Inbox</span></button>'+
'<button onclick="MB.go(\'Sent\',this)"><i class="fas fa-paper-plane"></i><span>Sent</span></button>'+
'<button onclick="MB.go(\'Drafts\',this)"><i class="fas fa-file-alt"></i><span>Drafts</span></button>'+
'<button onclick="alert(\'Coming soon\')"><i class="fas fa-th-large"></i><span>Tools</span></button>'+
'<button onclick="location.href=\'/settings\'"><i class="fas fa-cog"></i><span>Settings</span></button>';
document.body.appendChild(nav);
var fab=document.createElement('button');
fab.className='mob-fab';
fab.innerHTML='<i class="fas fa-pen"></i>';
fab.onclick=function(){if(typeof openCompose==='function')openCompose();else alert('Compose coming soon!');};
document.body.appendChild(fab);
});
window.MB={go:function(f,btn){
document.querySelectorAll('.mob-nav button').forEach(function(b){b.classList.remove('on');});
if(btn)btn.classList.add('on');
if(typeof loadEmails==='function')loadEmails(f);
else location.href='/inbox?folder='+f;
}};
})();
