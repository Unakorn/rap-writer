"""AI Ideas checks. Every model response is mocked; no API credit is used."""
from copy import deepcopy
import dataclasses
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lyric_engine as lyrics
import idea_engine as ideas
from rap_fixtures import rap_idea


def idea_request(**overrides):
    return dataclasses.replace(lyrics.LyricRequest(topic='', blocked_words='static, wire, neon'), **overrides)


def model_mock(**kwargs):
    # The idea engine deliberately reuses the established private transport.
    return patch.object(ideas, '_request_model', **kwargs)


class IdeaEngineTests(unittest.TestCase):
    def test_blank_brief_generates_one_real_request_using_selected_model(self):
        with model_mock(return_value=json.dumps(rap_idea())) as model:
            result = ideas.generate_idea(idea_request(model='gpt-4.1'), 'offline-secret')
        self.assertEqual(result, rap_idea())
        self.assertEqual(model.call_count, 1)
        self.assertEqual(model.call_args.kwargs['model'], 'gpt-4.1')
        self.assertEqual(model.call_args.kwargs['api_key'], 'offline-secret')
        self.assertGreater(model.call_args.kwargs['max_output_tokens'], 0)

    def test_exact_ten_key_schema_rejects_missing_extra_and_wrong_types(self):
        self.assertEqual(set(ideas.validate_idea(rap_idea())), set(rap_idea()))
        candidates = []
        for field in rap_idea():
            missing = rap_idea(); missing.pop(field); candidates.append(missing)
            invalid = rap_idea(); invalid[field] = ['wrong type']; candidates.append(invalid)
        extra = rap_idea(); extra['lyrics'] = 'Unwanted generated words'; candidates.append(extra)
        for candidate in candidates:
            with self.subTest(fields=list(candidate)):
                with self.assertRaises((lyrics.GenerationError, ValueError)):
                    ideas.validate_idea(candidate)

    def test_all_controls_use_exact_declared_choices(self):
        fields = {'style', 'mood', 'phrasing', 'rhyme_style', 'dynamics', 'imagery'}
        self.assertEqual(set(ideas.IDEA_CHOICES), fields)
        for field in fields:
            self.assertIn(rap_idea()[field], ideas.IDEA_CHOICES[field])
            candidate = rap_idea(); candidate[field] = 'Made up selection'
            with self.subTest(field=field), self.assertRaises((lyrics.GenerationError, ValueError)):
                ideas.validate_idea(candidate)

    def test_blocked_words_checked_in_every_generated_text_field(self):
        for field in ('topic', 'details', 'hook_note', 'good_words'):
            for token in ('STATIC', 'státic', 'sta\u200btic'):
                candidate = rap_idea(); candidate[field] += ' ' + token
                with self.subTest(field=field, token=token), self.assertRaises((lyrics.GenerationError, ValueError)):
                    ideas.validate_idea(candidate, blocked_words='static')
        candidate = rap_idea(); candidate['details'] += ' The wireless set is ready.'
        self.assertEqual(ideas.validate_idea(candidate, blocked_words='wire')['details'], candidate['details'])

    def test_blocked_candidate_is_repaired_once(self):
        invalid = rap_idea(); invalid['details'] += ' Static on the radio.'
        with model_mock(side_effect=[json.dumps(invalid), json.dumps(rap_idea())]) as model:
            result = ideas.generate_idea(idea_request(), 'offline-secret')
        self.assertEqual(result, rap_idea())
        self.assertEqual(model.call_count, 2)
        self.assertIn('static', model.call_args.kwargs['user_input'].lower())

    def test_invalid_outputs_exhaust_two_calls_without_returning_partial_idea(self):
        for invalid in ('not JSON', '{}', json.dumps({'topic': 'A fragment'})):
            with self.subTest(invalid=invalid), model_mock(return_value=invalid) as model:
                with self.assertRaises(lyrics.GenerationError):
                    ideas.generate_idea(idea_request(), 'offline-secret')
                self.assertEqual(model.call_count, 2)

    def test_recent_or_current_idea_repeat_gets_repaired(self):
        previous = rap_idea()
        replacement = rap_idea()
        replacement.update(topic='Two cousins restore a bicycle for their first day at college',
                           details='They learn to accept each other without pretending to agree about everything.',
                           hook_note='Take the long way round', good_words='')
        for request, recent in ((idea_request(topic=previous['topic'], hook_note=previous['hook_note']), []),
                                (idea_request(), [previous])):
            with self.subTest(recent=bool(recent)), model_mock(side_effect=[json.dumps(previous), json.dumps(replacement)]) as model:
                result = ideas.generate_idea(request, 'offline-secret', recent_ideas=recent)
            self.assertEqual(result, replacement)
            self.assertEqual(model.call_count, 2)

    def test_lyrics_keys_and_revision_text_never_sent_in_json(self):
        request = idea_request(existing_lyrics='PRIVATE-LYRIC-SENTINEL', revision_note='PRIVATE-REVISION-SENTINEL', explicit=False)
        request_before = dataclasses.asdict(request)
        recent = [dict(topic='An old topic', hook_note='An old hook', existing_lyrics='RECENT-PRIVATE-SENTINEL', api_key='RECENT-KEY-SENTINEL')]
        recent_before = deepcopy(recent)
        with model_mock(return_value=json.dumps(rap_idea())) as model:
            ideas.generate_idea(request, 'OFFLINE-KEY-SENTINEL', recent_ideas=recent)
        for call in model.call_args_list:
            payload = call.kwargs['user_input']
            json.loads(payload)
            for private in ('PRIVATE-LYRIC-SENTINEL', 'PRIVATE-REVISION-SENTINEL', 'OFFLINE-KEY-SENTINEL', 'RECENT-PRIVATE-SENTINEL', 'RECENT-KEY-SENTINEL'):
                self.assertNotIn(private, payload)
            self.assertIn('false', payload.lower())
        self.assertEqual(dataclasses.asdict(request), request_before)
        self.assertEqual(recent, recent_before)

    def test_missing_key_and_pre_cancel_make_no_requests(self):
        with model_mock() as model:
            with self.assertRaises(lyrics.GenerationError):
                ideas.generate_idea(idea_request(), '')
            cancelled = threading.Event(); cancelled.set()
            with self.assertRaises(lyrics.GenerationCancelled):
                ideas.generate_idea(idea_request(), 'offline-secret', cancel=cancelled)
        model.assert_not_called()

    def test_cancellation_after_response_prevents_idea_or_repair(self):
        for response in (json.dumps(rap_idea()), '{}'):
            cancel = threading.Event()
            def cancelled_response(**kwargs):
                cancel.set()
                return response
            with self.subTest(response=response[:20]), model_mock(side_effect=cancelled_response) as model:
                with self.assertRaises(lyrics.GenerationCancelled):
                    ideas.generate_idea(idea_request(), 'offline-secret', cancel=cancel)
                self.assertEqual(model.call_count, 1)

    def test_transport_error_does_not_retry_or_expose_partial_output(self):
        with model_mock(side_effect=lyrics.GenerationError('The API key was not accepted.')) as model:
            with self.assertRaises(lyrics.GenerationError):
                ideas.generate_idea(idea_request(), 'offline-secret')
        self.assertEqual(model.call_count, 1)

    def test_text_size_and_wanted_word_limits_reject_unusable_ideas(self):
        for field, limit in [('topic', 500), ('details', 1600), ('hook_note', 120), ('good_words', 320)]:
            values = ('x' * (limit + 1),) if field == 'good_words' else ('', '   ', 'x' * (limit + 1))
            for value in values:
                candidate = rap_idea(); candidate[field] = value
                with self.subTest(field=field, length=len(value)), self.assertRaises((lyrics.GenerationError, ValueError)):
                    ideas.validate_idea(candidate)
        for wanted in (',; ,', ', '.join(f'word{i}' for i in range(9)), 'x' * 61):
            candidate = rap_idea(); candidate['good_words'] = wanted
            with self.subTest(wanted=wanted), self.assertRaises((lyrics.GenerationError, ValueError)):
                ideas.validate_idea(candidate)

    def test_control_characters_are_repaired_and_duplicate_json_keys_rejected(self):
        for marker in ('\n', '\t', '\u200b', '\u2028', '\u2029'):
            candidate = rap_idea(); candidate['details'] += marker + 'Hidden control'
            with self.subTest(marker=repr(marker)), self.assertRaises((lyrics.GenerationError, ValueError)):
                ideas.validate_idea(candidate)
        duplicate = json.dumps(rap_idea())[:-1] + ', "topic": "A duplicate topic"}'
        with model_mock(side_effect=[duplicate, json.dumps(rap_idea())]) as model:
            self.assertEqual(ideas.generate_idea(idea_request(), 'offline-secret'), rap_idea())
        self.assertEqual(model.call_count, 2)

    def test_repeat_gate_normalizes_case_accents_and_punctuation(self):
        previous = rap_idea()
        repeated = rap_idea(); repeated.update(topic='A different topic', hook_note='KEEP, A PLÁCE FOR ME!')
        replacement = rap_idea(); replacement.update(
            topic='Two cousins restore a bicycle', hook_note='Take the long way round',
            details='Their rivalry becomes respect when each admits what the other does better.', good_words='')
        with model_mock(side_effect=[json.dumps(repeated), json.dumps(replacement)]) as model:
            result = ideas.generate_idea(idea_request(), 'offline-secret', recent_ideas=[previous])
        self.assertEqual(result, replacement)
        self.assertEqual(model.call_count, 2)

    def test_callback_cannot_change_inflight_request_or_recent_snapshot(self):
        request = idea_request()
        recent = [dict(topic='A previous topic', hook_note='A previous hook')]
        invalid = '{}'
        def response(**kwargs):
            request.blocked_words = 'mother'
            recent[0]['topic'] = rap_idea()['topic']
            return invalid if model.call_count == 1 else json.dumps(rap_idea())
        with model_mock(side_effect=response) as model:
            result = ideas.generate_idea(request, 'offline-secret', recent_ideas=recent)
        self.assertEqual(result, rap_idea())
        self.assertEqual(model.call_count, 2)


if __name__ == '__main__':
    unittest.main()
