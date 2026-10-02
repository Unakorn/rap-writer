"""Fresh AI brief regression checks; all transport calls are mocked."""
import dataclasses
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import idea_engine as ideas
import lyric_engine as lyrics
from rap_fixtures import rap_idea


def fresh_idea():
    result = rap_idea()
    result.update(
        topic='Wanting closeness while being afraid to accept it',
        details='The voice admits how pride can disguise a need for connection, then dares to speak honestly.',
        hook_note='Meet me halfway to honest', good_words='')
    return result


class FreshIdeaTests(unittest.TestCase):
    def test_empty_wanted_words_are_valid_without_empty_brief(self):
        self.assertEqual(ideas.validate_idea(fresh_idea())['good_words'], '')
        for field in ('topic', 'details', 'hook_note'):
            candidate = fresh_idea(); candidate[field] = ''
            with self.subTest(field=field), self.assertRaises(lyrics.ValidationError):
                ideas.validate_idea(candidate)

    def test_payload_has_no_scripted_seeds_and_includes_full_current_brief(self):
        request = lyrics.LyricRequest(
            topic='Previous idea', details='d' * 6000, good_words='w' * 4000,
            existing_lyrics='PRIVATE-LYRICS', revision_note='PRIVATE-REVISION')
        recent = [rap_idea()]
        with patch.object(ideas, '_request_model', return_value=json.dumps(fresh_idea())) as model:
            result = ideas.generate_idea(request, 'offline-key', recent_ideas=recent)
        self.assertEqual(result, fresh_idea())
        payload = json.loads(model.call_args.kwargs['user_input'])
        self.assertNotIn('variety_seeds', payload)
        self.assertEqual(payload['current_idea_to_avoid']['details'], request.details)
        self.assertEqual(payload['current_idea_to_avoid']['good_words'], request.good_words)
        self.assertEqual(payload['recent_ideas_to_avoid'][0]['details'], recent[0]['details'])
        self.assertEqual(payload['recent_ideas_to_avoid'][0]['good_words'], recent[0]['good_words'])
        for private in ('PRIVATE-LYRICS', 'PRIVATE-REVISION', 'offline-key'):
            self.assertNotIn(private, model.call_args.kwargs['user_input'])
        self.assertIn('laundromat', payload['blocked_words'])
        self.assertIn('laundry mat', payload['blocked_words'])

    def test_changed_topic_and_hook_cannot_hide_recycled_detail_phrase(self):
        previous = rap_idea()
        repeated = fresh_idea()
        repeated['details'] = 'A CRACKED phone screen becomes the center of an otherwise new story.'
        with patch.object(ideas, '_request_model', side_effect=[json.dumps(repeated), json.dumps(fresh_idea())]) as model:
            result = ideas.generate_idea(lyrics.LyricRequest(topic=''), 'offline-key', recent_ideas=[previous])
        self.assertEqual(result, fresh_idea())
        self.assertEqual(model.call_count, 2)
        self.assertIn('distinctive detail', json.loads(model.call_args.kwargs['user_input'])['problem_to_fix'])

    def test_recycled_wanted_phrase_is_detected_in_any_candidate_field(self):
        for field in ideas.IDEA_TEXT_LIMITS:
            candidate = fresh_idea()
            candidate[field] = 'Fresh thoughts near the paper menus'
            with self.subTest(field=field), self.assertRaises(lyrics.ValidationError):
                ideas._check_repetition(candidate, {'good_words': 'paper menus'}, [])
        candidate = fresh_idea(); candidate['details'] = 'We wait for the night bus to leave.'
        with self.assertRaises(lyrics.ValidationError):
            ideas._check_repetition(candidate, {'good_words': 'night bus'}, [])

    def test_ordinary_connectives_and_emotional_words_do_not_force_retry(self):
        candidate = fresh_idea()
        candidate['details'] = 'I want to feel love again, and let go of fear.'
        previous = {'details': 'I want to feel new hope for the first time.', 'good_words': 'love, time, let go'}
        ideas._check_repetition(candidate, previous, [])

    def test_repeated_details_exhaust_budget_without_offline_fallback(self):
        repeated = fresh_idea(); repeated['details'] = rap_idea()['details']
        with patch.object(ideas, '_request_model', return_value=json.dumps(repeated)) as model:
            with self.assertRaises(lyrics.GenerationError):
                ideas.generate_idea(lyrics.LyricRequest(topic=''), 'offline-key', recent_ideas=[rap_idea()])
        self.assertEqual(model.call_count, 2)

    def test_context_over_limit_is_rejected_before_model_call(self):
        for field, limit in (('details', 6000), ('good_words', 4000)):
            request = dataclasses.replace(lyrics.LyricRequest(topic=''), **{field: 'x' * (limit + 1)})
            with self.subTest(field=field), patch.object(ideas, '_request_model') as model:
                with self.assertRaises(lyrics.ValidationError):
                    ideas.generate_idea(request, 'offline-key')
                model.assert_not_called()


if __name__ == '__main__':
    unittest.main()
