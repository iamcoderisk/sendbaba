(function(){
if(window.innerWidth<=768)return;

var state={folder:'INBOX',emails:[],selected:null};
var colors=['#f86d31','#3b82f6','#10b981','#8b5cf6','#ec4899','#f59e0b','#06b6d4','#ef4444'];

document.addEventListener('DOMContentLoaded',function(){
    setTimeout(init,100);
});

function init(){
    // Remove any existing
    var old=document.querySelector('.sb-wrap');if(old)old.remove();
    old=document.querySelector('.sb-fab');if(old)old.remove();
    
    // Create main container
    var wrap=document.createElement('div');
    wrap.className='sb-wrap';
    wrap.innerHTML=buildNav()+buildSide()+buildList()+buildView();
    document.body.appendChild(wrap);
    
    // Create FAB
    var fab=document.createElement('button');
    fab.className='sb-fab';
    fab.innerHTML='<i class="fas fa-pen"></i> Compose';
    fab.onclick=function(){
        if(typeof window.openCompose==='function')window.openCompose();
        else if(typeof window.showComposeModal==='function')window.showComposeModal();
        else alert('Compose coming soon!');
    };
    document.body.appendChild(fab);
    
    // Load emails
    loadEmails('INBOX');
}

function buildNav(){
    return '<nav class="sb-nav">'+
        '<button class="sb-nav-toggle" onclick="SB.toggleSide()"><i class="fas fa-bars"></i></button>'+
        '<div class="sb-nav-logo"><i class="fas fa-paper-plane"></i></div>'+
        '<div class="sb-nav-list">'+
            '<button class="sb-nav-btn on" data-v="mail" onclick="SB.nav(\'mail\',this)"><i class="fas fa-envelope"></i><span>Mail</span></button>'+
            '<button class="sb-nav-btn" data-v="calendar" onclick="SB.nav(\'calendar\',this)"><i class="fas fa-calendar-alt"></i><span>Calendar</span></button>'+
            '<button class="sb-nav-btn" data-v="contacts" onclick="SB.nav(\'contacts\',this)"><i class="fas fa-address-book"></i><span>Contacts</span></button>'+
            '<button class="sb-nav-btn" data-v="files" onclick="SB.nav(\'files\',this)"><i class="fas fa-folder"></i><span>Files</span></button>'+
            '<button class="sb-nav-btn" onclick="location.href=\'/settings\'"><i class="fas fa-cog"></i><span>Settings</span></button>'+
        '</div>'+
    '</nav>';
}

function buildSide(){
    return '<aside class="sb-side">'+
        '<div class="sb-side-head"><h2>Mail</h2></div>'+
        '<div class="sb-side-body">'+
            '<div class="sb-folder on" data-f="INBOX" onclick="SB.folder(\'INBOX\',this)"><i class="fas fa-inbox"></i> Inbox <span class="cnt" id="cnt-inbox">0</span></div>'+
            '<div class="sb-folder" data-f="Starred" onclick="SB.folder(\'Starred\',this)"><i class="fas fa-star"></i> Starred</div>'+
            '<div class="sb-folder" data-f="Sent" onclick="SB.folder(\'Sent\',this)"><i class="fas fa-paper-plane"></i> Sent</div>'+
            '<div class="sb-folder" data-f="Drafts" onclick="SB.folder(\'Drafts\',this)"><i class="fas fa-file-alt"></i> Drafts</div>'+
            '<div class="sb-folder" data-f="Spam" onclick="SB.folder(\'Spam\',this)"><i class="fas fa-exclamation-triangle"></i> Spam</div>'+
            '<div class="sb-folder" data-f="Trash" onclick="SB.folder(\'Trash\',this)"><i class="fas fa-trash"></i> Trash</div>'+
            '<div class="sb-lbl">Labels</div>'+
            '<div class="sb-folder" onclick="SB.folder(\'Work\',this)"><i class="fas fa-circle" style="color:#3b82f6;font-size:8px"></i> Work</div>'+
            '<div class="sb-folder" onclick="SB.folder(\'Personal\',this)"><i class="fas fa-circle" style="color:#10b981;font-size:8px"></i> Personal</div>'+
            '<div class="sb-badge"><i class="fas fa-shield-alt"></i><div><strong>End-to-End Encrypted</strong><span>Your emails are secure</span></div></div>'+
            '<div class="sb-ad" onclick="window.open(\'/advertise\')"><small>Sponsored</small><strong>🚀 Grow Your Business</strong><span>Advertise with SendBaba</span></div>'+
        '</div>'+
    '</aside>';
}

function buildList(){
    return '<section class="sb-list">'+
        '<div class="sb-list-head">'+
            '<h1 id="list-title">Inbox</h1>'+
            '<div class="sb-search"><i class="fas fa-search"></i><input type="text" placeholder="Search emails..." onkeyup="SB.search(this.value)"></div>'+
        '</div>'+
        '<div class="sb-bar">'+
            '<div class="sb-bar-left">'+
                '<button class="sb-bar-btn" onclick="SB.selectAll()"><i class="far fa-square"></i></button>'+
                '<button class="sb-bar-btn" onclick="SB.refresh()"><i class="fas fa-sync-alt"></i></button>'+
                '<button class="sb-bar-btn"><i class="fas fa-archive"></i></button>'+
                '<button class="sb-bar-btn"><i class="fas fa-trash"></i></button>'+
            '</div>'+
            '<div class="sb-bar-right"><span id="mail-count">0 emails</span></div>'+
        '</div>'+
        '<div class="sb-mails" id="mail-list"><div class="sb-load"><i class="fas fa-spinner fa-spin"></i><p>Loading...</p></div></div>'+
    '</section>';
}

function buildView(){
    return '<section class="sb-view"><div class="sb-view-empty" id="mail-view"><i class="fas fa-envelope-open-text"></i><p>Select an email to read</p></div></section>';
}

function loadEmails(folder){
    state.folder=folder;
    var el=document.getElementById('mail-list');
    var title=document.getElementById('list-title');
    if(title)title.textContent=folder==='INBOX'?'Inbox':folder;
    if(el)el.innerHTML='<div class="sb-load"><i class="fas fa-spinner fa-spin"></i><p>Loading...</p></div>';
    
    var urls=[
        '/api/emails?folder='+encodeURIComponent(folder)+'&limit=50',
        '/api/mail/messages?folder='+encodeURIComponent(folder),
        '/api/messages?mailbox='+encodeURIComponent(folder)
    ];
    
    tryFetch(urls,0,function(data){
        var emails=data.emails||data.messages||data.data||[];
        if(Array.isArray(emails)){
            state.emails=emails;
            renderEmails(emails);
        }else{
            renderEmpty();
        }
    },function(){
        renderEmpty();
    });
}

function tryFetch(urls,i,success,fail){
    if(i>=urls.length){fail();return;}
    fetch(urls[i],{credentials:'same-origin'})
    .then(function(r){if(!r.ok)throw new Error();return r.json();})
    .then(function(d){
        var arr=d.emails||d.messages||d.data||[];
        if(Array.isArray(arr)&&arr.length>0)success(d);
        else tryFetch(urls,i+1,success,fail);
    })
    .catch(function(){tryFetch(urls,i+1,success,fail);});
}

function renderEmails(emails){
    var el=document.getElementById('mail-list');
    var cnt=document.getElementById('mail-count');
    var icnt=document.getElementById('cnt-inbox');
    if(cnt)cnt.textContent=emails.length+' emails';
    if(icnt&&state.folder==='INBOX')icnt.textContent=emails.length;
    if(!el)return;
    if(!emails.length){renderEmpty();return;}
    
    var h='';
    emails.forEach(function(e,idx){
        var name=e.from_name||e.from||e.sender||'Unknown';
        if(typeof name==='object')name=name.name||name.email||'Unknown';
        name=String(name);
        var ini=name.charAt(0).toUpperCase()||'?';
        var col=colors[ini.charCodeAt(0)%colors.length];
        var unread=!e.is_read&&!e.read&&!e.seen;
        var starred=e.is_starred||e.starred;
        var subj=e.subject||'(No subject)';
        var prev=e.preview||e.snippet||e.body_text||'';
        if(prev.length>60)prev=prev.substring(0,60)+'...';
        var time=fmtTime(e.date||e.received||e.created_at);
        var id=e.id||e.uid||idx;
        var enc=e.encrypted||e.is_encrypted;
        
        h+='<div class="sb-mail'+(unread?' new':'')+'" data-id="'+id+'" onclick="SB.open(\''+id+'\')">'+
            '<div class="sb-mail-chk"><input type="checkbox" onclick="event.stopPropagation()"></div>'+
            '<div class="sb-mail-av" style="background:'+col+'">'+ini+'</div>'+
            '<div class="sb-mail-body">'+
                '<div class="sb-mail-top">'+
                    '<span class="sb-mail-from">'+esc(name)+'</span>'+
                    '<span class="sb-mail-time">'+time+' <i class="fas fa-star sb-mail-star'+(starred?' on':'')+'" onclick="event.stopPropagation();SB.star(\''+id+'\')"></i></span>'+
                '</div>'+
                '<div class="sb-mail-subj">'+esc(subj)+'</div>'+
                '<div class="sb-mail-prev">'+esc(prev)+'</div>'+
                (enc?'<span class="sb-mail-tag"><i class="fas fa-lock"></i> Encrypted</span>':'')+
            '</div>'+
        '</div>';
    });
    el.innerHTML=h;
}

function renderEmpty(){
    var el=document.getElementById('mail-list');
    if(el)el.innerHTML='<div class="sb-load"><i class="fas fa-inbox"></i><p>No emails in '+state.folder+'</p></div>';
    var cnt=document.getElementById('mail-count');
    if(cnt)cnt.textContent='0 emails';
}

function openEmail(id){
    var e=null;
    for(var i=0;i<state.emails.length;i++){
        var m=state.emails[i];
        if(String(m.id)==String(id)||String(m.uid)==String(id)||i==id){e=m;break;}
    }
    if(!e)return;
    
    document.querySelectorAll('.sb-mail').forEach(function(el){el.classList.remove('on');});
    var clicked=document.querySelector('.sb-mail[data-id="'+id+'"]');
    if(clicked)clicked.classList.add('on');
    
    var name=e.from_name||e.from||'Unknown';
    if(typeof name==='object')name=name.name||name.email||'Unknown';
    var email=e.from_email||(typeof e.from==='object'?e.from.email:e.from)||'';
    var ini=String(name).charAt(0).toUpperCase()||'?';
    var col=colors[ini.charCodeAt(0)%colors.length];
    var subj=e.subject||'(No subject)';
    var body=e.body_html||e.html||e.body||e.body_text||'No content';
    
    var view=document.querySelector('.sb-view');
    if(view)view.innerHTML='<div class="sb-view-head">'+
        '<h1 class="sb-view-subj">'+esc(subj)+'</h1>'+
        '<div class="sb-view-meta">'+
            '<div class="sb-view-av" style="background:'+col+'">'+ini+'</div>'+
            '<div class="sb-view-info"><strong>'+esc(name)+'</strong><span>'+esc(email)+'</span></div>'+
            '<div class="sb-view-btns">'+
                '<button class="sb-view-btn" title="Reply"><i class="fas fa-reply"></i></button>'+
                '<button class="sb-view-btn" title="Forward"><i class="fas fa-share"></i></button>'+
                '<button class="sb-view-btn" title="Delete"><i class="fas fa-trash"></i></button>'+
                '<button class="sb-view-btn" title="More"><i class="fas fa-ellipsis-h"></i></button>'+
            '</div>'+
        '</div>'+
    '</div>'+
    '<div class="sb-view-body"><div class="sb-view-content">'+body+'</div></div>';
    
    fetch('/api/emails/'+id+'/read',{method:'POST',credentials:'same-origin'}).catch(function(){});
}

function fmtTime(d){
    if(!d)return'';
    try{
        var dt=new Date(d),now=new Date(),diff=Math.floor((now-dt)/86400000);
        if(isNaN(diff))return'';
        if(diff===0)return dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});
        if(diff===1)return'Yesterday';
        if(diff<7)return['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][dt.getDay()];
        return dt.toLocaleDateString();
    }catch(e){return'';}
}

function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=String(s);return d.innerHTML;}

// Global API
window.SB={
    folder:function(f,el){
        document.querySelectorAll('.sb-folder').forEach(function(x){x.classList.remove('on');});
        if(el)el.classList.add('on');
        loadEmails(f);
    },
    open:openEmail,
    refresh:function(){loadEmails(state.folder);},
    search:function(q){
        document.querySelectorAll('.sb-mail').forEach(function(el){
            el.style.display=el.textContent.toLowerCase().indexOf(q.toLowerCase())>-1?'':'none';
        });
    },
    selectAll:function(){
        var cb=document.querySelectorAll('.sb-mail-chk input');
        var all=Array.from(cb).every(function(c){return c.checked;});
        cb.forEach(function(c){c.checked=!all;});
    },
    star:function(id){
        var el=document.querySelector('.sb-mail[data-id="'+id+'"] .sb-mail-star');
        if(el)el.classList.toggle('on');
        fetch('/api/emails/'+id+'/star',{method:'POST',credentials:'same-origin'}).catch(function(){});
    },
    nav:function(v,btn){
        document.querySelectorAll('.sb-nav-btn').forEach(function(b){b.classList.remove('on');});
        if(btn)btn.classList.add('on');
        if(v!=='mail')alert(v.charAt(0).toUpperCase()+v.slice(1)+' coming soon!');
    },
    toggleSide:function(){
        var wrap=document.querySelector('.sb-wrap');
        if(!wrap)return;
        var cols=wrap.style.gridTemplateColumns;
        if(cols&&cols.indexOf('0px')>-1){
            wrap.style.gridTemplateColumns='64px 260px 400px 1fr';
        }else{
            wrap.style.gridTemplateColumns='64px 0px 400px 1fr';
        }
    }
};

window.loadEmails=loadEmails;
})();
