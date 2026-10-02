"""Regressions for unwanted settings and the draft/edit request contract."""
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lyric_engine as engine

LINES = '\n'.join((
    'I can want it and be scared',
    'I can start before I know',
    'If I wait until I am ready',
    'I might never let it show',
))


class FreshLyricsTests(unittest.TestCase):
    def test_rejected_settings_never_escape_even_with_empty_user_blocklist(self):
        for word in ('laundromat', 'laundry mat', 'laundry-mat', 'launderette',
                     'LAUNDRETTE', 'orange chairs', 'soda machine', 'vending machines'):
            with self.subTest(word=word):
                self.assertTrue(engine.blocked_hits('Meet at the ' + word, ''))
        self.assertFalse(engine.blocked_hits('The start of a different day', ''))

    def test_every_pass_sends_all_rejected_imagery_and_exact_current_brief(self):
        request = engine.LyricRequest(topic='Starting despite fear', details='No literal scene.',
                                      structure='4-line hook', blocked_words='', good_words='')
        bad = LINES.replace('I can start before I know', 'We meet at the laundry mat')
        with patch.object(engine, '_request_model', side_effect=[bad, bad, LINES]) as model:
            result = engine.generate_lyrics(request, 'test-key')
        self.assertEqual(result.lyrics, LINES)
        self.assertEqual(result.api_calls, 3)
        for call in model.call_args_list:
            settings = json.loads(call.kwargs['user_input'])['settings']
            self.assertIn('laundry mat', settings['blocked_words'])
            self.assertIn('laundromat', settings['blocked_words'])
            self.assertIn('orange chairs', settings['blocked_words'])
            self.assertEqual(settings['topic'], request.topic)
            self.assertEqual(settings['real_life_details'], request.details)
            self.assertEqual(settings['good_words'], [])
        first = json.loads(model.call_args_list[0].kwargs['user_input'])
        self.assertNotIn('existing_lyrics', first)

    def test_forbidden_editorial_output_is_never_released(self):
        request = engine.LyricRequest(topic='New beginnings', structure='4-line hook')
        bad = LINES.replace('I might never let it show', 'I wait at the laundromat')
        with patch.object(engine, '_request_model', side_effect=[LINES, bad, bad, bad]):
            with self.assertRaises(engine.GenerationError):
                engine.generate_lyrics(request, 'test-key')


if __name__ == '__main__':
    unittest.main()
