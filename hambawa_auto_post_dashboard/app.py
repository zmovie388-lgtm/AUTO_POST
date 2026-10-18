import os, json, sqlite3, asyncio, threading, logging
from functools import wraps
from urllib.parse import urlparse
from dotenv import load_dotenv
from flask import Flask, jsonify, request, session, redirect, url_for, render_template
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, MessageHandler, ChatMemberHandler, ContextTypes, filters

load_dotenv()
TOKEN=os.getenv('BOT_TOKEN','').strip(); ADMIN_RAW=os.getenv('ADMIN_ID','').strip(); PASSWORD=os.getenv('DASHBOARD_PASSWORD','').strip()
DB=os.getenv('DATABASE_PATH','bot_data.sqlite3'); PORT=int(os.getenv('PORT','8080'))
if not TOKEN: raise RuntimeError('Set BOT_TOKEN in .env')
if not ADMIN_RAW.isdigit(): raise RuntimeError('ADMIN_ID must be your numeric Telegram user ID')
if not PASSWORD: raise RuntimeError('Set DASHBOARD_PASSWORD in .env')
ADMIN_ID=int(ADMIN_RAW); logging.basicConfig(level=logging.INFO); log=logging.getLogger('hambawa')
web=Flask(__name__); web.secret_key=os.getenv('FLASK_SECRET_KEY','change-me-before-deploying')
web.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
bot_app=None; bot_loop=None

def conn():
    c=sqlite3.connect(DB,timeout=30); c.row_factory=sqlite3.Row; return c

def init_db():
    with conn() as c:
        c.execute('CREATE TABLE IF NOT EXISTS groups(chat_id INTEGER PRIMARY KEY,title TEXT,enabled INTEGER DEFAULT 1)')
        c.execute('CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS sent(chat_id INTEGER PRIMARY KEY,message_id INTEGER)')
        c.execute('CREATE TABLE IF NOT EXISTS buttons(id INTEGER PRIMARY KEY AUTOINCREMENT,label TEXT,url TEXT,ord INTEGER)')
def get(k,d=''):
    with conn() as c:
        r=c.execute('SELECT value FROM settings WHERE key=?',(k,)).fetchone(); return r['value'] if r else d
def put(k,v):
    with conn() as c: c.execute('INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',(k,str(v)))
def template():
    try: return json.loads(get('template_json',''))
    except Exception: return None
def groups():
    with conn() as c: return c.execute('SELECT * FROM groups ORDER BY title').fetchall()
def buttons():
    with conn() as c: return c.execute('SELECT * FROM buttons ORDER BY ord,id').fetchall()
def markup():
    b=buttons(); return InlineKeyboardMarkup([[InlineKeyboardButton(x['label'],url=x['url'])] for x in b]) if b else None
def save_group(cid,title):
    with conn() as c: c.execute('INSERT INTO groups(chat_id,title,enabled) VALUES(?,?,1) ON CONFLICT(chat_id) DO UPDATE SET title=excluded.title,enabled=1',(cid,title))
def set_sent(cid,mid):
    with conn() as c: c.execute('INSERT INTO sent(chat_id,message_id) VALUES(?,?) ON CONFLICT(chat_id) DO UPDATE SET message_id=excluded.message_id',(cid,mid))
def sent_id(cid):
    with conn() as c:
        r=c.execute('SELECT message_id FROM sent WHERE chat_id=?',(cid,)).fetchone(); return r['message_id'] if r else None
def kick_broadcast():
    if bot_app and bot_loop and bot_loop.is_running(): asyncio.run_coroutine_threadsafe(broadcast_template(bot_app),bot_loop)
def auth(fn):
    @wraps(fn)
    def inner(*a,**kw):
        if not session.get('ok'): return jsonify(ok=False,error='Login required'),401
        return fn(*a,**kw)
    return inner

@web.route('/login',methods=['GET','POST'])
def login():
    error=''
    if request.method=='POST':
        if request.form.get('password','')==PASSWORD: session['ok']=True; return redirect('/')
        error='Incorrect password'
    return render_template('login.html',error=error)
@web.get('/')
def home(): return render_template('index.html') if session.get('ok') else redirect(url_for('login'))
@web.post('/logout')
def logout(): session.clear(); return redirect('/login')
@web.get('/api/status')
@auth
def api_status():
    t=template(); return jsonify(ok=True,active=get('active','1')=='1',has_post=bool(t),kind=t.get('kind','') if t else '',preview=((t.get('text') or t.get('caption') or '')[:180]) if t else '',groups=[dict(chat_id=g['chat_id'],title=g['title'],enabled=bool(g['enabled'])) for g in groups()],buttons=[dict(label=b['label'],url=b['url']) for b in buttons()])
@web.post('/api/toggle')
@auth
def toggle():
    a=(request.get_json(silent=True) or {}).get('active')
    if not isinstance(a,bool): return jsonify(ok=False,error='Invalid active value'),400
    put('active','1' if a else '0')
    if a: kick_broadcast()
    return jsonify(ok=True)
@web.post('/api/post-now')
@auth
def post_now(): kick_broadcast(); return jsonify(ok=True)
@web.post('/api/clear-post')
@auth
def clear_post(): put('template_json',''); return jsonify(ok=True)
@web.post('/api/buttons')
@auth
def save_buttons():
    items=(request.get_json(silent=True) or {}).get('buttons',[])
    if not isinstance(items,list) or len(items)>20: return jsonify(ok=False,error='Maximum 20 buttons'),400
    clean=[]
    for x in items:
        label=str(x.get('label','')).strip()[:64]; url=str(x.get('url','')).strip()
        if not label and not url: continue
        p=urlparse(url)
        if not label or p.scheme not in ('https','http') or not p.netloc: return jsonify(ok=False,error='Each button needs a label and valid http/https URL'),400
        clean.append((label,url))
    with conn() as c:
        c.execute('DELETE FROM buttons'); c.executemany('INSERT INTO buttons(label,url,ord) VALUES(?,?,?)',[(a,b,i) for i,(a,b) in enumerate(clean)])
    return jsonify(ok=True,count=len(clean))
@web.post('/api/group/<int:cid>')
@auth
def group_toggle(cid):
    e=(request.get_json(silent=True) or {}).get('enabled')
    if not isinstance(e,bool): return jsonify(ok=False,error='Invalid value'),400
    with conn() as c: c.execute('UPDATE groups SET enabled=? WHERE chat_id=?',(1 if e else 0,cid))
    return jsonify(ok=True)

async def send_post(bot,cid,t,m):
    k=t['kind']; text=t.get('text',''); cap=t.get('caption',''); fid=t.get('file_id'); rm=m
    if k=='text': return await bot.send_message(cid,text,reply_markup=rm)
    methods={'photo':bot.send_photo,'video':bot.send_video,'document':bot.send_document,'animation':bot.send_animation,'audio':bot.send_audio,'voice':bot.send_voice}
    if k in methods: return await methods[k](chat_id=cid,**{k:fid},caption=cap or None,reply_markup=rm)
    raise ValueError('Unsupported post type')
async def broadcast_template(application):
    if get('active','1')!='1': return
    t=template()
    if not t: return
    for g in groups():
        if not g['enabled']: continue
        cid=int(g['chat_id']); old=sent_id(cid)
        if old:
            try: await application.bot.delete_message(cid,old)
            except TelegramError as e: log.warning('Old post delete failed in %s: %s',cid,e)
        try:
            m=await send_post(application.bot,cid,t,markup()); set_sent(cid,m.message_id)
        except Exception as e:
            log.exception('Post failed for %s',cid)
            try: await application.bot.send_message(ADMIN_ID,f"⚠️ {g['title']} වෙත post කරන්න බැරි වුණා: {str(e)[:500]}")
            except TelegramError: pass
        await asyncio.sleep(.15)
async def repeat_job(ctx): await broadcast_template(ctx.application)
async def start(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id==ADMIN_ID:
        await update.effective_message.reply_text('HAMBAWA AUTO POST BOT\n\nමේ private chat එකට Text/Photo/Video/Document එකක් යවලා template එක set කරන්න. Dashboard එකෙන් buttons manage කරන්න.\n/status /stop /resume /groups')
    else: await update.effective_message.reply_text('Private admin bot.')
async def status(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id==ADMIN_ID: await update.effective_message.reply_text(f"Auto post: {'ON' if get('active','1')=='1' else 'OFF'}\nSaved post: {'Yes' if template() else 'No'}\nGroups: {len(groups())}\nInterval: 10 minutes")
async def stop(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id==ADMIN_ID: put('active','0'); await update.effective_message.reply_text('⏸ Auto posting stopped.')
async def resume(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id==ADMIN_ID: put('active','1'); await update.effective_message.reply_text('▶ Auto posting resumed.'); await broadcast_template(ctx.application)
async def group_list(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user and update.effective_user.id==ADMIN_ID:
        gs=groups(); await update.effective_message.reply_text('\n'.join(f"{g['title']} — {g['chat_id']}" for g in gs) if gs else 'No groups saved yet.')
async def membership(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    x=update.my_chat_member
    if not x or x.chat.type not in ('group','supergroup'): return
    s=x.new_chat_member.status; cid=x.chat.id; title=x.chat.title or str(cid)
    if s=='administrator':
        save_group(cid,title)
        try: await ctx.bot.send_message(ADMIN_ID,f'✅ Group auto-saved: {title}\nID: {cid}')
        except TelegramError: pass
    elif s in ('left','kicked'):
        with conn() as c: c.execute('DELETE FROM groups WHERE chat_id=?',(cid,)); c.execute('DELETE FROM sent WHERE chat_id=?',(cid,))
async def receive_template(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user; m=update.effective_message
    if not u or u.id!=ADMIN_ID or not m or m.chat.type!='private': return
    t=None
    if m.text: t={'kind':'text','text':m.text}
    elif m.photo: t={'kind':'photo','file_id':m.photo[-1].file_id,'caption':m.caption or ''}
    elif m.video: t={'kind':'video','file_id':m.video.file_id,'caption':m.caption or ''}
    elif m.document: t={'kind':'document','file_id':m.document.file_id,'caption':m.caption or ''}
    elif m.animation: t={'kind':'animation','file_id':m.animation.file_id,'caption':m.caption or ''}
    elif m.audio: t={'kind':'audio','file_id':m.audio.file_id,'caption':m.caption or ''}
    elif m.voice: t={'kind':'voice','file_id':m.voice.file_id,'caption':m.caption or ''}
    if not t: await m.reply_text('Text, Photo, Video, Document, Animation, Audio හෝ Voice එකක් යවන්න.'); return
    put('template_json',json.dumps(t,ensure_ascii=False)); put('active','1')
    await m.reply_text('✅ Post template saved. Dashboard එකෙන් Inline URL buttons සකස් කරන්න. දැන් post කරන්න උත්සාහ කරනවා; ඉන්පසු විනාඩි 10කට වරක් repeat වෙනවා.')
    await broadcast_template(ctx.application)
async def post_init(application):
    global bot_loop
    bot_loop=asyncio.get_running_loop()
    application.job_queue.run_repeating(repeat_job,interval=600,first=600)
def run_web(): web.run(host='0.0.0.0',port=PORT,debug=False,use_reloader=False,threaded=True)
def main():
    global bot_app
    init_db(); threading.Thread(target=run_web,daemon=True).start()
    bot_app=Application.builder().token(TOKEN).post_init(post_init).build()
    bot_app.add_handler(CommandHandler('start',start)); bot_app.add_handler(CommandHandler('status',status)); bot_app.add_handler(CommandHandler('stop',stop)); bot_app.add_handler(CommandHandler('resume',resume)); bot_app.add_handler(CommandHandler('groups',group_list))
    bot_app.add_handler(ChatMemberHandler(membership,ChatMemberHandler.MY_CHAT_MEMBER))
    bot_app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND,receive_template))
    log.info('Dashboard on port %s; Telegram bot polling started',PORT); bot_app.run_polling(allowed_updates=Update.ALL_TYPES)
if __name__=='__main__': main()
