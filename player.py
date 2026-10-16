"""Small libmpv binding. Original and narration use Windows' shared audio mixer."""
import ctypes as C
import json
import os
from core import ROOT

class MPV:
    lib=None
    def __init__(self, window=None, **options):
        if MPV.lib is None:
            os.add_dll_directory(str(ROOT/'native'))
            lib=C.CDLL(str(ROOT/'native/libmpv-2.dll'))
            for name,restype,args in [
                ('mpv_create',C.c_void_p,[]),('mpv_initialize',C.c_int,[C.c_void_p]),
                ('mpv_set_option_string',C.c_int,[C.c_void_p,C.c_char_p,C.c_char_p]),
                ('mpv_set_property_string',C.c_int,[C.c_void_p,C.c_char_p,C.c_char_p]),
                ('mpv_get_property_string',C.c_void_p,[C.c_void_p,C.c_char_p]),
                ('mpv_command',C.c_int,[C.c_void_p,C.POINTER(C.c_char_p)]),
                ('mpv_free',None,[C.c_void_p]),('mpv_terminate_destroy',None,[C.c_void_p])]:
                fn=getattr(lib,name); fn.restype=restype; fn.argtypes=args
            MPV.lib=lib
        self.lib=MPV.lib; self.handle=self.lib.mpv_create()
        if not self.handle: raise RuntimeError('mpv_create failed')
        opts={'config':'no','terminal':'no','input-default-bindings':'no','input-vo-keyboard':'no',
              'osc':'no','idle':'yes','keep-open':'yes','audio-exclusive':'no','hwdec':'no',
              'ytdl':'no','network-timeout':'1','volume':'35'}
        if window: opts['wid']=str(window)
        else: opts.update({'vo':'null','video':'no'})
        opts.update(options)
        for k,v in opts.items():
            rc=self.lib.mpv_set_option_string(self.handle,k.encode(),str(v).encode())
            if rc<0: raise RuntimeError(f'mpv option {k}: {rc}')
        rc=self.lib.mpv_initialize(self.handle)
        if rc<0: raise RuntimeError(f'mpv initialize: {rc}')

    def command(self,*args):
        if not self.handle:raise RuntimeError('Плеер уже закрыт')
        arr=(C.c_char_p*(len(args)+1))(*(str(a).encode('utf-8') for a in args),None)
        rc=self.lib.mpv_command(self.handle,arr)
        if rc<0: raise RuntimeError(f'mpv {args[0]}: {rc}')

    def get(self,key,default=None):
        if not self.handle:return default
        p=self.lib.mpv_get_property_string(self.handle,key.encode())
        if not p:return default
        try:
            value=C.string_at(p).decode('utf-8')
            try:return json.loads(value)
            except (ValueError,TypeError):return value
        finally:self.lib.mpv_free(p)

    def set(self,key,value):
        if not self.handle:return
        value='yes' if value is True else 'no' if value is False else str(value)
        rc=self.lib.mpv_set_property_string(self.handle,key.encode(),value.encode('utf-8'))
        if rc<0:raise RuntimeError(f'mpv property {key}: {rc}')

    def close(self):
        if self.handle:self.lib.mpv_terminate_destroy(self.handle); self.handle=None

class Narration:
    """Synchronizes immutable per-cue WAVs to the primary video clock, including seeks."""
    def __init__(self, output):self.output=output; self.current=None; self.pending=None
    def sync(self,position,paused,cues):
        # Later cue wins on overlap, matching exported timeline.
        cue=next((c for c in reversed(cues) if c.start<=position<c.end and c.audio),None)
        if cue is None:
            if self.current is not None:self.output.command('stop')
            self.current=None; return
        offset=max(0.,position-cue.start)
        if self.current!=cue.audio:
            self.output.command('loadfile',cue.audio,'replace','-1',f'start={offset:.4f}')
            self.current=cue.audio
        self.output.set('pause',paused)
        actual=self.output.get('time-pos')
        if actual is not None and abs(float(actual)-offset)>.18:
            self.output.command('seek',offset,'absolute+exact')
    def stop(self):self.output.command('stop'); self.current=None
