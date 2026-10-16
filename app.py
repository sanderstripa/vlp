import argparse
import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
from core import ROOT, DATA, NO_WINDOW, Cue, Pipeline, export_audio, srt

def worker(args):
    def emit(e): print(json.dumps(e,ensure_ascii=False),flush=True)
    p=Pipeline(args.media,args.subtitle,track=args.track,emit=emit)
    # Real wall-clock sampling includes native child processes, unlike process_time.
    done=threading.Event()
    def sample():
        import psutil
        proc=psutil.Process(); known={}
        while not done.wait(1):
            processes=[proc]+proc.children(recursive=True); rss=0; cpu=0
            for item in processes:
                try:
                    t=item.cpu_times(); val=t.user+t.system
                    cpu+=max(0,val-known.get(item.pid,val)); known[item.pid]=val
                    rss+=item.memory_info().rss
                except psutil.Error:pass
            p.event('resources',rss_mb=round(rss/1048576,1),cpu_percent_one_core=round(cpu*100,1),vram_mb=0,gpu='disabled')
    threading.Thread(target=sample,daemon=True).start()
    try:p.execute()
    except Exception:return 1
    finally:done.set()
    return 0

def launch(smoke=None,smoke_full=False):
    import tkinter as tk
    from tkinter import ttk,filedialog,messagebox
    from player import MPV,Narration
    class App:
        def __init__(self):
            self.root=tk.Tk(); self.root.title('LocalDub · офлайн-плеер'); self.root.geometry('1060x710'); self.root.minsize(850,550)
            self.root.configure(bg='#17191d'); self.events=queue.Queue(); self.proc=None; self.cues=[]; self.media=None
            self.complete=False; self.preparing=False; self.translation=False; self.ready=0.; self.cache=None; self.start_at=0.
            self.want_pause=True; self.tracks=[]; self.duration=0.; self.auto_started=False
            self.last_wait=None; self.last_sync_log=0.; self.ai_clicked=None; self.first_audible_recorded=False
            self.closed=False
            style=ttk.Style(); style.theme_use('clam')
            style.configure('.',background='#22252b',foreground='#eeeeef',font=('Segoe UI',10),borderwidth=0)
            style.configure('TButton',padding=(10,6)); style.configure('TCombobox',fieldbackground='#30343a',foreground='#eeeeef')
            style.configure('TButton',background='#2b3038',bordercolor='#2b3038',lightcolor='#2b3038',darkcolor='#2b3038',relief='flat')
            style.map('TButton',background=[('active','#394353')])
            style.configure('TCombobox',bordercolor='#363d48',lightcolor='#363d48',darkcolor='#363d48',arrowcolor='#bac6d8',arrowsize=12)
            style.configure('Horizontal.TScale',background='#91b5ff',troughcolor='#343942',bordercolor='#343942',lightcolor='#91b5ff',darkcolor='#91b5ff',gripcount=0,sliderlength=12)
            style.configure('Horizontal.TProgressbar',background='#91b5ff',troughcolor='#343942',bordercolor='#343942',lightcolor='#91b5ff',darkcolor='#91b5ff')
            style.map('TCombobox',fieldbackground=[('readonly','#30343a')],foreground=[('readonly','#eeeeef')])
            top=ttk.Frame(self.root); top.pack(fill='x',padx=12,pady=10)
            ttk.Button(top,text='Открыть видео',command=self.open).pack(side='left')
            self.title=ttk.Label(top,text='LOCALDUB',anchor='w'); self.title.pack(side='left',padx=14,fill='x',expand=True)
            ttk.Button(top,text='Компоненты',command=self.components).pack(side='right')
            self.canvas=tk.Frame(self.root,bg='#08090b'); self.canvas.pack(fill='both',expand=True,padx=12)
            self.root.update_idletasks()
            try:self.video=MPV(self.canvas.winfo_id()); self.voice=MPV(); self.narration=Narration(self.voice)
            except Exception as e:
                messagebox.showerror('Компоненты плеера',str(e)+'\nЗапустите установку компонентов по инструкции.'); self.root.destroy(); return
            self.timeline=ttk.Scale(self.root,from_=0,to=1,command=lambda _:None); self.timeline.pack(fill='x',padx=12,pady=5)
            self.timeline.bind('<ButtonRelease-1>',lambda e:self.seek(float(self.timeline.get())))
            self.dragging=False; self.timeline.bind('<ButtonPress-1>',lambda e:setattr(self,'dragging',True))
            row=ttk.Frame(self.root); row.pack(fill='x',padx=12,pady=3)
            ttk.Button(row,text='▶ / Ⅱ',command=self.pause).pack(side='left')
            self.clock=ttk.Label(row,text='00:00 / 00:00'); self.clock.pack(side='left',padx=10)
            ttk.Label(row,text='Оригинал').pack(side='left'); self.original=ttk.Scale(row,from_=0,to=100,command=lambda v:self.video.set('volume',v)); self.original.set(35); self.original.pack(side='left',fill='x',expand=True,padx=6)
            ttk.Label(row,text='Озвучка').pack(side='left'); vol=ttk.Scale(row,from_=0,to=100,command=lambda v:self.voice.set('volume',v)); vol.set(85); vol.pack(side='left',fill='x',expand=True,padx=6)
            row=ttk.Frame(self.root); row.pack(fill='x',padx=12,pady=5)
            ttk.Label(row,text='Аудио').pack(side='left'); self.audio=ttk.Combobox(row,state='readonly',width=24); self.audio.pack(side='left',padx=5); self.audio.bind('<<ComboboxSelected>>',self.audio_change)
            ttk.Label(row,text='Субтитры').pack(side='left'); self.subs=ttk.Combobox(row,state='readonly',width=24); self.subs.pack(side='left',padx=5); self.subs.bind('<<ComboboxSelected>>',self.sub_change)
            ttk.Button(row,text='Открыть SRT',command=self.add_sub).pack(side='left',padx=5)
            row=ttk.Frame(self.root); row.pack(fill='x',padx=12,pady=5)
            self.lang=ttk.Combobox(row,state='readonly',values=['Английский → Русский'],width=24); self.lang.current(0); self.lang.pack(side='left')
            self.mode=ttk.Combobox(row,state='readonly',values=['Быстрый · буфер 10 с','Полностью заранее'],width=23); self.mode.current(0); self.mode.pack(side='left',padx=8)
            self.translate_button=ttk.Button(row,text='Перевести',command=self.translate); self.translate_button.pack(side='left')
            ttk.Button(row,text='Остановить ИИ',command=self.stop_ai).pack(side='left',padx=5)
            ttk.Button(row,text='Сохранить SRT + WAV',command=self.export).pack(side='right')
            self.progress=ttk.Progressbar(self.root,maximum=100); self.progress.pack(fill='x',padx=12,pady=4)
            self.status=ttk.Label(self.root,text='Откройте локальный файл. ИИ: английский → русский, CPU.',anchor='w'); self.status.pack(fill='x',padx=12,pady=(2,10))
            self.root.bind('<space>',lambda e:self.pause() if e.widget.winfo_class() not in ('TCombobox','TEntry') else None)
            self.root.protocol('WM_DELETE_WINDOW',self.close); self.root.after(50,self.tick)
            if smoke:self.root.after(500,self.smoke_start)
            self.root.mainloop()

        def error(self,text):
            if smoke:
                self.smoke_log['error']=str(text); self.root.after(50,self.smoke_finish)
            else:messagebox.showerror('LocalDub',str(text),parent=self.root)
        def open(self):
            name=filedialog.askopenfilename(filetypes=[('Видео','*.mkv *.mp4 *.avi *.mov *.webm *.m4v *.ts'),('Все файлы','*.*')])
            if not name:return
            self.open_path(name)
        def open_path(self,name):
            self.stop_ai(); self.media=Path(name); self.sidecar=self.media.with_suffix('.srt')
            if not self.sidecar.exists():self.sidecar=None
            self.cues=[]; self.translation=False; self.ready=0; self.complete=False; self.title['text']=self.media.name
            try:
                self.video.command('loadfile',name); self.video.set('pause',False); self.want_pause=False
                self.root.after(500,self.refresh_tracks)
            except Exception as e:self.error(e)
        def refresh_tracks(self):
            self.tracks=self.video.get('track-list',[]) or []
            self.audios=[t for t in self.tracks if t['type']=='audio']; self.subtitles=[t for t in self.tracks if t['type']=='sub']
            self.audio['values']=[f"{t['id']} · {t.get('lang','?')} · {t.get('title',t.get('codec',''))}" for t in self.audios]
            if self.audios:self.audio.current(next((i for i,t in enumerate(self.audios) if t.get('selected')),0))
            self.subs['values']=['Выключены']+[f"{t['id']} · {t.get('lang','?')} · {t.get('title',t.get('codec',''))}" for t in self.subtitles]
            self.subs.current(next((i+1 for i,t in enumerate(self.subtitles) if t.get('selected')),0))
            if not self.video.get('duration'):self.status['text']='Не удалось открыть видео: неподдерживаемый или повреждённый файл.'
        def audio_change(self,e=None):
            if self.preparing:self.stop_ai()
            self.translation=False; self.narration.stop(); self.video.set('aid',self.audios[self.audio.current()]['id'])
        def sub_change(self,e=None):self.video.set('sid','no' if self.subs.current()==0 else self.subtitles[self.subs.current()-1]['id'])
        def add_sub(self):
            name=filedialog.askopenfilename(filetypes=[('UTF-8 SRT','*.srt')])
            if name:
                self.sidecar=Path(name)
                if self.media:self.video.command('sub-add',name,'select'); self.root.after(200,self.refresh_tracks)
        def pause(self):
            if self.media:self.want_pause=not self.want_pause
        def seek(self,value):
            self.dragging=False
            if self.media:
                self.narration.stop(); self.video.command('seek',value,'absolute+exact')
        def stop_ai(self):
            if self.proc and self.proc.poll() is None:
                import psutil
                try:
                    parent=psutil.Process(self.proc.pid)
                    for child in parent.children(recursive=True):
                        try:child.kill()
                        except psutil.Error:pass
                    parent.kill()
                except psutil.Error:pass
                self.proc.wait(timeout=10)
            self.proc=None; self.preparing=False; self.translation=False
            if hasattr(self,'narration'):self.narration.stop()
            self.events=queue.Queue()
        def translate(self):
            if not self.media:return
            self.stop_ai(); self.cues=[]; self.ready=0; self.complete=False; self.cache=None
            self.translation=True; self.preparing=True; self.auto_started=False
            self.ai_clicked=time.perf_counter(); self.first_audible_recorded=False; self.last_wait=None
            self.start_at=float(self.video.get('time-pos',0) or 0); self.want_pause=True
            args=[sys.executable] if getattr(sys,'frozen',False) else [sys.executable,'-X','utf8',str(ROOT/'app.py')]
            args+=['--worker','--media',str(self.media),'--track',str(max(0,self.audio.current()))]
            # Explicit external SRT wins. Otherwise extract a selected/source-language text subtitle.
            subtitle=self.sidecar
            selected=self.subtitles[self.subs.current()-1] if self.subs.current()>0 else None
            candidate=selected or next((t for t in self.subtitles if t.get('lang') in ('en','eng')),None)
            if subtitle:args+=['--subtitle',str(subtitle)]
            elif candidate and candidate.get('codec') in ('subrip','ass','ssa','webvtt','mov_text'):
                args+=['--extract-sub',str(candidate['id'])]
            q=self.events
            self.proc=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding='utf-8',errors='replace',creationflags=NO_WINDOW)
            process=self.proc
            def read():
                for line in process.stdout:
                    try:q.put(json.loads(line))
                    except ValueError:pass
            def errors():
                text=process.stderr.read(); code=process.wait()
                if code:q.put({'stage':'error','message':text[-2400:] or f'Процесс ИИ завершился: {code}'})
            threading.Thread(target=read,daemon=True).start(); threading.Thread(target=errors,daemon=True).start()
        def export(self):
            if not self.complete:self.error('Дождитесь полного перевода для экспорта.'); return
            dest=filedialog.asksaveasfilename(defaultextension='.wav',filetypes=[('Озвучка WAV','*.wav')])
            if not dest:return
            cues=list(self.cues); duration=self.duration; q=self.events
            def work():
                try:
                    export_audio(cues,duration,dest); Path(dest).with_suffix('.srt').write_text(srt(cues),'utf-8-sig')
                    q.put({'stage':'export_done','message':'Сохранены WAV и SRT. Оригинальное видео не изменено.'})
                except Exception as e:q.put({'stage':'export_error','message':str(e)})
            threading.Thread(target=work,daemon=True).start()
        def components(self):
            if self.preparing:self.error('Остановите перевод перед установкой компонентов.'); return
            if not messagebox.askyesno('Однократная загрузка','Загрузить локальные компоненты и модели (около 500 МБ)? Нужен интернет только на этом шаге.'):return
            q=self.events
            def work():
                try:
                    from setup_components import install
                    install(report=lambda text:q.put({'stage':'install','message':text}))
                except Exception as e:q.put({'stage':'export_error','message':str(e)})
            threading.Thread(target=work,daemon=True).start()
        def tick(self):
            labels={'fingerprint':'Проверка файла и кэша','load_asr':'Загрузка распознавания','asr':'Распознавание',
                    'translation':'Перевод','tts':'Синтез речи','extract_audio':'Подготовка аудио','cache_hit':'Чтение кэша'}
            try:
                for _ in range(80):
                    try:event=self.events.get_nowait()
                    except queue.Empty:break
                    stage=event['stage']
                    if stage=='cue_ready':
                        c=Cue(**event['cue']); self.cues.append(c); self.ready=max(self.ready,c.end)
                    elif stage=='buffer':self.ready=event['ready_until']
                    elif stage=='complete':
                        self.complete=True; self.preparing=False; self.ready=event['duration']; self.cache=event['cache']
                        self.status['text']='Перевод готов · локальный кэш сохранён'; self.progress['value']=100
                    elif stage=='error':
                        if not self.preparing:continue
                        self.preparing=False; self.translation=False; self.narration.stop(); self.want_pause=True; self.error(event.get('message','Ошибка ИИ'))
                    elif stage in ('export_done','install'):self.status['text']=event['message']
                    elif stage=='export_error':self.error(event['message'])
                    elif stage in labels:self.status['text']=labels[stage]
                    elif stage=='resources':self.root.title(f"LocalDub · ИИ {event['rss_mb']:.0f} МБ · CPU {event['cpu_percent_one_core']:.0f}% одного ядра")
                if self.media:
                    pos=float(self.video.get('time-pos',0) or 0); self.duration=float(self.video.get('duration',0) or 0)
                    self.timeline.configure(to=max(1,self.duration))
                    if not self.dragging:self.timeline.set(pos)
                    def clock(t):return f'{int(t)//60:02}:{int(t)%60:02}'
                    self.clock['text']=f'{clock(pos)} / {clock(self.duration)}'
                    if self.translation and not self.auto_started:
                        enough=self.complete or (self.mode.current()==0 and self.ready>=self.start_at+10)
                        if enough:self.auto_started=True; self.want_pause=False
                    waiting=self.translation and not self.complete and (not self.auto_started or pos+.25>=self.ready)
                    paused=self.want_pause or waiting
                    self.video.set('pause',paused)
                    if self.translation:
                        self.narration.sync(pos,paused,self.cues)
                        if waiting!=self.last_wait:
                            self.playlog('buffer_wait',waiting=waiting,position=pos,ready_until=self.ready); self.last_wait=waiting
                        voice_pos=self.voice.get('time-pos')
                        if self.narration.current and not paused and voice_pos is not None:
                            if not self.first_audible_recorded:
                                self.playlog('first_voice_playback',latency_s=time.perf_counter()-self.ai_clicked,
                                             position=pos,backend=self.voice.get('current-ao'))
                                self.first_audible_recorded=True
                            if time.monotonic()-self.last_sync_log>1:
                                cue=next(c for c in self.cues if c.audio==self.narration.current)
                                self.playlog('sync',position=pos,drift_s=float(voice_pos)-(pos-cue.start))
                                self.last_sync_log=time.monotonic()
                    if waiting:self.status['text']=f'Ожидание перевода · готово {clock(self.ready)} · видео на паузе'
                    if self.preparing:self.progress['value']=100*self.ready/max(1,self.duration)
            except Exception as e:self.status['text']='Ошибка воспроизведения: '+str(e)
            self.root.after(50,self.tick)
        def playlog(self,stage,**data):
            DATA.mkdir(parents=True,exist_ok=True)
            with (DATA/'playback.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps({'stage':stage,'time':time.time(),**data},ensure_ascii=False)+'\n')
        def close(self):
            if self.closed:return
            self.closed=True
            for callback in self.root.tk.call('after','info'):self.root.after_cancel(callback)
            self.stop_ai(); self.voice.close(); self.video.close(); self.root.destroy()
        def smoke_start(self):
            if smoke_full:self.mode.current(1)
            self.smoke_log={}; self.open_path(str(ROOT/'test-video.mp4')); self.root.after(900,self.smoke_translate)
        def smoke_translate(self):
            self.smoke_log['video_position_before_ai']=self.video.get('time-pos')
            self.smoke_log['audio_backend']=self.video.get('current-ao')
            self.translate(); self.smoke_deadline=time.monotonic()+90; self.root.after(200,self.smoke_wait)
        def smoke_wait(self):
            if self.complete:
                self.smoke_log['translated_cues']=len(self.cues); self.smoke_log['cache']=self.cache
                self.want_pause=False; self.seek(2.3); self.root.after(700,self.smoke_pause)
            elif time.monotonic()>self.smoke_deadline:
                self.smoke_log['error']='translation timeout'; self.smoke_finish()
            else:self.root.after(200,self.smoke_wait)
        def smoke_pause(self):
            self.smoke_log['voice_backend']=self.voice.get('current-ao'); self.smoke_log['narration_file']=self.narration.current
            self.want_pause=True; self.root.after(200,self.smoke_hold)
        def smoke_hold(self):
            self.smoke_pos=float(self.video.get('time-pos',0)); self.root.after(400,self.smoke_seek)
        def smoke_seek(self):
            self.smoke_log['pause_drift_s']=abs(float(self.video.get('time-pos',0))-self.smoke_pos)
            self.seek(4.8); self.root.after(600,self.smoke_finish)
        def smoke_finish(self):
            self.smoke_log['position_after_seek']=self.video.get('time-pos'); self.smoke_log['voice_after_seek']=self.narration.current
            self.smoke_log['voice_paused']=self.voice.get('pause'); self.smoke_log['video_paused']=self.video.get('pause')
            from core import atomic
            atomic(Path(smoke),self.smoke_log)
            try:
                from PIL import ImageGrab
                self.root.lift(); self.root.update()
                x=self.root.winfo_rootx(); y=self.root.winfo_rooty()
                ImageGrab.grab(bbox=(x,y,x+self.root.winfo_width(),y+self.root.winfo_height())).save(Path(smoke).with_suffix('.png'))
            except Exception:pass
            self.close()
    App()

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--worker',action='store_true'); parser.add_argument('--setup',action='store_true')
    parser.add_argument('--media'); parser.add_argument('--subtitle'); parser.add_argument('--track',type=int,default=0); parser.add_argument('--extract-sub',type=int)
    parser.add_argument('--smoke',help='Write automated GUI smoke evidence JSON and PNG')
    parser.add_argument('--smoke-full',action='store_true')
    args=parser.parse_args()
    if args.worker and sys.stdout is None:
        # Windowed Python has no sys.stdout even when the parent supplies a pipe.
        import os,ctypes,msvcrt,io
        handle=ctypes.windll.kernel32.GetStdHandle
        handle.argtypes=[ctypes.c_ulong]; handle.restype=ctypes.c_void_p
        fd=msvcrt.open_osfhandle(handle(-11 & 0xffffffff),os.O_WRONLY)
        sys.stdout=io.TextIOWrapper(os.fdopen(fd,'wb',closefd=False),encoding='utf-8',write_through=True)
    if args.worker and sys.stdout is not None:
        sys.stdout.reconfigure(encoding='utf-8',newline='\n',write_through=True)
    if args.setup:
        from setup_components import install
        install()
    elif args.worker:
        if args.extract_sub is not None:
            from core import probe,run
            DATA.mkdir(parents=True,exist_ok=True)
            dest=DATA/f'embedded-{__import__("os").getpid()}.srt'
            try:
                # mpv track IDs are 1-based per type; ffmpeg subtitle selectors are 0-based.
                run([ROOT/'native/ffmpeg.exe','-v','error','-y','-i',args.media,'-map',f'0:s:{args.extract_sub-1}',dest])
                args.subtitle=str(dest); result=worker(args)
            except Exception as e:
                print(json.dumps({'stage':'error','message':str(e)},ensure_ascii=False),flush=True); result=1
            finally:dest.unlink(missing_ok=True)
            sys.exit(result)
        sys.exit(worker(args))
    else:launch(args.smoke,args.smoke_full)
