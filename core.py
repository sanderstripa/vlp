import os
# Ivy Bridge has AVX, not AVX2. Never request CUDA or an AVX2-only dispatch.
import ctypes
_avx = os.name != 'nt' or bool(ctypes.windll.kernel32.IsProcessorFeaturePresent(39))
os.environ.setdefault('CT2_FORCE_CPU_ISA', 'AVX' if _avx else 'GENERIC')
os.environ.setdefault('CT2_USE_MKL', '0')
os.environ.setdefault('OMP_NUM_THREADS', '4')
os.environ.setdefault('HF_HUB_OFFLINE', '1')
os.environ.setdefault('HF_HUB_DISABLE_TELEMETRY', '1')
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time
import wave
from dataclasses import dataclass, asdict

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent
DATA = Path(os.environ['LOCALDUB_DATA']) if os.environ.get('LOCALDUB_DATA') else Path(os.environ.get('LOCALAPPDATA', str(ROOT))) / 'LocalDub'
NO_WINDOW = 0x08000000 if os.name == 'nt' else 0

def run(args, timeout=180, **kwargs):
    p = subprocess.run([str(x) for x in args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       creationflags=NO_WINDOW, timeout=timeout, **kwargs)
    if p.returncode: raise RuntimeError(p.stderr.decode('utf-8', 'replace')[-2400:] or f'Exit {p.returncode}')
    return p.stdout

def atomic(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), 'utf-8'); tmp.replace(path)

def digest(path):
    with Path(path).open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

def probe(path):
    return json.loads(run([ROOT/'native/ffprobe.exe', '-v','error','-show_format','-show_streams','-of','json', path]))

@dataclass
class Cue:
    start: float
    end: float
    text: str
    translated: str = ''
    audio: str = ''

def parse_srt(text):
    def seconds(t):
        h,m,s = t.replace(',', '.').split(':'); return int(h)*3600+int(m)*60+float(s)
    cues=[]
    for block in re.split(r'\n\s*\n', text.replace('\r','').strip()):
        lines=block.splitlines()
        n=next((i for i,l in enumerate(lines) if '-->' in l), None)
        if n is None: continue
        a,b=lines[n].split('-->')
        start,end=seconds(a.strip()),seconds(b.strip().split()[0])
        body=re.sub(r'<[^>]*>|\{[^}]*\}', '', ' '.join(lines[n+1:])).strip()
        if body and end>start>=0: cues.append(Cue(start,end,body))
    return sorted(cues, key=lambda c:c.start)

def stamp(t):
    t=max(0,round(t*1000)); h,t=divmod(t,3600000); m,t=divmod(t,60000); s,ms=divmod(t,1000)
    return f'{h:02}:{m:02}:{s:02},{ms:03}'

def srt(cues, translated=True):
    return '\n\n'.join(f'{i+1}\n{stamp(c.start)} --> {stamp(c.end)}\n{c.translated if translated else c.text}' for i,c in enumerate(cues))+'\n'

class Cancelled(Exception): pass

class Pipeline:
    """Single sequential CPU worker. All published audio is immutable and atomic."""
    def __init__(self, media, subtitle=None, source='en', target='ru', track=0, emit=lambda e:None, cache_root=None):
        if (source,target) != ('en','ru'): raise ValueError('В MVP установлена только пара английский → русский.')
        self.media=Path(media); self.subtitle=Path(subtitle) if subtitle else None
        self.source=source; self.target=target; self.track=int(track); self.emit=emit
        self.stop=threading.Event(); self.cues=[]; self.ready_until=0.; self.duration=0.; self.cache=None
        self.cache_root=Path(cache_root or DATA/'cache'); self.started=time.perf_counter(); self.first=False
        self.mt=None; self.asr=None; self.sp=None

    def check(self):
        if self.stop.is_set(): raise Cancelled()

    def event(self, stage, **data):
        event={'stage':stage,'elapsed_s':round(time.perf_counter()-self.started,3),**data}
        self.emit(event)
        if self.cache:
            with (self.cache/'metrics.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(event,ensure_ascii=False)+'\n')

    def timed(self, stage, fn, media_s=0):
        self.check(); before=time.perf_counter(); cpu=time.process_time()
        self.event(stage)
        result=fn(); elapsed=time.perf_counter()-before
        import psutil
        proc=psutil.Process(); children=proc.children(recursive=True)
        rss=proc.memory_info().rss+sum(p.memory_info().rss for p in children if p.is_running())
        self.event(stage+'_done', seconds=round(elapsed,4), media_s=media_s,
                   rtf=round(elapsed/media_s,4) if media_s else None,
                   cpu_seconds=time.process_time()-cpu, rss_mb=round(rss/1048576,1),
                   gpu='disabled', vram_mb=0)
        return result

    def translate(self,text):
        if self.mt is None:
            import ctranslate2
            import sentencepiece
            folder=ROOT/'models/translation'
            self.mt=ctranslate2.Translator(str(folder), device='cpu',compute_type='int8', inter_threads=1,intra_threads=4)
            candidates=list(folder.rglob('source.spm'))+list(folder.rglob('sentencepiece.model'))
            if not candidates: raise RuntimeError('В модели перевода нет source.spm')
            self.sp=sentencepiece.SentencePieceProcessor(model_file=str(candidates[0]))
            tgt=folder/'target.spm'
            self.tgt=sentencepiece.SentencePieceProcessor(model_file=str(tgt)) if tgt.exists() else self.sp
        # Bound token count; subtitles can contain arbitrary untrusted text.
        pieces=self.sp.encode(text, out_type=str)
        outputs=[]
        for i in range(0,len(pieces),200):
            self.check()
            result=self.mt.translate_batch([pieces[i:i+200]+['</s>']],beam_size=4,max_decoding_length=256)[0]
            outputs.append(self.tgt.decode(result.hypotheses[0]))
        return ' '.join(outputs)

    def speak(self, cue, dest):
        raw=dest.with_suffix('.raw.wav'); tmp=dest.with_suffix('.part.wav')
        try:
            run([ROOT/'native/piper/piper.exe','--model', ROOT/'models/ru_RU-denis-medium.onnx',
                 '--output_file',raw], input=(cue.translated+'\n').encode('utf-8'))
            with wave.open(str(raw)) as f: duration=f.getnframes()/f.getframerate()
            slot=max(.15,cue.end-cue.start)
            factor=min(2.,max(1.,duration/slot))
            if duration/slot>2: self.event('speech_clipped',text=cue.translated,original_s=duration,slot_s=slot)
            run([ROOT/'native/ffmpeg.exe','-v','error','-y','-i',raw,'-af',f'atempo={factor},apad,atrim=duration={slot}',
                 '-ar','22050','-ac','1','-c:a','pcm_s16le',tmp])
            tmp.replace(dest)
        finally:
            raw.unlink(missing_ok=True); tmp.unlink(missing_ok=True)

    def save(self, complete=False):
        atomic(self.cache/'state.json',{'schema':1,'duration':self.duration,'ready_until':self.ready_until,
               'complete':complete,'cues':[asdict(c) for c in self.cues]})
        (self.cache/'translated.srt').write_text(srt([c for c in self.cues if c.audio]),'utf-8-sig')
        (self.cache/'source.srt').write_text(srt(self.cues,False),'utf-8-sig')

    def prepare_cues(self, cues):
        for cue in cues:
            self.check()
            key=hashlib.sha256(json.dumps([cue.start,cue.end,cue.text],ensure_ascii=False).encode()).hexdigest()[:24]
            meta=self.cache/(key+'.json'); audio=self.cache/(key+'.wav')
            if meta.exists() and audio.exists():
                saved=json.loads(meta.read_text('utf-8'))
                with wave.open(str(audio)) as w:
                    if w.getnframes()<=0: raise RuntimeError('Повреждён WAV кэша')
                cue.translated=saved['translated']; cue.audio=str(audio); self.event('cache_hit',start=cue.start)
            else:
                cue.translated=self.timed('translation',lambda:self.translate(cue.text),cue.end-cue.start)
                self.timed('tts',lambda:self.speak(cue,audio),cue.end-cue.start)
                cue.audio=str(audio); atomic(meta,asdict(cue))
            self.cues.append(cue); self.save()
            if not self.first:
                self.first=True; self.event('first_voice_ready',latency_s=time.perf_counter()-self.started)
            self.event('cue_ready',cue=asdict(cue))

    def execute(self):
        try:
            self.event('profile',asr='Systran/faster-whisper-tiny',translation='opus-mt-en-ru-int8',
                       tts='Piper Denis medium',cpu_isa=os.environ['CT2_FORCE_CPU_ISA'],threads=4,gpu='disabled')
            self.event('fingerprint')
            identity={'video':digest(self.media),'subtitle':digest(self.subtitle) if self.subtitle else None,
                      'source':self.source,'target':self.target,'track':self.track,'pipeline':4,
                      'models':digest(ROOT/'component-manifest.json')}
            self.cache=self.cache_root/hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
            self.cache.mkdir(parents=True,exist_ok=True); atomic(self.cache/'identity.json',identity)
            info=probe(self.media); self.duration=float(info['format']['duration'])
            if self.subtitle:
                cues=parse_srt(self.subtitle.read_text('utf-8-sig'))
                if not cues: raise RuntimeError('В SRT нет корректных реплик. Нужен текстовый UTF-8 SRT.')
                self.prepare_cues(cues)
                self.ready_until=self.duration
            else:
                for start in range(0,int(self.duration)+1,25):
                    self.check(); length=min(25,self.duration-start)
                    if length<=.05: break
                    transcript=self.cache/f'asr-{start}.json'
                    if transcript.exists(): cues=[Cue(**c) for c in json.loads(transcript.read_text('utf-8'))]
                    else:
                        if self.asr is None:
                            self.event('load_asr')
                            from faster_whisper import WhisperModel
                            self.asr=WhisperModel(str(ROOT/'models/whisper-tiny'),device='cpu',compute_type='int8',cpu_threads=4,
                                                  num_workers=1,local_files_only=True)
                        wav=self.cache/'asr-input.wav'
                        self.timed('extract_audio',lambda:run([ROOT/'native/ffmpeg.exe','-v','error','-y','-ss',start,
                            '-i',self.media,'-t',length,'-map',f'0:a:{self.track}','-ar','16000','-ac','1',wav]),length)
                        def recognize():
                            segments,_=self.asr.transcribe(str(wav),language=self.source,beam_size=1,vad_filter=False,
                                                          condition_on_previous_text=False)
                            return [Cue(start+s.start,min(start+s.end,start+length),s.text.strip()) for s in segments if s.text.strip() and s.end>s.start]
                        cues=self.timed('asr',recognize,length); atomic(transcript,[asdict(c) for c in cues]); wav.unlink(missing_ok=True)
                    self.prepare_cues(cues); self.ready_until=start+length; self.save()
                    self.event('buffer',ready_until=self.ready_until,duration=self.duration)
            self.save(True); self.event('complete',cache=str(self.cache),ready_until=self.duration,duration=self.duration)
        except Cancelled: self.event('cancelled')
        except Exception as e: self.event('error',message=str(e)); raise
        finally:
            self.mt=None; self.asr=None; self.sp=None

def export_audio(cues, duration, dest):
    """Bounded-memory PCM timeline, silence between cues, clips overlapping cues."""
    dest=Path(dest); tmp=dest.with_suffix('.part.wav')
    total=int(duration*22050); cursor=0
    def silence(f,n):
        while n>0:
            size=min(n,22050); f.writeframesraw(b'\0\0'*size); n-=size
    with wave.open(str(tmp),'wb') as out:
        out.setparams((1,2,22050,0,'NONE','not compressed'))
        for i,c in enumerate(cues):
            if not c.audio: raise RuntimeError('Сначала дождитесь полного перевода.')
            begin=int(c.start*22050)
            if begin>cursor: silence(out,begin-cursor); cursor=begin
            limit=min(total,int(c.end*22050),int(cues[i+1].start*22050) if i+1<len(cues) else total)
            with wave.open(c.audio,'rb') as inp:
                skip=max(0,cursor-begin); inp.setpos(min(skip,inp.getnframes()))
                remaining=max(0,limit-cursor)
                while remaining:
                    data=inp.readframes(min(remaining,22050))
                    if not data: break
                    out.writeframesraw(data); count=len(data)//2; cursor+=count; remaining-=count
        silence(out,max(0,total-cursor))
    tmp.replace(dest)
