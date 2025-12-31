var folder='inbox',emails=[],contacts=[],current=null,chats={},activeChat=null,pollInterval=null,viewingEmail=false,onlineUsers={},lastEmailCount=0,soundEnabled=true,colors=['#f86d31','#3b82f6','#10b981','#8b5cf6','#ec4899','#f59e0b','#06b6d4','#ef4444','#6366f1','#14b8a6'],mediaRecorder=null,audioChunks=[],recordingInterval=null,recordingTime=0,audioCtx=null,currentAttachments=[],currentAttIdx=0;
function toast(m,t){var b=document.getElementById('toast-box'),d=document.createElement('div');d.className='toast '+(t||'info');d.innerHTML='<i class="fas fa-'+(t==='success'?'check-circle':t==='error'?'exclamation-circle':'info-circle')+'"></i>'+m;b.appendChild(d);setTimeout(function(){d.style.opacity='0';setTimeout(function(){d.remove()},300)},3500)}
function esc(s){if(!s)return'';var d=document.createElement('div');d.textContent=s;return d.innerHTML}
function fmtTime(d){if(!d)return'';try{var dt=new Date(d),now=new Date(),diff=Math.floor((now-dt)/86400000);if(diff===0)return dt.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});if(diff===1)return'Yesterday';if(diff<7)return['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][dt.getDay()];return dt.toLocaleDateString([],{month:'short',day:'numeric'})}catch(e){return''}}
function getColor(c){return colors[c.charCodeAt(0)%colors.length]}
function formatSize(b){if(!b)return'';if(b<1024)return b+' B';if(b<1048576)return Math.round(b/1024)+' KB';return(b/1048576).toFixed(1)+' MB'}
function initSound(){try{audioCtx=new(window.AudioContext||window.webkitAudioContext)()}catch(e){}}
function playSound(){if(!soundEnabled||!audioCtx)return;try{if(audioCtx.state==='suspended')audioCtx.resume();var now=audioCtx.currentTime,o1=audioCtx.createOscillator(),g1=audioCtx.createGain();o1.connect(g1);g1.connect(audioCtx.destination);o1.frequency.value=880;o1.type='sine';g1.gain.setValueAtTime(.3,now);g1.gain.exponentialRampToValueAtTime(.01,now+.3);o1.start(now);o1.stop(now+.3)}catch(e){}}
function toggleDark(){document.body.classList.toggle('dark');localStorage.setItem('dark',document.body.classList.contains('dark'));var tog=document.getElementById('darkToggle');if(tog)tog.classList.toggle('on',document.body.classList.contains('dark'));toast(document.body.classList.contains('dark')?'Dark mode':'Light mode','success')}
function initDarkMode(){if(localStorage.getItem('dark')==='true'){document.body.classList.add('dark');var tog=document.getElementById('darkToggle');if(tog)tog.classList.add('on')}}
function toggleSidebar(){document.getElementById('app').classList.toggle('sidebar-collapsed');document.getElementById('nav-toggle').classList.toggle('rotated')}
function updateFabVisibility(){var fab=document.getElementById('fab');if(viewingEmail&&window.innerWidth>768)fab.classList.add('hidden');else fab.classList.remove('hidden')}
function loadFolder(f,el){folder=f;document.querySelectorAll('.folder').forEach(function(x){x.classList.remove('on')});if(el)el.classList.add('on');else{var x=document.querySelector('.folder[data-folder="'+f+'"]');if(x)x.classList.add('on')}var titles={inbox:'Inbox',sent:'Sent',drafts:'Drafts',spam:'Spam',trash:'Trash',starred:'Starred'};var titleEl=document.getElementById('list-title');titleEl.innerHTML=titles[f]||f;var emptyBtn=document.getElementById('empty-trash-btn');if(emptyBtn){emptyBtn.classList.toggle('show',f==='trash')}document.getElementById('email-list').innerHTML='<div class="loading"><i class="fas fa-spinner"></i><p>Loading...</p></div>';if(f==='inbox'&&window.PRELOADED_EMAILS&&window.PRELOADED_EMAILS.length>0&&!window.PRELOAD_USED){window.PRELOAD_USED=true;emails=window.PRELOADED_EMAILS;lastEmailCount=emails.length;renderEmails(emails);var cnt=document.getElementById('inbox-cnt');if(cnt&&window.PRELOADED_UNREAD)cnt.textContent=window.PRELOADED_UNREAD;return}fetch('/api/emails?folder='+f+'&per_page=50',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){if(d.success&&d.emails){emails=d.emails;if(f==='inbox')lastEmailCount=emails.length;renderEmails(emails);var unread=emails.filter(function(e){return!e.is_read}).length;var cnt=document.getElementById('inbox-cnt');if(cnt)cnt.textContent=f==='inbox'&&unread?unread:''}else{emails=[];renderEmpty()}}).catch(function(){renderEmpty()})}
function renderEmails(list){var el=document.getElementById('email-list');if(!list.length){renderEmpty();return}el.innerHTML=list.map(function(e){var name=e.from_name||(e.from_email?e.from_email.split('@')[0]:'?'),i=name.charAt(0).toUpperCase(),col=getColor(i),u=!e.is_read,s=e.is_starred,tm=fmtTime(e.received_at),p=(e.preview||e.body_text||'').substring(0,60),att=e.has_attachments||e.attachments_count>0;return'<div class="email-item'+(u?' unread':'')+'" data-id="'+e.id+'"><div class="swipe-action'+(folder==='trash'?'':' delete')+'"><i class="fas fa-'+(folder==='trash'?'undo':'trash')+'"></i><span>'+(folder==='trash'?'Restore':'Delete')+'</span></div><div class="email-av" style="background:'+col+'">'+i+'</div><div class="email-content"><div class="email-row1"><span class="email-from">'+esc(name)+'</span><span class="email-time">'+tm+'</span></div><div class="email-subj">'+esc(e.subject||'(No subject)')+'</div><div class="email-preview">'+esc(p)+'</div></div><div class="email-indicators">'+(att?'<i class="fas fa-paperclip email-attach"></i>':'')+(u?'<div class="email-badge"></div>':'')+'<i class="fas fa-star email-star'+(s?' on':'')+'" data-id="'+e.id+'"></i></div></div>'}).join('');initEmailEvents();initSwipe()}
function renderEmpty(){var ic={trash:'fa-trash',spam:'fa-exclamation-triangle',starred:'fa-star',drafts:'fa-file-alt',sent:'fa-paper-plane'};document.getElementById('email-list').innerHTML='<div class="empty-state"><i class="fas '+(ic[folder]||'fa-inbox')+'"></i><p>No emails in '+folder+'</p></div>'}
function initEmailEvents(){document.querySelectorAll('.email-item').forEach(function(item){item.addEventListener('click',function(e){if(e.target.classList.contains('email-star'))return;openMail(this.getAttribute('data-id'),this)})});document.querySelectorAll('.email-star').forEach(function(star){star.addEventListener('click',function(e){e.stopPropagation();this.classList.toggle('on');starEmail(this.getAttribute('data-id'))})})}
function initSwipe(){document.querySelectorAll('.email-item').forEach(function(item){var startX=0,curX=0,drag=false,sw=item.querySelector('.swipe-action');item.addEventListener('touchstart',function(e){startX=e.touches[0].clientX;curX=startX;drag=true},{passive:true});item.addEventListener('touchmove',function(e){if(!drag)return;curX=e.touches[0].clientX;var d=startX-curX;if(d>0&&d<100){this.style.transform='translateX(-'+d+'px)';if(sw)sw.style.transform='translateX('+(100-d)+'%)'}},{passive:true});item.addEventListener('touchend',function(){drag=false;var d=startX-curX,self=this;if(d>70){var id=this.getAttribute('data-id');this.style.transform='translateX(-100%)';this.style.opacity='0';setTimeout(function(){self.style.height='0';self.style.margin='0';self.style.padding='0'},100);setTimeout(function(){if(folder==='trash'){restoreEmail(id);toast('Email restored','success')}else{deleteEmail(id);toast('Email deleted','success')}self.remove()},400)}else{this.style.transform='';if(sw)sw.style.transform=''}})})}
function openMail(id,el){viewingEmail=true;updateFabVisibility();fetch('/api/email/'+id,{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){if(!d.success||!d.email)return;var e=d.email;current=e;var name=e.from_name||(e.from_email?e.from_email.split('@')[0]:'?'),i=name.charAt(0).toUpperCase(),col=getColor(i),body=e.body_html||(e.body_text?e.body_text.replace(/\n/g,'<br>'):''),tm=fmtTime(e.received_at);if(el)el.classList.remove('unread');currentAttachments=e.attachments||[];var attHtml='';if(currentAttachments.length){attHtml='<div class="view-attachments"><h4><i class="fas fa-paperclip"></i> Attachments ('+currentAttachments.length+')</h4><div class="attachment-list">'+currentAttachments.map(function(a,idx){var isImg=/\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(a.filename),isPdf=/\.pdf$/i.test(a.filename),url='/api/attachment/'+a.id;if(isImg)return'<img class="attachment-preview" src="'+url+'" alt="'+esc(a.filename)+'" onclick="openAttachment('+idx+')">';var icon='fa-file';if(isPdf)icon='fa-file-pdf';else if(/\.(doc|docx)$/i.test(a.filename))icon='fa-file-word';else if(/\.(xls|xlsx)$/i.test(a.filename))icon='fa-file-excel';else if(/\.(zip|rar|7z)$/i.test(a.filename))icon='fa-file-archive';else if(/\.(mp3|wav|ogg)$/i.test(a.filename))icon='fa-file-audio';else if(/\.(mp4|mov|avi)$/i.test(a.filename))icon='fa-file-video';return'<div class="attachment-item" onclick="openAttachment('+idx+')"><i class="fas '+icon+'"></i><div class="att-info"><div class="att-name">'+esc(a.filename)+'</div><div class="att-size">'+formatSize(a.size)+'</div></div></div>'}).join('')+'</div></div>'}var isTrash=folder==='trash';if(window.innerWidth>768){document.querySelectorAll('.email-item').forEach(function(x){x.classList.remove('selected')});if(el)el.classList.add('selected');document.getElementById('email-view').innerHTML='<div class="view-head"><button class="view-back" onclick="closeDesktopView()"><i class="fas fa-arrow-left"></i></button><div class="view-subj">'+esc(e.subject||'(No subject)')+'</div><div class="view-actions">'+(isTrash?'<button class="view-btn restore" onclick="restoreCurrent()" title="Restore"><i class="fas fa-undo"></i></button>':'')+'<button class="view-btn" onclick="starCurrent()"><i class="fas fa-star"></i></button><button class="view-btn" onclick="deleteCurrent()"><i class="fas fa-trash"></i></button></div></div><div class="view-meta"><div class="view-av" style="background:'+col+'">'+i+'</div><div class="view-info"><div class="name">'+esc(name)+'</div><div class="email">'+esc(e.from_email||'')+'</div><div class="time">'+tm+'</div></div></div><div class="view-body"><div class="view-content">'+body+'</div>'+attHtml+'</div>'+(isTrash?'':'<div class="reply-box"><div class="reply-toolbar"><button onclick="rExec(\'bold\')"><i class="fas fa-bold"></i></button><button onclick="rExec(\'italic\')"><i class="fas fa-italic"></i></button><button onclick="rExec(\'underline\')"><i class="fas fa-underline"></i></button><div class="sep"></div><button onclick="rExec(\'insertUnorderedList\')"><i class="fas fa-list-ul"></i></button><button onclick="rInsertLink()"><i class="fas fa-link"></i></button></div><div class="reply-input" id="reply-input" contenteditable="true" data-placeholder="Write a reply..."></div><div class="reply-footer"><div class="reply-attach"><button onclick="rAttach()"><i class="fas fa-paperclip"></i></button><button onclick="rImage()"><i class="fas fa-image"></i></button></div><button class="reply-send" onclick="sendReply()"><i class="fas fa-paper-plane"></i> Send</button></div></div>')}else{document.getElementById('ev-title').textContent=e.subject||'(No subject)';document.getElementById('ev-star').className=(e.is_starred?'fas':'far')+' fa-star';var restoreBtn=document.getElementById('ev-restore');if(restoreBtn)restoreBtn.style.display=isTrash?'flex':'none';document.getElementById('ev-body').innerHTML='<div class="ev-subject">'+esc(e.subject||'(No subject)')+'</div><div class="ev-meta"><div class="ev-av" style="background:'+col+'">'+i+'</div><div class="ev-info"><div class="name">'+esc(name)+'</div><div class="email">'+esc(e.from_email||'')+'</div><div class="time">'+tm+'</div></div></div><div class="ev-content">'+body+'</div>'+attHtml;var evFooter=document.getElementById('ev-footer');if(isTrash){evFooter.innerHTML='<button class="restore" onclick="restoreCurrent()"><i class="fas fa-undo"></i> Restore</button><button onclick="deleteCurrent()"><i class="fas fa-trash"></i> Delete Forever</button>'}else{evFooter.innerHTML='<button onclick="replyEmail()"><i class="fas fa-reply"></i> Reply</button><button class="primary" onclick="fwdEmail()"><i class="fas fa-share"></i> Forward</button>'}document.getElementById('ev-panel').classList.add('show')}})}
function openAttachment(idx){currentAttIdx=idx;var a=currentAttachments[idx];if(!a)return;var url='/api/attachment/'+a.id,isImg=/\.(jpg|jpeg|png|gif|webp|bmp)$/i.test(a.filename),isPdf=/\.pdf$/i.test(a.filename),content=document.getElementById('lightbox-content');if(isImg){content.innerHTML='<img src="'+url+'" alt="'+esc(a.filename)+'">'} else if(isPdf){content.innerHTML='<iframe src="'+url+'" type="application/pdf"></iframe>'}else{content.innerHTML='<div class="pdf-fallback"><i class="fas fa-file"></i><h3>'+esc(a.filename)+'</h3><p>'+formatSize(a.size)+'</p><a href="'+url+'" download="'+esc(a.filename)+'"><i class="fas fa-download"></i> Download</a></div>'}document.getElementById('lightbox').classList.add('show')}
function closeLightbox(){document.getElementById('lightbox').classList.remove('show')}
function prevAttachment(){currentAttIdx=(currentAttIdx-1+currentAttachments.length)%currentAttachments.length;openAttachment(currentAttIdx)}
function nextAttachment(){currentAttIdx=(currentAttIdx+1)%currentAttachments.length;openAttachment(currentAttIdx)}
function downloadAttachment(){var a=currentAttachments[currentAttIdx];if(a)window.open('/api/attachment/'+a.id+'?download=1','_blank')}
function closeDesktopView(){viewingEmail=false;updateFabVisibility();document.getElementById('email-view').innerHTML='<div class="view-empty"><i class="far fa-envelope-open"></i><p>Select an email to read</p></div>';document.querySelectorAll('.email-item').forEach(function(x){x.classList.remove('selected')});current=null}
function closeEV(){viewingEmail=false;updateFabVisibility();document.getElementById('ev-panel').classList.remove('show')}
function starEmail(id){fetch('/api/email/'+id+'/star',{method:'POST',credentials:'same-origin'})}
function starCurrent(){if(current){starEmail(current.id);current.is_starred=!current.is_starred;toast(current.is_starred?'Starred':'Unstarred','success')}}
function deleteEmail(id){return fetch('/api/email/'+id+'/delete',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({})}).then(function(r){return r.json()}).then(function(d){if(d.success){emails=emails.filter(function(e){return e.id!=id});return true}return false}).catch(function(){return false})}
function restoreEmail(id){return fetch('/api/email/'+id+'/restore',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({})}).then(function(r){return r.json()}).then(function(d){if(d.success){emails=emails.filter(function(e){return e.id!=id});return true}return false}).catch(function(){return false})}
function restoreCurrent(){if(!current)return;restoreEmail(current.id).then(function(ok){if(ok){closeEV();closeDesktopView();renderEmails(emails);current=null;toast('Email restored to inbox','success')}else toast('Restore failed','error')})}
function deleteCurrent(){if(!current)return;if(folder==='trash'){showConfirm('Permanently delete this email?','This action cannot be undone.',function(){permanentDelete(current.id).then(function(ok){if(ok){closeEV();closeDesktopView();emails=emails.filter(function(e){return e.id!=current.id});renderEmails(emails);current=null;toast('Email permanently deleted','success')}else toast('Delete failed','error')})})}else{deleteEmail(current.id).then(function(ok){if(ok){closeEV();closeDesktopView();renderEmails(emails);current=null;toast('Email moved to trash','success')}else toast('Delete failed','error')})}}
function permanentDelete(id){return fetch('/api/email/'+id+'/permanent-delete',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({})}).then(function(r){return r.json()}).then(function(d){return d.success}).catch(function(){return false})}
function emptyTrash(){showConfirm('Empty trash?','All emails in trash will be permanently deleted. This cannot be undone.',function(){toast('Emptying trash...','info');fetch('/api/emails/empty-trash',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({})}).then(function(r){return r.json()}).then(function(d){if(d.success){emails=[];renderEmpty();toast('Trash emptied','success')}else toast(d.error||'Failed','error')}).catch(function(){toast('Network error','error')})})}
function showConfirm(title,msg,onConfirm){document.getElementById('confirm-title').innerHTML='<i class="fas fa-exclamation-triangle"></i> '+title;document.getElementById('confirm-msg').textContent=msg;document.getElementById('confirm-modal').classList.add('show');document.getElementById('confirm-yes').onclick=function(){document.getElementById('confirm-modal').classList.remove('show');if(onConfirm)onConfirm()}}
function closeConfirm(){document.getElementById('confirm-modal').classList.remove('show')}
function replyEmail(){if(!current)return;closeEV();openCompose({type:'reply',to:current.from_email,subj:'Re: '+(current.subject||''),body:'<br><br><hr><p>On '+fmtTime(current.received_at)+', '+esc(current.from_email)+' wrote:</p><blockquote style="border-left:3px solid #ccc;padding-left:12px;margin-left:0;color:#666">'+(current.body_text||'')+'</blockquote>'})}
function fwdEmail(){if(!current)return;closeEV();openCompose({type:'fwd',to:'',subj:'Fwd: '+(current.subject||''),body:'<br><br><hr><p>---------- Forwarded ----------</p><p>From: '+esc(current.from_email)+'</p><p>Subject: '+esc(current.subject)+'</p><br>'+(current.body_text||'')})}
function openCompose(data){var d=data||{};document.getElementById('compose-title').textContent=d.type==='reply'?'Reply':d.type==='fwd'?'Forward':'New Message';document.getElementById('compose-to').value=d.to||'';document.getElementById('compose-subj').value=d.subj||'';document.getElementById('compose-editor').innerHTML=d.body||'';document.getElementById('compose-overlay').classList.add('show')}
function closeCompose(){document.getElementById('compose-overlay').classList.remove('show');cancelRecording()}
function execCmd(cmd,val){document.execCommand(cmd,false,val||null)}
function insertLink(){var url=prompt('Enter URL:');if(url)execCmd('createLink',url)}
function insertImage(){var url=prompt('Enter image URL:');if(url)execCmd('insertImage',url)}
function rExec(cmd){document.execCommand(cmd,false,null)}
function rInsertLink(){var url=prompt('Enter URL:');if(url)document.execCommand('createLink',false,url)}
function rAttach(){var i=document.createElement('input');i.type='file';i.onchange=function(){toast('Attached: '+i.files[0].name,'success')};i.click()}
function rImage(){var i=document.createElement('input');i.type='file';i.accept='image/*';i.onchange=function(){toast('Image attached','success')};i.click()}
function sendEmail(){var to=document.getElementById('compose-to').value.trim(),subj=document.getElementById('compose-subj').value.trim(),body=document.getElementById('compose-editor').innerHTML.trim();if(!to||to.indexOf('@')<0){toast('Enter valid email','error');return}if(!subj){toast('Enter subject','error');return}toast('Sending...','info');fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({to:to,subject:subj,body:body,is_html:true})}).then(function(r){return r.json()}).then(function(d){if(d.success){toast('Email sent!','success');closeCompose();document.getElementById('compose-to').value='';document.getElementById('compose-subj').value='';document.getElementById('compose-editor').innerHTML=''}else toast(d.error||'Failed','error')}).catch(function(){toast('Network error','error')})}
function sendReply(){if(!current)return;var body=document.getElementById('reply-input');if(!body||!body.innerHTML.trim()){toast('Write a message','error');return}toast('Sending...','info');fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({to:current.from_email,subject:'Re: '+(current.subject||''),body:body.innerHTML,is_html:true})}).then(function(r){return r.json()}).then(function(d){if(d.success){toast('Reply sent!','success');body.innerHTML=''}else toast(d.error||'Failed','error')}).catch(function(){toast('Network error','error')})}
function saveDraft(){var to=document.getElementById('compose-to').value.trim(),subj=document.getElementById('compose-subj').value.trim(),body=document.getElementById('compose-editor').innerHTML.trim();fetch('/api/drafts',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({to:to,subject:subj,body:body})}).then(function(r){return r.json()}).then(function(d){if(d.success){toast('Draft saved!','success');closeCompose()}else toast(d.error||'Failed','error')}).catch(function(){toast('Network error','error')})}
function loadContacts(){fetch('/api/contacts',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){if(d.success&&d.contacts)contacts=d.contacts}).catch(function(){})}
function searchContacts(q){var box=document.getElementById('contact-suggestions');if(q.length<2){box.classList.remove('show');return}var m=contacts.filter(function(c){return c.email.toLowerCase().indexOf(q.toLowerCase())>=0}).slice(0,5);if(m.length){box.innerHTML=m.map(function(c){var i=c.email.charAt(0).toUpperCase(),col=getColor(i);return'<div class="contact-sug" onclick="selectContact(\''+c.email+'\')"><div class="sug-av" style="background:'+col+'">'+i+'</div><div class="sug-email">'+esc(c.email)+'</div></div>'}).join('');box.classList.add('show')}else box.classList.remove('show')}
function selectContact(email){document.getElementById('compose-to').value=email;document.getElementById('contact-suggestions').classList.remove('show');document.getElementById('compose-subj').focus()}
function attachFile(){var i=document.createElement('input');i.type='file';i.onchange=function(){toast('Attached: '+i.files[0].name,'success')};i.click()}
function attachImage(){var i=document.createElement('input');i.type='file';i.accept='image/*';i.onchange=function(){toast('Image attached','success')};i.click()}
function attachVideo(){var i=document.createElement('input');i.type='file';i.accept='video/*';i.onchange=function(){toast('Video attached','success')};i.click()}
function startRecording(){navigator.mediaDevices.getUserMedia({audio:true}).then(function(stream){mediaRecorder=new MediaRecorder(stream);audioChunks=[];mediaRecorder.ondataavailable=function(e){audioChunks.push(e.data)};mediaRecorder.start();recordingTime=0;document.getElementById('audio-recorder').classList.add('show');recordingInterval=setInterval(function(){recordingTime++;var m=Math.floor(recordingTime/60),s=recordingTime%60;document.getElementById('audio-time').textContent=m+':'+(s<10?'0':'')+s},1000);toast('Recording...','info')}).catch(function(){toast('Microphone denied','error')})}
function pauseRecording(){if(mediaRecorder&&mediaRecorder.state==='recording'){mediaRecorder.pause();toast('Paused','info')}else if(mediaRecorder&&mediaRecorder.state==='paused'){mediaRecorder.resume();toast('Resumed','info')}}
function doneRecording(){if(mediaRecorder){mediaRecorder.stop();mediaRecorder.onstop=function(){toast('Voice recorded','success')};clearInterval(recordingInterval);document.getElementById('audio-recorder').classList.remove('show')}}
function cancelRecording(){if(mediaRecorder){try{mediaRecorder.stop()}catch(e){}}clearInterval(recordingInterval);document.getElementById('audio-recorder').classList.remove('show');audioChunks=[]}
function startPolling(){pollInterval=setInterval(function(){if(folder==='inbox'){fetch('/api/emails/unread-count',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){if(d.success){var cnt=d.unread_count||0;var el=document.getElementById('inbox-cnt');if(el)el.textContent=cnt||'';var badge=document.getElementById('notif-badge');if(badge){badge.textContent=cnt;badge.style.display=cnt>0?'flex':'none'}}}).catch(function(){});fetch('/api/emails?folder=inbox&per_page=50',{credentials:'same-origin'}).then(function(r){return r.json()}).then(function(d){if(d.success&&d.emails){var newCount=d.emails.length;if(newCount>lastEmailCount&&lastEmailCount>0){var diff=newCount-lastEmailCount;emails=d.emails;renderEmails(emails);playSound();toast(diff+' new email'+(diff>1?'s':'')+'!','info')}lastEmailCount=newCount}}).catch(function(){})}},3000)}
function mobileNav(f,btn){document.querySelectorAll('.mob-nav button').forEach(function(b){b.classList.remove('on')});if(btn)btn.classList.add('on');loadFolder(f)}
function openTools(){document.getElementById('tools-overlay').classList.add('show')}
function closeTools(){document.getElementById('tools-overlay').classList.remove('show')}
function showNotifications(){toast('No new notifications','info')}
function closeChatMain(){
    document.getElementById('chat-main').classList.remove('show');
    activeChat=null;
}

function startChatPoll(){
    stopChatPoll();
    chatPoll=setInterval(function(){
        if(activeChat)fetchChatHistory(activeChat);
        loadChats();
        updateOnlineStatus();
    },800);
}

function stopChatPoll(){
    if(chatPoll){clearInterval(chatPoll);chatPoll=null;}
}

function updateOnlineStatus(){
    fetch('/api/chat/online',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({})}).catch(function(){});
}

function loadChats(){
    fetch('/api/chat/conversations',{credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(d){
        if(d.success&&d.conversations){
            d.conversations.forEach(function(c){
                var existing=chats[c.email]||{};
                chats[c.email]={
                    email:c.email,
                    messages:existing.messages||[],
                    unread:c.unread||0,
                    last_message:c.last_message,
                    is_online:c.is_online||false
                };
                onlineUsers[c.email]=c.is_online||false;
            });
            renderChatList();
            if(activeChat)updateChatHeader();
        }
    }).catch(function(){});
}

function renderChatList(filter){
    var el=document.getElementById('chat-list'),keys=Object.keys(chats);
    if(filter==='unread')keys=keys.filter(function(k){return chats[k].unread>0});
    if(filter==='groups')keys=[];
    if(!keys.length){
        el.innerHTML='<div class="chat-empty-list"><i class="fas fa-comments"></i><p>No conversations yet</p><span>Start a new chat above</span></div>';
        return;
    }
    keys.sort(function(a,b){
        var ta=chats[a].last_message_at||0,tb=chats[b].last_message_at||0;
        return new Date(tb)-new Date(ta);
    });
    el.innerHTML=keys.map(function(k){
        var c=chats[k],i=k.charAt(0).toUpperCase(),col=getColor(i);
        var lastMsg=c.last_message||(c.messages&&c.messages.length?c.messages[c.messages.length-1].text:'');
        var on=onlineUsers[k];
        var name=k.split('@')[0].replace(/\./g,' ');
        name=name.charAt(0).toUpperCase()+name.slice(1);
        return '<div class="chat-item'+(activeChat===k?' active':'')+'" onclick="selectChat(\''+k+'\')">'+
            '<div class="chat-av" style="background:'+col+'">'+i+'<span class="online-dot '+(on?'on':'')+'"></span></div>'+
            '<div class="chat-info"><div class="chat-name">'+esc(name)+'</div><div class="chat-preview">'+esc((lastMsg||'').substring(0,32))+(lastMsg&&lastMsg.length>32?'...':'')+'</div></div>'+
            (c.unread?'<div class="chat-badge">'+c.unread+'</div>':'')+
        '</div>';
    }).join('');
}

function selectChat(email){
    activeChat=email;
    if(!chats[email])chats[email]={email:email,messages:[],is_online:false};
    chats[email].unread=0;
    renderChatList();
    
    var i=email.charAt(0).toUpperCase(),col=getColor(i),on=onlineUsers[email];
    var name=email.split('@')[0].replace(/\./g,' ');
    name=name.charAt(0).toUpperCase()+name.slice(1);
    
    var chatMain=document.getElementById('chat-main');
    chatMain.innerHTML=
        '<div class="chat-header">'+
            '<button class="chat-back" onclick="closeChatMain()"><i class="fas fa-arrow-left"></i></button>'+
            '<div class="chat-av" style="background:'+col+'">'+i+'</div>'+
            '<div class="chat-header-info"><div class="chat-header-name">'+esc(name)+'</div><div class="chat-header-status '+(on?'online':'offline')+'" id="chat-status">'+(on?'Online':'Offline')+'</div></div>'+
            '<button class="chat-more" onclick="showChatOptions()"><i class="fas fa-ellipsis-v"></i></button>'+
        '</div>'+
        '<div class="chat-body" id="chat-messages"><div class="chat-loading"><i class="fas fa-spinner fa-spin"></i></div></div>'+
        '<div class="chat-footer">'+
            '<button class="chat-attach" onclick="chatAttach()"><i class="fas fa-plus"></i></button>'+
            '<input type="text" class="chat-input" id="chat-input" placeholder="Message..." onkeypress="if(event.key===\'Enter\')sendChatMsg()">'+
            '<button class="chat-send" onclick="sendChatMsg()"><i class="fas fa-paper-plane"></i></button>'+
        '</div>';
    
    if(window.innerWidth<=768)chatMain.classList.add('show');
    
    fetchChatHistory(email);
    fetch('/api/chat/mark-read',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({with:email})}).catch(function(){});
}

function updateChatHeader(){
    var statusEl=document.getElementById('chat-status');
    if(statusEl&&activeChat){
        var on=onlineUsers[activeChat];
        statusEl.textContent=on?'Online':'Offline';
        statusEl.className='chat-header-status '+(on?'online':'offline');
    }
}

function fetchChatHistory(email){
    fetch('/api/chat/history?with='+encodeURIComponent(email),{credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(d){
        if(d.success&&d.messages){
            var oldLen=chats[email].messages?chats[email].messages.length:0;
            chats[email].messages=d.messages.map(function(m){
                return{text:m.content,sent:m.sent_by_me,time:m.time,id:m.id};
            });
            if(chats[email].messages.length>oldLen&&oldLen>0){
                playSound();
            }
            renderChatMessages();
        }
    }).catch(function(){});
}

function renderChatMessages(){
    var el=document.getElementById('chat-messages');
    if(!el||!activeChat)return;
    var c=chats[activeChat];
    if(!c||!c.messages||!c.messages.length){
        el.innerHTML='<div class="chat-empty-msg"><i class="fas fa-hand-wave"></i><p>Say hello!</p></div>';
        return;
    }
    var wasAtBottom=el.scrollHeight-el.scrollTop-el.clientHeight<100;
    el.innerHTML=c.messages.map(function(m){
        return '<div class="msg '+(m.sent?'sent':'recv')+'">'+
            '<div class="msg-bubble">'+esc(m.text)+'</div>'+
            '<div class="msg-meta">'+(m.time||'')+(m.sent?' <i class="fas fa-check-double"></i>':'')+'</div>'+
        '</div>';
    }).join('');
    if(wasAtBottom||c.messages.length<20)el.scrollTop=el.scrollHeight;
}

function sendChatMsg(){
    var input=document.getElementById('chat-input'),text=input.value.trim();
    if(!text||!activeChat)return;
    
    var now=new Date();
    var timeStr=now.getHours().toString().padStart(2,'0')+':'+now.getMinutes().toString().padStart(2,'0');
    
    if(!chats[activeChat].messages)chats[activeChat].messages=[];
    chats[activeChat].messages.push({text:text,sent:true,time:timeStr});
    input.value='';
    renderChatMessages();
    
    fetch('/api/chat/send',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({to:activeChat,message:text})
    }).then(function(r){return r.json()})
    .then(function(d){
        if(!d.success)toast('Failed to send','error');
    }).catch(function(){toast('Network error','error');});
}

function startNewChat(){
    var input=document.getElementById('chat-new-email'),email=input.value.trim().toLowerCase();
    if(!email||email.indexOf('@')<0){toast('Enter valid email','error');return;}
    if(!chats[email])chats[email]={email:email,messages:[],is_online:false};
    input.value='';
    renderChatList();
    selectChat(email);
}

function switchTab(tab,el){
    document.querySelectorAll('.chat-tab').forEach(function(t){t.classList.remove('on')});
    el.classList.add('on');
    renderChatList(tab==='all'?null:tab);
}

function chatAttach(){toast('Coming soon','info');}
function showChatOptions(){toast('Options coming soon','info');}
function openInvite(){document.getElementById('invite-modal').classList.add('show');}
function closeInvite(){document.getElementById('invite-modal').classList.remove('show');document.getElementById('invite-email').value='';}
function sendInvite(){var email=document.getElementById('invite-email').value.trim();if(!email||email.indexOf('@')<0){toast('Enter valid email','error');return;}toast('Invitation sent to '+email,'success');closeInvite();}

// ============ MULTI-SELECT MODE ============
var selectMode=false,selectedIds=[];

function initLongPress(){
    document.querySelectorAll('.email-item').forEach(function(item){
        var timer=null,moved=false;
        item.addEventListener('touchstart',function(e){
            moved=false;
            timer=setTimeout(function(){
                if(!moved){navigator.vibrate&&navigator.vibrate(50);enterSelectMode();toggleSelect(item);}
            },500);
        },{passive:true});
        item.addEventListener('touchmove',function(){moved=true;clearTimeout(timer);},{passive:true});
        item.addEventListener('touchend',function(){clearTimeout(timer);});
    });
}

function enterSelectMode(){
    if(selectMode)return;
    selectMode=true;selectedIds=[];
    document.body.classList.add('select-mode');
    showSelectBar();
}

function exitSelectMode(){
    selectMode=false;selectedIds=[];
    document.body.classList.remove('select-mode');
    document.querySelectorAll('.email-item.selected').forEach(function(el){el.classList.remove('selected');});
    hideSelectBar();
}

function toggleSelect(el){
    var id=parseInt(el.getAttribute('data-id'));
    if(el.classList.contains('selected')){
        el.classList.remove('selected');
        selectedIds=selectedIds.filter(function(x){return x!==id;});
    }else{
        el.classList.add('selected');
        selectedIds.push(id);
    }
    updateSelectBar();
    if(selectedIds.length===0)exitSelectMode();
}

function showSelectBar(){
    if(document.getElementById('select-bar'))return;
    var bar=document.createElement('div');
    bar.id='select-bar';bar.className='select-bar';
    bar.innerHTML='<button onclick="exitSelectMode()"><i class="fas fa-times"></i></button><span id="sel-count">0</span>'+(folder==='trash'?'<button onclick="restoreSelected()"><i class="fas fa-undo"></i></button>':'')+'<button onclick="deleteSelected()"><i class="fas fa-trash"></i></button>';
    document.body.appendChild(bar);
}

function hideSelectBar(){var bar=document.getElementById('select-bar');if(bar)bar.remove();}
function updateSelectBar(){var c=document.getElementById('sel-count');if(c)c.textContent=selectedIds.length+' selected';}

function deleteSelected(){
    if(!selectedIds.length)return;
    showConfirm('Delete '+selectedIds.length+' emails?','',function(){
        Promise.all(selectedIds.map(function(id){
            return fetch('/api/email/'+id+(folder==='trash'?'/permanent-delete':'/delete'),{method:'POST',credentials:'same-origin'});
        })).then(function(){
            emails=emails.filter(function(e){return selectedIds.indexOf(e.id)<0;});
            renderEmails(emails);exitSelectMode();
            toast('Deleted','success');
        });
    });
}

function restoreSelected(){
    if(!selectedIds.length)return;
    Promise.all(selectedIds.map(function(id){
        return fetch('/api/email/'+id+'/restore',{method:'POST',credentials:'same-origin'});
    })).then(function(){
        emails=emails.filter(function(e){return selectedIds.indexOf(e.id)<0;});
        renderEmails(emails);exitSelectMode();
        toast('Restored','success');
    });
}

var _origInitEmailEvents=initEmailEvents;
initEmailEvents=function(){
    _origInitEmailEvents();
    initLongPress();
    document.querySelectorAll('.email-item').forEach(function(item){
        item.addEventListener('click',function(e){
            if(selectMode){e.preventDefault();e.stopPropagation();toggleSelect(this);return false;}
        },true);
    });
};

// ============ KEYBOARD SHORTCUTS ============
document.addEventListener('keydown',function(e){
    if(e.target.tagName==='INPUT'||e.target.tagName==='TEXTAREA'||e.target.isContentEditable)return;
    if(e.key==='c')openCompose();
    if(e.key==='r'&&current)replyEmail();
    if(e.key==='?')toast('c=compose r=reply s=star #=delete','info');
});

console.log('SendBaba Mail loaded');

// ============ REAL-TIME CHAT SYSTEM ============
var chatPoll=null;

function openChat(){
    document.getElementById('chat-overlay').classList.add('show');
    loadChats();
    startChatPoll();
}

function closeChat(){
    document.getElementById('chat-overlay').classList.remove('show');
    if(window.innerWidth<=768)document.getElementById('chat-main').classList.remove('show');
    stopChatPoll();
    activeChat=null;
}

function closeChatMain(){
    document.getElementById('chat-main').classList.remove('show');
    activeChat=null;
}

function startChatPoll(){
    stopChatPoll();
    chatPoll=setInterval(function(){
        if(activeChat)fetchChatHistory(activeChat);
        loadChats();
    },800);
}

function stopChatPoll(){
    if(chatPoll){clearInterval(chatPoll);chatPoll=null;}
}

function loadChats(){
    fetch('/api/chat/conversations',{credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(d){
        if(d.success&&d.conversations){
            d.conversations.forEach(function(c){
                var existing=chats[c.email]||{};
                chats[c.email]={
                    email:c.email,
                    messages:existing.messages||[],
                    unread:c.unread||0,
                    last_message:c.last_message,
                    is_online:c.is_online||false
                };
                onlineUsers[c.email]=c.is_online||false;
            });
            renderChatList();
            if(activeChat)updateChatStatus();
        }
    }).catch(function(){});
}

function renderChatList(filter){
    var el=document.getElementById('chat-list'),keys=Object.keys(chats);
    if(filter==='unread')keys=keys.filter(function(k){return chats[k].unread>0});
    if(!keys.length){
        el.innerHTML='<div style="padding:40px;text-align:center;color:#64748b"><i class="fas fa-comments" style="font-size:40px;opacity:.3;display:block;margin-bottom:12px"></i>No conversations yet</div>';
        return;
    }
    el.innerHTML=keys.map(function(k){
        var c=chats[k],i=k.charAt(0).toUpperCase(),col=getColor(i);
        var lastMsg=c.last_message||(c.messages&&c.messages.length?c.messages[c.messages.length-1].text:'');
        var on=onlineUsers[k];
        var name=k.split('@')[0].replace(/\./g,' ');
        return '<div class="chat-item'+(activeChat===k?' on':'')+'" onclick="selectChat(\''+k+'\')">'+
            '<div class="chat-item-av" style="background:'+col+'">'+i+'<span class="status-dot '+(on?'online':'')+'"></span></div>'+
            '<div class="chat-item-info"><div class="chat-item-name">'+esc(name)+'</div>'+
            '<div class="chat-item-last">'+esc((lastMsg||'').substring(0,30))+'</div></div>'+
            (c.unread?'<div class="chat-item-unread">'+c.unread+'</div>':'')+
        '</div>';
    }).join('');
}

function selectChat(email){
    activeChat=email;
    if(!chats[email])chats[email]={email:email,messages:[],is_online:false};
    chats[email].unread=0;
    renderChatList();
    
    var i=email.charAt(0).toUpperCase(),col=getColor(i),on=onlineUsers[email];
    var name=email.split('@')[0].replace(/\./g,' ');
    
    document.getElementById('chat-main').innerHTML=
        '<div class="chat-main-head">'+
            '<button class="chat-back-btn" onclick="closeChatMain()"><i class="fas fa-arrow-left"></i></button>'+
            '<div class="chat-main-av" style="background:'+col+'">'+i+'</div>'+
            '<div class="chat-main-info"><div class="chat-main-name">'+esc(name)+'</div>'+
            '<div class="chat-main-status" id="chat-status">'+(on?'<span class="online">Online</span>':'<span class="offline">Offline</span>')+'</div></div>'+
            '<button onclick="closeChatMain()" class="chat-close-btn"><i class="fas fa-times"></i></button>'+
        '</div>'+
        '<div class="chat-messages" id="chat-messages"><div style="display:flex;justify-content:center;padding:40px"><i class="fas fa-spinner fa-spin"></i></div></div>'+
        '<div class="chat-input-area">'+
            '<input type="text" class="chat-input" id="chat-input" placeholder="Type a message..." onkeypress="if(event.key===\'Enter\')sendChatMsg()">'+
            '<button class="chat-send" onclick="sendChatMsg()"><i class="fas fa-paper-plane"></i></button>'+
        '</div>';
    
    if(window.innerWidth<=768)document.getElementById('chat-main').classList.add('show');
    
    // IMPORTANT: Fetch messages from server
    fetchChatHistory(email);
    
    // Mark as read
    fetch('/api/chat/mark-read',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({with:email})}).catch(function(){});
}

function updateChatStatus(){
    var el=document.getElementById('chat-status');
    if(el&&activeChat){
        var on=onlineUsers[activeChat];
        el.innerHTML=on?'<span class="online">Online</span>':'<span class="offline">Offline</span>';
    }
}

function fetchChatHistory(email){
    fetch('/api/chat/history?with='+encodeURIComponent(email),{credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(d){
        if(d.success&&d.messages){
            var oldLen=(chats[email].messages||[]).length;
            chats[email].messages=d.messages.map(function(m){
                return{text:m.content,sent:m.sent_by_me,time:m.time,id:m.id};
            });
            if(chats[email].messages.length>oldLen&&oldLen>0)playSound();
            renderChatMessages();
        }else{
            chats[email].messages=[];
            renderChatMessages();
        }
    }).catch(function(e){
        console.error('Chat fetch error:',e);
        renderChatMessages();
    });
}

function renderChatMessages(){
    var el=document.getElementById('chat-messages');
    if(!el||!activeChat)return;
    var c=chats[activeChat];
    if(!c||!c.messages||!c.messages.length){
        el.innerHTML='<div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#64748b;padding:40px;text-align:center"><i class="fas fa-comments" style="font-size:50px;opacity:.2;margin-bottom:16px"></i><p>No messages yet</p><p style="font-size:13px;margin-top:8px">Send a message to start chatting!</p></div>';
        return;
    }
    var wasAtBottom=el.scrollHeight-el.scrollTop-el.clientHeight<100;
    el.innerHTML=c.messages.map(function(m){
        return '<div class="chat-msg '+(m.sent?'sent':'recv')+'">'+
            '<div class="chat-bubble">'+esc(m.text)+'</div>'+
            '<div class="chat-time">'+(m.time||'')+(m.sent?' ✓✓':'')+'</div>'+
        '</div>';
    }).join('');
    if(wasAtBottom||c.messages.length<=20)el.scrollTop=el.scrollHeight;
}

function sendChatMsg(){
    var input=document.getElementById('chat-input'),text=input.value.trim();
    if(!text||!activeChat)return;
    
    var now=new Date();
    var timeStr=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2);
    
    if(!chats[activeChat].messages)chats[activeChat].messages=[];
    chats[activeChat].messages.push({text:text,sent:true,time:timeStr});
    input.value='';
    renderChatMessages();
    
    fetch('/api/chat/send',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body:JSON.stringify({to:activeChat,message:text})
    }).then(function(r){return r.json()})
    .then(function(d){if(!d.success)toast('Send failed','error');})
    .catch(function(){toast('Network error','error');});
}

function startNewChat(){
    var input=document.getElementById('chat-new-email'),email=input.value.trim().toLowerCase();
    if(!email||email.indexOf('@')<0){toast('Enter valid email','error');return;}
    if(!chats[email])chats[email]={email:email,messages:[],is_online:false};
    input.value='';
    renderChatList();
    selectChat(email);
}

function switchTab(tab,el){
    document.querySelectorAll('.chat-tab').forEach(function(t){t.classList.remove('on')});
    el.classList.add('on');
    renderChatList(tab==='all'?null:tab);
}

function openInvite(){document.getElementById('invite-modal').classList.add('show');}
function closeInvite(){document.getElementById('invite-modal').classList.remove('show');}
function sendInvite(){
    var email=document.getElementById('invite-email').value.trim();
    if(!email){toast('Enter email','error');return;}
    toast('Invite sent to '+email,'success');
    closeInvite();
}

console.log('Chat system loaded!');


// ============ VOICE MESSAGES - COMPLETE SYSTEM ============
var voiceRecorder=null,voiceStream=null,voiceChunks=[],voiceTimer=null,voiceSeconds=0,isVoiceRecording=false;
var currentAudio=null,currentAudioBtn=null;

// High quality audio recording
function startVoiceRecording(){
    if(isVoiceRecording)return;
    
    var constraints={
        audio:{
            echoCancellation:true,
            noiseSuppression:true,
            autoGainControl:true,
            sampleRate:48000,
            channelCount:1
        }
    };
    
    navigator.mediaDevices.getUserMedia(constraints)
    .then(function(stream){
        voiceStream=stream;
        isVoiceRecording=true;
        voiceChunks=[];
        voiceSeconds=0;
        
        // Try different formats for compatibility
        var options={mimeType:'audio/webm;codecs=opus'};
        if(!MediaRecorder.isTypeSupported(options.mimeType)){
            options={mimeType:'audio/webm'};
        }
        if(!MediaRecorder.isTypeSupported(options.mimeType)){
            options={mimeType:'audio/ogg;codecs=opus'};
        }
        if(!MediaRecorder.isTypeSupported(options.mimeType)){
            options={};
        }
        
        voiceRecorder=new MediaRecorder(stream,options);
        
        voiceRecorder.ondataavailable=function(e){
            if(e.data&&e.data.size>0)voiceChunks.push(e.data);
        };
        
        voiceRecorder.start(100);
        
        // Show recording UI
        showVoiceRecordingUI();
        
        voiceTimer=setInterval(function(){
            voiceSeconds++;
            updateVoiceTimer();
            // Max 5 minutes
            if(voiceSeconds>=300)sendVoiceRecording();
        },1000);
        
    }).catch(function(err){
        console.error('Mic error:',err);
        toast('Microphone access denied','error');
    });
}

function showVoiceRecordingUI(){
    var area=document.querySelector('.chat-input-area');
    if(!area)return;
    area.innerHTML=
        '<div class="voice-record-ui">'+
            '<button class="voice-cancel-btn" onclick="cancelVoiceRecording()"><i class="fas fa-trash"></i></button>'+
            '<div class="voice-record-indicator">'+
                '<span class="voice-record-dot"></span>'+
                '<span class="voice-record-time" id="voice-timer">0:00</span>'+
            '</div>'+
            '<div class="voice-waveform">'+
                '<span></span><span></span><span></span><span></span><span></span>'+
                '<span></span><span></span><span></span><span></span><span></span>'+
            '</div>'+
            '<button class="voice-send-btn" onclick="sendVoiceRecording()"><i class="fas fa-paper-plane"></i></button>'+
        '</div>';
}

function updateVoiceTimer(){
    var el=document.getElementById('voice-timer');
    if(el){
        var m=Math.floor(voiceSeconds/60);
        var s=voiceSeconds%60;
        el.textContent=m+':'+(s<10?'0':'')+s;
    }
}

function cancelVoiceRecording(){
    isVoiceRecording=false;
    clearInterval(voiceTimer);
    
    if(voiceRecorder&&voiceRecorder.state!=='inactive'){
        voiceRecorder.stop();
    }
    if(voiceStream){
        voiceStream.getTracks().forEach(function(t){t.stop();});
    }
    
    voiceChunks=[];
    restoreChatInputUI();
}

function sendVoiceRecording(){
    if(!isVoiceRecording||!voiceRecorder)return;
    
    isVoiceRecording=false;
    clearInterval(voiceTimer);
    
    var duration=voiceSeconds;
    
    voiceRecorder.onstop=function(){
        if(voiceStream){
            voiceStream.getTracks().forEach(function(t){t.stop();});
        }
        
        if(voiceChunks.length===0){
            toast('Recording failed','error');
            restoreChatInputUI();
            return;
        }
        
        var blob=new Blob(voiceChunks,{type:voiceRecorder.mimeType||'audio/webm'});
        
        if(blob.size<1000){
            toast('Recording too short','error');
            restoreChatInputUI();
            return;
        }
        
        uploadVoiceMessage(blob,duration);
        restoreChatInputUI();
    };
    
    if(voiceRecorder.state!=='inactive'){
        voiceRecorder.stop();
    }else{
        restoreChatInputUI();
    }
}

function uploadVoiceMessage(blob,duration){
    // Add temp message
    var tempId='voice_'+Date.now();
    var now=new Date();
    var timeStr=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2);
    
    if(!chats[activeChat])chats[activeChat]={email:activeChat,messages:[]};
    if(!chats[activeChat].messages)chats[activeChat].messages=[];
    
    chats[activeChat].messages.push({
        id:tempId,
        text:'🎤 Sending...',
        sent:true,
        time:timeStr,
        type:'audio',
        audio_url:URL.createObjectURL(blob),
        duration:duration,
        uploading:true
    });
    renderChatMessages();
    
    // Upload
    var formData=new FormData();
    formData.append('audio',blob,'voice.webm');
    formData.append('to',activeChat);
    formData.append('duration',duration.toString());
    
    fetch('/api/chat/send-audio',{
        method:'POST',
        credentials:'same-origin',
        body:formData
    })
    .then(function(r){return r.json();})
    .then(function(d){
        if(d.success){
            // Update temp message
            var msgs=chats[activeChat].messages;
            for(var i=0;i<msgs.length;i++){
                if(msgs[i].id===tempId){
                    msgs[i].id=d.message_id;
                    msgs[i].text='🎤 Voice message';
                    msgs[i].audio_url=d.audio_url;
                    msgs[i].uploading=false;
                    break;
                }
            }
            renderChatMessages();
            toast('Voice sent!','success');
        }else{
            toast(d.error||'Upload failed','error');
            // Remove temp message
            chats[activeChat].messages=chats[activeChat].messages.filter(function(m){return m.id!==tempId;});
            renderChatMessages();
        }
    })
    .catch(function(e){
        console.error('Upload error:',e);
        toast('Upload failed','error');
        chats[activeChat].messages=chats[activeChat].messages.filter(function(m){return m.id!==tempId;});
        renderChatMessages();
    });
}

function restoreChatInputUI(){
    var area=document.querySelector('.chat-input-area');
    if(!area)return;
    area.innerHTML=
        '<button class="chat-mic-btn" onclick="startVoiceRecording()"><i class="fas fa-microphone"></i></button>'+
        '<input type="text" class="chat-input" id="chat-input" placeholder="Type a message..." onkeypress="if(event.key===\'Enter\')sendChatMsg()">'+
        '<button class="chat-send-btn" onclick="sendChatMsg()"><i class="fas fa-paper-plane"></i></button>';
}

// Audio Playback System
function playVoice(url,btn,msgId){
    var icon=btn.querySelector('i');
    var progress=btn.parentElement.querySelector('.voice-progress');
    var timeEl=btn.parentElement.querySelector('.voice-current-time');
    
    // If same audio is playing, toggle pause
    if(currentAudio&&currentAudioBtn===btn){
        if(currentAudio.paused){
            currentAudio.play();
            icon.className='fas fa-pause';
        }else{
            currentAudio.pause();
            icon.className='fas fa-play';
        }
        return;
    }
    
    // Stop any playing audio
    if(currentAudio){
        currentAudio.pause();
        currentAudio.currentTime=0;
        if(currentAudioBtn){
            currentAudioBtn.querySelector('i').className='fas fa-play';
            var oldProgress=currentAudioBtn.parentElement.querySelector('.voice-progress');
            if(oldProgress)oldProgress.style.width='0%';
        }
    }
    
    // Create new audio
    currentAudio=new Audio(url);
    currentAudioBtn=btn;
    
    currentAudio.onloadstart=function(){
        icon.className='fas fa-spinner fa-spin';
    };
    
    currentAudio.oncanplay=function(){
        icon.className='fas fa-pause';
        currentAudio.play();
    };
    
    currentAudio.ontimeupdate=function(){
        if(progress&&currentAudio.duration){
            var pct=(currentAudio.currentTime/currentAudio.duration)*100;
            progress.style.width=pct+'%';
        }
        if(timeEl){
            var t=Math.floor(currentAudio.currentTime);
            var m=Math.floor(t/60);
            var s=t%60;
            timeEl.textContent=m+':'+(s<10?'0':'')+s;
        }
    };
    
    currentAudio.onended=function(){
        icon.className='fas fa-play';
        if(progress)progress.style.width='0%';
        if(timeEl)timeEl.textContent='0:00';
        currentAudio=null;
        currentAudioBtn=null;
    };
    
    currentAudio.onerror=function(e){
        console.error('Audio error:',e);
        icon.className='fas fa-play';
        toast('Cannot play audio','error');
        currentAudio=null;
        currentAudioBtn=null;
    };
}

function forwardVoice(audioUrl,duration){
    // Show forward modal
    var contacts=Object.keys(chats).filter(function(e){return e!==activeChat;});
    
    if(contacts.length===0){
        toast('No contacts to forward to','error');
        return;
    }
    
    var modal=document.createElement('div');
    modal.className='forward-modal';
    modal.id='forward-modal';
    modal.innerHTML=
        '<div class="forward-box">'+
            '<div class="forward-head"><h3>Forward Voice Message</h3><button onclick="closeForwardModal()"><i class="fas fa-times"></i></button></div>'+
            '<div class="forward-list" id="forward-list">'+
                contacts.map(function(c){
                    var name=c.split('@')[0].replace(/\./g,' ');
                    var initial=c.charAt(0).toUpperCase();
                    return '<div class="forward-item" onclick="doForwardVoice(\''+c+'\',\''+audioUrl+'\','+duration+')">'+
                        '<div class="forward-av" style="background:'+getColor(initial)+'">'+initial+'</div>'+
                        '<span>'+esc(name)+'</span>'+
                    '</div>';
                }).join('')+
            '</div>'+
        '</div>';
    document.body.appendChild(modal);
    setTimeout(function(){modal.classList.add('show');},10);
}

function closeForwardModal(){
    var modal=document.getElementById('forward-modal');
    if(modal){
        modal.classList.remove('show');
        setTimeout(function(){modal.remove();},200);
    }
}

function doForwardVoice(toEmail,audioUrl,duration){
    closeForwardModal();
    
    // Fetch the audio and re-upload
    fetch(audioUrl,{credentials:'same-origin'})
    .then(function(r){return r.blob();})
    .then(function(blob){
        var formData=new FormData();
        formData.append('audio',blob,'voice.webm');
        formData.append('to',toEmail);
        formData.append('duration',duration.toString());
        
        return fetch('/api/chat/send-audio',{
            method:'POST',
            credentials:'same-origin',
            body:formData
        });
    })
    .then(function(r){return r.json();})
    .then(function(d){
        if(d.success){
            toast('Voice forwarded to '+toEmail.split('@')[0],'success');
        }else{
            toast('Forward failed','error');
        }
    })
    .catch(function(){
        toast('Forward failed','error');
    });
}

// Override renderChatMessages for voice support
var _baseRenderChatMessages=typeof renderChatMessages==='function'?renderChatMessages:function(){};
renderChatMessages=function(){
    var el=document.getElementById('chat-messages');
    if(!el||!activeChat)return;
    
    var c=chats[activeChat];
    if(!c||!c.messages||!c.messages.length){
        el.innerHTML='<div class="chat-empty"><i class="fas fa-comments"></i><p>No messages yet</p><span>Send a message to start the conversation</span></div>';
        return;
    }
    
    var wasAtBottom=el.scrollHeight-el.scrollTop-el.clientHeight<100;
    
    el.innerHTML=c.messages.map(function(m,idx){
        var isAudio=m.type==='audio'&&m.audio_url;
        var content;
        
        if(isAudio){
            var dur=m.duration||0;
            var mins=Math.floor(dur/60);
            var secs=dur%60;
            var durStr=mins+':'+(secs<10?'0':'')+secs;
            
            content=
                '<div class="voice-bubble">'+
                    '<button class="voice-play-btn" onclick="playVoice(\''+m.audio_url+'\',this,'+m.id+')"><i class="fas fa-play"></i></button>'+
                    '<div class="voice-wave-display">'+
                        '<div class="voice-progress-bar"><div class="voice-progress"></div></div>'+
                        '<div class="voice-meta"><span class="voice-current-time">0:00</span><span class="voice-total-time">'+durStr+'</span></div>'+
                    '</div>'+
                    '<button class="voice-fwd-btn" onclick="forwardVoice(\''+m.audio_url+'\','+dur+')" title="Forward"><i class="fas fa-share"></i></button>'+
                '</div>';
        }else{
            content='<div class="chat-bubble">'+esc(m.text)+'</div>';
        }
        
        return '<div class="chat-msg '+(m.sent?'sent':'recv')+'" data-id="'+m.id+'">'+
            content+
            '<div class="chat-meta">'+(m.time||'')+(m.sent?' <i class="fas fa-check-double"></i>':'')+'</div>'+
        '</div>';
    }).join('');
    
    if(wasAtBottom||c.messages.length<=20)el.scrollTop=el.scrollHeight;
};

// Override selectChat to include mic button
var _baseSelectChat=typeof selectChat==='function'?selectChat:function(){};
selectChat=function(email){
    activeChat=email;
    if(!chats[email])chats[email]={email:email,messages:[],is_online:false};
    chats[email].unread=0;
    renderChatList();
    
    var i=email.charAt(0).toUpperCase(),col=getColor(i),on=onlineUsers[email]||false;
    var name=email.split('@')[0].replace(/\./g,' ');
    
    document.getElementById('chat-main').innerHTML=
        '<div class="chat-main-head">'+
            '<button class="chat-back-btn" onclick="closeChatMain()"><i class="fas fa-arrow-left"></i></button>'+
            '<div class="chat-main-av" style="background:'+col+'">'+i+'</div>'+
            '<div class="chat-main-info"><div class="chat-main-name">'+esc(name)+'</div>'+
            '<div class="chat-main-status" id="chat-status">'+(on?'<span class="online">Online</span>':'<span class="offline">Offline</span>')+'</div></div>'+
            '<button class="chat-close-btn" onclick="closeChatMain()"><i class="fas fa-times"></i></button>'+
        '</div>'+
        '<div class="chat-messages" id="chat-messages"><div class="chat-loading"><i class="fas fa-spinner fa-spin"></i></div></div>'+
        '<div class="chat-input-area">'+
            '<button class="chat-mic-btn" onclick="startVoiceRecording()"><i class="fas fa-microphone"></i></button>'+
            '<input type="text" class="chat-input" id="chat-input" placeholder="Type a message..." onkeypress="if(event.key===\'Enter\')sendChatMsg()">'+
            '<button class="chat-send-btn" onclick="sendChatMsg()"><i class="fas fa-paper-plane"></i></button>'+
        '</div>';
    
    if(window.innerWidth<=768)document.getElementById('chat-main').classList.add('show');
    
    fetchChatHistory(email);
    fetch('/api/chat/mark-read',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({with:email})}).catch(function(){});
};

// Override fetchChatHistory for voice support
var _baseFetchChatHistory=typeof fetchChatHistory==='function'?fetchChatHistory:function(){};
fetchChatHistory=function(email){
    fetch('/api/chat/history?with='+encodeURIComponent(email),{credentials:'same-origin'})
    .then(function(r){return r.json()})
    .then(function(d){
        if(d.success&&d.messages){
            var oldLen=(chats[email].messages||[]).length;
            chats[email].messages=d.messages.map(function(m){
                return{
                    id:m.id,
                    text:m.content,
                    sent:m.sent_by_me,
                    time:m.time,
                    type:m.type||'text',
                    audio_url:m.audio_url,
                    duration:m.duration||0
                };
            });
            if(chats[email].messages.length>oldLen&&oldLen>0)playSound();
            renderChatMessages();
        }else{
            chats[email].messages=[];
            renderChatMessages();
        }
    }).catch(function(e){
        console.error('Chat fetch error:',e);
        chats[email].messages=[];
        renderChatMessages();
    });
};

console.log('Voice messaging system loaded!');
