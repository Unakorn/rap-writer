"""Offline imported-map regressions, including rap hook and repair behavior."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lyric_engine as engine
from song_structure import validate_song_structure, parse_song_structure, SongStructureError
from rap_fixtures import song_map
from test_rap_lyric_engine import EIGHT_LINES, request, sectioned_lyrics


class ImportedMapTests(unittest.TestCase):
    def test_preserves_musical_map_and_instrumental_heading_across_repair(self):
        song = song_map()
        original = json.dumps(song, sort_keys=True)
        shape = [(s['name'], s['suggested_lines']) for s in song['sections']]
        valid = sectioned_lyrics(shape)
        invalid = valid.replace('[Intro]', '[Intro]\nSome unwanted vocals', 1)
        configured = request(song_structure=song, structure='4-line hook')
        with patch.object(engine, '_request_model', side_effect=[valid, invalid, valid]) as model:
            result = engine.generate_lyrics(configured, 'offline-test-key')
        self.assertEqual(result.api_calls, 3)
        self.assertEqual(engine.song_structure_issues(result.lyrics, song), [])
        self.assertTrue(result.lyrics.startswith('[Intro]\n[Hook]'))
        self.assertEqual(json.dumps(song, sort_keys=True), original)
        for call in model.call_args_list:
            settings = json.loads(call.kwargs['user_input'])['settings']
            self.assertEqual(settings['song_structure'], song)
            self.assertEqual(settings['structure'], 'Imported song JSON')
            self.assertIsNone(settings['exact_lyric_line_count'])
            self.assertEqual(settings['expected_sections'], [{'name': n, 'lines': c} for n, c in shape])

    def test_imported_hook_names_are_exact_and_repeated_order_checked(self):
        song = song_map()
        valid = sectioned_lyrics([(s['name'], s['suggested_lines']) for s in song['sections']])
        for invalid in (valid.replace('[Hook]', '[Chorus]', 1), valid.replace('[Hook]', '[hook]', 1),
                        valid + '\n[Outro]', valid.replace('[Intro]', '', 1)):
            with self.subTest(invalid=invalid[:35]):
                self.assertTrue(engine.song_structure_issues(invalid, song))

    def test_invalid_maps_rejected_before_api_and_duplicate_json_keys_rejected(self):
        for change in ('overlap', 'tempo', 'instrumental', 'total', 'unknown'):
            song = song_map()
            if change == 'overlap': song['sections'][1]['start_bar'] = 2
            if change == 'tempo': song['sections'][0]['bpm'] = float('nan')
            if change == 'instrumental': song['sections'][0]['suggested_lines'] = 1
            if change == 'total': song['total_bars'] += 1
            if change == 'unknown': song['surprise'] = 'ignore'
            with self.subTest(change=change), patch.object(engine, '_request_model') as model:
                with self.assertRaises(engine.ValidationError):
                    engine.generate_lyrics(request(song_structure=song), 'offline-test-key')
                model.assert_not_called()
        with self.assertRaises(SongStructureError):
            parse_song_structure('{"version": 1, "version": 2}')

    def test_request_snapshot_does_not_mutate_with_caller_map(self):
        song = song_map()
        before = validate_song_structure(song)
        valid = sectioned_lyrics([(s['name'], s['suggested_lines']) for s in song['sections']])
        def response(**kwargs):
            song['sections'][1]['name'] = 'Unexpected alteration'
            return valid
        with patch.object(engine, '_request_model', side_effect=response) as model:
            result = engine.generate_lyrics(request(song_structure=song), 'offline-test-key')
        self.assertEqual(result.lyrics, valid)
        self.assertEqual(json.loads(model.call_args_list[1].kwargs['user_input'])['settings']['song_structure'], before)

    def test_four_and_eight_line_hooks_repair_missing_lines_and_plain_final_heading(self):
        for count in (4, 8):
            valid = '\n'.join(EIGHT_LINES.splitlines()[:count])
            for invalid in ('\n'.join(valid.splitlines()[:-1]), 'Final hook:\n' + '\n'.join(valid.splitlines()[1:])):
                with self.subTest(count=count), patch.object(engine, '_request_model', side_effect=[valid, invalid, valid]):
                    result = engine.generate_lyrics(request(structure=f'{count}-line hook'), 'offline-test-key')
                self.assertEqual(result.lyrics, valid)
                self.assertEqual(result.api_calls, 3)


if __name__ == '__main__':
    unittest.main()
