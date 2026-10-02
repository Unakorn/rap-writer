"""Offline behavioral checks for the Rap Writer generation engine."""

from __future__ import annotations

import dataclasses
import io
import json
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import MagicMock, patch
import urllib.error


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import lyric_engine as engine


EIGHT_LINES = "\n".join([
    "I left the rent receipt beside your coffee cup",
    "You called me after work to say the car was stuck",
    "I had eleven dollars folded in my jeans",
    "We split the fries and never said what broke our peace",
    "Your mother called and I pretended I was fine",
    "You watched me count the headlights passing on the drive",
    "I kept the little note you wrote behind the bill",
    "I read it when the house gets quiet and I sit still",
])


def request(**changes):
    return dataclasses.replace(
        engine.LyricRequest(
            topic="Rent is due, and my brother still needs a ride home",
            structure="8 lines",
            blocked_words="static, wire, wires",
        ),
        **changes,
    )


def completed_response(text=EIGHT_LINES):
    return {
        "status": "completed",
        "output": [{
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": text}],
        }],
    }


def sectioned_lyrics(sections):
    lines = []
    for name, count in sections:
        lines.append(f"[{name}]")
        lines.extend(EIGHT_LINES.splitlines()[index % 8] for index in range(count))
    return "\n".join(lines)


class RapContractTests(unittest.TestCase):
    def test_defaults_and_full_song_shape(self):
        default = engine.LyricRequest(topic="An ordinary goodbye")
        self.assertEqual(default.style, "Melodic rap")
        self.assertEqual(default.mood, "Reflective / hopeful")
        self.assertEqual(default.phrasing, "Melodic / pocketed")
        self.assertEqual(default.rhyme_style, "Internal + end rhymes")
        self.assertEqual(default.dynamics, "Rapped verses / sung hook")
        self.assertEqual(default.imagery, "Concrete / personal")
        self.assertEqual(default.structure, "Full song")
        self.assertEqual(list(engine.DEFAULT_SONG_STRUCTURE), [
            ("Hook", 8), ("Verse 1", 16), ("Hook", 8),
            ("Verse 2", 16), ("Bridge", 4), ("Final hook", 8),
        ])
        self.assertEqual(sum(count for _, count in engine.DEFAULT_SONG_STRUCTURE), 60)

    def test_rap_fields_are_validated_before_contacting_model(self):
        for field in ("phrasing", "rhyme_style", "hook_note", "dynamics", "imagery"):
            with self.subTest(field=field):
                with patch.object(engine, "_request_model") as model:
                    with self.assertRaises(engine.ValidationError):
                        engine.generate_lyrics(request(**{field: None}), "test-key")
                model.assert_not_called()

    def test_creative_controls_survive_draft_editorial_and_repair(self):
        settings = dict(
            style="Melodic rap", mood="Hopeful", phrasing="Short and airy",
            rhyme_style="Loose / slant", hook_note="Come home before the kettle cools",
            revision_note="Keep the hook tender", good_words="coffee",
            require_good_words=True, dynamics="Driving throughout", imagery="Direct / blunt",
        )
        invalid = EIGHT_LINES.replace("coffee", "static")
        for rewriting in (False, True):
            with self.subTest(rewriting=rewriting):
                configured = request(**settings, existing_lyrics=EIGHT_LINES if rewriting else "")
                with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, invalid, EIGHT_LINES]) as model:
                    result = engine.generate_lyrics(configured, "test-key")
                self.assertEqual(result.api_calls, 3)
                for call in model.call_args_list:
                    payload = json.loads(call.kwargs["user_input"])
                    for key, value in settings.items():
                        expected = [value] if key == "good_words" else value
                        self.assertEqual(payload["settings"][key], expected)
                    self.assertIn("rap", call.kwargs["instructions"].casefold())
                    self.assertNotIn("alternative rock", call.kwargs["instructions"].casefold())
                first = json.loads(model.call_args_list[0].kwargs["user_input"])
                self.assertEqual(first.get("existing_lyrics", ""), EIGHT_LINES if rewriting else "")
                self.assertTrue(json.loads(model.call_args_list[2].kwargs["user_input"])["problems_to_fix"])


class TermMatchingTests(unittest.TestCase):
    def test_term_separators_and_normalized_deduplication(self):
        self.assertEqual(
            engine.split_terms(" Wire,wire; NÉON\nneon; late-night, late night ,,"),
            ["Wire", "NÉON", "late-night"],
        )

    def test_empty_terms(self):
        self.assertEqual(engine.split_terms(" ,;\n \n"), [])
        self.assertEqual(engine.blocked_hits(EIGHT_LINES, ""), [])
        self.assertEqual(engine.missing_good_words(EIGHT_LINES, ""), [])

    def test_word_boundaries_do_not_ban_longer_words(self):
        self.assertEqual(engine.blocked_hits("wireless wiring, rewired", "wire, wires"), [])
        self.assertEqual(engine.blocked_hits("a WIRE by the door", "wire"), ["wire"])

    def test_accents_formatting_characters_and_compatibility_characters(self):
        for text in ("státic", "sta\u200btic", "ｓｔａｔｉｃ", "sta\u2060tic", "sta\ufe0ftic", "sta\u034ftic"):
            with self.subTest(text=text):
                self.assertEqual(engine.blocked_hits(text, "static"), ["static"])

    def test_phrase_matching_accepts_punctuation_and_hyphens(self):
        for text in ("rent-money", "rent, money", "rent\nmoney", "RENT   MONEY"):
            with self.subTest(text=text):
                self.assertEqual(engine.blocked_hits(text, "rent money"), ["rent money"])
        self.assertEqual(engine.blocked_hits("rent was money", "rent money"), [])

    def test_good_words_use_same_normalization_and_word_boundaries(self):
        self.assertEqual(
            engine.missing_good_words("Café food in a late-night diner", "cafe; late night; brother"),
            ["brother"],
        )
        self.assertEqual(engine.missing_good_words("wireless", "wire"), ["wire"])


class RequestValidationTests(unittest.TestCase):
    def test_normal_request_and_revision_without_new_topic(self):
        engine.validate_request(request())
        engine.validate_request(request(topic="", existing_lyrics=EIGHT_LINES))

    def test_a_subject_or_existing_draft_is_required(self):
        with self.assertRaises(engine.ValidationError):
            engine.validate_request(request(topic=" \n", existing_lyrics="\t"))

    def test_bad_field_types_are_validation_errors(self):
        for field, value in [
            ("topic", None), ("details", 42), ("blocked_words", ["static"]),
            ("good_words", ["rent"]), ("existing_lyrics", None),
            ("explicit", "yes"), ("require_good_words", "yes"),
        ]:
            with self.subTest(field=field):
                with self.assertRaises(engine.ValidationError):
                    engine.validate_request(request(**{field: value}))

    def test_good_phrase_cannot_contain_a_blocked_word(self):
        for good in ("wire", "telephone wire", "telephone-wíre"):
            with self.subTest(good=good):
                with self.assertRaises(engine.ValidationError):
                    engine.validate_request(request(blocked_words="wire", good_words=good))

    def test_good_and_blocked_word_substrings_can_coexist(self):
        engine.validate_request(request(blocked_words="wire", good_words="wireless"))

    def test_conflicting_phrases_use_normalized_tokens(self):
        with self.assertRaises(engine.ValidationError):
            engine.validate_request(request(blocked_words="rent money", good_words="my rent-money"))


class CustomStructureParsingTests(unittest.TestCase):
    def test_canonical_song_plan_preserves_repeated_sections(self):
        structure = "Intro: 4\nVerse 1: 16\nHook: 8\nVerse 2: 16\nHook: 8\nOutro: 4"
        self.assertEqual(engine.parse_structure(structure), [
            ("Intro", 4), ("Verse 1", 16), ("Hook", 8),
            ("Verse 2", 16), ("Hook", 8), ("Outro", 4),
        ])
        engine.validate_request(request(structure=structure))

    def test_fixed_presets_have_no_custom_sections(self):
        for structure in ("8 lines", "16 lines", "24 lines", "32 lines", "4-line hook", "4-line chorus", "8-line chorus", "8 bars", "16 bars", "24 bars", "32 bars", "8-line hook", "Full song"):
            with self.subTest(structure=structure):
                self.assertEqual(engine.parse_structure(structure), [])

    def test_one_section_and_hyphenated_names(self):
        self.assertEqual(engine.parse_structure("Pre-Hook 2: 1"), [("Pre-Hook 2", 1)])

    def test_unknown_presets_and_non_text_values_are_rejected(self):
        for structure in ("", "80 bars", "Custom", "A complete song please", None, 16):
            with self.subTest(structure=structure):
                with self.assertRaises(engine.ValidationError):
                    engine.parse_structure(structure)

    def test_section_and_total_bar_limits_accept_boundaries(self):
        twelve = "\n".join(f"Section {index}: 1" for index in range(1, 13))
        self.assertEqual(len(engine.parse_structure(twelve)), 12)
        engine.validate_request(request(structure=twelve))
        maximum_bars = "Verse 1: 64\nVerse 2: 64\nOutro: 32"
        self.assertEqual(sum(count for _, count in engine.parse_structure(maximum_bars)), 160)
        engine.validate_request(request(structure=maximum_bars))

    def test_names_accept_forty_characters(self):
        name = "A" * 40
        self.assertEqual(engine.parse_structure(f"{name}: 8"), [(name, 8)])

    def test_malformed_plans_are_rejected(self):
        for structure in (
            ": 8", "Verse:", "Verse: eight", "Verse: 8.5", "Verse: -1",
            "Verse: 0", "Verse: 65", "Verse: 8 bars", "[Verse]: 8",
            "Verse: one: 8", "Verse/Hook: 8", "Verse!: 8", "Verse\nHook",
            "Verse: 8\nHook", "Verse: 8\n: 4", f"{'A' * 41}: 8",
            "Verse 1: 64\nVerse 2: 64\nOutro: 33",
            "\n".join(f"Section {index}: 1" for index in range(13)),
        ):
            with self.subTest(structure=structure):
                with self.assertRaises(engine.ValidationError):
                    engine.parse_structure(structure)

    def test_malformed_plan_fails_before_any_model_call(self):
        with patch.object(engine, "_request_model") as model:
            with self.assertRaises(engine.ValidationError):
                engine.generate_lyrics(request(structure="Verse: 16\nHook: banana"), "test-key")
        model.assert_not_called()

    def test_blocked_words_in_required_headers_fail_before_model_call(self):
        for structure, blocked in (("Static memories: 8", "static"), ("Rent-money: 8", "rent money")):
            with self.subTest(structure=structure):
                with patch.object(engine, "_request_model") as model:
                    with self.assertRaises(engine.ValidationError):
                        engine.generate_lyrics(request(structure=structure, blocked_words=blocked), "test-key")
                model.assert_not_called()

    def test_header_substrings_do_not_conflict_with_blocked_words(self):
        engine.validate_request(request(structure="Wireless: 8", blocked_words="wire"))


class CustomStructureGenerationTests(unittest.TestCase):
    def test_valid_sectioned_output_is_returned_after_editorial_pass(self):
        sections = [("Intro", 4), ("Verse 1", 16), ("Hook", 8), ("Verse 2", 16), ("Hook", 8), ("Outro", 4)]
        plan = "\n".join(f"{name}: {count}" for name, count in sections)
        lyrics = sectioned_lyrics(sections)
        with patch.object(engine, "_request_model", return_value=lyrics):
            result = engine.generate_lyrics(request(structure=plan), "test-key")
        self.assertEqual(result.lyrics, lyrics)
        self.assertEqual(result.api_calls, 2)

    def test_header_casing_does_not_change_the_structure(self):
        lyrics = sectioned_lyrics([("INTRO", 1), ("vErSe 1", 2)])
        with patch.object(engine, "_request_model", return_value=lyrics):
            result = engine.generate_lyrics(request(structure="Intro: 1\nVerse 1: 2"), "test-key")
        self.assertEqual(result.lyrics, lyrics)
        self.assertEqual(result.api_calls, 2)

    def test_repeated_headers_must_still_be_in_the_requested_order(self):
        valid = sectioned_lyrics([("Hook", 2), ("Verse 1", 2), ("Hook", 2)])
        invalid = sectioned_lyrics([("Hook", 2), ("Hook", 2), ("Verse 1", 2)])
        with patch.object(engine, "_request_model", side_effect=[valid, invalid, valid]):
            result = engine.generate_lyrics(request(structure="Hook: 2\nVerse 1: 2\nHook: 2"), "test-key")
        self.assertEqual(result.lyrics, valid)
        self.assertEqual(result.api_calls, 3)

    def test_wrong_shapes_are_repaired_before_release(self):
        valid = sectioned_lyrics([("Intro", 2), ("Verse 1", 2)])
        candidates = {
            "same total but wrong per-section count": sectioned_lyrics([("Intro", 1), ("Verse 1", 3)]),
            "missing heading": "\n".join(valid.splitlines()[1:]),
            "spurious section": valid + "\n[Outro]\nI parked beside the curb",
            "preface": "Here are your lyrics\n" + valid,
            "wrong heading": valid.replace("[Verse 1]", "[Verse 2]"),
            "plain heading": valid.replace("[Intro]", "Intro:"),
            "punctuation-only lyric": valid.replace(EIGHT_LINES.splitlines()[0], "...", 1),
            "empty lyric": valid.replace(EIGHT_LINES.splitlines()[0], "", 1),
            "extra lyric after final section": valid + "\nI parked beside the curb",
        }
        for label, invalid in candidates.items():
            with self.subTest(shape=label):
                with patch.object(engine, "_request_model", side_effect=[valid, invalid, valid]):
                    result = engine.generate_lyrics(request(structure="Intro: 2\nVerse 1: 2"), "test-key")
                self.assertEqual(result.lyrics, valid)
                self.assertEqual(result.api_calls, 3)

    def test_blank_separator_lines_do_not_count_as_bars(self):
        lyrics = sectioned_lyrics([("Intro", 2), ("Verse 1", 2)]).replace("[Verse 1]", "\n[Verse 1]")
        with patch.object(engine, "_request_model", return_value=lyrics):
            result = engine.generate_lyrics(request(structure="Intro: 2\nVerse 1: 2"), "test-key")
        self.assertEqual(result.lyrics, lyrics)
        self.assertEqual(result.api_calls, 2)

    def test_lyric_body_excludes_section_headings(self):
        lyrics = sectioned_lyrics([("Brother", 1), ("Home", 1)])
        body = engine.lyric_body(lyrics)
        self.assertNotIn("Brother", body)
        self.assertNotIn("Home", body)
        self.assertEqual(body.splitlines(), [EIGHT_LINES.splitlines()[0]] * 2)

    def test_required_good_word_in_header_does_not_satisfy_lyric_requirement(self):
        invalid = sectioned_lyrics([("Brother", 2)])
        valid = invalid.replace("coffee cup", "brother's cup")
        with patch.object(engine, "_request_model", side_effect=[invalid, invalid, valid]):
            result = engine.generate_lyrics(
                request(structure="Brother: 2", good_words="brother", require_good_words=True), "test-key"
            )
        self.assertEqual(result.lyrics, valid)
        self.assertEqual(result.api_calls, 3)

    def test_section_heading_cannot_hide_a_blocked_phrase_in_lyric_lines(self):
        invalid = "[Verse]\nI need rent\n[Hook]\nmoney before dawn"
        valid = "[Verse]\nI need rent\n[Hook]\npaid before dawn"
        with patch.object(engine, "_request_model", side_effect=[valid, invalid, valid]):
            result = engine.generate_lyrics(
                request(structure="Verse: 1\nHook: 1", blocked_words="rent money"), "test-key"
            )
        self.assertEqual(result.lyrics, valid)
        self.assertEqual(result.api_calls, 3)

    def test_long_custom_plan_raises_budget_at_sixty_four_bars(self):
        for count, budget in ((63, 6000), (64, 10000)):
            lyrics = sectioned_lyrics([("Verse 1", count)])
            with self.subTest(count=count):
                with patch.object(engine, "_request_model", return_value=lyrics) as model:
                    result = engine.generate_lyrics(request(structure=f"Verse 1: {count}"), "test-key")
                self.assertEqual(result.api_calls, 2)
                for call in model.call_args_list:
                    self.assertEqual(call.kwargs.get("max_output_tokens", 6000), budget)

    def test_long_custom_repairs_keep_larger_token_budget(self):
        valid = sectioned_lyrics([("Verse 1", 32), ("Verse 2", 32)])
        invalid = sectioned_lyrics([("Verse 1", 32), ("Verse 2", 31)])
        with patch.object(engine, "_request_model", side_effect=[valid, invalid, valid]) as model:
            result = engine.generate_lyrics(request(structure="Verse 1: 32\nVerse 2: 32"), "test-key")
        self.assertEqual(result.api_calls, 3)
        for call in model.call_args_list:
            self.assertEqual(call.kwargs.get("max_output_tokens"), 10000)

    def test_full_song_preset_enforces_sections_and_counts(self):
        valid = sectioned_lyrics(engine.DEFAULT_SONG_STRUCTURE)
        invalid = sectioned_lyrics([("Hook", 7), ("Verse 1", 17), ("Hook", 8), ("Verse 2", 16), ("Bridge", 4), ("Final hook", 8)])
        with patch.object(engine, "_request_model", side_effect=[valid, invalid, valid]) as model:
            result = engine.generate_lyrics(request(structure="Full song"), "test-key")
        self.assertEqual(result.lyrics, valid)
        self.assertEqual(result.api_calls, 3)
        for call in model.call_args_list:
            self.assertEqual(call.kwargs.get("max_output_tokens", 6000), 6000)


class GenerationPipelineTests(unittest.TestCase):
    def test_editorial_pass_always_runs_before_release(self):
        edited = EIGHT_LINES.replace("coffee cup", "paper cup")
        with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, edited]) as model:
            result = engine.generate_lyrics(request(), "test-key")
        self.assertEqual(result.lyrics, edited)
        self.assertEqual(result.api_calls, 2)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(model.call_count, 2)

    def test_valid_draft_cannot_bypass_invalid_editorial_result(self):
        invalid = EIGHT_LINES.replace("coffee", "static")
        with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, invalid, EIGHT_LINES]) as model:
            result = engine.generate_lyrics(request(), "test-key")
        self.assertEqual(result.lyrics, EIGHT_LINES)
        self.assertEqual(result.api_calls, 3)
        self.assertEqual(result.attempts, 2)
        self.assertEqual(model.call_count, 3)

    def test_invalid_outputs_exhaust_budget_without_being_returned(self):
        invalid = EIGHT_LINES.replace("coffee", "sta\u200btic")
        with patch.object(engine, "_request_model", return_value=invalid) as model:
            with self.assertRaises(engine.GenerationError):
                engine.generate_lyrics(request(), "test-key")
        self.assertEqual(model.call_count, 4)

    def test_optional_good_words_do_not_prevent_release(self):
        with patch.object(engine, "_request_model", return_value=EIGHT_LINES):
            result = engine.generate_lyrics(request(good_words="brother"), "test-key")
        self.assertEqual(result.lyrics, EIGHT_LINES)

    def test_required_good_words_force_repair(self):
        fixed = EIGHT_LINES.replace("Your mother", "Your brother")
        with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, EIGHT_LINES, fixed]):
            result = engine.generate_lyrics(
                request(good_words="brother", require_good_words=True), "test-key"
            )
        self.assertIn("brother", result.lyrics)
        self.assertEqual(result.api_calls, 3)

    def test_fixed_structures_accept_only_correct_nonempty_line_count(self):
        for structure, count in [
            ("8 bars", 8), ("16 bars", 16), ("24 bars", 24),
            ("32 bars", 32), ("8-line hook", 8), ("8 lines", 8), ("16 lines", 16), ("24 lines", 24), ("32 lines", 32), ("4-line hook", 4), ("4-line chorus", 4), ("8-line chorus", 8),
        ]:
            lines = "\n".join(EIGHT_LINES.splitlines()[i % 8] for i in range(count))
            with self.subTest(structure=structure):
                with patch.object(engine, "_request_model", return_value=lines):
                    result = engine.generate_lyrics(request(structure=structure), "test-key")
                self.assertEqual(len([line for line in result.lyrics.splitlines() if line.strip()]), count)

    def test_short_candidate_is_repaired(self):
        short = "\n".join(EIGHT_LINES.splitlines()[:7])
        with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, short, EIGHT_LINES]):
            result = engine.generate_lyrics(request(), "test-key")
        self.assertEqual(result.api_calls, 3)
        self.assertEqual(result.lyrics, EIGHT_LINES)

    def test_section_headers_do_not_count_as_lyric_lines(self):
        for heading in ("[Verse 1]", "Chorus", "Final chorus", "Final chorus:"):
            with self.subTest(heading=heading):
                header_candidate = heading + "\n" + "\n".join(EIGHT_LINES.splitlines()[:7])
                with patch.object(engine, "_request_model", side_effect=[EIGHT_LINES, header_candidate, EIGHT_LINES]):
                    result = engine.generate_lyrics(request(), "test-key")
                self.assertEqual(result.api_calls, 3)
                self.assertEqual(result.lyrics, EIGHT_LINES)

    def test_invalid_request_never_calls_model(self):
        with patch.object(engine, "_request_model") as model:
            with self.assertRaises(engine.ValidationError):
                engine.generate_lyrics(request(topic=""), "test-key")
        model.assert_not_called()

    def test_empty_api_key_never_calls_model(self):
        with patch.object(engine, "_request_model") as model:
            with self.assertRaises((engine.ValidationError, engine.GenerationError)):
                engine.generate_lyrics(request(), "  ")
        model.assert_not_called()

    def test_cancelled_before_start_never_calls_model(self):
        cancellation = threading.Event()
        cancellation.set()
        with patch.object(engine, "_request_model") as model:
            with self.assertRaises(engine.GenerationCancelled):
                engine.generate_lyrics(request(), "test-key", cancel=cancellation)
        model.assert_not_called()

    def test_cancellation_during_first_call_stops_editorial_call(self):
        cancellation = threading.Event()

        def cancel_and_return(**_):
            cancellation.set()
            return EIGHT_LINES

        with patch.object(engine, "_request_model", side_effect=cancel_and_return) as model:
            with self.assertRaises(engine.GenerationCancelled):
                engine.generate_lyrics(request(), "test-key", cancel=cancellation)
        self.assertEqual(model.call_count, 1)

    def test_cancellation_during_editorial_pass_prevents_release(self):
        cancellation = threading.Event()
        count = 0

        def return_and_cancel_second(**_):
            nonlocal count
            count += 1
            if count == 2:
                cancellation.set()
            return EIGHT_LINES

        with patch.object(engine, "_request_model", side_effect=return_and_cancel_second):
            with self.assertRaises(engine.GenerationCancelled):
                engine.generate_lyrics(request(), "test-key", cancel=cancellation)
        self.assertEqual(count, 2)


class ResponseTransportTests(unittest.TestCase):
    def call_response(self, response, model="gpt-5-mini", **options):
        opened = MagicMock()
        opened.__enter__.return_value.read.return_value = json.dumps(response).encode("utf-8")
        opened.__enter__.return_value.status = 200
        with patch.object(engine.urllib.request, "urlopen", return_value=opened) as urlopen:
            result = engine._request_model(
                api_key="test-secret-key", model=model,
                instructions="Write lyrics.", user_input="The rent is due.", cancel=None,
                **options,
            )
        return result, urlopen.call_args.args[0]

    def test_completed_response_parses_and_disables_api_storage(self):
        result, sent = self.call_response(completed_response())
        payload = json.loads(sent.data.decode("utf-8"))
        self.assertEqual(result, EIGHT_LINES)
        self.assertEqual(sent.full_url, "https://api.openai.com/v1/responses")
        self.assertEqual(sent.get_method(), "POST")
        self.assertEqual(payload["model"], "gpt-5-mini")
        self.assertIs(payload["store"], False)
        self.assertEqual(payload["max_output_tokens"], 6000)
        self.assertEqual(payload["reasoning"]["effort"], "low")

    def test_custom_output_budget_is_sent_to_the_api(self):
        _, sent = self.call_response(completed_response(), max_output_tokens=10000)
        payload = json.loads(sent.data.decode("utf-8"))
        self.assertEqual(payload["max_output_tokens"], 10000)

    def test_non_reasoning_models_do_not_receive_reasoning_option(self):
        _, sent = self.call_response(completed_response(), model="gpt-4.1")
        payload = json.loads(sent.data.decode("utf-8"))
        self.assertEqual(payload["model"], "gpt-4.1")
        self.assertNotIn("reasoning", payload)

    def test_multiple_text_segments_are_preserved(self):
        data = completed_response("First lyric line")
        data["output"][0]["content"].append({"type": "output_text", "text": "Second lyric line"})
        result, _ = self.call_response(data)
        self.assertIn("First lyric line", result)
        self.assertIn("Second lyric line", result)

    def test_incomplete_response_never_releases_partial_lyrics(self):
        data = completed_response()
        data["status"] = "incomplete"
        data["incomplete_details"] = {"reason": "max_output_tokens"}
        with self.assertRaises(engine.GenerationError):
            self.call_response(data)

    def test_refusal_even_alongside_text_is_an_error(self):
        data = completed_response()
        data["output"][0]["content"].append({"type": "refusal", "refusal": "Cannot comply."})
        with self.assertRaises(engine.GenerationError):
            self.call_response(data)

    def test_empty_or_missing_text_is_an_error(self):
        for data in (completed_response(" \n"), {"status": "completed", "output": []}):
            with self.subTest(data=data):
                with self.assertRaises(engine.GenerationError):
                    self.call_response(data)

    def test_http_error_body_is_not_exposed_to_user(self):
        secret = "test-private-body-value"
        error = urllib.error.HTTPError(
            "https://api.openai.com/v1/responses", 401, "Unauthorized", {},
            io.BytesIO(json.dumps({"error": {"message": secret}}).encode()),
        )
        with patch.object(engine.urllib.request, "urlopen", side_effect=error):
            with self.assertRaises(engine.GenerationError) as raised:
                engine._request_model(
                    api_key="test-secret-key", model="gpt-5-mini", instructions="Write.",
                    user_input="Rent.", cancel=None,
                )
        self.assertNotIn(secret, str(raised.exception))
        self.assertNotIn("test-secret-key", str(raised.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

