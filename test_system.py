"""Real offline integration tests, not mocked translations. Run after setup."""
import json
import os
from pathlib import Path
import socket
import tempfile
import time
import unittest
import wave
import threading
from core import ROOT,Cue,Pipeline,parse_srt,export_audio,run,atomic
from player import MPV,Narration

EVIDENCE=ROOT/'evidence'
EVIDENCE.mkdir(exist_ok=True)

class Integration(unittest.TestCase):
    def test_srt_parser(self):
        cues=parse_srt('1\r\n00:00:01,200 --> 00:00:03,000\r\n<i>Hello</i>\r\nworld\r\n\r\n2\n00:00:04,000 --> 00:00:03,000\ninvalid')
        self.assertEqual(len(cues),1); self.assertEqual(cues[0].text,'Hello world'); self.assertEqual(cues[0].start,1.2)

    def test_offline_chains_and_cache(self):
        # All models must be present. Any socket connection is an immediate test failure.
        original=socket.socket.connect
        def blocked(*args,**kwargs):raise AssertionError('Unexpected network connection')
        socket.socket.connect=blocked
        try:
            with tempfile.TemporaryDirectory(dir=EVIDENCE) as folder:
                summaries={}
                for mode,subtitle in [('srt',ROOT/'test-video.srt'),('asr',None)]:
                    events=[]; pipeline=Pipeline(ROOT/'test-video.mp4',subtitle,emit=events.append,cache_root=folder)
                    pipeline.execute()
                    self.assertEqual(len(pipeline.cues),3)
                    self.assertTrue(all(any('\u0400'<=ch<='\u04ff' for ch in c.translated) for c in pipeline.cues))
                    self.assertIn('Поезд',pipeline.cues[1].translated)
                    output=EVIDENCE/f'{mode}-narration.wav'; export_audio(pipeline.cues,pipeline.duration,output)
                    with wave.open(str(output)) as f:
                        self.assertAlmostEqual(f.getnframes()/f.getframerate(),14,places=2)
                        import numpy as np
                        self.assertGreater(np.abs(np.frombuffer(f.readframes(f.getnframes()),dtype='<i2').astype(float)).max(),100)
                    atomic(EVIDENCE/f'{mode}-events.json',events)
                    cached=[]; again=Pipeline(ROOT/'test-video.mp4',subtitle,emit=cached.append,cache_root=folder)
                    again.translate=lambda _:self.fail('Translation invoked on cached media')
                    again.speak=lambda *_:self.fail('TTS invoked on cached media')
                    before=time.perf_counter(); again.execute()
                    self.assertEqual(sum(e['stage']=='cache_hit' for e in cached),3)
                    self.assertFalse(any(e['stage']=='load_asr' for e in cached))
                    summaries[mode]={'total_s':events[-1]['elapsed_s'],'first_voice_s':next(e['latency_s'] for e in events if e['stage']=='first_voice_ready'),
                                     'cache_reopen_s':time.perf_counter()-before,'translations':[c.translated for c in pipeline.cues]}
                atomic(EVIDENCE/'benchmark.json',summaries)
        finally:socket.socket.connect=original

    def test_invalid_media_reports_error(self):
        with tempfile.TemporaryDirectory(dir=EVIDENCE) as folder:
            p=Path(folder)/'broken.mkv'; p.write_bytes(b'invalid video')
            events=[]; pipeline=Pipeline(p,emit=events.append,cache_root=folder)
            with self.assertRaises(RuntimeError):pipeline.execute()
            self.assertEqual(events[-1]['stage'],'error')

    def test_clock_pause_and_seek(self):
        original=MPV(ao='null'); voice=MPV(ao='null'); narration=Narration(voice)
        try:
            original.command('loadfile',ROOT/'test-video.mp4'); time.sleep(.4)
            cues=[Cue(0,14,'test',audio=str(EVIDENCE/'srt-narration.wav'))]
            narration.sync(2.5,True,cues); time.sleep(.3)
            self.assertIsNotNone(narration.current)
            self.assertEqual(voice.get('pause'),'yes')
            narration.sync(4.5,True,cues); time.sleep(.3)
            self.assertLess(abs(float(voice.get('time-pos'))-4.5),.2)
            narration.sync(20,False,cues); self.assertIsNone(narration.current)
        finally:voice.close();original.close()

def loopback():
    """Capture actual shared WASAPI output and detect both independently generated tones."""
    import soundcard as sc
    import numpy as np
    with tempfile.TemporaryDirectory(dir=EVIDENCE) as folder:
        folder=Path(folder); video=folder/'tone.mp4'; dub=folder/'voice.wav'
        run([ROOT/'native/ffmpeg.exe','-v','error','-y','-f','lavfi','-i','color=c=black:s=320x180:r=24',
             '-f','lavfi','-i','sine=frequency=440:duration=5','-t','5','-c:v','libx264','-c:a','aac',video])
        run([ROOT/'native/ffmpeg.exe','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=5','-ar','22050','-ac','1',dub])
        speaker=sc.default_speaker(); mic=sc.get_microphone(speaker.id,include_loopback=True)
        main=MPV(); voice=MPV(); narration=Narration(voice); result={}
        try:
            with mic.recorder(samplerate=48000,channels=2,blocksize=2048) as recorder:
                main.set('volume',35);voice.set('volume',60)
                main.command('loadfile',video)
                cues=[Cue(0,5,'tone',audio=str(dub))]
                blocks=[]
                for _ in range(60):
                    pos=float(main.get('time-pos',0) or 0); narration.sync(pos,False,cues)
                    blocks.append(recorder.record(numframes=2048))
                samples=np.concatenate(blocks).mean(axis=1); samples=samples[24000:]
                spectrum=np.abs(np.fft.rfft(samples*np.hanning(len(samples)))); hz=np.fft.rfftfreq(len(samples),1/48000)
                peaks={str(f):float(spectrum[np.abs(hz-f)<3].max()) for f in (440,880)}
                noise=float(np.median(spectrum[(hz>200)&(hz<1500)]))
                result={'device':speaker.name,'main_ao':main.get('current-ao'),'voice_ao':voice.get('current-ao'),
                        'tone_peaks':peaks,'median_noise':noise,'samples':len(samples),
                        'passed':all(v>max(.01,noise*30) for v in peaks.values())}
                pcm=(np.clip(samples,-1,1)*32767).astype('<i2')
                with wave.open(str(EVIDENCE/'wasapi-mix.wav'),'wb') as f:
                    f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes(pcm.tobytes())
                atomic(EVIDENCE/'wasapi-mix.json',result)
                if not result['passed']:raise AssertionError(str(result))
                print(json.dumps(result))
        finally:voice.close();main.close()

if __name__=='__main__':
    import sys
    if '--loopback' in sys.argv:loopback()
    else:
        # Explicit order: clock test consumes a real export produced by the chain test.
        suite=unittest.TestSuite(Integration(n) for n in ['test_srt_parser','test_offline_chains_and_cache','test_invalid_media_reports_error','test_clock_pause_and_seek'])
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        sys.exit(not result.wasSuccessful())
