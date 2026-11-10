"""Portable scheduler tests; native/model integration remains in test_system.py."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from core import Pipeline, Cue, block_order, media_fingerprint

class Scheduling(unittest.TestCase):
    def test_seek_priority_visits_each_block_once(self):
        self.assertEqual(block_order(25,19),[2,3,0,1])
        self.assertEqual(block_order(16,999),[1,0])
        self.assertEqual(block_order(0),[])

    def test_fingerprint_is_bounded_and_changes_with_middle(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'large'; path.write_bytes(b'a'*1000000)
            before=media_fingerprint(path)
            with path.open('r+b') as stream:stream.seek(500000); stream.write(b'b')
            self.assertNotEqual(before,media_fingerprint(path))

    def test_silence_coverage_seek_and_complete(self):
        with tempfile.TemporaryDirectory() as folder:
            media=Path(folder)/'movie'; media.write_bytes(b'video')
            sub=Path(folder)/'movie.srt'; sub.write_text('1\n00:00:01,000 --> 00:00:02,000\nHello\n')
            events=[]; pipeline=Pipeline(media,sub,start_at=18,cache_root=Path(folder)/'cache',emit=events.append)
            def prepare(cues):
                for cue in cues:
                    cue.translated='Привет'; cue.audio='fake.wav'; pipeline.cues.append(cue)
            with patch('core.probe',return_value={'format':{'duration':'26'}}),patch.object(pipeline,'prepare_cues',side_effect=prepare):
                pipeline.execute()
            buffers=[e for e in events if e['stage']=='buffer']
            self.assertEqual(buffers[0]['ranges'],[[16,24]])
            self.assertEqual(buffers[0]['ready_until'],24)
            self.assertEqual(buffers[-1]['ranges'],[[0,26]])
            self.assertEqual(events[-1]['stage'],'complete')
            self.assertTrue(json.loads((pipeline.cache/'state.json').read_text())['complete'])

    def test_cross_boundary_subtitle_prepared_before_coverage(self):
        with tempfile.TemporaryDirectory() as folder:
            media=Path(folder)/'movie'; media.write_bytes(b'video')
            sub=Path(folder)/'movie.srt'; sub.write_text('1\n00:00:07,000 --> 00:00:11,000\nHello\n')
            events=[]; p=Pipeline(media,sub,start_at=9,cache_root=Path(folder)/'cache',emit=events.append)
            prepared=[]
            def prepare(cues):
                prepared.extend(cues); p.cues.extend(cues)
            with patch('core.probe',return_value={'format':{'duration':'20'}}),patch.object(p,'prepare_cues',side_effect=prepare):p.execute()
            self.assertEqual(len(prepared),1)
            self.assertEqual(prepared[0].start,7)
            self.assertEqual(next(e for e in events if e['stage']=='buffer')['ranges'],[[8,16]])

if __name__=='__main__':unittest.main()
